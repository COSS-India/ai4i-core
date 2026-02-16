"""
Pipeline Service - Main orchestration logic

Handles the execution of multi-task AI pipelines (e.g., Speech-to-Speech translation).
Adapted from Dhruva-Platform-2 inference_service.py run_pipeline_inference method.
Includes distributed tracing for end-to-end observability.
"""

import logging
import json
import re
from copy import deepcopy
from typing import Dict, Any, List, Optional
from models.pipeline_request import PipelineInferenceRequest, TaskType, PipelineTask
from models.pipeline_response import PipelineInferenceResponse, PipelineTaskOutput
from utils.http_client import ServiceClient
from middleware.exceptions import (
    PipelineTaskError, 
    ServiceUnavailableError, 
    ModelNotFoundError,
    PipelineError
)

# Import OpenTelemetry for manual span creation
try:
    from opentelemetry import trace
    from opentelemetry.trace import Status, StatusCode
    TRACING_AVAILABLE = True
except ImportError:
    TRACING_AVAILABLE = False
    logging.warning("OpenTelemetry not available, manual tracing disabled")
    # Create dummy classes for when tracing is not available
    class Status:
        def __init__(self, code, description=None):
            self.code = code
            self.description = description
    class StatusCode:
        ERROR = "ERROR"
        OK = "OK"

logger = logging.getLogger(__name__)

# Get tracer for manual span creation
if TRACING_AVAILABLE:
    tracer = trace.get_tracer(__name__)
else:
    tracer = None


