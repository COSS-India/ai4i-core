"""
Core business logic for Audio Language Detection inference.
"""

import base64
import logging
import time
from typing import List, Optional
from uuid import UUID

import requests
from opentelemetry import trace
from opentelemetry.trace import Status, StatusCode

from ai4icore_telemetry import StandardSpanManager
from app.schemas.inference import (
    AudioInput,
    AudioLangDetectionInferenceRequest,
    AudioLangDetectionInferenceResponse,
    AudioLangDetectionOutput,
    AudioLangDetectionResponseConfig,
    AllScores,
)
from app.repositories.audio_lang_detection_repository import AudioLangDetectionRepository
from app.clients.triton_client import AudioLangDetectionTritonClient
from ai4icore_exceptions import TritonInferenceError

logger = logging.getLogger(__name__)
tracer = trace.get_tracer("audio-lang-detection-service")
_standard_spans = StandardSpanManager("audio-lang-detection")


class AudioLangDetectionService:
    """
    Audio Language Detection inference service.

    Responsibilities:
    - Take AudioLangDetectionInferenceRequest
    - For each audio:
      - Resolve base64 content (direct or via audioUri download)
      - Call Triton (Audio Language Detection model)
      - Map detection model output to AudioLangDetectionInferenceResponse
    - Persist requests and results to database
    """

    def __init__(
        self,
        repository: AudioLangDetectionRepository,
        triton_client: AudioLangDetectionTritonClient,
        model_name: str,
    ):
        self.repository = repository
        self.triton_client = triton_client
        self.model_name = model_name

    def _resolve_audio_base64(self, audio: AudioInput) -> Optional[str]:
        """
        Resolve an audio into base64:

        - If audioContent is provided, use it directly
        - Else, download from audioUri and base64-encode it
        """
        if audio.audioContent:
            return audio.audioContent

        if audio.audioUri:
            try:
                resp = requests.get(str(audio.audioUri), timeout=300)
                resp.raise_for_status()
                return base64.b64encode(resp.content).decode("utf-8")
            except Exception as exc:
                logger.error("Failed to download audio from %s: %s", audio.audioUri, exc)
                return None

        return None

    def _empty_output(self) -> AudioLangDetectionOutput:
        """Return an empty output for failed/missing audio."""
        return AudioLangDetectionOutput(
            language_code="",
            confidence=0.0,
            all_scores=AllScores(
                predicted_language="",
                confidence=0.0,
                top_scores=[],
            ),
        )

    async def run_inference(
        self,
        request: AudioLangDetectionInferenceRequest,
        user_id: Optional[int] = None,
        api_key_id: Optional[int] = None,
        session_id: Optional[int] = None,
    ) -> AudioLangDetectionInferenceResponse:
        """
        Async audio language detection inference entrypoint.

        Creates database request record, processes inference, logs results, and updates status.
        OpenTelemetry's tracer.start_as_current_span() is a no-op when tracing isn't configured.
        """
        start_time = time.time()
        request_id: Optional[UUID] = None
        has_errors = False
        service_id = request.config.serviceId
        input_count = len(request.audio or [])

        with _standard_spans.inference(
            service_id=service_id,
            model_name=self.model_name,
            input_count=input_count,
            input_type="audio",
            user_id=user_id,
            api_key_id=api_key_id,
            session_id=session_id,
        ) as parent_span:
            # Phase 6: persist (create request)
            with _standard_spans.persist() as persist_span:
                try:
                    request_record = await self.repository.create_request(
                        model_id=service_id,
                        audio_duration=None,
                        user_id=user_id,
                        api_key_id=api_key_id,
                        session_id=session_id,
                    )
                    request_id = request_record.id
                    persist_span.set_attribute("audio-lang-detection.request_id", str(request_id))
                except Exception as e:
                    persist_span.add_event(
                        "audio-lang-detection.db.create_request.failed",
                        {"error.type": type(e).__name__, "error.message": str(e)},
                    )

            # Phase 2: preprocess
            resolved_audio: List[Optional[str]] = []
            with _standard_spans.preprocess() as preprocess_span:
                preprocess_span.set_attribute("audio-lang-detection.input_count", input_count)
                for idx, audio_item in enumerate(request.audio or []):
                    audio_b64 = self._resolve_audio_base64(audio_item)
                    resolved_audio.append(audio_b64)
                    preprocess_span.add_event(
                        "audio-lang-detection.audio.resolved",
                        {
                            "audio_index": idx,
                            "has_content": bool(audio_item.audioContent),
                            "has_uri": bool(audio_item.audioUri),
                            "resolved": bool(audio_b64),
                            "audio_size_bytes": len(audio_b64) if audio_b64 else 0,
                        },
                    )

            # Phase 4: triton inference (single span; per-audio work is events)
            output_list: List[AudioLangDetectionOutput] = []
            inferred_rows: List[tuple] = []
            with _standard_spans.triton_inference() as triton_span:
                for idx, audio_base64 in enumerate(resolved_audio):
                    if not audio_base64:
                        output_list.append(self._empty_output())
                        continue

                    triton_span.add_event(
                        "audio-lang-detection.audio.inference.started", {"audio_index": idx}
                    )
                    try:
                        detection_data = self.triton_client.run_audio_lang_detection_inference(
                            audio_base64, model_name=self.model_name
                        )
                        if not detection_data:
                            output_list.append(self._empty_output())
                            triton_span.add_event(
                                "audio-lang-detection.audio.inference.empty_result",
                                {"audio_index": idx},
                            )
                            continue

                        all_scores_data = detection_data.get("all_scores", {})
                        language_code = detection_data.get("language_code", "")
                        confidence = detection_data.get("confidence", 0.0)

                        inferred_rows.append((idx, language_code, confidence, all_scores_data))

                        output_list.append(
                            AudioLangDetectionOutput(
                                language_code=language_code,
                                confidence=confidence,
                                all_scores=AllScores(
                                    predicted_language=all_scores_data.get("predicted_language", ""),
                                    confidence=all_scores_data.get("confidence", 0.0),
                                    top_scores=all_scores_data.get("top_scores", []),
                                ),
                            )
                        )
                        triton_span.add_event(
                            "audio-lang-detection.audio.inference.completed",
                            {
                                "audio_index": idx,
                                "detected_language": language_code,
                                "confidence": confidence,
                            },
                        )
                    except TritonInferenceError as exc:
                        has_errors = True
                        triton_span.add_event(
                            "audio-lang-detection.audio.inference.failed",
                            {
                                "audio_index": idx,
                                "error.type": "TritonInferenceError",
                                "error.message": str(exc),
                            },
                        )
                        triton_span.set_status(Status(StatusCode.ERROR, str(exc)))
                        triton_span.record_exception(exc)
                        output_list.append(self._empty_output())
                    except Exception as exc:
                        has_errors = True
                        triton_span.add_event(
                            "audio-lang-detection.audio.inference.failed",
                            {
                                "audio_index": idx,
                                "error.type": type(exc).__name__,
                                "error.message": str(exc),
                            },
                        )
                        triton_span.set_status(Status(StatusCode.ERROR, str(exc)))
                        triton_span.record_exception(exc)
                        output_list.append(self._empty_output())

            # Phase 6: persist results + update status
            processing_time = time.time() - start_time
            with _standard_spans.persist() as persist_span:
                if request_id:
                    for idx, language_code, confidence, all_scores_data in inferred_rows:
                        try:
                            await self.repository.create_result(
                                request_id=request_id,
                                language_code=language_code,
                                confidence=confidence,
                                all_scores=all_scores_data,
                            )
                            persist_span.add_event(
                                "audio-lang-detection.db.result.created",
                                {"audio_index": idx},
                            )
                        except Exception as e:
                            persist_span.add_event(
                                "audio-lang-detection.db.result.failed",
                                {
                                    "audio_index": idx,
                                    "error.type": type(e).__name__,
                                    "error.message": str(e),
                                },
                            )

                    try:
                        status_str = "failed" if has_errors else "completed"
                        await self.repository.update_request_status(
                            request_id=request_id,
                            status=status_str,
                            processing_time=processing_time,
                        )
                        persist_span.set_attribute("audio-lang-detection.status", status_str)
                    except Exception as e:
                        persist_span.add_event(
                            "audio-lang-detection.db.update_status.failed",
                            {"error.type": type(e).__name__, "error.message": str(e)},
                        )

                persist_span.set_attribute(
                    "audio-lang-detection.processing_time_seconds", processing_time
                )

            response_config = (
                AudioLangDetectionResponseConfig(serviceId=request.config.serviceId)
                if request.config.serviceId
                else None
            )

            if parent_span is not None:
                try:
                    parent_span.set_attribute(
                        "audio-lang-detection.output_count", len(output_list)
                    )
                except Exception:
                    pass

            return AudioLangDetectionInferenceResponse(
                taskType="audio-lang-detection",
                output=output_list,
                config=response_config,
            )
