"""
Core business logic for Language Detection inference.
"""

import json
import logging
import math
import time
from typing import List, Optional

import numpy as np
from opentelemetry import trace
from opentelemetry.trace import Status, StatusCode

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

logger = logging.getLogger(__name__)
tracer = trace.get_tracer("language-detection-service")


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
        """Run language detection inference."""
        start_time = time.time()
        request_id = None

        with tracer.start_as_current_span("language-detection.process_batch") as span:
            try:
                service_id = request.config.serviceId

                span.set_attribute("language-detection.total_inputs", len(request.input))
                span.set_attribute("language-detection.service_id", service_id)
                span.set_attribute("language-detection.model_name", self.model_name)

                # Prepare input texts
                with tracer.start_as_current_span("language-detection.preprocess_texts") as preprocess_span:
                    input_texts = []
                    for text_input in request.input:
                        normalized_text = self.text_service.normalize_text(text_input.source)
                        input_texts.append(normalized_text)
                    total_text_length = sum(len(text) for text in input_texts)
                    preprocess_span.set_attribute("language-detection.total_text_length", total_text_length)
                    preprocess_span.set_attribute("language-detection.preprocessed_count", len(input_texts))

                # Create request record
                with tracer.start_as_current_span("language-detection.create_db_request") as db_span:
                    request_record = await self.repository.create_request(
                        model_id=service_id,
                        text_length=total_text_length,
                        user_id=int(user_id) if user_id else None,
                        api_key_id=None,
                        session_id=None,
                    )
                    request_id = request_record.id
                    db_span.set_attribute("language-detection.request_id", str(request_id))

                # Prepare Triton inputs/outputs
                with tracer.start_as_current_span("language-detection.prepare_triton_io") as io_span:
                    inputs, outputs = self.triton_client.get_language_detection_io_for_triton(input_texts)
                    io_span.set_attribute("language-detection.input_count", len(inputs))
                    io_span.set_attribute("language-detection.output_count", len(outputs))

                # Send request to Triton
                response = self.triton_client.send_triton_request(
                    model_name=self.model_name,
                    inputs=inputs,
                    outputs=outputs,
                )

                # Parse response
                with tracer.start_as_current_span("language-detection.parse_response") as parse_span:
                    encoded_result = response.as_numpy("OUTPUT_TEXT")
                    if encoded_result is None:
                        encoded_result = np.array([])
                    parse_span.set_attribute(
                        "language-detection.result_size",
                        encoded_result.size if encoded_result is not None else 0,
                    )

                # Process results
                results: List[LanguageDetectionOutput] = []
                if encoded_result.size > 0:
                    result_list = encoded_result.tolist()

                    with tracer.start_as_current_span("language-detection.process_results") as process_span:
                        process_span.set_attribute("language-detection.result_count", len(result_list))

                        for idx, (source_text, result_row) in enumerate(zip(input_texts, result_list)):
                            if result_row and len(result_row) > 0:
                                json_str = (
                                    result_row[0].decode("utf-8")
                                    if isinstance(result_row[0], bytes)
                                    else str(result_row[0])
                                )
                                try:
                                    detection_data = json.loads(json_str)
                                    lang_code_full = detection_data.get("langCode", "other")
                                    raw_confidence = float(detection_data.get("confidence", 0.0))

                                    logger.debug(
                                        f"Triton model returned confidence: {raw_confidence} "
                                        f"for text: '{source_text[:50]}...' (lang: {lang_code_full})"
                                    )

                                    if "_" in lang_code_full:
                                        lang_code, script_code = lang_code_full.split("_", 1)
                                    else:
                                        lang_code = lang_code_full
                                        script_code = "Latn"

                                    language_name = self.INDICLID_TO_LANGUAGE.get(lang_code_full, "Other")

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

                                    # Normalize for DB constraint
                                    normalized_confidence = self.normalize_confidence_score(raw_confidence)

                                    with tracer.start_as_current_span("language-detection.store_result") as store_span:
                                        await self.repository.create_result(
                                            request_id=request_id,
                                            source_text=source_text,
                                            detected_language=lang_code,
                                            detected_script=script_code,
                                            confidence_score=normalized_confidence,
                                            language_name=language_name,
                                        )
                                        store_span.set_attribute("language-detection.detected_language", lang_code)
                                        store_span.set_attribute("language-detection.confidence", normalized_confidence)

                                except (json.JSONDecodeError, KeyError, ValueError) as e:
                                    logger.error(f"Failed to parse language detection result: {e}")
                                    results.append(
                                        LanguageDetectionOutput(source=source_text, langPrediction=[])
                                    )
                            else:
                                results.append(
                                    LanguageDetectionOutput(source=source_text, langPrediction=[])
                                )
                else:
                    for source_text in input_texts:
                        results.append(
                            LanguageDetectionOutput(source=source_text, langPrediction=[])
                        )

                response_model = LanguageDetectionInferenceResponse(output=results)

                # Update request status
                processing_time = time.time() - start_time
                with tracer.start_as_current_span("language-detection.update_status") as status_span:
                    await self.repository.update_request_status(
                        request_id=request_id,
                        status="completed",
                        processing_time=processing_time,
                    )
                    status_span.set_attribute("language-detection.processing_time", processing_time)
                    status_span.set_attribute("language-detection.request_id", str(request_id))

                span.set_attribute("language-detection.output_count", len(results))
                span.set_attribute("language-detection.processing_time", processing_time)

                logger.info(
                    f"Language detection completed for request {request_id} in {processing_time:.2f}s"
                )
                return response_model

            except TritonInferenceError as e:
                logger.error(f"Language detection Triton inference failed: {e}")
                span.set_attribute("error", True)
                span.set_attribute("error.type", type(e).__name__)
                span.set_attribute("error.message", str(e))
                span.set_status(Status(StatusCode.ERROR, str(e)))
                span.record_exception(e)

                if request_id:
                    try:
                        await self.repository.update_request_status(
                            request_id=request_id,
                            status="failed",
                            error_message=str(e),
                        )
                    except Exception as update_error:
                        logger.error(f"Failed to update request status: {update_error}")

                raise

            except Exception as e:
                logger.error(f"Language detection failed: {e}")
                span.set_attribute("error", True)
                span.set_attribute("error.type", type(e).__name__)
                span.set_attribute("error.message", str(e))
                span.set_status(Status(StatusCode.ERROR, str(e)))
                span.record_exception(e)

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
                raise TritonInferenceError(f"Language detection failed: {e}")
