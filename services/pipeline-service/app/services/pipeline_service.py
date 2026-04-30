"""
Pipeline Service - Main orchestration logic

Handles the execution of multi-task AI pipelines (e.g., Speech-to-Speech translation).
Uses StandardSpanManager phases as children of the router's pipeline.inference span.
"""

import logging
import json
import re
from typing import Any, Dict, List, Optional

from app.schemas.pipeline_request import PipelineInferenceRequest, TaskType, PipelineTask
from app.schemas.pipeline_response import PipelineInferenceResponse, PipelineTaskOutput
from app.clients.http_client import ServiceClient
from ai4icore_constants.exceptions import (
    PipelineTaskError,
    ServiceUnavailableError,
    ModelNotFoundError,
    AuthenticationError,
)
from ai4icore_telemetry import StandardSpanManager

try:
    from opentelemetry import trace as otel_trace
    from opentelemetry.trace import Status, StatusCode

    _OTEL_TRACING = True
except ImportError:
    otel_trace = None
    Status = None
    StatusCode = None
    _OTEL_TRACING = False

logger = logging.getLogger(__name__)
_standard_spans = StandardSpanManager("pipeline")


def _task_event_payload(task: PipelineTask, task_index: int) -> Dict[str, Any]:
    return {
        "task.index": task_index,
        "pipeline.task.type": task.taskType.value,
        "pipeline.task.service_id": task.config.serviceId,
    }