class PipelineService:
    """Service for orchestrating AI pipeline tasks."""
    
    def __init__(self, service_client: ServiceClient):
        """Initialize pipeline service with service client."""
        self.service_client = service_client
    
    async def run_pipeline_inference(
        self,
        request: PipelineInferenceRequest,
        jwt_token: Optional[str] = None,
        api_key: Optional[str] = None,
        user_id: Optional[int] = None
    ) -> PipelineInferenceResponse:
        """
        Execute a multi-task AI pipeline.
        
        Args:
            request: Pipeline inference request with tasks and input data
            jwt_token: JWT token for authentication
            api_key: API key for authentication
            user_id: User ID for tenant routing in downstream services
            
        Returns:
            Pipeline inference response with outputs from each task
        """
        results = []
        previous_output = request.inputData.copy()
        
        logger.info(f"🚀 Starting pipeline with {len(request.pipelineTasks)} tasks")
        
        # Create a parent span for the entire pipeline if tracing is available
        if TRACING_AVAILABLE and tracer:
            # Create readable task names for the span
            task_names = []
            for t in request.pipelineTasks:
                task_name = str(t.taskType).upper()
                if task_name == "TRANSLATION":
                    task_name = "NMT"
                task_names.append(task_name)
            
            with tracer.start_as_current_span(
                f"Pipeline: {' → '.join(task_names)}",
                attributes={
                    "pipeline.task_count": len(request.pipelineTasks),
                    "pipeline.tasks": ",".join(task_names)
                }
            ):
                return await self._execute_pipeline_tasks(
                    request, results, previous_output, jwt_token, api_key, user_id
                )
        else:
            return await self._execute_pipeline_tasks(
                request, results, previous_output, jwt_token, api_key, user_id
            )
    
    async def _execute_pipeline_tasks(
        self,
        request: PipelineInferenceRequest,
        results: List[PipelineTaskOutput],
        previous_output: Dict[str, Any],
        jwt_token: Optional[str],
        api_key: Optional[str],
        user_id: Optional[int] = None
    ) -> PipelineInferenceResponse:
        """Execute all pipeline tasks in sequence."""
        # Execute each task in sequence
        for task_idx, pipeline_task in enumerate(request.pipelineTasks, start=1):
            logger.info(f"📋 Executing task {task_idx}/{len(request.pipelineTasks)}: {pipeline_task.taskType}")
            
            # Create a span for each task if tracing is available
            # Use clear names like "ASR Task", "NMT Task", "TTS Task"
            task_type_name = str(pipeline_task.taskType).upper()
            if task_type_name == "TRANSLATION":
                task_type_name = "NMT"
            span_name = f"{task_type_name} Task"
            
            try:
                if TRACING_AVAILABLE and tracer:
                    with tracer.start_as_current_span(
                        span_name,
                        attributes={
                            "task.index": task_idx,
                            "task.type": str(pipeline_task.taskType),
                            "task.service_id": pipeline_task.config.serviceId,
                            "task.language": str(pipeline_task.config.language.dict()) if pipeline_task.config.language else "unknown"
                        }
                    ) as span:
                        # Call the appropriate service based on task type
                        task_output = await self._execute_task(
                            task=pipeline_task,
                            input_data=previous_output,
                            jwt_token=jwt_token,
                            api_key=api_key,
                            control_config=request.controlConfig,
                            user_id=user_id
                        )
                        
                        # Add success attributes to span
                        span.set_attribute("task.status", "success")
                        span.set_attribute("task.output_count", len(task_output.output) if task_output.output else 0)
                else:
                    # No tracing available, execute directly
                    task_output = await self._execute_task(
                        task=pipeline_task,
                        input_data=previous_output,
                        jwt_token=jwt_token,
                        api_key=api_key,
                        control_config=request.controlConfig,
                        user_id=user_id
                    )
                
                # Store result
                results.append(task_output)
                
                # Transform output for next task
                previous_output = self._transform_output_for_next_task(
                    task_type=pipeline_task.taskType,
                    output=task_output
                )
                
                logger.info(f"✅ Task {task_idx} completed successfully")
                
            except Exception as e:
                # Parse structured error if available
                error_info = self._parse_error(e, task_idx, pipeline_task.taskType)
                
                error_msg = error_info["message"]
                error_code = error_info["code"]
                service_error = error_info.get("service_error")
                
                logger.error(f"❌ Task {task_idx} ({pipeline_task.taskType}) failed: {error_msg}")
                
                # Record detailed error in span if tracing is available
                if TRACING_AVAILABLE and tracer:
                    current_span = trace.get_current_span()
                    if current_span:
                        current_span.set_attribute("task.status", "error")
                        current_span.set_attribute("error", True)
                        current_span.set_attribute("error.message", error_msg)
                        current_span.set_attribute("error.code", error_code)
                        current_span.set_attribute("error.type", type(e).__name__)
                        current_span.set_attribute("task.index", task_idx)
                        current_span.set_attribute("task.type", str(pipeline_task.taskType))
                        current_span.set_attribute("task.service_id", pipeline_task.config.serviceId)
                        
                        # Add service error details if available
                        if service_error:
                            if "model" in service_error:
                                current_span.set_attribute("error.model", service_error["model"])
                            if "service" in service_error:
                                current_span.set_attribute("error.service", service_error["service"])
                            if "status_code" in service_error:
                                current_span.set_attribute("error.service_status_code", service_error["status_code"])
                        
                        # Add error event for better visibility in Jaeger
                        current_span.add_event("pipeline.task.failed", {
                            "task_index": task_idx,
                            "task_type": str(pipeline_task.taskType),
                            "error_code": error_code,
                            "error_message": error_msg
                        })
                        
                        current_span.record_exception(e)
                        current_span.set_status(Status(StatusCode.ERROR, error_msg))
                
                # Raise appropriate error type
                if error_code == "MODEL_NOT_FOUND":
                    raise ModelNotFoundError(
                        message=error_msg,
                        model_name=service_error.get("model", "unknown") if service_error else "unknown",
                        service_name=service_error.get("service", "unknown") if service_error else "unknown"
                    )
                elif error_code == "SERVICE_UNAVAILABLE":
                    raise ServiceUnavailableError(
                        message=error_msg,
                        service_name=service_error.get("service", "unknown") if service_error else "unknown"
                    )
                else:
                    raise PipelineTaskError(
                        message=error_msg,
                        task_index=task_idx,
                        task_type=str(pipeline_task.taskType),
                        service_error=service_error,
                        error_code=error_code
                    )
        
        logger.info(f"✅ Pipeline completed successfully with {len(results)} tasks")
        
        return PipelineInferenceResponse(pipelineResponse=results)
    
    def _parse_error(self, error: Exception, task_index: int, task_type: TaskType) -> Dict[str, Any]:
        """
        Parse error to extract meaningful information and determine error code.
        
        Returns:
            Dict with message, code, and service_error details
        """
        error_str = str(error)
        error_code = "PIPELINE_TASK_ERROR"
        service_error = {}
        
        # Try to parse structured error from HTTP client
        try:
            # Check if error message is a JSON string (from HTTP client)
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
                        **details
                    }
                    
                    # Extract model name from error message if present
                    model_match = re.search(r"model[:\s]+['\"]?([^'\"]+)['\"]?", message, re.IGNORECASE)
                    if model_match:
                        service_error["model"] = model_match.group(1)
                    
                    # Determine error code based on message content
                    message_lower = message.lower()
                    if "not found" in message_lower or "404" in message_lower:
                        if "model" in message_lower:
                            error_code = "MODEL_NOT_FOUND"
                        else:
                            error_code = "SERVICE_NOT_FOUND"
                    elif "timeout" in message_lower or "timed out" in message_lower:
                        error_code = "SERVICE_TIMEOUT"
                    elif "connection" in message_lower or "unreachable" in message_lower:
                        error_code = "SERVICE_UNAVAILABLE"
                    elif status_code == 503:
                        error_code = "SERVICE_UNAVAILABLE"
                    elif status_code == 404:
                        error_code = "MODEL_NOT_FOUND"
                    
                    # Build user-friendly message
                    if error_code == "MODEL_NOT_FOUND":
                        model_name = service_error.get("model", "unknown")
                        user_message = f"Model '{model_name}' not found in {service_name} service. Please verify the model name and ensure it is loaded in the Triton inference server."
                    elif error_code == "SERVICE_UNAVAILABLE":
                        user_message = f"{service_name} service is unavailable. The service may be down or unreachable."
                    elif error_code == "SERVICE_TIMEOUT":
                        user_message = f"{service_name} service request timed out. The service may be overloaded."
                    else:
                        user_message = f"{service_name} service error: {message}"
                    
                    return {
                        "message": user_message,
                        "code": error_code,
                        "service_error": service_error
                    }
        except (json.JSONDecodeError, ValueError, KeyError):
            # Not a structured error, parse from string
            pass
        
        # Parse error message for common patterns
        error_lower = error_str.lower()
        
        # Check for model not found errors
        model_match = re.search(r"model[:\s]+['\"]?([^'\"]+)['\"]?\s+is\s+not\s+found", error_str, re.IGNORECASE)
        if model_match:
            model_name = model_match.group(1)
            service_error["model"] = model_name
            error_code = "MODEL_NOT_FOUND"
            return {
                "message": f"Model '{model_name}' not found. Please verify the model name and ensure it is loaded in the Triton inference server.",
                "code": error_code,
                "service_error": service_error
            }
        
        # Check for service unavailable
        if "connection" in error_lower or "unreachable" in error_lower or "timeout" in error_lower:
            error_code = "SERVICE_UNAVAILABLE"
            return {
                "message": f"Service unavailable: {error_str}",
                "code": error_code,
                "service_error": service_error
            }
        
        # Default: return original error message
        return {
            "message": f"Pipeline task failed: {error_str}",
            "code": error_code,
            "service_error": service_error
        }
    
    async def _execute_task(
        self,
        task: PipelineTask,
        input_data: Dict[str, Any],
        jwt_token: Optional[str] = None,
        api_key: Optional[str] = None,
        control_config: Optional[Dict[str, Any]] = None,
        user_id: Optional[int] = None
    ) -> PipelineTaskOutput:
        """Execute a single pipeline task with distributed tracing."""
        
        if task.taskType == TaskType.ASR:
            # Construct ASR request with detailed tracing
            with tracer.start_as_current_span("pipeline.construct_asr_request") as construct_span:
                asr_config = {
                    "serviceId": task.config.serviceId,
                    "language": task.config.language.dict(),
                }
                
                # Add optional ASR config fields
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
                    "config": asr_config
                }
                
                # Add controlConfig if present
                if control_config:
                    asr_request["controlConfig"] = control_config
                
                audio_count = len(input_data.get("audio", []))
                construct_span.set_attribute("asr.service_id", task.config.serviceId)
                construct_span.set_attribute("asr.audio_count", audio_count)
                if task.config.audioFormat:
                    construct_span.set_attribute("asr.audio_format", task.config.audioFormat)
                if task.config.transcriptionFormat:
                    construct_span.set_attribute("asr.transcription_format", task.config.transcriptionFormat)
                
                logger.info(f"📝 ASR request constructed with {audio_count} audio inputs")
            
            try:
                # Call ASR service with tracing
                with tracer.start_as_current_span("pipeline.call_asr_service") as call_span:
                    call_span.set_attribute("asr.service_id", task.config.serviceId)
                    call_span.add_event("asr.request.started")
                    
                    response = await self.service_client.call_asr_service(asr_request, jwt_token=jwt_token, api_key=api_key, user_id=user_id)
                    
                    output_count = len(response.get("output", []))
                    call_span.set_attribute("asr.output_count", output_count)
                    call_span.add_event("asr.request.completed", {
                        "output_count": output_count
                    })
                
                # Process response with tracing
                with tracer.start_as_current_span("pipeline.process_asr_response") as process_span:
                    process_span.set_attribute("asr.output_count", output_count)
                    
                    result = PipelineTaskOutput(
                        taskType="asr",
                        serviceId=task.config.serviceId,
                        output=response.get("output", []),
                        config=response.get("config")
                    )
                    
                    process_span.add_event("asr.response.processed")
                    return result
                    
            except Exception as e:
                logger.error(f"❌ ASR service call failed: {e}")
                if TRACING_AVAILABLE:
                    current_span = trace.get_current_span()
                    if current_span:
                        current_span.set_attribute("error", True)
                        current_span.set_attribute("error.type", type(e).__name__)
                        current_span.set_attribute("error.message", str(e))
                        current_span.set_status(Status(StatusCode.ERROR, str(e)))
                        current_span.record_exception(e)
                        current_span.add_event("asr.request.failed", {
                            "error_type": type(e).__name__,
                            "error_message": str(e)
                        })
                raise
        
        elif task.taskType == TaskType.TRANSLATION:
            # Construct NMT request with detailed tracing
            with tracer.start_as_current_span("pipeline.construct_nmt_request") as construct_span:
                nmt_request = {
                    "input": input_data.get("input", []),
                    "config": {
                        "serviceId": task.config.serviceId,
                        "language": task.config.language.dict()
                    }
                }
                
                input_count = len(input_data.get("input", []))
                construct_span.set_attribute("nmt.service_id", task.config.serviceId)
                construct_span.set_attribute("nmt.input_count", input_count)
                
                # Add language details to span
                lang_config = task.config.language.dict()
                if "sourceLanguage" in lang_config:
                    construct_span.set_attribute("nmt.source_language", lang_config["sourceLanguage"])
                if "targetLanguage" in lang_config:
                    construct_span.set_attribute("nmt.target_language", lang_config["targetLanguage"])
                if "sourceScriptCode" in lang_config:
                    construct_span.set_attribute("nmt.source_script_code", lang_config["sourceScriptCode"])
                if "targetScriptCode" in lang_config:
                    construct_span.set_attribute("nmt.target_script_code", lang_config["targetScriptCode"])
                
                logger.info(f"📝 Translation request constructed with {input_count} text inputs")
            
            try:
                # Call NMT service with tracing
                with tracer.start_as_current_span("pipeline.call_nmt_service") as call_span:
                    call_span.set_attribute("nmt.service_id", task.config.serviceId)
                    call_span.add_event("nmt.request.started")
                    
                    response = await self.service_client.call_nmt_service(nmt_request, jwt_token=jwt_token, api_key=api_key, user_id=user_id)
                    
                    output_count = len(response.get("output", []))
                    call_span.set_attribute("nmt.output_count", output_count)
                    call_span.add_event("nmt.request.completed", {
                        "output_count": output_count
                    })
                
                # Process response with tracing
                with tracer.start_as_current_span("pipeline.process_nmt_response") as process_span:
                    process_span.set_attribute("nmt.output_count", output_count)
                    
                    result = PipelineTaskOutput(
                        taskType="translation",
                        serviceId=task.config.serviceId,
                        output=response.get("output", []),
                        config=None
                    )
                    
                    process_span.add_event("nmt.response.processed")
                    return result
                    
            except Exception as e:
                logger.error(f"❌ NMT service call failed: {e}")
                if TRACING_AVAILABLE:
                    current_span = trace.get_current_span()
                    if current_span:
                        current_span.set_attribute("error", True)
                        current_span.set_attribute("error.type", type(e).__name__)
                        current_span.set_attribute("error.message", str(e))
                        current_span.set_status(Status(StatusCode.ERROR, str(e)))
                        current_span.record_exception(e)
                        current_span.add_event("nmt.request.failed", {
                            "error_type": type(e).__name__,
                            "error_message": str(e)
                        })
                raise
        
        elif task.taskType == TaskType.TTS:
            # Construct TTS request with detailed tracing
            with tracer.start_as_current_span("pipeline.construct_tts_request") as construct_span:
                tts_request = {
                    "input": input_data.get("input", []),
                    "config": {
                        "serviceId": task.config.serviceId,
                        "language": task.config.language.dict(),
                        "gender": task.config.gender or "male",
                        "audioFormat": task.config.audioFormat or "wav",
                        "samplingRate": 22050,
                        "encoding": "base64"
                    }
                }
                
                input_count = len(input_data.get("input", []))
                construct_span.set_attribute("tts.service_id", task.config.serviceId)
                construct_span.set_attribute("tts.input_count", input_count)
                construct_span.set_attribute("tts.gender", task.config.gender or "male")
                construct_span.set_attribute("tts.audio_format", task.config.audioFormat or "wav")
                construct_span.set_attribute("tts.sampling_rate", 22050)
                construct_span.set_attribute("tts.encoding", "base64")
                
                # Add language details
                lang_config = task.config.language.dict()
                if "sourceLanguage" in lang_config:
                    construct_span.set_attribute("tts.language", lang_config["sourceLanguage"])
                
                logger.info(f"📝 TTS request constructed with {input_count} text inputs")
            
            try:
                # Call TTS service with tracing
                with tracer.start_as_current_span("pipeline.call_tts_service") as call_span:
                    call_span.set_attribute("tts.service_id", task.config.serviceId)
                    call_span.add_event("tts.request.started")
                    
                    response = await self.service_client.call_tts_service(tts_request, jwt_token=jwt_token, api_key=api_key, user_id=user_id)
                    
                    audio_count = len(response.get("audio", []))
                    call_span.set_attribute("tts.audio_count", audio_count)
                    call_span.add_event("tts.request.completed", {
                        "audio_count": audio_count
                    })
                
                # Process response with tracing
                with tracer.start_as_current_span("pipeline.process_tts_response") as process_span:
                    audio_count = len(response.get("audio", []))
                    process_span.set_attribute("tts.audio_count", audio_count)
                    
                    logger.info(f"✅ TTS service returned {audio_count} audio outputs")
                    
                    # TTS service returns audio in "audio" field, map to output
                    result = PipelineTaskOutput(
                        taskType="tts",
                        serviceId=task.config.serviceId,
                        output=response.get("audio", []),
                        audio=response.get("audio", []),
                        config=response.get("config")
                    )
                    
                    process_span.add_event("tts.response.processed")
                    return result
                    
            except Exception as e:
                logger.error(f"❌ TTS service call failed: {e}")
                if TRACING_AVAILABLE:
                    current_span = trace.get_current_span()
                    if current_span:
                        current_span.set_attribute("error", True)
                        current_span.set_attribute("error.type", type(e).__name__)
                        current_span.set_attribute("error.message", str(e))
                        current_span.set_status(Status(StatusCode.ERROR, str(e)))
                        current_span.record_exception(e)
                        current_span.add_event("tts.request.failed", {
                            "error_type": type(e).__name__,
                            "error_message": str(e)
                        })
                raise
        
        else:
            error_msg = f"Unsupported task type: {task.taskType}"
            logger.error(f"❌ {error_msg}")
            if TRACING_AVAILABLE:
                current_span = trace.get_current_span()
                if current_span:
                    current_span.set_attribute("error", True)
                    current_span.set_attribute("error.message", error_msg)
            raise ValueError(error_msg)
    
    def _transform_output_for_next_task(
        self,
        task_type: TaskType,
        output: PipelineTaskOutput
    ) -> Dict[str, Any]:
        """
        Transform task output to input format for next task.
        
        Adapted from Dhruva-Platform-2 inference_service.py logic.
        """
        output_dict = output.dict()
        
        # Remove config from previous output
        output_dict.pop("config", None)
        
        # Transform based on task type
        if task_type == TaskType.ASR:
            # ASR output goes to Translation input
            # Transform: output -> input, source -> source
            logger.info(f"🔄 Transforming ASR output for next task")
            transformed = {
                "input": []
            }
            for item in output_dict.get("output", []):
                source_text = item.get("source", "")
                if not source_text or not source_text.strip():
                    error_msg = "ASR task produced empty transcription. Cannot proceed to translation."
                    logger.error(f"❌ {error_msg}: {item}")
                    if TRACING_AVAILABLE:
                        current_span = trace.get_current_span()
                        if current_span:
                            current_span.set_attribute("error", True)
                            current_span.set_attribute("error.message", error_msg)
                    raise ValueError(error_msg)
                transformed["input"].append({
                    "source": source_text
                })
            logger.info(f"✅ Transformed {len(transformed['input'])} ASR outputs for translation")
            return transformed
        
        elif task_type == TaskType.TRANSLATION:
            # Translation output goes to TTS input
            # Transform: output -> input, target -> source (use translated as source for TTS)
            logger.info(f"🔄 Transforming Translation output for next task")
            transformed = {
                "input": []
            }
            for item in output_dict.get("output", []):
                translated_text = item.get("target", "")
                if not translated_text or not translated_text.strip():
                    error_msg = "Translation task produced empty result. Cannot proceed to TTS."
                    logger.error(f"❌ {error_msg}: {item}")
                    if TRACING_AVAILABLE:
                        current_span = trace.get_current_span()
                        if current_span:
                            current_span.set_attribute("error", True)
                            current_span.set_attribute("error.message", error_msg)
                    raise ValueError(error_msg)
                transformed["input"].append({
                    "source": translated_text
                })
            logger.info(f"✅ Transformed {len(transformed['input'])} translation outputs for TTS")
            return transformed
        
        elif task_type == TaskType.TTS:
            # TTS is typically the final task
            # Return as-is (or process if needed)
            logger.info(f"🔄 TTS output passed through (final task)")
            return output_dict
        
        else:
            logger.warning(f"⚠️ Unknown task type for transformation: {task_type}")
            return output_dict
