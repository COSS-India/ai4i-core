"""
Core business logic for Speaker Diarization inference.
"""

import base64
import logging
import time
from typing import Dict, List, Optional
from uuid import UUID

import requests
from opentelemetry.trace import Status, StatusCode

from ai4icore_telemetry import StandardSpanManager
from app.schemas.inference import (
    AudioInput,
    Segment,
    SpeakerDiarizationInferenceRequest,
    SpeakerDiarizationInferenceResponse,
    SpeakerDiarizationOutput,
    SpeakerDiarizationResponseConfig,
)
from app.repositories.speaker_diarization_repository import SpeakerDiarizationRepository
from app.clients.triton_client import SpeakerDiarizationTritonClient
from ai4icore_exceptions import TritonInferenceError

logger = logging.getLogger(__name__)
_standard_spans = StandardSpanManager("speaker-diarization")


class SpeakerDiarizationService:
    """
    Speaker Diarization inference service.

    Responsibilities:
    - Take SpeakerDiarizationInferenceRequest
    - For each audio:
      - Resolve base64 content (direct or via audioUri download)
      - Call Triton (Speaker Diarization model)
      - Map diarization model output to SpeakerDiarizationInferenceResponse
    - Persist requests and results to database
    """

    def __init__(
        self,
        repository: SpeakerDiarizationRepository,
        triton_client: SpeakerDiarizationTritonClient,
        model_name: str,
    ):
        self.repository = repository
        self.triton_client = triton_client
        self.model_name = model_name

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

    def _empty_output(self) -> SpeakerDiarizationOutput:
        """Return an empty output for failed/missing audio."""
        return SpeakerDiarizationOutput(
            total_segments=0,
            num_speakers=0,
            speakers=[],
            segments=[],
        )

    async def run_inference(
        self,
        request: SpeakerDiarizationInferenceRequest,
        user_id: Optional[int] = None,
        api_key_id: Optional[int] = None,
        session_id: Optional[int] = None,
    ) -> SpeakerDiarizationInferenceResponse:
        """
        Async speaker diarization inference entrypoint.

        Phases: preprocess → resolve_model → triton_inference → postprocess → persist.
        """
        start_time = time.time()
        request_id: Optional[UUID] = None
        has_errors = False

        service_id = request.config.serviceId if request.config else None
        input_count = len(request.audio or [])
        model_name = self.model_name

        with _standard_spans.inference(
            service_id=service_id,
            model_name=None,
            input_count=input_count,
            input_type="audio",
            user_id=user_id,
            api_key_id=api_key_id,
            session_id=session_id,
        ) as parent_span:
            try:
                resolved_audio: List[Optional[str]] = []
                with _standard_spans.preprocess() as preprocess_span:
                    preprocess_span.set_attribute(
                        "speaker-diarization.input_count", input_count
                    )
                    total_audio_bytes = 0
                    for audio_idx, audio_item in enumerate(request.audio or []):
                        audio_base64 = self._resolve_audio_base64(audio_item)
                        resolved_audio.append(audio_base64)
                        if audio_base64:
                            try:
                                total_audio_bytes += len(base64.b64decode(audio_base64))
                            except Exception:
                                pass
                        preprocess_span.add_event(
                            "speaker-diarization.audio.resolved",
                            {
                                "audio_index": audio_idx,
                                "has_content": bool(audio_item.audioContent),
                                "has_uri": bool(audio_item.audioUri),
                                "resolved": bool(audio_base64),
                                "audio_size_bytes": len(audio_base64)
                                if audio_base64
                                else 0,
                            },
                        )
                    preprocess_span.set_attribute(
                        "speaker-diarization.input.audio_bytes_total",
                        total_audio_bytes,
                    )
                    if parent_span is not None:
                        try:
                            parent_span.set_attribute(
                                "speaker-diarization.input.audio_bytes_total",
                                total_audio_bytes,
                            )
                        except Exception:
                            pass

                with _standard_spans.resolve_model() as resolve_span:
                    resolve_span.set_attribute(
                        "speaker-diarization.model_name", model_name
                    )
                    if parent_span is not None:
                        try:
                            parent_span.set_attribute(
                                "speaker-diarization.model_name", model_name
                            )
                        except Exception:
                            pass

                diarization_raw: List[Optional[Dict]] = [None] * len(resolved_audio)

                with _standard_spans.triton_inference() as triton_span:
                    triton_span.set_attribute(
                        "speaker-diarization.batch_size", input_count
                    )
                    for audio_idx, audio_base64 in enumerate(resolved_audio):
                        if not audio_base64:
                            continue

                        triton_span.add_event(
                            "speaker-diarization.audio.inference.started",
                            {"audio_index": audio_idx},
                        )
                        num_speakers = None
                        try:
                            diarization_data = (
                                self.triton_client.run_speaker_diarization_inference(
                                    audio_base64,
                                    num_speakers,
                                    model_name=model_name,
                                )
                            )
                            if not diarization_data:
                                triton_span.add_event(
                                    "speaker-diarization.audio.inference.empty_result",
                                    {"audio_index": audio_idx},
                                )
                                continue

                            raw_segments = diarization_data.get("segments", [])
                            diarization_raw[audio_idx] = diarization_data
                            triton_span.add_event(
                                "speaker-diarization.audio.inference.completed",
                                {
                                    "audio_index": audio_idx,
                                    "segment_count": len(raw_segments),
                                },
                            )
                        except TritonInferenceError as exc:
                            has_errors = True
                            triton_span.add_event(
                                "speaker-diarization.audio.inference.failed",
                                {
                                    "audio_index": audio_idx,
                                    "error.type": "TritonInferenceError",
                                    "error.message": str(exc),
                                },
                            )
                            triton_span.set_status(Status(StatusCode.ERROR, str(exc)))
                            triton_span.record_exception(exc)
                            logger.error(
                                "Speaker Diarization Triton inference failed: %s", exc
                            )
                        except Exception as exc:
                            has_errors = True
                            triton_span.add_event(
                                "speaker-diarization.audio.inference.failed",
                                {
                                    "audio_index": audio_idx,
                                    "error.type": type(exc).__name__,
                                    "error.message": str(exc),
                                },
                            )
                            triton_span.set_status(Status(StatusCode.ERROR, str(exc)))
                            triton_span.record_exception(exc)
                            logger.error(
                                "Error in speaker diarization inference: %s",
                                exc,
                                exc_info=True,
                            )

                output_list: List[SpeakerDiarizationOutput] = []
                with _standard_spans.postprocess() as post_span:
                    for audio_idx in range(len(resolved_audio)):
                        if not resolved_audio[audio_idx]:
                            output_list.append(self._empty_output())
                            continue

                        diarization_data = diarization_raw[audio_idx]
                        if not diarization_data:
                            output_list.append(self._empty_output())
                            continue

                        raw_segments = diarization_data.get("segments", [])
                        segments_list: List[Segment] = []
                        speakers_set = set()

                        for seg in raw_segments:
                            speaker = seg.get("speaker", "")
                            seg_start = float(seg.get("start_time", 0.0))
                            seg_end = float(seg.get("end_time", 0.0))
                            duration = seg_end - seg_start

                            if speaker:
                                speakers_set.add(speaker)

                            segments_list.append(
                                Segment(
                                    start_time=seg_start,
                                    end_time=seg_end,
                                    duration=duration,
                                    speaker=speaker,
                                )
                            )

                        segments_list.sort(key=lambda x: x.start_time)

                        output_list.append(
                            SpeakerDiarizationOutput(
                                total_segments=len(segments_list),
                                num_speakers=len(speakers_set),
                                speakers=sorted(list(speakers_set)),
                                segments=segments_list,
                            )
                        )

                    post_span.set_attribute(
                        "speaker-diarization.output_count", len(output_list)
                    )
                    post_span.set_attribute(
                        "speaker-diarization.has_errors", has_errors
                    )

                processing_time = time.time() - start_time

                with _standard_spans.persist() as persist_span:
                    try:
                        request_record = await self.repository.create_request(
                            model_id=service_id,
                            audio_duration=None,
                            num_speakers=None,
                            user_id=user_id,
                            api_key_id=api_key_id,
                            session_id=session_id,
                        )
                        request_id = request_record.id
                        persist_span.set_attribute(
                            "speaker-diarization.request_id", str(request_id)
                        )
                        persist_span.add_event(
                            "speaker-diarization.db.request_created",
                            {"request_id": str(request_id)},
                        )
                    except Exception as e:
                        persist_span.add_event(
                            "speaker-diarization.db.create_request.failed",
                            {
                                "error.type": type(e).__name__,
                                "error.message": str(e),
                            },
                        )
                        logger.error("Failed to create request record: %s", e)

                    if request_id:
                        db_results_saved = 0
                        for audio_idx, out in enumerate(output_list):
                            segments_dict = [
                                {
                                    "start_time": seg.start_time,
                                    "end_time": seg.end_time,
                                    "duration": seg.duration,
                                    "speaker": seg.speaker,
                                }
                                for seg in out.segments
                            ]
                            try:
                                await self.repository.create_result(
                                    request_id=request_id,
                                    total_segments=out.total_segments,
                                    num_speakers=out.num_speakers,
                                    speakers=out.speakers,
                                    segments=segments_dict,
                                )
                                db_results_saved += 1
                                persist_span.add_event(
                                    "speaker-diarization.db.result.created",
                                    {"audio_index": audio_idx},
                                )
                            except Exception as e:
                                has_errors = True
                                persist_span.add_event(
                                    "speaker-diarization.db.create_result.failed",
                                    {
                                        "audio_index": audio_idx,
                                        "error.type": type(e).__name__,
                                        "error.message": str(e),
                                    },
                                )
                                logger.error(
                                    "Failed to create result record (audio_index=%s): %s",
                                    audio_idx,
                                    e,
                                )
                        persist_span.set_attribute(
                            "speaker-diarization.db_results_created",
                            db_results_saved,
                        )
                        persist_span.set_attribute(
                            "speaker-diarization.db_results_expected",
                            len(output_list),
                        )

                        try:
                            status_str = "failed" if has_errors else "completed"
                            await self.repository.update_request_status(
                                request_id=request_id,
                                status=status_str,
                                processing_time=processing_time,
                            )
                            persist_span.add_event(
                                "speaker-diarization.db.request_completed",
                                {
                                    "request_id": str(request_id),
                                    "status": status_str,
                                    "processing_time_seconds": processing_time,
                                },
                            )
                        except Exception as e:
                            persist_span.add_event(
                                "speaker-diarization.db.update_status.failed",
                                {
                                    "error.type": type(e).__name__,
                                    "error.message": str(e),
                                },
                            )
                            logger.error("Failed to update request status: %s", e)

                response_config = None
                if request.config and request.config.serviceId:
                    response_config = SpeakerDiarizationResponseConfig(
                        serviceId=request.config.serviceId,
                        language=None,
                    )

                if parent_span is not None:
                    try:
                        parent_span.set_attribute(
                            "speaker-diarization.output_count", len(output_list)
                        )
                    except Exception:
                        pass

                return SpeakerDiarizationInferenceResponse(
                    taskType="speaker-diarization",
                    output=output_list,
                    config=response_config,
                )
            except Exception as e:
                logger.error("Speaker diarization inference failed: %s", e)

                if request_id:
                    try:
                        await self.repository.update_request_status(
                            request_id, "failed", error_message=str(e)
                        )
                    except Exception as update_error:
                        logger.error(
                            "Failed to update request status: %s", update_error
                        )
                else:
                    try:
                        dr = await self.repository.create_request(
                            model_id=service_id,
                            audio_duration=None,
                            num_speakers=None,
                            user_id=user_id,
                            api_key_id=api_key_id,
                            session_id=session_id,
                        )
                        await self.repository.update_request_status(
                            dr.id, "failed", error_message=str(e)
                        )
                    except Exception as db_err:
                        logger.error(
                            "speaker-diarization: failed to record failed request: %s",
                            db_err,
                        )

                raise
