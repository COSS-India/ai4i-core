"""
LLM Service
Main LLM service containing core inference logic
"""

import time
import logging
from typing import Optional, List
from uuid import UUID

from models.llm_request import LLMInferenceRequest
from models.llm_response import LLMInferenceResponse, LLMOutput
from repositories.llm_repository import LLMRepository
from utils.triton_client import TritonClient

logger = logging.getLogger(__name__)


class TritonInferenceError(Exception):
    """Triton inference error"""
    pass


class TextProcessingError(Exception):
    """Text processing error"""
    pass


class LLMService:
    """Main LLM service for inference"""
    
    def __init__(self, repository: LLMRepository, triton_client: TritonClient, resolved_model_name: Optional[str] = None):
        self.repository = repository
        self.triton_client = triton_client
        self.resolved_model_name = resolved_model_name  # Model name from Model Management
    
    def get_model_name(self, service_id: str) -> str:
        """Get model name resolved via Model Management (REQUIRED - no fallback)"""
        if not self.resolved_model_name:
            raise TritonInferenceError(
                f"Model name not resolved via Model Management for serviceId: {service_id}. "
                f"Please ensure the model is properly configured in Model Management database with inference endpoint schema."
            )
        return self.resolved_model_name
    
    async def run_inference(
        self,
        request: LLMInferenceRequest,
        user_id: Optional[int] = None,
        api_key_id: Optional[int] = None,
        session_id: Optional[int] = None
    ) -> LLMInferenceResponse:
        """Run LLM inference on the given request"""
        start_time = time.time()
        request_id = None
        
        try:
            # Extract configuration
            service_id = request.config.serviceId
            input_lang = request.config.inputLanguage
            output_lang = request.config.outputLanguage
            
            # Get model name
            model_name = self.get_model_name(service_id)
            
            # Preprocess input texts
            input_texts = []
            for text_input in request.input:
                # Normalize text: replace newlines with spaces, strip whitespace
                normalized_text = text_input.source.replace("\n", " ").strip() if text_input.source else " "
                input_texts.append(normalized_text)
            
            # Create database request record
            total_text_length = sum(len(text) for text in input_texts)
            request_record = await self.repository.create_request(
                model_id=service_id,
                input_language=input_lang,
                output_language=output_lang,
                text_length=total_text_length,
                user_id=user_id,
                api_key_id=api_key_id,
                session_id=session_id
            )
            request_id = request_record.id
            
            # Batch processing (process individually for now)
            results = []
            
            for i, input_text in enumerate(input_texts):
                try:
                    # Send Triton request for single text
                    response = await self.triton_client.send_triton_request(
                        model_name=model_name,
                        inputs=[input_text],
                        input_language=input_lang,
                        output_language=output_lang
                    )
                    
                    # Extract output text from response
                    # Response format from the curl example:
                    # {
                    #     "model_name": "llm",
                    #     "model_version": "1",
                    #     "outputs": [{"name": "OUTPUT_TEXT", "datatype": "BYTES", "shape": [1,1], "data": ["..."]}]
                    # }
                    outputs = response.get("outputs", [])
                    output_text = ""
                    
                    for output in outputs:
                        if output.get("name") == "OUTPUT_TEXT":
                            data = output.get("data", [])
                            if data and len(data) > 0:
                                # Handle different data structures
                                if isinstance(data[0], list):
                                    # Nested list structure [1,1] shape
                                    if len(data[0]) > 0:
                                        output_text = str(data[0][0]) if not isinstance(data[0][0], bytes) else data[0][0].decode("utf-8")
                                elif isinstance(data[0], bytes):
                                    output_text = data[0].decode("utf-8")
                                else:
                                    output_text = str(data[0])
                            break
                    
                    # If no output found in expected format, try alternative
                    if not output_text and "outputs" in response:
                        # Try to extract from any output
                        for output in response["outputs"]:
                            data = output.get("data", [])
                            if data:
                                if isinstance(data[0], list) and len(data[0]) > 0:
                                    output_text = str(data[0][0]) if not isinstance(data[0][0], bytes) else data[0][0].decode("utf-8")
                                else:
                                    output_text = str(data[0]) if not isinstance(data[0], bytes) else data[0].decode("utf-8")
                    
                    results.append(LLMOutput(
                        source=input_text,
                        target=output_text
                    ))
                    
                except Exception as e:
                    logger.error(f"LLM inference failed for text {i}: {e}")
                    # Add error result
                    results.append(LLMOutput(
                        source=input_text,
                        target=""
                    ))
            
            # Create response
            response = LLMInferenceResponse(output=results)
            
            # Database logging
            for result in results:
                await self.repository.create_result(
                    request_id=request_id,
                    output_text=result.target,
                    source_text=result.source
                )
            
            # Update request status
            processing_time = time.time() - start_time
            await self.repository.update_request_status(
                request_id=request_id,
                status="completed",
                processing_time=processing_time
            )
            
            logger.info(f"LLM inference completed for request {request_id} in {processing_time:.2f}s")
            return response
            
        except Exception as e:
            logger.error(f"LLM inference failed: {e}")
            
            # Update request status to failed
            if request_id:
                try:
                    await self.repository.update_request_status(
                        request_id=request_id,
                        status="failed",
                        error_message=str(e)
                    )
                except Exception as update_error:
                    logger.error(f"Failed to update request status: {update_error}")
            
            # Re-raise with appropriate error type
            if isinstance(e, TritonInferenceError):
                raise
            elif isinstance(e, TextProcessingError):
                raise
            else:
                raise TextProcessingError(f"LLM inference failed: {e}")

