"""
Pipeline Service - Main orchestration logic

Handles the execution of multi-task AI pipelines (e.g., Speech-to-Speech translation).
Adapted from Dhruva-Platform-2 inference_service.py run_pipeline_inference method.
Includes distributed tracing for end-to-end observability.
"""

import logging
from copy import deepcopy
from typing import Dict, Any, List, Optional
from models.pipeline_request import PipelineInferenceRequest, TaskType, PipelineTask
from models.pipeline_response import PipelineInferenceResponse, PipelineTaskOutput
from utils.http_client import ServiceClient

# Import OpenTelemetry for manual span creation
try:
    from opentelemetry import trace
    TRACING_AVAILABLE = True
except ImportError:
    TRACING_AVAILABLE = False
    logging.warning("OpenTelemetry not available, manual tracing disabled")

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
        api_key: Optional[str] = None
    ) -> PipelineInferenceResponse:
        """
        Execute a multi-task AI pipeline.
        
        Args:
            request: Pipeline inference request with tasks and input data
            jwt_token: JWT token for authentication
            api_key: API key for authentication
            
        Returns:
            Pipeline inference response with outputs from each task
        """
        results = []
        previous_output = request.inputData.copy()
        
        logger.info(f"🚀 Starting pipeline with {len(request.pipelineTasks)} tasks")
        
        # Create a parent span for the entire pipeline if tracing is available
        if TRACING_AVAILABLE and tracer:
            with tracer.start_as_current_span(
                "pipeline.run_inference",
                attributes={
                    "pipeline.task_count": len(request.pipelineTasks),
                    "pipeline.tasks": ",".join([str(t.taskType) for t in request.pipelineTasks])
                }
            ):
                return await self._execute_pipeline_tasks(
                    request, results, previous_output, jwt_token, api_key
                )
        else:
            return await self._execute_pipeline_tasks(
                request, results, previous_output, jwt_token, api_key
            )
    
    async def _execute_pipeline_tasks(
        self,
        request: PipelineInferenceRequest,
        results: List[PipelineTaskOutput],
        previous_output: Dict[str, Any],
        jwt_token: Optional[str],
        api_key: Optional[str]
    ) -> PipelineInferenceResponse:
        """Execute all pipeline tasks in sequence."""
        # Execute each task in sequence
        for task_idx, pipeline_task in enumerate(request.pipelineTasks, start=1):
            logger.info(f"📋 Executing task {task_idx}/{len(request.pipelineTasks)}: {pipeline_task.taskType}")
            
            # Create a span for each task if tracing is available
            span_name = f"pipeline.task.{pipeline_task.taskType}"
            
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
                            control_config=request.controlConfig
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
                        control_config=request.controlConfig
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
                error_msg = f"Pipeline failed at task {task_idx} ({pipeline_task.taskType}): {str(e)}"
                logger.error(f"❌ Task {task_idx} ({pipeline_task.taskType}) failed: {e}")
                
                # Record error in span if tracing is available
                if TRACING_AVAILABLE and tracer:
                    current_span = trace.get_current_span()
                    if current_span:
                        current_span.set_attribute("task.status", "error")
                        current_span.set_attribute("error.message", str(e))
                        current_span.set_attribute("error.type", type(e).__name__)
                        current_span.record_exception(e)
                
                raise RuntimeError(error_msg) from e
        
        logger.info(f"✅ Pipeline completed successfully with {len(results)} tasks")
        
        return PipelineInferenceResponse(pipelineResponse=results)
    
    async def _execute_task(
        self,
        task: PipelineTask,
        input_data: Dict[str, Any],
        jwt_token: Optional[str] = None,
        api_key: Optional[str] = None,
        control_config: Optional[Dict[str, Any]] = None
    ) -> PipelineTaskOutput:
        """Execute a single pipeline task with distributed tracing."""
        
        if task.taskType == TaskType.ASR:
            # Construct ASR request
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
            
            logger.info(f"📝 ASR request constructed with {len(input_data.get('audio', []))} audio inputs")
            
            # Add span attributes for ASR request
            if TRACING_AVAILABLE:
                current_span = trace.get_current_span()
                if current_span:
                    current_span.set_attribute("asr.service_id", task.config.serviceId)
                    current_span.set_attribute("asr.audio_count", len(input_data.get("audio", [])))
            
            try:
                # Call ASR service
                response = await self.service_client.call_asr_service(asr_request, jwt_token=jwt_token, api_key=api_key)
                
                # Add response attributes to span
                if TRACING_AVAILABLE:
                    current_span = trace.get_current_span()
                    if current_span:
                        current_span.set_attribute("asr.output_count", len(response.get("output", [])))
                
                return PipelineTaskOutput(
                    taskType="asr",
                    serviceId=task.config.serviceId,
                    output=response.get("output", []),
                    config=response.get("config")
                )
            except Exception as e:
                logger.error(f"❌ ASR service call failed: {e}")
                if TRACING_AVAILABLE:
                    current_span = trace.get_current_span()
                    if current_span:
                        current_span.set_attribute("error", True)
                        current_span.record_exception(e)
                raise
        
        elif task.taskType == TaskType.TRANSLATION:
            # Construct NMT request
            nmt_request = {
                "input": input_data.get("input", []),
                "config": {
                    "serviceId": task.config.serviceId,
                    "language": task.config.language.dict()
                }
            }
            
            logger.info(f"📝 Translation request constructed with {len(input_data.get('input', []))} text inputs")
            
            # Add span attributes for NMT request
            if TRACING_AVAILABLE:
                current_span = trace.get_current_span()
                if current_span:
                    current_span.set_attribute("nmt.service_id", task.config.serviceId)
                    current_span.set_attribute("nmt.input_count", len(input_data.get("input", [])))
            
            try:
                # Call NMT service
                response = await self.service_client.call_nmt_service(nmt_request, jwt_token=jwt_token, api_key=api_key)
                
                # Add response attributes to span
                if TRACING_AVAILABLE:
                    current_span = trace.get_current_span()
                    if current_span:
                        current_span.set_attribute("nmt.output_count", len(response.get("output", [])))
                
                return PipelineTaskOutput(
                    taskType="translation",
                    serviceId=task.config.serviceId,
                    output=response.get("output", []),
                    config=None
                )
            except Exception as e:
                logger.error(f"❌ NMT service call failed: {e}")
                if TRACING_AVAILABLE:
                    current_span = trace.get_current_span()
                    if current_span:
                        current_span.set_attribute("error", True)
                        current_span.record_exception(e)
                raise
        
        elif task.taskType == TaskType.TTS:
            # Construct TTS request
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
            
            logger.info(f"📝 TTS request constructed with {len(input_data.get('input', []))} text inputs")
            
            # Add span attributes for TTS request
            if TRACING_AVAILABLE:
                current_span = trace.get_current_span()
                if current_span:
                    current_span.set_attribute("tts.service_id", task.config.serviceId)
                    current_span.set_attribute("tts.input_count", len(input_data.get("input", [])))
                    current_span.set_attribute("tts.gender", task.config.gender or "male")
                    current_span.set_attribute("tts.audio_format", task.config.audioFormat or "wav")
            
            try:
                # Call TTS service
                response = await self.service_client.call_tts_service(tts_request, jwt_token=jwt_token, api_key=api_key)
                
                # Add response attributes to span
                if TRACING_AVAILABLE:
                    current_span = trace.get_current_span()
                    if current_span:
                        current_span.set_attribute("tts.audio_count", len(response.get("audio", [])))
                
                logger.info(f"✅ TTS service returned {len(response.get('audio', []))} audio outputs")
                
                # TTS service returns audio in "audio" field, map to output
                return PipelineTaskOutput(
                    taskType="tts",
                    serviceId=task.config.serviceId,
                    output=response.get("audio", []),
                    audio=response.get("audio", []),
                    config=response.get("config")
                )
            except Exception as e:
                logger.error(f"❌ TTS service call failed: {e}")
                if TRACING_AVAILABLE:
                    current_span = trace.get_current_span()
                    if current_span:
                        current_span.set_attribute("error", True)
                        current_span.record_exception(e)
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
