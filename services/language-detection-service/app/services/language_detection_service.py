"""
Core business logic for Language Detection inference.
"""

import json
import logging
import math
import time
from typing import List, Optional

import numpy as np

from app.schemas.inference import (
    LanguageDetectionInferenceRequest,
    LanguageDetectionInferenceResponse,
    LanguageDetectionOutput,
    LanguagePrediction,
)
from app.repositories.language_detection_repository import LanguageDetectionRepository
from app.services.text_service import TextService
from app.clients.triton_client import LanguageDetectionTritonClient
from ai4icore_exceptions import TritonInferenceError
from ai4icore_telemetry import StandardSpanManager

logger = logging.getLogger(__name__)
_standard_spans = StandardSpanManager("language-detection")


def _count_words(text: str) -> int:
    try:
        return len(text.split()) if text else 0
    except Exception:
        return 0


class LanguageDetectionService:
    """Main language detection service for text language identification."""

    # Mapping from IndicLID format (lang_Script) to full language names
    INDICLID_TO_LANGUAGE = {
        "asm_Beng": "Assamese",
        "asm_Latn": "Assamese (Latin script)",
        "ben_Beng": "Bengali",
        "ben_Latn": "Bengali (Latin script)",
        "brx_Deva": "Bodo",
        "brx_Latn": "Bodo (Latin script)",
        "doi_Deva": "Dogri",
        "doi_Latn": "Dogri (Latin script)",
        "eng_Latn": "English",
        "guj_Gujr": "Gujarati",
        "guj_Latn": "Gujarati (Latin script)",
        "hin_Deva": "Hindi",
        "hin_Latn": "Hindi (Latin script)",
        "kan_Knda": "Kannada",
        "kan_Latn": "Kannada (Latin script)",
        "kas_Arab": "Kashmiri (Perso-Arabic script)",
        "kas_Deva": "Kashmiri (Devanagari script)",
        "kas_Latn": "Kashmiri (Latin script)",
        "kok_Deva": "Konkani",
        "kok_Latn": "Konkani (Latin script)",
        "mai_Deva": "Maithili",
        "mai_Latn": "Maithili (Latin script)",
        "mal_Mlym": "Malayalam",
        "mal_Latn": "Malayalam (Latin script)",
        "mni_Beng": "Manipuri (Bengali script)",
        "mni_Mtei": "Manipuri (Meitei Mayek script)",
        "mni_Latn": "Manipuri (Latin script)",
        "mar_Deva": "Marathi",
        "mar_Latn": "Marathi (Latin script)",
        "nep_Deva": "Nepali",
        "nep_Latn": "Nepali (Latin script)",
        "ori_Orya": "Odia",
        "ori_Latn": "Odia (Latin script)",
        "pan_Guru": "Punjabi",
        "pan_Latn": "Punjabi (Latin script)",
        "san_Deva": "Sanskrit",
        "san_Latn": "Sanskrit (Latin script)",
        "sat_Olck": "Santali",
        "snd_Arab": "Sindhi (Perso-Arabic script)",
        "snd_Latn": "Sindhi (Latin script)",
        "tam_Taml": "Tamil",
        "tam_Latn": "Tamil (Latin script)",
        "tel_Telu": "Telugu",
        "tel_Latn": "Telugu (Latin script)",
        "urd_Arab": "Urdu",
        "urd_Latn": "Urdu (Latin script)",
        "other": "Other",
    }

    def __init__(
        self,
        repository: LanguageDetectionRepository,
        text_service: TextService,
        triton_client: LanguageDetectionTritonClient,
        model_name: str,
    ):
        self.repository = repository
        self.text_service = text_service
        self.triton_client = triton_client
        self.model_name = model_name

    @staticmethod
    def normalize_confidence_score(confidence: float) -> float:
        """Normalize confidence score to [0.0, 1.0] range.

        The database constraint requires confidence_score to be in [0.0, 1.0].
        Uses sigmoid for scores outside this range.
        """
        if 0.0 <= confidence <= 1.0:
            return confidence
        logger.warning(
            f"Confidence score {confidence} is outside [0.0, 1.0] range. "
            f"Normalizing using sigmoid function."
        )
        return 1.0 / (1.0 + math.exp(-confidence))

    async def run_inference(
        self,
        request: LanguageDetectionInferenceRequest,
        api_key_name: Optional[str] = None,
        user_id: Optional[str] = None,
    ) -> LanguageDetectionInferenceResponse:
        """Run language detection inference (standard 7-phase spans)."""
        start_time = time.time()
        request_id = None
        service_id = request.config.serviceId
        input_count = len(request.input)
        uid_int = int(user_id) if user_id else None
        model_name = self.model_name

        with _standard_spans.inference(
            service_id=service_id,
            model_name=None,
            input_count=input_count,
            input_type="text",
            user_id=uid_int,
            api_key_id=None,
            session_id=None,
        ) as parent_span:
            try:
                input_texts: List[str] = []
                with _standard_spans.preprocess() as preprocess_span:
                    for text_input in request.input:
                        normalized_text = self.text_service.normalize_text(text_input.source)
                        input_texts.append(normalized_text)
                    total_text_length = sum(len(text) for text in input_texts)
                    total_words = sum(_count_words(t) for t in input_texts)
                    preprocess_span.set_attribute(
                        "language-detection.input.character_length", total_text_length
                    )
                    preprocess_span.set_attribute(
                        "language-detection.input.word_count", total_words
                    )
                    preprocess_span.set_attribute(
                        "language-detection.preprocessed_count", len(input_texts)
                    )
                    if parent_span is not None:
                        try:
                            parent_span.set_attribute(
                                "language-detection.input.character_length",
                                total_text_length,
                            )
                            parent_span.set_attribute(
                                "language-detection.input.word_count", total_words
                            )
                        except Exception:
                            pass

                with _standard_spans.resolve_model() as resolve_span:
                    resolve_span.set_attribute(
                        "language-detection.model_name", model_name
                    )
                    if parent_span is not None:
                        try:
                            parent_span.set_attribute(
                                "language-detection.model_name", model_name
                            )
                        except Exception:
                            pass

                with _standard_spans.triton_inference() as triton_span:
                    inputs, outputs = (
                        self.triton_client.get_language_detection_io_for_triton(
                            input_texts
                        )
                    )
                    triton_span.set_attribute(
                        "language-detection.triton.input_tensor_count", len(inputs)
                    )
                    triton_span.set_attribute(
                        "language-detection.triton.output_tensor_count", len(outputs)
                    )
                    triton_span.add_event(
                        "language-detection.prepare_triton_inputs.completed",
                        {"batch_size": len(input_texts)},
                    )

                    response = self.triton_client.send_triton_request(
                        model_name=model_name,
                        inputs=inputs,
                        outputs=outputs,
                    )

                    encoded_result = response.as_numpy("OUTPUT_TEXT")
                    if encoded_result is None:
                        encoded_result = np.array([])
                    triton_span.set_attribute(
                        "language-detection.result_element_count",
                        int(encoded_result.size),
                    )
                    triton_span.add_event(
                        "language-detection.extract_outputs.completed",
                        {"size": int(encoded_result.size)},
                    )

                results: List[LanguageDetectionOutput] = []
                db_rows: List[dict] = []

                with _standard_spans.postprocess() as post_span:
                    if encoded_result.size > 0:
                        result_list = encoded_result.tolist()
                        post_span.set_attribute(
                            "language-detection.result_count", len(result_list)
                        )

                        for idx, (source_text, result_row) in enumerate(
                            zip(input_texts, result_list)
                        ):
                            if result_row and len(result_row) > 0:
                                json_str = (
                                    result_row[0].decode("utf-8")
                                    if isinstance(result_row[0], bytes)
                                    else str(result_row[0])
                                )
                                try:
                                    detection_data = json.loads(json_str)
                                    lang_code_full = detection_data.get(
                                        "langCode", "other"
                                    )
                                    raw_confidence = float(
                                        detection_data.get("confidence", 0.0)
                                    )

                                    logger.debug(
                                        "Triton model returned confidence: %s for text: '%s...' (lang: %s)",
                                        raw_confidence,
                                        source_text[:50],
                                        lang_code_full,
                                    )

                                    if "_" in lang_code_full:
                                        lang_code, script_code = lang_code_full.split(
                                            "_", 1
                                        )
                                    else:
                                        lang_code = lang_code_full
                                        script_code = "Latn"

                                    language_name = self.INDICLID_TO_LANGUAGE.get(
                                        lang_code_full, "Other"
                                    )

                                    prediction = LanguagePrediction(
                                        langCode=lang_code,
                                        scriptCode=script_code,
                                        langScore=raw_confidence,
                                        language=language_name,
                                    )

                                    results.append(
                                        LanguageDetectionOutput(
                                            source=source_text,
                                            langPrediction=[prediction],
                                        )
                                    )

                                    normalized_confidence = (
                                        self.normalize_confidence_score(raw_confidence)
                                    )
                                    db_rows.append(
                                        {
                                            "source_text": source_text,
                                            "detected_language": lang_code,
                                            "detected_script": script_code,
                                            "confidence_score": normalized_confidence,
                                            "language_name": language_name,
                                        }
                                    )
                                    post_span.add_event(
                                        "language-detection.output.parsed",
                                        {
                                            "index": idx,
                                            "lang": lang_code,
                                        },
                                    )

                                except (json.JSONDecodeError, KeyError, ValueError) as e:
                                    logger.error(
                                        "Failed to parse language detection result: %s", e
                                    )
                                    results.append(
                                        LanguageDetectionOutput(
                                            source=source_text, langPrediction=[]
                                        )
                                    )
                            else:
                                results.append(
                                    LanguageDetectionOutput(
                                        source=source_text, langPrediction=[]
                                    )
                                )
                    else:
                        for source_text in input_texts:
                            results.append(
                                LanguageDetectionOutput(
                                    source=source_text, langPrediction=[]
                                )
                            )

                    total_out_chars = sum(len(r.source) for r in results)
                    post_span.set_attribute(
                        "language-detection.output.character_length", total_out_chars
                    )
                    if parent_span is not None:
                        try:
                            parent_span.set_attribute(
                                "language-detection.output.character_length",
                                total_out_chars,
                            )
                        except Exception:
                            pass

                response_model = LanguageDetectionInferenceResponse(output=results)
                processing_time = time.time() - start_time

                with _standard_spans.persist() as persist_span:
                    request_record = await self.repository.create_request(
                        model_id=service_id,
                        text_length=total_text_length,
                        user_id=uid_int,
                        api_key_id=None,
                        session_id=None,
                    )
                    request_id = request_record.id
                    persist_span.set_attribute(
                        "language-detection.request_id", str(request_id)
                    )
                    persist_span.add_event(
                        "language-detection.db.request_created",
                        {"request_id": str(request_id)},
                    )

                    for row in db_rows:
                        await self.repository.create_result(
                            request_id=request_id,
                            source_text=row["source_text"],
                            detected_language=row["detected_language"],
                            detected_script=row["detected_script"],
                            confidence_score=row["confidence_score"],
                            language_name=row["language_name"],
                        )
                        persist_span.add_event(
                            "language-detection.db.result.created",
                            {
                                "detected_language": row["detected_language"],
                            },
                        )

                    await self.repository.update_request_status(
                        request_id=request_id,
                        status="completed",
                        processing_time=processing_time,
                    )
                    persist_span.add_event(
                        "language-detection.db.request_completed",
                        {
                            "request_id": str(request_id),
                            "processing_time_seconds": processing_time,
                        },
                    )

                if parent_span is not None:
                    try:
                        parent_span.set_attribute(
                            "language-detection.output_count", len(results)
                        )
                    except Exception:
                        pass

                logger.info(
                    "Language detection completed for request %s in %.2fs",
                    request_id,
                    processing_time,
                )
                return response_model

            except TritonInferenceError as e:
                logger.error("Language detection Triton inference failed: %s", e)
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
                            len(self.text_service.normalize_text(ti.source))
                            for ti in request.input
                        )
                        dr = await self.repository.create_request(
                            model_id=service_id,
                            text_length=ttl,
                            user_id=uid_int,
                            api_key_id=None,
                            session_id=None,
                        )
                        await self.repository.update_request_status(
                            request_id=dr.id,
                            status="failed",
                            error_message=str(e),
                        )
                    except Exception as db_err:
                        logger.error(
                            "language-detection: failed to record failed request: %s",
                            db_err,
                        )
                raise

            except Exception as e:
                logger.error("Language detection failed: %s", e)
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
                            len(self.text_service.normalize_text(ti.source))
                            for ti in request.input
                        )
                        dr = await self.repository.create_request(
                            model_id=service_id,
                            text_length=ttl,
                            user_id=uid_int,
                            api_key_id=None,
                            session_id=None,
                        )
                        await self.repository.update_request_status(
                            request_id=dr.id,
                            status="failed",
                            error_message=str(e),
                        )
                    except Exception as db_err:
                        logger.error(
                            "language-detection: failed to record failed request: %s",
                            db_err,
                        )

                if isinstance(e, TritonInferenceError):
                    raise
                raise TritonInferenceError(f"Language detection failed: {e}") from e
