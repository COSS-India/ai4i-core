"""
Core business logic for OCR inference.

This mirrors the behavior of Dhruva's /services/inference/ocr while fitting
into the microservice structure used by ASR/TTS/NMT in this repository.
"""

import base64
import logging
import time
from typing import List, Optional

import requests
from opentelemetry import trace
from opentelemetry.trace import Status, StatusCode

from models.ocr_request import OCRInferenceRequest, ImageInput
from models.ocr_response import OCRInferenceResponse, TextOutput
from repositories.ocr_repository import OCRRepository
from utils.triton_client import TritonClient, TritonInferenceError

logger = logging.getLogger(__name__)
# Use service name to get the same tracer instance as main.py
tracer = trace.get_tracer("ocr-service")


class OCRService:
    """
    OCR inference service.

    Responsibilities:
    - Take OCRInferenceRequest
    - For each image:
      - Resolve base64 content (direct or via imageUri download)
      - Call Triton (Surya OCR)
      - Map OCR model output to OCRInferenceResponse
    - Log requests and results to database
    """

    def __init__(self, repository: OCRRepository, triton_client: TritonClient, model_name: str):
        """
        Initialize OCR service.
        
        Args:
            repository: OCR repository for database operations
            triton_client: Triton client instance
            model_name: Model name (should be resolved by Model Management middleware)
        """
        self.repository = repository
        self.triton_client = triton_client
        self.model_name = model_name

    def _resolve_image_base64(self, image: ImageInput) -> Optional[str]:
        """
        Resolve an image into base64:

        - If imageContent is provided, use it directly
        - Else, download from imageUri and base64-encode it
        """
        if not tracer:
            # Fallback if tracing not available
            return self._resolve_image_base64_impl(image)
        
        with tracer.start_as_current_span("ocr.resolve_image") as span:
            if image.imageContent:
                span.set_attribute("ocr.image_source", "content")
                span.set_attribute("ocr.image_size_bytes", len(image.imageContent) if image.imageContent else 0)
                span.add_event("ocr.image.resolved", {"source": "content"})
                return image.imageContent

            if image.imageUri:
                span.set_attribute("ocr.image_source", "uri")
                span.set_attribute("ocr.image_uri", str(image.imageUri))
                try:
                    span.add_event("ocr.image.download.start", {"uri": str(image.imageUri)})
                    resp = requests.get(str(image.imageUri), timeout=30)
                    resp.raise_for_status()
                    image_bytes = base64.b64encode(resp.content).decode("utf-8")
                    span.set_attribute("ocr.image_size_bytes", len(image_bytes))
                    span.set_attribute("ocr.download_status", "success")
                    span.add_event("ocr.image.download.complete", {
                        "size_bytes": len(image_bytes),
                        "status": "success"
                    })
                    return image_bytes
                except Exception as exc:
                    # Don't set error: True - OpenTelemetry sets it automatically when status is ERROR
                    span.set_attribute("error.type", type(exc).__name__)
                    span.set_attribute("error.message", str(exc))
                    span.set_attribute("ocr.download_status", "failed")
                    span.set_status(Status(StatusCode.ERROR, str(exc)))
                    span.record_exception(exc)
                    logger.error(
                        "Failed to download image from %s: %s", image.imageUri, exc
                    )
                    return None

            # No content and no URI
            span.set_attribute("ocr.image_source", "none")
            span.set_attribute("error", True)
            span.set_attribute("error.message", "No image content or URI provided")
            return None

    def _resolve_image_base64_impl(self, image: ImageInput) -> Optional[str]:
        """Fallback implementation when tracing is not available."""
        if image.imageContent:
            return image.imageContent

        if image.imageUri:
            try:
                resp = requests.get(str(image.imageUri), timeout=30)
                resp.raise_for_status()
                return base64.b64encode(resp.content).decode("utf-8")
            except Exception as exc:
                logger.error(
                    "Failed to download image from %s: %s", image.imageUri, exc
                )
                return None

        return None

    async def run_inference(
        self, 
        request: OCRInferenceRequest,
        user_id: Optional[int] = None,
        api_key_id: Optional[int] = None,
        session_id: Optional[int] = None
    ) -> OCRInferenceResponse:
        """
        Async OCR inference entrypoint.
        
        Creates database request record, processes inference, logs results, and updates status.
        """
        if not tracer:
            # Fallback if tracing not available
            return await self._run_inference_impl(request, user_id, api_key_id, session_id)
        
        start_time = time.time()
        db_request = None
        
        with tracer.start_as_current_span("ocr.process_batch") as span:
            try:
                # Extract configuration
                service_id = request.config.serviceId
                language = request.config.language.sourceLanguage
                
                # Create database request record
                db_request = await self.repository.create_request(
                    model_id=service_id,
                    language=language,
                    image_count=len(request.image),
                    user_id=user_id,
                    api_key_id=api_key_id,
                    session_id=session_id
                )
                
                logger.info(f"Created OCR request {db_request.id} for {len(request.image)} image(s)")
                
                span.set_attribute("ocr.total_images", len(request.image))
                
                # Resolve all images to base64 first
                with tracer.start_as_current_span("ocr.resolve_images") as resolve_span:
                    images_b64: List[str] = []
                    resolved_count = 0
                    for idx, img in enumerate(request.image):
                        resolved = self._resolve_image_base64(img)
                        if not resolved:
                            images_b64.append("")
                        else:
                            images_b64.append(resolved)
                            resolved_count += 1
                    resolve_span.set_attribute("ocr.resolved_count", resolved_count)
                    resolve_span.set_attribute("ocr.failed_count", len(request.image) - resolved_count)

                # Call Triton in a single batch for all non-empty images
                outputs: List[TextOutput] = []
                try:
                    # For empty entries, we'll skip Triton and just return empty text
                    non_empty_indices = [i for i, v in enumerate(images_b64) if v]
                    non_empty_images = [images_b64[i] for i in non_empty_indices]

                    ocr_results: List[dict] = []
                    if non_empty_images:
                        with tracer.start_as_current_span("ocr.triton_batch") as triton_span:
                            triton_span.set_attribute("ocr.batch_size", len(non_empty_images))
                            triton_span.add_event("ocr.triton.batch.start", {"batch_size": len(non_empty_images)})
                            batch_results = self.triton_client.run_ocr_batch(non_empty_images)
                            ocr_results = batch_results
                            triton_span.set_attribute("ocr.results_count", len(ocr_results))
                            # Count successful results
                            success_count = sum(1 for r in ocr_results if r.get("success", False))
                            triton_span.set_attribute("ocr.success_count", success_count)
                            triton_span.add_event("ocr.triton.batch.complete", {
                                "results_count": len(ocr_results),
                                "success_count": success_count
                            })

                    # Map back to original indices
                    result_map = {idx: {} for idx in range(len(images_b64))}
                    for local_idx, global_idx in enumerate(non_empty_indices):
                        if local_idx < len(ocr_results):
                            result_map[global_idx] = ocr_results[local_idx] or {}
                except TritonInferenceError as exc:
                    span.set_attribute("error", True)
                    span.set_attribute("error.type", "TritonInferenceError")
                    span.set_attribute("error.message", str(exc))
                    span.record_exception(exc)
                    logger.error("OCR Triton inference failed: %s", exc)
                    # In case of a global Triton failure, return empty outputs
                    for _ in request.image:
                        outputs.append(TextOutput(source="", target=""))
                    # Update request status to failed
                    if db_request:
                        try:
                            await self.repository.update_request_status(
                                db_request.id, "failed", error_message=str(exc)
                            )
                        except Exception as update_error:
                            logger.error(f"Failed to update request status: {update_error}")
                    return OCRInferenceResponse(output=outputs, config=request.config.dict())

                # Build TextOutput list
                with tracer.start_as_current_span("ocr.build_response") as build_span:
                    successful_outputs = 0
                    for idx in range(len(request.image)):
                        ocr_result = result_map.get(idx, {})  # type: ignore[name-defined]
                        if not images_b64[idx] or not ocr_result or not ocr_result.get(
                            "success", False
                        ):
                            outputs.append(TextOutput(source="", target=""))
                            continue

                        full_text = ocr_result.get("full_text", "") or ""
                        outputs.append(TextOutput(source=full_text, target=""))
                        if full_text:
                            successful_outputs += 1
                    build_span.set_attribute("ocr.successful_outputs", successful_outputs)

                span.set_attribute("ocr.output_count", len(outputs))
                
                # Log results to database
                for output in outputs:
                    if output.source:  # Only log non-empty results
                        await self.repository.create_result(
                            request_id=db_request.id,
                            extracted_text=output.source,
                            page_count=1  # Each output represents one page/image
                        )
                
                # Update request status
                processing_time = time.time() - start_time
                await self.repository.update_request_status(
                    db_request.id, "completed", processing_time
                )
                
                logger.info(f"OCR inference completed in {processing_time:.2f}s")
                return OCRInferenceResponse(output=outputs, config=request.config.dict())
                
            except Exception as e:
                span.set_attribute("error", True)
                span.set_attribute("error.type", type(e).__name__)
                span.set_attribute("error.message", str(e))
                span.set_status(Status(StatusCode.ERROR, str(e)))
                span.record_exception(e)
                logger.error(f"OCR inference failed: {e}")
                
                # Update request status to failed
                if db_request:
                    try:
                        await self.repository.update_request_status(
                            db_request.id, "failed", error_message=str(e)
                        )
                    except Exception as update_error:
                        logger.error(f"Failed to update request status: {update_error}")
                
                raise

    async def _run_inference_impl(
        self, 
        request: OCRInferenceRequest,
        user_id: Optional[int] = None,
        api_key_id: Optional[int] = None,
        session_id: Optional[int] = None
    ) -> OCRInferenceResponse:
        """Fallback implementation when tracing is not available."""
        start_time = time.time()
        db_request = None
        
        try:
            # Extract configuration
            service_id = request.config.serviceId
            language = request.config.language.sourceLanguage
            
            # Create database request record
            db_request = await self.repository.create_request(
                model_id=service_id,
                language=language,
                image_count=len(request.image),
                user_id=user_id,
                api_key_id=api_key_id,
                session_id=session_id
            )
            
            logger.info(f"Created OCR request {db_request.id} for {len(request.image)} image(s)")
            
            # Resolve all images to base64 first
            images_b64: List[str] = []
            for img in request.image:
                resolved = self._resolve_image_base64_impl(img)
                if not resolved:
                    images_b64.append("")
                else:
                    images_b64.append(resolved)

            # Call Triton in a single batch for all non-empty images
            outputs: List[TextOutput] = []
            try:
                # For empty entries, we'll skip Triton and just return empty text
                non_empty_indices = [i for i, v in enumerate(images_b64) if v]
                non_empty_images = [images_b64[i] for i in non_empty_indices]

                ocr_results: List[dict] = []
                if non_empty_images:
                    batch_results = self.triton_client.run_ocr_batch(non_empty_images)
                    ocr_results = batch_results

                # Map back to original indices
                result_map = {idx: {} for idx in range(len(images_b64))}
                for local_idx, global_idx in enumerate(non_empty_indices):
                    if local_idx < len(ocr_results):
                        result_map[global_idx] = ocr_results[local_idx] or {}
            except TritonInferenceError as exc:
                logger.error("OCR Triton inference failed: %s", exc)
                # In case of a global Triton failure, return empty outputs
                for _ in request.image:
                    outputs.append(TextOutput(source="", target=""))
                return OCRInferenceResponse(output=outputs, config=request.config.dict())

            # Build TextOutput list
            for idx in range(len(request.image)):
                ocr_result = result_map.get(idx, {})  # type: ignore[name-defined]
                if not images_b64[idx] or not ocr_result or not ocr_result.get(
                    "success", False
                ):
                    outputs.append(TextOutput(source="", target=""))
                    continue

                full_text = ocr_result.get("full_text", "") or ""
                outputs.append(TextOutput(source=full_text, target=""))

            # Create response
            response = OCRInferenceResponse(output=outputs, config=request.config.dict())
            
            # Log results to database
            for output in outputs:
                if output.source:  # Only log non-empty results
                    await self.repository.create_result(
                        request_id=db_request.id,
                        extracted_text=output.source,
                        page_count=1  # Each output represents one page/image
                    )
            
            # Update request status
            processing_time = time.time() - start_time
            await self.repository.update_request_status(
                db_request.id, "completed", processing_time
            )
            
            logger.info(f"OCR inference completed in {processing_time:.2f}s")
            return response
            
        except Exception as e:
            logger.error(f"OCR inference failed: {e}")
            
            # Update request status to failed
            if db_request:
                try:
                    await self.repository.update_request_status(
                        db_request.id, "failed", error_message=str(e)
                    )
                except Exception as update_error:
                    logger.error(f"Failed to update request status: {update_error}")
            
            raise


