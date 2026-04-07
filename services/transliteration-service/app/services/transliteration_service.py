"""
Core business logic for Transliteration inference.
"""

import logging
import time
from typing import Dict, List, Optional

import numpy as np
from opentelemetry import trace
from opentelemetry.trace import Status, StatusCode

from app.schemas.inference import (
    TransliterationInferenceRequest,
    TransliterationInferenceResponse,
    TransliterationOutput,
)
from app.repositories.transliteration_repository import TransliterationRepository
from app.clients.triton_client import TransliterationTritonClient
from app.services.text_service import TextService
from ai4icore_exceptions import TritonInferenceError

logger = logging.getLogger(__name__)
tracer = trace.get_tracer("transliteration-service")


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

        with tracer.start_as_current_span("transliteration.process_batch") as span:
            try:
                service_id = request.config.serviceId
                source_lang = request.config.language.sourceLanguage
                target_lang = request.config.language.targetLanguage
                is_sentence = request.config.isSentence
                top_k = request.config.numSuggestions

                model_name = self.model_name

                span.set_attribute("transliteration.total_inputs", len(request.input))
                span.set_attribute("transliteration.service_id", service_id)
                span.set_attribute("transliteration.source_language", source_lang)
                span.set_attribute("transliteration.target_language", target_lang)
                span.set_attribute("transliteration.is_sentence", is_sentence)
                span.set_attribute("transliteration.model_name", model_name)

                if user_id:
                    span.set_attribute("user.id", str(user_id))
                if api_key_id:
                    span.set_attribute("api_key.id", str(api_key_id))

                # Validate top_k for sentence level
                if top_k > 0 and is_sentence:
                    raise ValueError("numSuggestions (top_k) is not valid for sentence level transliteration")

                # Preprocess input texts
                with tracer.start_as_current_span("transliteration.preprocess_texts") as preprocess_span:
                    input_texts: List[str] = []
                    for text_input in request.input:
                        normalized = text_input.source.replace("\n", " ").strip() if text_input.source else ""
                        input_texts.append(normalized)
                    preprocess_span.set_attribute("transliteration.preprocessed_count", len(input_texts))
                    preprocess_span.set_attribute("transliteration.total_chars", sum(len(t) for t in input_texts))

                # Create database request record
                total_text_length = sum(len(text) for text in input_texts)
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

                # Batch processing
                max_batch_size = 100
                output_batch: List[List[str]] = []

                with tracer.start_as_current_span("transliteration.batch_processing") as batch_span:
                    batch_span.set_attribute("transliteration.batch_size", max_batch_size)

                    for i in range(0, len(input_texts), max_batch_size):
                        batch = input_texts[i:i + max_batch_size]

                        try:
                            # Prepare Triton inputs
                            with tracer.start_as_current_span("transliteration.prepare_triton_inputs"):
                                inputs, outputs = self.triton_client.get_transliteration_io_for_triton(
                                    batch, source_lang, target_lang, not is_sentence, top_k
                                )

                            # Send Triton request
                            with tracer.start_as_current_span("transliteration.triton_inference") as triton_span:
                                try:
                                    response = self.triton_client.send_triton_request(
                                        model_name=model_name,
                                        inputs=inputs,
                                        outputs=outputs,
                                    )
                                    triton_span.set_attribute("transliteration.triton_success", True)
                                except TritonInferenceError:
                                    raise
                                except Exception as exc:
                                    raise TritonInferenceError(f"Triton inference failed: {exc}") from exc

                            # Extract results
                            with tracer.start_as_current_span("transliteration.extract_results"):
                                encoded_result = response.as_numpy("OUTPUT_TEXT")
                                if encoded_result is None:
                                    encoded_result = np.array([np.array([])])

                                batch_results: List[List[str]] = []
                                for result_row in encoded_result:
                                    if isinstance(result_row, np.ndarray):
                                        decoded_results = [
                                            r.decode("utf-8") if isinstance(r, bytes) else str(r)
                                            for r in result_row
                                        ]
                                        batch_results.append(decoded_results)
                                    else:
                                        decoded_result = result_row.decode("utf-8") if isinstance(result_row, bytes) else str(result_row)
                                        batch_results.append([decoded_result])

                                output_batch.extend(batch_results)

                        except Exception as e:
                            logger.error(f"Triton inference failed for batch {i // max_batch_size}: {e}")
                            raise TritonInferenceError(f"Triton inference failed: {e}")

                # Format response
                results: List[TransliterationOutput] = []
                for source_text, result_list in zip(input_texts, output_batch):
                    if not source_text:
                        transliterated = source_text
                    elif len(result_list) == 1:
                        transliterated = result_list[0] if result_list else source_text
                    else:
                        transliterated = result_list if result_list else [source_text]

                    results.append(TransliterationOutput(
                        source=source_text,
                        target=transliterated,
                    ))

                response = TransliterationInferenceResponse(output=results)

                # Database logging
                for result in results:
                    await self.repository.create_result(
                        request_id=request_id,
                        transliterated_text=result.target,
                        source_text=result.source,
                    )

                # Update request status
                processing_time = time.time() - start_time
                await self.repository.update_request_status(
                    request_id=request_id,
                    status="completed",
                    processing_time=processing_time,
                )

                span.set_attribute("transliteration.processing_time_seconds", processing_time)
                span.set_attribute("transliteration.output_count", len(response.output))

                logger.info(f"Transliteration inference completed for request {request_id} in {processing_time:.2f}s")
                return response

            except Exception as e:
                span.set_attribute("error", True)
                span.set_attribute("error.type", type(e).__name__)
                span.set_attribute("error.message", str(e))
                span.set_status(Status(StatusCode.ERROR, str(e)))
                span.record_exception(e)
                logger.error(f"Transliteration inference failed: {e}")

                if request_id:
                    try:
                        await self.repository.update_request_status(
                            request_id=request_id,
                            status="failed",
                            error_message=str(e),
                        )
                    except Exception as update_error:
                        logger.error(f"Failed to update request status: {update_error}")

                if isinstance(e, TritonInferenceError):
                    raise
                raise TritonInferenceError(f"Transliteration inference failed: {e}")