class PipelineService:
    """Service for orchestrating AI pipeline tasks."""

    def __init__(self, service_client: ServiceClient):
        self.service_client = service_client

    async def run_pipeline_inference(
        self,
        request: PipelineInferenceRequest,
        jwt_token: Optional[str] = None,
        api_key: Optional[str] = None,
        user_id: Optional[int] = None,
    ) -> PipelineInferenceResponse:
        """
        Execute a multi-task AI pipeline.

        Standard phases (under router pipeline.inference): preprocess → resolve_model →
        triton_inference → postprocess → persist (orchestration has no DB).
        """
        results: List[PipelineTaskOutput] = []
        previous_output = request.inputData.copy()

        logger.info(
            "Starting pipeline with %s tasks", len(request.pipelineTasks)
        )

        with _standard_spans.preprocess() as preprocess_span:
            preprocess_span.set_attribute(
                "pipeline.task_count", len(request.pipelineTasks)
            )
            preprocess_span.set_attribute(
                "pipeline.task_types",
                ",".join(t.taskType.value for t in request.pipelineTasks),
            )
            preprocess_span.set_attribute(
                "pipeline.has_input_data",
                bool(getattr(request, "inputData", None)),
            )
            audio_n = len(request.inputData.get("audio", []))
            if audio_n:
                preprocess_span.set_attribute("pipeline.input.audio_count", audio_n)
            text_n = len(request.inputData.get("input", []))
            if text_n:
                preprocess_span.set_attribute(
                    "pipeline.input.text_segments", text_n
                )

        service_chain = ",".join(t.config.serviceId for t in request.pipelineTasks)
        with _standard_spans.resolve_model() as resolve_span:
            resolve_span.set_attribute("pipeline.model_name", service_chain)
            resolve_span.set_attribute(
                "pipeline.task_chain",
                ",".join(t.taskType.value for t in request.pipelineTasks),
            )

        with _standard_spans.triton_inference() as triton_span:
            triton_span.set_attribute(
                "pipeline.downstream_task_count", len(request.pipelineTasks)
            )
            for task_idx, pipeline_task in enumerate(request.pipelineTasks, start=1):
                logger.info(
                    "Executing task %s/%s: %s",
                    task_idx,
                    len(request.pipelineTasks),
                    pipeline_task.taskType,
                )
                triton_span.add_event(
                    "pipeline.task.started",
                    _task_event_payload(pipeline_task, task_idx),
                )

                try:
                    task_output = await self._execute_task(
                        task=pipeline_task,
                        input_data=previous_output,
                        task_index=task_idx,
                        triton_span=triton_span,
                        jwt_token=jwt_token,
                        api_key=api_key,
                        control_config=request.controlConfig,
                        user_id=user_id,
                    )
                    triton_span.add_event(
                        "pipeline.task.completed",
                        {
                            **_task_event_payload(pipeline_task, task_idx),
                            "task.output_count": len(task_output.output)
                            if task_output.output
                            else 0,
                        },
                    )
                except AuthenticationError:
                    raise
                except Exception as e:
                    error_info = self._parse_error(
                        e, task_idx, pipeline_task.taskType
                    )
                    error_msg = error_info["message"]
                    error_code = error_info["code"]
                    service_error = error_info.get("service_error")

                    logger.error(
                        "Task %s (%s) failed: %s",
                        task_idx,
                        pipeline_task.taskType,
                        error_msg,
                    )

                    triton_span.set_attribute("task.status", "error")
                    triton_span.set_attribute("error", True)
                    triton_span.set_attribute("error.message", error_msg)
                    triton_span.set_attribute("error.code", error_code)
                    triton_span.set_attribute("error.type", type(e).__name__)
                    triton_span.set_attribute("task.index", task_idx)
                    triton_span.set_attribute(
                        "task.type", str(pipeline_task.taskType)
                    )
                    triton_span.set_attribute(
                        "task.service_id", pipeline_task.config.serviceId
                    )
                    if service_error:
                        if "model" in service_error:
                            triton_span.set_attribute(
                                "error.model", service_error["model"]
                            )
                        if "service" in service_error:
                            triton_span.set_attribute(
                                "error.service", service_error["service"]
                            )
                        if "status_code" in service_error:
                            triton_span.set_attribute(
                                "error.service_status_code",
                                service_error["status_code"],
                            )

                    triton_span.add_event(
                        "pipeline.task.failed",
                        {
                            "task_index": task_idx,
                            "task_type": str(pipeline_task.taskType),
                            "error_code": error_code,
                            "error_message": error_msg,
                        },
                    )
                    if _OTEL_TRACING:
                        triton_span.record_exception(e)
                        if Status is not None and StatusCode is not None:
                            triton_span.set_status(
                                Status(StatusCode.ERROR, error_msg)
                            )

                    if error_code == "MODEL_NOT_FOUND":
                        raise ModelNotFoundError(
                            message=error_msg,
                            model_name=service_error.get("model", "unknown")
                            if service_error
                            else "unknown",
                            service_name=service_error.get("service", "unknown")
                            if service_error
                            else "unknown",
                        )
                    if error_code == "SERVICE_UNAVAILABLE":
                        raise ServiceUnavailableError(
                            message=error_msg,
                            service_name=service_error.get("service", "unknown")
                            if service_error
                            else "unknown",
                        )
                    raise PipelineTaskError(
                        message=error_msg,
                        task_index=task_idx,
                        task_type=str(pipeline_task.taskType),
                        service_error=service_error,
                        error_code=error_code,
                    )

                results.append(task_output)
                previous_output = self._transform_output_for_next_task(
                    task_type=pipeline_task.taskType,
                    output=task_output,
                )
                logger.info("Task %s completed successfully", task_idx)

        with _standard_spans.postprocess() as post_span:
            response = PipelineInferenceResponse(pipelineResponse=results)
            post_span.set_attribute("pipeline.output_task_count", len(results))
            post_span.add_event(
                "pipeline.response.built",
                {"task_results": len(results)},
            )

        with _standard_spans.persist() as persist_span:
            persist_span.add_event(
                "pipeline.persist.not_applicable",
                {"reason": "orchestration_only_no_database"},
            )

        if _OTEL_TRACING and otel_trace is not None:
            parent = otel_trace.get_current_span()
            if parent is not None and parent.is_recording():
                try:
                    parent.set_attribute("pipeline.output_count", len(results))
                except Exception:
                    pass

        logger.info(
            "Pipeline completed successfully with %s tasks", len(results)
        )
        return response

    def _parse_error(
        self, error: Exception, task_index: int, task_type: TaskType
    ) -> Dict[str, Any]:
        """Parse error to extract meaningful information and determine error code."""
        error_str = str(error)
        error_code = "PIPELINE_TASK_ERROR"
        service_error: Dict[str, Any] = {}

        try:
            if error_str.startswith("{") or error_str.startswith("["):
                error_dict = json.loads(error_str)
                if isinstance(error_dict, dict):
                    service_name = error_dict.get("service", "unknown")
                    status_code = error_dict.get("status_code", 500)
                    message = error_dict.get("message", error_str)
                    details = error_dict.get("details", {})

                    service_error = {
                        "service": service_name,
                        "status_code": status_code,
                        **details,
                    }

                    model_match = re.search(
                        r"model[:\s]+['\"]?([^'\"]+)['\"]?",
                        message,
                        re.IGNORECASE,
                    )
                    if model_match:
                        service_error["model"] = model_match.group(1)

                    message_lower = message.lower()
                    if "not found" in message_lower or "404" in message_lower:
                        if "model" in message_lower:
                            error_code = "MODEL_NOT_FOUND"
                        else:
                            error_code = "SERVICE_NOT_FOUND"
                    elif "timeout" in message_lower or "timed out" in message_lower:
                        error_code = "SERVICE_TIMEOUT"
                    elif (
                        "connection" in message_lower
                        or "unreachable" in message_lower
                    ):
                        error_code = "SERVICE_UNAVAILABLE"
                    elif status_code == 503:
                        error_code = "SERVICE_UNAVAILABLE"
                    elif status_code == 404:
                        error_code = "MODEL_NOT_FOUND"

                    if error_code == "MODEL_NOT_FOUND":
                        model_name = service_error.get("model", "unknown")
                        user_message = (
                            f"Model '{model_name}' not found in {service_name} service. "
                            "Please verify the model name and ensure it is loaded in the Triton inference server."
                        )
                    elif error_code == "SERVICE_UNAVAILABLE":
                        user_message = (
                            f"{service_name} service is unavailable. "
                            "The service may be down or unreachable."
                        )
                    elif error_code == "SERVICE_TIMEOUT":
                        user_message = (
                            f"{service_name} service request timed out. "
                            "The service may be overloaded."
                        )
                    else:
                        user_message = f"{service_name} service error: {message}"

                    return {
                        "message": user_message,
                        "code": error_code,
                        "service_error": service_error,
                    }
        except (json.JSONDecodeError, ValueError, KeyError):
            pass

        error_lower = error_str.lower()

        model_match = re.search(
            r"model[:\s]+['\"]?([^'\"]+)['\"]?\s+is\s+not\s+found",
            error_str,
            re.IGNORECASE,
        )
        if model_match:
            model_name = model_match.group(1)
            service_error["model"] = model_name
            error_code = "MODEL_NOT_FOUND"
            return {
                "message": (
                    f"Model '{model_name}' not found. Please verify the model name "
                    "and ensure it is loaded in the Triton inference server."
                ),
                "code": error_code,
                "service_error": service_error,
            }

        if (
            "connection" in error_lower
            or "unreachable" in error_lower
            or "timeout" in error_lower
        ):
            error_code = "SERVICE_UNAVAILABLE"
            return {
                "message": f"Service unavailable: {error_str}",
                "code": error_code,
                "service_error": service_error,
            }

        return {
            "message": f"Pipeline task failed: {error_str}",
            "code": error_code,
            "service_error": service_error,
        }

    async def _execute_task(
        self,
        task: PipelineTask,
        input_data: Dict[str, Any],
        *,
        task_index: int,
        triton_span: Any,
        jwt_token: Optional[str] = None,
        api_key: Optional[str] = None,
        control_config: Optional[Dict[str, Any]] = None,
        user_id: Optional[int] = None,
    ) -> PipelineTaskOutput:
        """Execute a single pipeline task (HTTP to downstream service)."""

        if task.taskType == TaskType.ASR:
            triton_span.add_event(
                "pipeline.task.asr.preprocess",
                _task_event_payload(task, task_index),
            )
            asr_config = {
                "serviceId": task.config.serviceId,
                "language": task.config.language.dict(),
            }
            if task.config.audioFormat:
                asr_config["audioFormat"] = task.config.audioFormat
            if task.config.preProcessors:
                asr_config["preProcessors"] = task.config.preProcessors
            if task.config.postProcessors:
                asr_config["postProcessors"] = task.config.postProcessors
            if task.config.transcriptionFormat:
                asr_config["transcriptionFormat"] = task.config.transcriptionFormat

            asr_request = {
                "audio": input_data.get("audio", []),
                "config": asr_config,
            }
            if control_config:
                asr_request["controlConfig"] = control_config

            audio_count = len(input_data.get("audio", []))
            triton_span.add_event(
                "pipeline.task.asr.request_ready",
                {
                    **_task_event_payload(task, task_index),
                    "asr.audio_count": audio_count,
                },
            )
            logger.info(
                "ASR request constructed with %s audio inputs", audio_count
            )

            try:
                triton_span.add_event(
                    "pipeline.task.invoke.started",
                    {**_task_event_payload(task, task_index), "downstream": "asr"},
                )
                response = await self.service_client.call_asr_service(
                    asr_request,
                    jwt_token=jwt_token,
                    api_key=api_key,
                    user_id=user_id,
                )
                output_count = len(response.get("output", []))
                triton_span.add_event(
                    "pipeline.task.invoke.completed",
                    {
                        **_task_event_payload(task, task_index),
                        "downstream": "asr",
                        "asr.output_count": output_count,
                    },
                )

                result = PipelineTaskOutput(
                    taskType="asr",
                    serviceId=task.config.serviceId,
                    output=response.get("output", []),
                    config=response.get("config"),
                )
                triton_span.add_event(
                    "pipeline.task.asr.postprocess",
                    _task_event_payload(task, task_index),
                )
                return result

            except AuthenticationError:
                raise
            except Exception as e:
                logger.error("ASR service call failed: %s", e)
                triton_span.set_attribute("error", True)
                triton_span.set_attribute("error.type", type(e).__name__)
                triton_span.set_attribute("error.message", str(e))
                if _OTEL_TRACING and Status is not None and StatusCode is not None:
                    triton_span.set_status(Status(StatusCode.ERROR, str(e)))
                triton_span.record_exception(e)
                triton_span.add_event(
                    "pipeline.task.invoke.failed",
                    {
                        "downstream": "asr",
                        "error_type": type(e).__name__,
                        "error_message": str(e),
                    },
                )
                raise

        if task.taskType == TaskType.TRANSLATION:
            triton_span.add_event(
                "pipeline.task.translation.preprocess",
                _task_event_payload(task, task_index),
            )
            nmt_request = {
                "input": input_data.get("input", []),
                "config": {
                    "serviceId": task.config.serviceId,
                    "language": task.config.language.dict(),
                },
            }
            input_count = len(input_data.get("input", []))
            lang_config = task.config.language.dict()
            triton_span.add_event(
                "pipeline.task.translation.request_ready",
                {
                    **_task_event_payload(task, task_index),
                    "nmt.input_count": input_count,
                    "nmt.source_language": lang_config.get("sourceLanguage", ""),
                    "nmt.target_language": lang_config.get("targetLanguage", ""),
                },
            )
            logger.info(
                "Translation request constructed with %s text inputs",
                input_count,
            )

            try:
                triton_span.add_event(
                    "pipeline.task.invoke.started",
                    {
                        **_task_event_payload(task, task_index),
                        "downstream": "nmt",
                    },
                )
                response = await self.service_client.call_nmt_service(
                    nmt_request,
                    jwt_token=jwt_token,
                    api_key=api_key,
                    user_id=user_id,
                )
                output_count = len(response.get("output", []))
                triton_span.add_event(
                    "pipeline.task.invoke.completed",
                    {
                        **_task_event_payload(task, task_index),
                        "downstream": "nmt",
                        "nmt.output_count": output_count,
                    },
                )

                result = PipelineTaskOutput(
                    taskType="translation",
                    serviceId=task.config.serviceId,
                    output=response.get("output", []),
                    config=None,
                )
                triton_span.add_event(
                    "pipeline.task.translation.postprocess",
                    _task_event_payload(task, task_index),
                )
                return result

            except Exception as e:
                logger.error("NMT service call failed: %s", e)
                triton_span.set_attribute("error", True)
                triton_span.set_attribute("error.type", type(e).__name__)
                triton_span.set_attribute("error.message", str(e))
                if _OTEL_TRACING and Status is not None and StatusCode is not None:
                    triton_span.set_status(Status(StatusCode.ERROR, str(e)))
                triton_span.record_exception(e)
                triton_span.add_event(
                    "pipeline.task.invoke.failed",
                    {
                        "downstream": "nmt",
                        "error_type": type(e).__name__,
                        "error_message": str(e),
                    },
                )
                raise

        if task.taskType == TaskType.TTS:
            triton_span.add_event(
                "pipeline.task.tts.preprocess",
                _task_event_payload(task, task_index),
            )
            tts_request = {
                "input": input_data.get("input", []),
                "config": {
                    "serviceId": task.config.serviceId,
                    "language": task.config.language.dict(),
                    "gender": task.config.gender or "male",
                    "audioFormat": task.config.audioFormat or "wav",
                    "samplingRate": 22050,
                    "encoding": "base64",
                },
            }
            input_count = len(input_data.get("input", []))
            lang_config = task.config.language.dict()
            triton_span.add_event(
                "pipeline.task.tts.request_ready",
                {
                    **_task_event_payload(task, task_index),
                    "tts.input_count": input_count,
                    "tts.language": lang_config.get("sourceLanguage", ""),
                },
            )
            logger.info(
                "TTS request constructed with %s text inputs", input_count
            )

            try:
                triton_span.add_event(
                    "pipeline.task.invoke.started",
                    {
                        **_task_event_payload(task, task_index),
                        "downstream": "tts",
                    },
                )
                response = await self.service_client.call_tts_service(
                    tts_request,
                    jwt_token=jwt_token,
                    api_key=api_key,
                    user_id=user_id,
                )
                audio_count = len(response.get("audio", []))
                triton_span.add_event(
                    "pipeline.task.invoke.completed",
                    {
                        **_task_event_payload(task, task_index),
                        "downstream": "tts",
                        "tts.audio_count": audio_count,
                    },
                )

                logger.info(
                    "TTS service returned %s audio outputs", audio_count
                )
                result = PipelineTaskOutput(
                    taskType="tts",
                    serviceId=task.config.serviceId,
                    output=response.get("audio", []),
                    audio=response.get("audio", []),
                    config=response.get("config"),
                )
                triton_span.add_event(
                    "pipeline.task.tts.postprocess",
                    _task_event_payload(task, task_index),
                )
                return result

            except Exception as e:
                logger.error("TTS service call failed: %s", e)
                triton_span.set_attribute("error", True)
                triton_span.set_attribute("error.type", type(e).__name__)
                triton_span.set_attribute("error.message", str(e))
                if _OTEL_TRACING and Status is not None and StatusCode is not None:
                    triton_span.set_status(Status(StatusCode.ERROR, str(e)))
                triton_span.record_exception(e)
                triton_span.add_event(
                    "pipeline.task.invoke.failed",
                    {
                        "downstream": "tts",
                        "error_type": type(e).__name__,
                        "error_message": str(e),
                    },
                )
                raise

        error_msg = f"Unsupported task type: {task.taskType}"
        logger.error("%s", error_msg)
        triton_span.set_attribute("error", True)
        triton_span.set_attribute("error.message", error_msg)
        raise ValueError(error_msg)

    def _transform_output_for_next_task(
        self,
        task_type: TaskType,
        output: PipelineTaskOutput,
    ) -> Dict[str, Any]:
        """Transform task output to input format for next task."""
        output_dict = output.dict()
        output_dict.pop("config", None)

        if task_type == TaskType.ASR:
            logger.info("Transforming ASR output for next task")
            transformed: Dict[str, Any] = {"input": []}
            for item in output_dict.get("output", []):
                source_text = item.get("source", "")
                if not source_text or not source_text.strip():
                    error_msg = (
                        "ASR task produced empty transcription. "
                        "Cannot proceed to translation."
                    )
                    logger.error("%s: %s", error_msg, item)
                    if _OTEL_TRACING and otel_trace is not None:
                        current_span = otel_trace.get_current_span()
                        if current_span is not None:
                            current_span.set_attribute("error", True)
                            current_span.set_attribute("error.message", error_msg)
                    raise ValueError(error_msg)
                transformed["input"].append({"source": source_text})
            logger.info(
                "Transformed %s ASR outputs for translation",
                len(transformed["input"]),
            )
            return transformed

        if task_type == TaskType.TRANSLATION:
            logger.info("Transforming Translation output for next task")
            transformed = {"input": []}
            for item in output_dict.get("output", []):
                translated_text = item.get("target", "")
                if not translated_text or not translated_text.strip():
                    error_msg = (
                        "Translation task produced empty result. "
                        "Cannot proceed to TTS."
                    )
                    logger.error("%s: %s", error_msg, item)
                    if _OTEL_TRACING and otel_trace is not None:
                        current_span = otel_trace.get_current_span()
                        if current_span is not None:
                            current_span.set_attribute("error", True)
                            current_span.set_attribute("error.message", error_msg)
                    raise ValueError(error_msg)
                transformed["input"].append({"source": translated_text})
            logger.info(
                "Transformed %s translation outputs for TTS",
                len(transformed["input"]),
            )
            return transformed

        if task_type == TaskType.TTS:
            logger.info("TTS output passed through (final task)")
            return output_dict

        logger.warning("Unknown task type for transformation: %s", task_type)
        return output_dict
