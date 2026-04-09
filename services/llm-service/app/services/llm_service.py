"""
Core business logic for LLM inference.
"""

import logging
import time
from typing import Optional, List

from opentelemetry import trace
from opentelemetry.trace import Status, StatusCode

from app.schemas.inference import (
    LLMInferenceRequest,
    LLMInferenceResponse,
    LLMOutput,
)
from app.repositories.llm_repository import LLMRepository
from app.clients.triton_client import LLMTritonClient
from ai4icore_exceptions import TritonInferenceError

logger = logging.getLogger(__name__)
tracer = trace.get_tracer("llm-service")


class TextProcessingError(Exception):
    """Text processing error."""


class LLMService:
    """Main LLM service for inference."""

    SERVICE_REGISTRY = {
        "llm": "llm",
        "ai4bharat/llm": "llm",
        "default-llm": "llm",
    }

    def __init__(
        self,
        repository: LLMRepository,
        triton_client: LLMTritonClient,
        model_name: str = "llm",
    ):
        self.repository = repository
        self.triton_client = triton_client
        self.model_name = model_name

    def get_model_name(self, service_id: str) -> str:
        """Get model name based on service ID."""
        return self.SERVICE_REGISTRY.get(service_id, self.model_name)

    async def run_inference(
        self,
        request: LLMInferenceRequest,
        user_id: Optional[int] = None,
        api_key_id: Optional[int] = None,
        session_id: Optional[int] = None,
    ) -> LLMInferenceResponse:
        """Run LLM inference on the given request."""
        start_time = time.time()
        request_id = None

        with tracer.start_as_current_span("llm.process_batch") as span:
            try:
                service_id = request.config.serviceId
                input_lang = request.config.inputLanguage
                output_lang = request.config.outputLanguage

                model_name = self.get_model_name(service_id)

                span.set_attribute("llm.total_inputs", len(request.input))
                span.set_attribute("llm.service_id", service_id)
                span.set_attribute("llm.model_name", model_name)
                if input_lang:
                    span.set_attribute("llm.input_language", input_lang)
                if output_lang:
                    span.set_attribute("llm.output_language", output_lang)
                if user_id:
                    span.set_attribute("user.id", str(user_id))
                if api_key_id:
                    span.set_attribute("api_key.id", str(api_key_id))

                # Preprocess input texts
                with tracer.start_as_current_span("llm.preprocess_texts") as preprocess_span:
                    input_texts: List[str] = []
                    for text_input in request.input:
                        normalized = text_input.source.replace("\n", " ").strip() if text_input.source else " "
                        input_texts.append(normalized)
                    preprocess_span.set_attribute("llm.preprocessed_count", len(input_texts))

                # Create database request record
                total_text_length = sum(len(text) for text in input_texts)
                request_record = await self.repository.create_request(
                    model_id=service_id,
                    input_language=input_lang,
                    output_language=output_lang,
                    text_length=total_text_length,
                    user_id=user_id,
                    api_key_id=api_key_id,
                    session_id=session_id,
                )
                request_id = request_record.id

                # Process each input text
                results: List[LLMOutput] = []

                for i, input_text in enumerate(input_texts):
                    try:
                        response = await self.triton_client.send_triton_request(
                            model_name=model_name,
                            inputs=[input_text],
                            input_language=input_lang,
                            output_language=output_lang,
                        )

                        # Extract output text from response
                        outputs = response.get("outputs", [])
                        output_text = ""

                        for output in outputs:
                            if output.get("name") == "OUTPUT_TEXT":
                                data = output.get("data", [])
                                if data and len(data) > 0:
                                    if isinstance(data[0], list):
                                        if len(data[0]) > 0:
                                            output_text = str(data[0][0]) if not isinstance(data[0][0], bytes) else data[0][0].decode("utf-8")
                                    elif isinstance(data[0], bytes):
                                        output_text = data[0].decode("utf-8")
                                    else:
                                        output_text = str(data[0])
                                break

                        # Fallback: try any output
                        if not output_text and "outputs" in response:
                            for output in response["outputs"]:
                                data = output.get("data", [])
                                if data:
                                    if isinstance(data[0], list) and len(data[0]) > 0:
                                        output_text = str(data[0][0]) if not isinstance(data[0][0], bytes) else data[0][0].decode("utf-8")
                                    else:
                                        output_text = str(data[0]) if not isinstance(data[0], bytes) else data[0].decode("utf-8")

                        results.append(LLMOutput(source=input_text, target=output_text))

                    except Exception as e:
                        logger.error(f"LLM inference failed for text {i}: {e}")
                        results.append(LLMOutput(source=input_text, target=""))

                response = LLMInferenceResponse(output=results)

                # Database logging
                for result in results:
                    await self.repository.create_result(
                        request_id=request_id,
                        output_text=result.target,
                        source_text=result.source,
                    )

                # Update request status
                processing_time = time.time() - start_time
                await self.repository.update_request_status(
                    request_id=request_id,
                    status="completed",
                    processing_time=processing_time,
                )

                span.set_attribute("llm.processing_time_seconds", processing_time)
                span.set_attribute("llm.output_count", len(response.output))

                logger.info(f"LLM inference completed for request {request_id} in {processing_time:.2f}s")
                return response

            except Exception as e:
                span.set_attribute("error", True)
                span.set_attribute("error.type", type(e).__name__)
                span.set_attribute("error.message", str(e))
                span.set_status(Status(StatusCode.ERROR, str(e)))
                span.record_exception(e)
                logger.error(f"LLM inference failed: {e}")

                if request_id:
                    try:
                        await self.repository.update_request_status(
                            request_id=request_id,
                            status="failed",
                            error_message=str(e),
                        )
                    except Exception as update_error:
                        logger.error(f"Failed to update request status: {update_error}")

                # Check for static fallback on Triton-related errors
                is_triton_error = (
                    isinstance(e, TritonInferenceError)
                    or "triton" in str(e).lower()
                    or "connection" in str(e).lower()
                    or "timeout" in str(e).lower()
                )
                if isinstance(e, TritonInferenceError):
                    raise
                elif isinstance(e, TextProcessingError):
                    raise
                else:
                    raise TextProcessingError(f"LLM inference failed: {e}")
