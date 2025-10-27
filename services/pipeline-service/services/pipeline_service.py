"""
Pipeline Service - Main orchestration logic

Handles the execution of multi-task AI pipelines (e.g., Speech-to-Speech translation).
Adapted from Dhruva-Platform-2 inference_service.py run_pipeline_inference method.
"""

import logging
from copy import deepcopy
from typing import Dict, Any, List, Optional
from models.pipeline_request import PipelineInferenceRequest, TaskType, PipelineTask
from models.pipeline_response import PipelineInferenceResponse, PipelineTaskOutput
from utils.http_client import ServiceClient

logger = logging.getLogger(__name__)


class PipelineService:
    """Service for orchestrating AI pipeline tasks."""
    
    def __init__(self, service_client: ServiceClient):
        """Initialize pipeline service with service client."""
        self.service_client = service_client
    
    async def run_pipeline_inference(
        self,
        request: PipelineInferenceRequest,
        api_key: Optional[str] = None
    ) -> PipelineInferenceResponse:
        """
        Execute a multi-task AI pipeline.
        
        Args:
            request: Pipeline inference request with tasks and input data
            api_key: API key for authentication
            
        Returns:
            Pipeline inference response with outputs from each task
        """
        results = []
        previous_output = request.inputData.copy()
        
        logger.info(f"Starting pipeline with {len(request.pipelineTasks)} tasks")
        
        # Execute each task in sequence
        for task_idx, pipeline_task in enumerate(request.pipelineTasks, start=1):
            logger.info(f"Executing task {task_idx}/{len(request.pipelineTasks)}: {pipeline_task.taskType}")
            
            try:
                # Call the appropriate service based on task type
                task_output = await self._execute_task(
                    task=pipeline_task,
                    input_data=previous_output,
                    api_key=api_key
                )
                
                # Store result
                results.append(task_output)
                
                # Transform output for next task
                previous_output = self._transform_output_for_next_task(
                    task_type=pipeline_task.taskType,
                    output=task_output
                )
                
                logger.info(f"Task {task_idx} completed successfully")
                
            except Exception as e:
                logger.error(f"Task {task_idx} ({pipeline_task.taskType}) failed: {e}")
                raise RuntimeError(f"Pipeline failed at task {task_idx} ({pipeline_task.taskType}): {str(e)}") from e
        
        logger.info(f"Pipeline completed successfully with {len(results)} tasks")
        
        return PipelineInferenceResponse(pipelineResponse=results)
    
    async def _execute_task(
        self,
        task: PipelineTask,
        input_data: Dict[str, Any],
        api_key: Optional[str] = None
    ) -> PipelineTaskOutput:
        """Execute a single pipeline task."""
        
        if task.taskType == TaskType.ASR:
            # Construct ASR request
            asr_request = {
                "audio": input_data.get("audio", []),
                "config": {
                    "serviceId": task.config.serviceId,
                    "language": task.config.language.dict(),
                    "audioFormat": task.config.audioFormat,
                    "preProcessors": task.config.preProcessors,
                    "postProcessors": task.config.postProcessors,
                    "transcriptionFormat": task.config.transcriptionFormat or "transcript"
                }
            }
            
            # Call ASR service
            response = await self.service_client.call_asr_service(asr_request, api_key)
            
            return PipelineTaskOutput(
                taskType="asr",
                serviceId=task.config.serviceId,
                output=response.get("output", []),
                config=response.get("config")
            )
        
        elif task.taskType == TaskType.TRANSLATION:
            # Construct NMT request
            nmt_request = {
                "input": input_data.get("input", []),
                "config": {
                    "serviceId": task.config.serviceId,
                    "language": task.config.language.dict()
                }
            }
            
            # Call NMT service
            response = await self.service_client.call_nmt_service(nmt_request, api_key)
            
            return PipelineTaskOutput(
                taskType="translation",
                serviceId=task.config.serviceId,
                output=response.get("output", []),
                config=None
            )
        
        elif task.taskType == TaskType.TTS:
            # Construct TTS request
            tts_request = {
                "input": input_data.get("input", []),
                "config": {
                    "serviceId": task.config.serviceId,
                    "language": task.config.language.dict(),
                    "gender": task.config.gender or "male",
                    "audioFormat": task.config.audioFormat or "wav",
                    "encoding": "base64"
                }
            }
            
            # Call TTS service
            response = await self.service_client.call_tts_service(tts_request, api_key)
            
            return PipelineTaskOutput(
                taskType="tts",
                serviceId=task.config.serviceId,
                output=response.get("audio", []),
                config=response.get("config")
            )
        
        else:
            raise ValueError(f"Unsupported task type: {task.taskType}")
    
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
            logger.info(f"Transforming ASR output for next task. Output: {output_dict}")
            transformed = {
                "input": []
            }
            for item in output_dict.get("output", []):
                source_text = item.get("source", "")
                if not source_text or not source_text.strip():
                    logger.warning(f"Empty or missing source in ASR output: {item}")
                    raise ValueError("ASR task produced empty transcription. Cannot proceed to translation.")
                transformed["input"].append({
                    "source": source_text
                })
            logger.info(f"Transformed input for translation: {transformed}")
            return transformed
        
        elif task_type == TaskType.TRANSLATION:
            # Translation output goes to TTS input
            # Transform: output -> input, target -> source (use translated as source for TTS)
            logger.info(f"Transforming Translation output for next task. Output: {output_dict}")
            transformed = {
                "input": []
            }
            for item in output_dict.get("output", []):
                translated_text = item.get("target", "")
                if not translated_text or not translated_text.strip():
                    logger.warning(f"Empty or missing target in Translation output: {item}")
                    raise ValueError("Translation task produced empty result. Cannot proceed to TTS.")
                transformed["input"].append({
                    "source": translated_text
                })
            logger.info(f"Transformed input for TTS: {transformed}")
            return transformed
        
        elif task_type == TaskType.TTS:
            # TTS is typically the final task
            # Return as-is (or process if needed)
            return output_dict
        
        else:
            return output_dict
