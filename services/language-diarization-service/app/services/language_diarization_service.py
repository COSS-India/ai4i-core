"""
Core business logic for Language Diarization inference.
"""

import base64
import logging
import time
from typing import Dict, List, Optional
from uuid import UUID

import requests
from ai4icore_telemetry import StandardSpanManager, Status, StatusCode
from app.schemas.inference import (
    AudioInput,
    LanguageDiarizationInferenceRequest,
    LanguageSegment,
    LanguageDiarizationInferenceResponse,
    LanguageDiarizationOutput,
    LanguageDiarizationResponseConfig,
)
from app.repositories.language_diarization_repository import LanguageDiarizationRepository
from app.clients.triton_client import LanguageDiarizationTritonClient
from ai4icore_exceptions import TritonInferenceError

logger = logging.getLogger(__name__)
_standard_spans = StandardSpanManager("language-diarization")

# Triton model name (see LanguageDiarizationTritonClient.send_triton_request)
_LANG_DIAR_MODEL_NAME = "lang_diarization"


class LanguageDiarizationService:
    """
    Language Diarization inference service.

    Responsibilities:
    - Take LanguageDiarizationInferenceRequest
    - For each audio:
      - Resolve base64 content (direct or via audioUri download)
      - Call Triton (Language Diarization model)
      - Map diarization model output to response format
    - Persist requests and results to database
    """

    def __init__(
        self,
        triton_client: LanguageDiarizationTritonClient,
        repository: Optional[LanguageDiarizationRepository] = None,
    ):
        self.triton_client = triton_client
        self.repository = repository

    def _resolve_audio_base64(self, audio: AudioInput) -> Optional[str]:
        """Resolve an audio into base64 (content or download from URI)."""
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

    def _empty_output(self, target_language: str = "") -> LanguageDiarizationOutput:
        return LanguageDiarizationOutput(
            total_segments=0,
            segments=[],
            target_language=target_language,
        )

    async def run_inference(
        self,
        request: LanguageDiarizationInferenceRequest,
        user_id: Optional[int] = None,
        api_key_id: Optional[int] = None,
        session_id: Optional[int] = None,
    ) -> LanguageDiarizationInferenceResponse:
        """Asynchronous language diarization inference entrypoint."""
        start_time = time.time()
        request_id: Optional[UUID] = None
        has_errors = False

        service_id = request.config.serviceId if request.config else None
        input_count = len(request.audio or [])

        with _standard_spans.inference(
            service_id=service_id,
            model_name=_LANG_DIAR_MODEL_NAME,
            input_count=input_count,
            input_type="audio",
            user_id=user_id,
            api_key_id=api_key_id,
            session_id=session_id,
        ) as parent_span:
            resolved_audio: List[Optional[str]] = []

            with _standard_spans.preprocess() as preprocess_span:
                preprocess_span.set_attribute(
                    "language-diarization.preprocess.modality", "audio"
                )
                preprocess_span.set_attribute(
                    "language-diarization.preprocess.operations",
                    "resolve_audio_base64(download_if_uri),base64_decode_size_estimate",
                )
                preprocess_span.set_attribute(
                    "language-diarization.preprocess.audio_count", input_count
                )
                total_audio_bytes = 0
                for idx, audio_item in enumerate(request.audio):
                    audio_base64 = self._resolve_audio_base64(audio_item)
                    resolved_audio.append(audio_base64)
                    if audio_base64:
                        try:
                            total_audio_bytes += len(base64.b64decode(audio_base64))
                        except Exception:
                            pass
                    preprocess_span.add_event(
                        "language-diarization.preprocess.audio.resolved",
                        {
                            "audio_index": idx,
                            "has_content": bool(audio_item.audioContent),
                            "has_uri": bool(audio_item.audioUri),
                            "resolved": bool(audio_base64),
                            "audio_size_bytes": len(audio_base64)
                            if audio_base64
                            else 0,
                        },
                    )
                preprocess_span.set_attribute(
                    "language-diarization.preprocess.audio_bytes_total",
                    total_audio_bytes,
                )
                preprocess_span.add_event(
                    "language-diarization.preprocess.completed",
                    {
                        "audio_count": input_count,
                        "audio_bytes_total": total_audio_bytes,
                        "resolved_count": sum(1 for a in resolved_audio if a),
                    },
                )
                if parent_span is not None:
                    try:
                        parent_span.set_attribute(
                            "language-diarization.input.audio_bytes_total",
                            total_audio_bytes,
                        )
                    except Exception:
                        pass

            with _standard_spans.resolve_model() as resolve_span:
                resolve_span.set_attribute(
                    "language-diarization.resolve_model.resolution_source",
                    "constant_in_service",
                )
                resolve_span.set_attribute(
                    "language-diarization.resolve_model.model_name", _LANG_DIAR_MODEL_NAME
                )
                try:
                    resolve_span.set_attribute(
                        "language-diarization.resolve_model.triton_endpoint",
                        getattr(self.triton_client, "triton_url", None),
                    )
                except Exception:
                    pass
                resolve_span.add_event(
                    "language-diarization.resolve_model.completed",
                    {"model_name": _LANG_DIAR_MODEL_NAME},
                )
                if parent_span is not None:
                    try:
                        parent_span.set_attribute(
                            "language-diarization.model_name",
                            _LANG_DIAR_MODEL_NAME,
                        )
                    except Exception:
                        pass

            diarization_raw: List[Optional[Dict]] = [None] * input_count

            with _standard_spans.triton_inference() as triton_span:
                triton_span.set_attribute(
                    "language-diarization.triton_inference.task",
                    "language_diarization",
                )
                triton_span.set_attribute(
                    "language-diarization.triton_inference.model_name",
                    _LANG_DIAR_MODEL_NAME,
                )
                triton_span.set_attribute(
                    "language-diarization.triton_inference.audio_count", input_count
                )
                target_language = ""
                for idx, audio_base64 in enumerate(resolved_audio):
                    if not audio_base64:
                        continue

                    triton_span.add_event(
                        "language-diarization.triton_inference.item.started",
                        {"audio_index": idx},
                    )
                    try:
                        diarization_data = (
                            self.triton_client.run_language_diarization_inference(
                                audio_base64, target_language
                            )
                        )
                        if not diarization_data:
                            triton_span.add_event(
                                "language-diarization.triton_inference.item.empty_result",
                                {"audio_index": idx},
                            )
                            continue

                        diarization_raw[idx] = diarization_data
                        raw_segments = diarization_data.get("segments", [])
                        triton_span.add_event(
                            "language-diarization.triton_inference.item.completed",
                            {
                                "audio_index": idx,
                                "segment_count": len(raw_segments),
                            },
                        )
                    except TritonInferenceError as exc:
                        has_errors = True
                        triton_span.add_event(
                            "language-diarization.triton_inference.item.failed",
                            {
                                "audio_index": idx,
                                "error.type": "TritonInferenceError",
                                "error.message": str(exc),
                            },
                        )
                        triton_span.set_status(Status(StatusCode.ERROR, str(exc)))
                        triton_span.record_exception(exc)
                        logger.error(
                            "Language Diarization Triton inference failed: %s", exc
                        )
                    except Exception as exc:
                        has_errors = True
                        triton_span.add_event(
                            "language-diarization.triton_inference.item.failed",
                            {
                                "audio_index": idx,
                                "error.type": type(exc).__name__,
                                "error.message": str(exc),
                            },
                        )
                        triton_span.set_status(Status(StatusCode.ERROR, str(exc)))
                        triton_span.record_exception(exc)
                        logger.error(
                            "Error in language diarization inference: %s",
                            exc,
                            exc_info=True,
                        )

            output_list: List[LanguageDiarizationOutput] = []
            with _standard_spans.postprocess() as post_span:
                post_span.set_attribute(
                    "language-diarization.postprocess.expected_count", input_count
                )
                for idx in range(input_count):
                    if not resolved_audio[idx]:
                        output_list.append(self._empty_output())
                        continue

                    diarization_data = diarization_raw[idx]
                    if not diarization_data:
                        output_list.append(self._empty_output())
                        continue

                    segments_list: List[LanguageSegment] = []
                    raw_segments = diarization_data.get("segments", [])
                    for seg in raw_segments:
                        language = seg.get("language", "")
                        seg_start = float(seg.get("start_time", 0.0))
                        seg_end = float(seg.get("end_time", 0.0))
                        duration = float(seg.get("duration", seg_end - seg_start))
                        confidence = float(seg.get("confidence", 0.0))

                        segments_list.append(
                            LanguageSegment(
                                start_time=seg_start,
                                end_time=seg_end,
                                duration=duration,
                                language=language,
                                confidence=confidence,
                            )
                        )

                    segments_list.sort(key=lambda x: x.start_time)
                    tgt_lang = diarization_data.get("target_language", "")

                    post_span.add_event(
                        "language-diarization.postprocess.item.parsed",
                        {
                            "audio_index": idx,
                            "segment_count": len(segments_list),
                            "target_language": tgt_lang,
                        },
                    )

                    output_list.append(
                        LanguageDiarizationOutput(
                            total_segments=len(segments_list),
                            segments=segments_list,
                            target_language=tgt_lang,
                        )
                    )

                post_span.set_attribute(
                    "language-diarization.postprocess.output_count", len(output_list)
                )
                post_span.add_event(
                    "language-diarization.postprocess.completed",
                    {
                        "output_count": len(output_list),
                        "has_errors": bool(has_errors),
                    },
                )

            processing_time = time.time() - start_time

            if self.repository:
                with _standard_spans.persist() as persist_span:
                    persist_span.set_attribute(
                        "language-diarization.db.operations",
                        "language_diarization_requests.insert,language_diarization_results.insert_per_audio,language_diarization_requests.status_update",
                    )
                    model_id = (
                        request.config.serviceId
                        if request.config
                        else "lang_diarization"
                    )
                    try:
                        request_record = await self.repository.create_request(
                            model_id=model_id,
                            audio_duration=None,
                            target_language="",
                            user_id=user_id,
                            api_key_id=api_key_id,
                            session_id=session_id,
                        )
                        request_id = request_record.id
                        persist_span.set_attribute(
                            "language-diarization.db.language_diarization_request.id",
                            str(request_id),
                        )
                        persist_span.set_attribute(
                            "language-diarization.request_id", str(request_id)
                        )
                        persist_span.add_event(
                            "language-diarization.db.language_diarization_request.insert",
                            {"table": "language_diarization_requests", "request_id": str(request_id)},
                        )
                        logger.info(
                            "Created language diarization request %s", request_id
                        )
                    except Exception as e:
                        persist_span.add_event(
                            "language-diarization.db.language_diarization_request.insert_failed",
                            {
                                "error.type": type(e).__name__,
                                "error.message": str(e),
                            },
                        )
                        logger.error("Failed to create request record: %s", e)

                    if request_id:
                        inserted_results = 0
                        for idx, out in enumerate(output_list):
                            try:
                                segments_dict = [
                                    {
                                        "start_time": seg.start_time,
                                        "end_time": seg.end_time,
                                        "duration": seg.duration,
                                        "language": seg.language,
                                        "confidence": seg.confidence,
                                    }
                                    for seg in out.segments
                                ]
                                await self.repository.create_result(
                                    request_id=request_id,
                                    total_segments=out.total_segments,
                                    segments=segments_dict,
                                    target_language=out.target_language,
                                )
                                inserted_results += 1
                                persist_span.add_event(
                                    "language-diarization.db.language_diarization_result.insert",
                                    {
                                        "audio_index": idx,
                                        "segment_count": len(out.segments),
                                    },
                                )
                            except Exception as e:
                                has_errors = True
                                persist_span.add_event(
                                    "language-diarization.db.language_diarization_result.insert_failed",
                                    {
                                        "audio_index": idx,
                                        "error.type": type(e).__name__,
                                        "error.message": str(e),
                                    },
                                )
                                logger.error(
                                    "Failed to create result record: %s", e
                                )
                        persist_span.set_attribute(
                            "language-diarization.db.language_diarization_result.inserted_count",
                            inserted_results,
                        )

                        try:
                            req_status = "failed" if has_errors else "completed"
                            await self.repository.update_request_status(
                                request_id=request_id,
                                status=req_status,
                                processing_time=processing_time,
                            )
                            persist_span.add_event(
                                "language-diarization.db.language_diarization_request.status_update",
                                {
                                    "request_id": str(request_id),
                                    "status": req_status,
                                    "processing_time_seconds": processing_time,
                                },
                            )
                        except Exception as e:
                            persist_span.add_event(
                                "language-diarization.db.language_diarization_request.status_update_failed",
                                {
                                    "error.type": type(e).__name__,
                                    "error.message": str(e),
                                },
                            )
                            logger.error("Failed to update request status: %s", e)

            if has_errors:
                _standard_spans.note_partial_inference_failure(
                    "One or more audio inputs failed during Triton inference or DB result persistence"
                )

            if parent_span is not None:
                try:
                    parent_span.set_attribute(
                        "language-diarization.output_count", len(output_list)
                    )
                except Exception:
                    pass

            response_config = None
            if request.config.serviceId:
                response_config = LanguageDiarizationResponseConfig(
                    serviceId=request.config.serviceId,
                )

            return LanguageDiarizationInferenceResponse(
                taskType="language-diarization",
                output=output_list,
                config=response_config,
            )
