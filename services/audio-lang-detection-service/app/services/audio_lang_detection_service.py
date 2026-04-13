"""
Core business logic for Audio Language Detection inference.
"""

import base64
import logging
import time
from typing import Dict, List, Optional, Tuple
from uuid import UUID

import requests
from ai4icore_telemetry import StandardSpanManager, Status, StatusCode
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
        """Resolve audio into base64 (content or download from URI)."""
        if audio.audioContent:
            return audio.audioContent

        if audio.audioUri:
            try:
                resp = requests.get(str(audio.audioUri), timeout=300)
                resp.raise_for_status()
                return base64.b64encode(resp.content).decode("utf-8")
            except Exception as exc:
                logger.error(
                    "Failed to download audio from %s: %s", audio.audioUri, exc
                )
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

        Standard phases: preprocess → resolve_model → triton_inference → postprocess → persist.
        """
        start_time = time.time()
        request_id: Optional[UUID] = None
        has_errors = False
        service_id = request.config.serviceId
        input_count = len(request.audio or [])
        model_name = self.model_name

        with _standard_spans.inference(
            service_id=service_id,
            model_name=model_name,
            input_count=input_count,
            input_type="audio",
            user_id=user_id,
            api_key_id=api_key_id,
            session_id=session_id,
        ) as parent_span:
            resolved_audio: List[Optional[str]] = []
            with _standard_spans.preprocess() as preprocess_span:
                preprocess_span.set_attribute(
                    "audio-lang-detection.preprocess.modality", "audio"
                )
                preprocess_span.set_attribute(
                    "audio-lang-detection.preprocess.operations",
                    "resolve_audio_base64(download_if_uri),base64_decode_size_estimate",
                )
                preprocess_span.set_attribute(
                    "audio-lang-detection.preprocess.audio_count", input_count
                )
                total_audio_bytes = 0
                for idx, audio_item in enumerate(request.audio or []):
                    audio_b64 = self._resolve_audio_base64(audio_item)
                    resolved_audio.append(audio_b64)
                    if audio_b64:
                        try:
                            total_audio_bytes += len(base64.b64decode(audio_b64))
                        except Exception:
                            pass
                    preprocess_span.add_event(
                        "audio-lang-detection.preprocess.audio.resolved",
                        {
                            "audio_index": idx,
                            "has_content": bool(audio_item.audioContent),
                            "has_uri": bool(audio_item.audioUri),
                            "resolved": bool(audio_b64),
                            "audio_size_bytes": len(audio_b64) if audio_b64 else 0,
                        },
                    )
                preprocess_span.set_attribute(
                    "audio-lang-detection.preprocess.audio_bytes_total",
                    total_audio_bytes,
                )
                preprocess_span.add_event(
                    "audio-lang-detection.preprocess.completed",
                    {
                        "audio_count": input_count,
                        "audio_bytes_total": total_audio_bytes,
                        "resolved_count": sum(1 for a in resolved_audio if a),
                    },
                )
                if parent_span is not None:
                    try:
                        parent_span.set_attribute(
                            "audio-lang-detection.input.audio_bytes_total",
                            total_audio_bytes,
                        )
                    except Exception:
                        pass

            with _standard_spans.resolve_model() as resolve_span:
                resolve_span.set_attribute(
                    "audio-lang-detection.resolve_model.resolution_source",
                    "configured_on_service",
                )
                resolve_span.set_attribute(
                    "audio-lang-detection.resolve_model.model_name", model_name
                )
                try:
                    resolve_span.set_attribute(
                        "audio-lang-detection.resolve_model.triton_endpoint",
                        getattr(self.triton_client, "triton_url", None),
                    )
                except Exception:
                    pass
                resolve_span.add_event(
                    "audio-lang-detection.resolve_model.completed",
                    {"model_name": model_name},
                )
                if parent_span is not None:
                    try:
                        parent_span.set_attribute(
                            "audio-lang-detection.model_name", model_name
                        )
                    except Exception:
                        pass

            # Raw Triton JSON per index (None = skip / failed / empty)
            detection_results: List[Optional[Dict]] = [None] * len(resolved_audio)

            with _standard_spans.triton_inference() as triton_span:
                triton_span.set_attribute(
                    "audio-lang-detection.triton_inference.task",
                    "audio_language_detection",
                )
                triton_span.set_attribute(
                    "audio-lang-detection.triton_inference.model_name",
                    model_name,
                )
                triton_span.set_attribute(
                    "audio-lang-detection.triton_inference.audio_count", input_count
                )
                for idx, audio_base64 in enumerate(resolved_audio):
                    if not audio_base64:
                        continue

                    triton_span.add_event(
                        "audio-lang-detection.triton_inference.item.started",
                        {"audio_index": idx},
                    )
                    try:
                        detection_data = (
                            self.triton_client.run_audio_lang_detection_inference(
                                audio_base64, model_name=model_name
                            )
                        )
                        if not detection_data:
                            triton_span.add_event(
                                "audio-lang-detection.triton_inference.item.empty_result",
                                {"audio_index": idx},
                            )
                            continue

                        detection_results[idx] = detection_data
                        language_code = detection_data.get("language_code", "")
                        confidence = detection_data.get("confidence", 0.0)
                        triton_span.add_event(
                            "audio-lang-detection.triton_inference.item.completed",
                            {
                                "audio_index": idx,
                                "detected_language": language_code,
                                "confidence": confidence,
                            },
                        )
                    except TritonInferenceError as exc:
                        has_errors = True
                        triton_span.add_event(
                            "audio-lang-detection.triton_inference.item.failed",
                            {
                                "audio_index": idx,
                                "error.type": "TritonInferenceError",
                                "error.message": str(exc),
                            },
                        )
                        triton_span.set_status(Status(StatusCode.ERROR, str(exc)))
                        triton_span.record_exception(exc)
                    except Exception as exc:
                        has_errors = True
                        triton_span.add_event(
                            "audio-lang-detection.triton_inference.item.failed",
                            {
                                "audio_index": idx,
                                "error.type": type(exc).__name__,
                                "error.message": str(exc),
                            },
                        )
                        triton_span.set_status(Status(StatusCode.ERROR, str(exc)))
                        triton_span.record_exception(exc)

            if has_errors:
                _standard_spans.note_partial_inference_failure(
                    "One or more audio inputs failed during Triton inference"
                )

            inferred_rows: List[Tuple[int, str, float, dict]] = []
            output_list: List[AudioLangDetectionOutput] = []

            with _standard_spans.postprocess() as post_span:
                post_span.set_attribute(
                    "audio-lang-detection.postprocess.expected_count",
                    len(resolved_audio),
                )
                for idx in range(len(resolved_audio)):
                    if not resolved_audio[idx]:
                        output_list.append(self._empty_output())
                        continue

                    detection_data = detection_results[idx]
                    if not detection_data:
                        output_list.append(self._empty_output())
                        continue

                    all_scores_data = detection_data.get("all_scores", {})
                    language_code = detection_data.get("language_code", "")
                    confidence = detection_data.get("confidence", 0.0)

                    inferred_rows.append(
                        (idx, language_code, confidence, all_scores_data)
                    )
                    output_list.append(
                        AudioLangDetectionOutput(
                            language_code=language_code,
                            confidence=confidence,
                            all_scores=AllScores(
                                predicted_language=all_scores_data.get(
                                    "predicted_language", ""
                                ),
                                confidence=all_scores_data.get("confidence", 0.0),
                                top_scores=all_scores_data.get("top_scores", []),
                            ),
                        )
                    )

                post_span.set_attribute(
                    "audio-lang-detection.postprocess.output_count", len(output_list)
                )
                post_span.set_attribute(
                    "audio-lang-detection.postprocess.db_candidate_count",
                    len(inferred_rows),
                )
                post_span.add_event(
                    "audio-lang-detection.postprocess.completed",
                    {
                        "output_count": len(output_list),
                        "db_candidate_count": len(inferred_rows),
                        "has_errors": bool(has_errors),
                    },
                )

            processing_time = time.time() - start_time

            with _standard_spans.persist() as persist_span:
                persist_span.set_attribute(
                    "audio-lang-detection.db.operations",
                    "audio_lang_detection_requests.insert,audio_lang_detection_results.insert_per_audio,audio_lang_detection_requests.status_update",
                )
                try:
                    request_record = await self.repository.create_request(
                        model_id=service_id,
                        audio_duration=None,
                        user_id=user_id,
                        api_key_id=api_key_id,
                        session_id=session_id,
                    )
                    request_id = request_record.id
                    persist_span.set_attribute(
                        "audio-lang-detection.db.audio_lang_detection_request.id",
                        str(request_id),
                    )
                    persist_span.set_attribute(
                        "audio-lang-detection.request_id", str(request_id)
                    )
                    persist_span.add_event(
                        "audio-lang-detection.db.audio_lang_detection_request.insert",
                        {"table": "audio_lang_detection_requests", "request_id": str(request_id)},
                    )
                except Exception as e:
                    persist_span.add_event(
                        "audio-lang-detection.db.audio_lang_detection_request.insert_failed",
                        {
                            "error.type": type(e).__name__,
                            "error.message": str(e),
                        },
                    )

                if request_id:
                    inserted_results = 0
                    for idx, language_code, confidence, all_scores_data in inferred_rows:
                        try:
                            await self.repository.create_result(
                                request_id=request_id,
                                language_code=language_code,
                                confidence=confidence,
                                all_scores=all_scores_data,
                            )
                            inserted_results += 1
                            persist_span.add_event(
                                "audio-lang-detection.db.audio_lang_detection_result.insert",
                                {"audio_index": idx},
                            )
                        except Exception as e:
                            persist_span.add_event(
                                "audio-lang-detection.db.audio_lang_detection_result.insert_failed",
                                {
                                    "audio_index": idx,
                                    "error.type": type(e).__name__,
                                    "error.message": str(e),
                                },
                            )
                    persist_span.set_attribute(
                        "audio-lang-detection.db.audio_lang_detection_result.inserted_count",
                        inserted_results,
                    )
                    persist_span.set_attribute(
                        "audio-lang-detection.db.audio_lang_detection_result.expected_count",
                        len(inferred_rows),
                    )

                    try:
                        status_str = "failed" if has_errors else "completed"
                        await self.repository.update_request_status(
                            request_id=request_id,
                            status=status_str,
                            processing_time=processing_time,
                        )
                        persist_span.add_event(
                            "audio-lang-detection.db.audio_lang_detection_request.status_update",
                            {
                                "request_id": str(request_id),
                                "status": status_str,
                                "processing_time_seconds": processing_time,
                            },
                        )
                    except Exception as e:
                        persist_span.add_event(
                            "audio-lang-detection.db.audio_lang_detection_request.status_update_failed",
                            {
                                "error.type": type(e).__name__,
                                "error.message": str(e),
                            },
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
