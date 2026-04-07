"""
Core business logic for OCR inference.
"""

import base64
import logging
import time
from typing import List, Optional

import requests
from opentelemetry import trace
from opentelemetry.trace import Status, StatusCode

from app.schemas.inference import (
    OCRInferenceRequest,
    OCRInferenceResponse,
    ImageInput,
    TextOutput,
)
from app.repositories.ocr_repository import OCRRepository
from app.clients.triton_client import OCRTritonClient
from ai4icore_exceptions import TritonInferenceError

logger = logging.getLogger(__name__)
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

    def __init__(self, repository: OCRRepository, triton_client: OCRTritonClient, model_name: str):
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

        OpenTelemetry's tracer.start_as_current_span() is a no-op when tracing isn't configured.
        """
        with tracer.start_as_current_span("ocr.resolve_image") as span:
            if image.imageContent:
                span.set_attribute("ocr.image_source", "content")
                return image.imageContent

            if image.imageUri:
                span.set_attribute("ocr.image_source", "uri")
                span.set_attribute("ocr.image_uri", str(image.imageUri))
                try:
                    resp = requests.get(str(image.imageUri), timeout=30)
                    resp.raise_for_status()
                    image_bytes = base64.b64encode(resp.content).decode("utf-8")
                    return image_bytes
                except Exception as exc:
                    span.set_attribute("error.type", type(exc).__name__)
                    span.set_attribute("error.message", str(exc))
                    span.set_status(Status(StatusCode.ERROR, str(exc)))
                    span.record_exception(exc)
                    logger.error(
                        "Failed to download image from %s: %s", image.imageUri, exc
                    )
                    return None

            span.set_attribute("ocr.image_source", "none")
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
        OpenTelemetry's tracer.start_as_current_span() is a no-op when tracing isn't configured.
        """
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
                span.set_attribute("ocr.service_id", service_id)
                span.set_attribute("ocr.language", language)
                span.set_attribute("ocr.model_name", self.model_name)

                if user_id:
                    span.set_attribute("user.id", str(user_id))
                if api_key_id:
                    span.set_attribute("api_key.id", str(api_key_id))
                if session_id:
                    span.set_attribute("session.id", str(session_id))

                # Resolve all images to base64 first
                with tracer.start_as_current_span("ocr.resolve_images") as resolve_span:
                    images_b64: List[str] = []
                    resolved_count = 0
                    for img in request.image:
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
                    non_empty_indices = [i for i, v in enumerate(images_b64) if v]
                    non_empty_images = [images_b64[i] for i in non_empty_indices]

                    ocr_results: List[dict] = []
                    if non_empty_images:
                        with tracer.start_as_current_span("ocr.triton_batch") as triton_span:
                            triton_span.set_attribute("ocr.batch_size", len(non_empty_images))
                            batch_results = self.triton_client.run_ocr_batch(non_empty_images)
                            ocr_results = batch_results
                            triton_span.set_attribute("ocr.results_count", len(ocr_results))

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
                    for _ in request.image:
                        outputs.append(TextOutput(source="", target=""))
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
                        ocr_result = result_map.get(idx, {})
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
                            page_count=1
                        )

                # Update request status
                processing_time = time.time() - start_time
                await self.repository.update_request_status(
                    db_request.id, "completed", processing_time
                )

                span.set_attribute("ocr.processing_time_seconds", processing_time)
                logger.info(f"OCR inference completed in {processing_time:.2f}s")
                return OCRInferenceResponse(output=outputs, config=request.config.dict())

            except Exception as e:
                span.set_attribute("error", True)
                span.set_attribute("error.type", type(e).__name__)
                span.set_attribute("error.message", str(e))
                span.set_status(Status(StatusCode.ERROR, str(e)))
                span.record_exception(e)
                logger.error(f"OCR inference failed: {e}")

                if db_request:
                    try:
                        await self.repository.update_request_status(
                            db_request.id, "failed", error_message=str(e)
                        )
                    except Exception as update_error:
                        logger.error(f"Failed to update request status: {update_error}")

                raise
