"""
Core business logic for Transliteration inference.
"""

import logging
import time
from typing import List, Optional

import numpy as np
from app.schemas.inference import (
    TransliterationInferenceRequest,
    TransliterationInferenceResponse,
    TransliterationOutput,
)
from app.repositories.transliteration_repository import TransliterationRepository
from app.clients.triton_client import TransliterationTritonClient
from app.services.text_service import TextService
from ai4icore_exceptions import TritonInferenceError
from ai4icore_telemetry import StandardSpanManager, Status, StatusCode

logger = logging.getLogger(__name__)
_standard_spans = StandardSpanManager("transliteration")


def _count_words(text: str) -> int:
    try:
        return len(text.split()) if text else 0
    except Exception:
        return 0


class TransliterationService:
    """Main transliteration service for inference."""

    def __init__(
        self,
        repository: TransliterationRepository,
        text_service: TextService,
        triton_client: TransliterationTritonClient,
        model_name: str = "transliteration",
    ):
        self.repository = repository
        self.text_service = text_service
        self.triton_client = triton_client
        self.model_name = model_name

    async def run_inference(
        self,
        request: TransliterationInferenceRequest,
        user_id: Optional[int] = None,
        api_key_id: Optional[int] = None,
        session_id: Optional[int] = None,
    ) -> TransliterationInferenceResponse:
        """Run transliteration inference on the given request."""
        start_time = time.time()
        request_id = None

        service_id = request.config.serviceId
        source_lang = request.config.language.sourceLanguage
        target_lang = request.config.language.targetLanguage
        is_sentence = request.config.isSentence
        top_k = request.config.numSuggestions
        input_count = len(request.input or [])
        model_name = self.model_name

        with _standard_spans.inference(
            service_id=service_id,
            model_name=None,
            input_count=input_count,
            input_type="text",
            user_id=user_id,
            api_key_id=api_key_id,
            session_id=session_id,
            extra_attrs={
                "transliteration.source_language": source_lang,
                "transliteration.target_language": target_lang,
                "transliteration.is_sentence": is_sentence,
            },
        ) as parent_span:
            try:
                if top_k > 0 and is_sentence:
                    raise ValueError(
                        "numSuggestions (top_k) is not valid for sentence level transliteration"
                    )

                input_texts: List[str] = []
                with _standard_spans.preprocess() as preprocess_span:
                    for text_input in request.input:
                        normalized = (
                            text_input.source.replace("\n", " ").strip()
                            if text_input.source
                            else ""
                        )
                        input_texts.append(normalized)
                    total_text_length = sum(len(t) for t in input_texts)
                    total_input_words = sum(_count_words(t) for t in input_texts)
                    preprocess_span.set_attribute(
                        "transliteration.preprocessed_count", len(input_texts)
                    )
                    preprocess_span.set_attribute(
                        "transliteration.input.character_length", total_text_length
                    )
                    preprocess_span.set_attribute(
                        "transliteration.input.word_count", total_input_words
                    )
                    if parent_span is not None:
                        try:
                            parent_span.set_attribute(
                                "transliteration.input.character_length",
                                total_text_length,
                            )
                            parent_span.set_attribute(
                                "transliteration.input.word_count",
                                total_input_words,
                            )
                        except Exception:
                            pass

                with _standard_spans.resolve_model() as resolve_span:
                    resolve_span.set_attribute(
                        "transliteration.model_name", model_name
                    )
                    if parent_span is not None:
                        try:
                            parent_span.set_attribute(
                                "transliteration.model_name", model_name
                            )
                        except Exception:
                            pass

                max_batch_size = 100
                output_batch: List[List[str]] = []
                batch_count = (len(input_texts) + max_batch_size - 1) // max_batch_size

                with _standard_spans.triton_inference() as triton_span:
                    triton_span.set_attribute(
                        "transliteration.batch_size", max_batch_size
                    )
                    triton_span.set_attribute(
                        "transliteration.batch_count", batch_count
                    )

                    for i in range(0, len(input_texts), max_batch_size):
                        batch = input_texts[i : i + max_batch_size]
                        batch_index = i // max_batch_size
                        triton_span.add_event(
                            "transliteration.batch.started",
                            {
                                "batch_index": batch_index,
                                "batch_size": len(batch),
                            },
                        )
                        try:
                            inputs, outputs = (
                                self.triton_client.get_transliteration_io_for_triton(
                                    batch,
                                    source_lang,
                                    target_lang,
                                    not is_sentence,
                                    top_k,
                                )
                            )
                            triton_span.add_event(
                                "transliteration.prepare_triton_inputs.completed",
                                {
                                    "batch_index": batch_index,
                                    "batch_size": len(batch),
                                },
                            )
                            response = self.triton_client.send_triton_request(
                                model_name=model_name,
                                inputs=inputs,
                                outputs=outputs,
                            )
                            encoded_result = response.as_numpy("OUTPUT_TEXT")
                            if encoded_result is None:
                                encoded_result = np.array([np.array([])])

                            batch_results: List[List[str]] = []
                            for result_row in encoded_result:
                                if isinstance(result_row, np.ndarray):
                                    decoded_results = [
                                        r.decode("utf-8")
                                        if isinstance(r, bytes)
                                        else str(r)
                                        for r in result_row
                                    ]
                                    batch_results.append(decoded_results)
                                else:
                                    decoded_result = (
                                        result_row.decode("utf-8")
                                        if isinstance(result_row, bytes)
                                        else str(result_row)
                                    )
                                    batch_results.append([decoded_result])

                            output_batch.extend(batch_results)
                            triton_span.add_event(
                                "transliteration.extract_results.completed",
                                {
                                    "batch_index": batch_index,
                                    "result_count": len(batch_results),
                                },
                            )
                            triton_span.add_event(
                                "transliteration.batch.completed",
                                {
                                    "batch_index": batch_index,
                                    "result_count": len(batch_results),
                                },
                            )
                        except TritonInferenceError:
                            raise
                        except Exception as exc:
                            triton_span.set_status(
                                Status(StatusCode.ERROR, str(exc))
                            )
                            triton_span.record_exception(exc)
                            logger.error(
                                "Triton inference failed for batch %s: %s",
                                batch_index,
                                exc,
                            )
                            raise TritonInferenceError(
                                f"Triton inference failed: {exc}"
                            ) from exc

                results: List[TransliterationOutput] = []
                with _standard_spans.postprocess() as post_span:
                    for source_text, result_list in zip(input_texts, output_batch):
                        if not source_text:
                            transliterated = source_text
                        elif len(result_list) == 1:
                            transliterated = (
                                result_list[0] if result_list else source_text
                            )
                        else:
                            transliterated = (
                                result_list if result_list else [source_text]
                            )
                        results.append(
                            TransliterationOutput(
                                source=source_text,
                                target=transliterated,
                            )
                        )
                    total_out_chars = sum(len(str(r.target)) for r in results)
                    total_out_words = sum(_count_words(str(r.target)) for r in results)
                    post_span.set_attribute(
                        "transliteration.output.character_length",
                        total_out_chars,
                    )
                    post_span.set_attribute(
                        "transliteration.output.word_count",
                        total_out_words,
                    )
                    post_span.set_attribute(
                        "transliteration.formatted_count", len(results)
                    )
                    if parent_span is not None:
                        try:
                            parent_span.set_attribute(
                                "transliteration.output.character_length",
                                total_out_chars,
                            )
                            parent_span.set_attribute(
                                "transliteration.output.word_count",
                                total_out_words,
                            )
                        except Exception:
                            pass

                response = TransliterationInferenceResponse(output=results)

                with _standard_spans.persist() as persist_span:
                    request_record = await self.repository.create_request(
                        model_id=service_id,
                        source_language=source_lang,
                        target_language=target_lang,
                        text_length=total_text_length,
                        is_sentence_level=is_sentence,
                        num_suggestions=top_k,
                        user_id=user_id,
                        api_key_id=api_key_id,
                        session_id=session_id,
                    )
                    request_id = request_record.id
                    persist_span.set_attribute(
                        "transliteration.request_id", str(request_id)
                    )
                    persist_span.add_event(
                        "transliteration.db.request_created",
                        {"request_id": str(request_id)},
                    )

                    for idx, result in enumerate(results):
                        await self.repository.create_result(
                            request_id=request_id,
                            transliterated_text=result.target,
                            source_text=result.source,
                        )
                        persist_span.add_event(
                            "transliteration.db.result.created",
                            {"result_index": idx, "request_id": str(request_id)},
                        )

                    processing_time = time.time() - start_time
                    await self.repository.update_request_status(
                        request_id=request_id,
                        status="completed",
                        processing_time=processing_time,
                    )
                    persist_span.add_event(
                        "transliteration.db.request_completed",
                        {
                            "request_id": str(request_id),
                            "processing_time_seconds": processing_time,
                        },
                    )

                if parent_span is not None:
                    try:
                        parent_span.set_attribute(
                            "transliteration.output_count", len(response.output)
                        )
                    except Exception:
                        pass

                processing_time = time.time() - start_time
                logger.info(
                    "Transliteration inference completed for request %s in %.2fs",
                    request_id,
                    processing_time,
                )
                return response

            except Exception as e:
                logger.error("Transliteration inference failed: %s", e)

                if request_id:
                    try:
                        await self.repository.update_request_status(
                            request_id=request_id,
                            status="failed",
                            error_message=str(e),
                        )
                    except Exception as update_error:
                        logger.error(
                            "Failed to update request status: %s", update_error
                        )
                else:
                    try:
                        ttl = sum(
                            len(
                                (
                                    ti.source.replace("\n", " ").strip()
                                    if ti.source
                                    else ""
                                )
                            )
                            for ti in (request.input or [])
                        )
                        dr = await self.repository.create_request(
                            model_id=service_id,
                            source_language=source_lang,
                            target_language=target_lang,
                            text_length=ttl,
                            is_sentence_level=is_sentence,
                            num_suggestions=top_k,
                            user_id=user_id,
                            api_key_id=api_key_id,
                            session_id=session_id,
                        )
                        await self.repository.update_request_status(
                            request_id=dr.id,
                            status="failed",
                            error_message=str(e),
                        )
                    except Exception as db_err:
                        logger.error(
                            "Transliteration: failed to record failed request: %s",
                            db_err,
                        )

                if isinstance(e, TritonInferenceError):
                    raise
                raise TritonInferenceError(
                    f"Transliteration inference failed: {e}"
                ) from e
