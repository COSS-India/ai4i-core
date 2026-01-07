"""
Core business logic for OCR inference.

This mirrors the behavior of Dhruva's /services/inference/ocr while fitting
into the microservice structure used by ASR/TTS/NMT in this repository.
"""

import base64
import logging
from typing import List, Optional

import requests
from opentelemetry import trace
from opentelemetry.trace import Status, StatusCode

from models.ocr_request import OCRInferenceRequest, ImageInput
from models.ocr_response import OCRInferenceResponse, TextOutput
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
    """

    def __init__(self, triton_client: TritonClient, model_name: str):
        """
        Initialize OCR service.
        
        Args:
            triton_client: Triton client instance
            model_name: Model name (should be resolved by Model Management middleware)
        """
        self.triton_client = triton_client
        self.model_name = model_name

    def _resolve_image_base64(self, image: ImageInput) -> Optional[str]:
        """
        Resolve an image into base64:

        - If imageContent is provided, use it directly
        - Else, download from imageUri and base64-encode it
        
        NOTE: This method no longer creates spans to reduce noise.
        Image resolution is tracked as events in the parent "OCR Processing" span.
        """
        # Removed span creation - this is now collapsed into parent span
        # Technical details are tracked via events/attributes in parent
        # Safely check imageContent - handle both None and empty string cases
        if image.imageContent is not None and image.imageContent:
            return image.imageContent

        if image.imageUri:
            try:
                resp = requests.get(str(image.imageUri), timeout=30)
                resp.raise_for_status()
                image_bytes = base64.b64encode(resp.content).decode("utf-8")
                return image_bytes
            except Exception as exc:
                logger.error(
                    "Failed to download image from %s: %s", image.imageUri, exc
                )
                return None

        # No content and no URI
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

    def run_inference(self, request: OCRInferenceRequest) -> OCRInferenceResponse:
        """
        Synchronous OCR inference entrypoint.

        NOTE: This is intentionally synchronous like ASR/TTS core services; the
        FastAPI router can call it from an async endpoint.
        """
        if not tracer:
            # Fallback if tracing not available
            return self._run_inference_impl(request)
        
        # Business-level span: Main OCR processing workflow
        with tracer.start_as_current_span("OCR Processing") as span:
            span.set_attribute("purpose", "Runs the complete OCR workflow: image preparation, AI processing, and response construction")
            span.set_attribute("user_visible", True)
            span.set_attribute("impact_if_slow", "User waits longer for OCR results")
            span.set_attribute("owner", "AI Platform")
            span.set_attribute("ocr.total_images", len(request.image))
            
            # Collapse image resolution into parent span (no separate span for the loop)
            # Individual image resolution is now just an attribute/event
            images_b64: List[str] = []
            resolved_count = 0
            for idx, img in enumerate(request.image):
                resolved = self._resolve_image_base64(img)
                if not resolved:
                    images_b64.append("")
                else:
                    images_b64.append(resolved)
                    resolved_count += 1
                    # Add event for successful resolution (instead of separate span)
                    # Safely extract image size - resolved is guaranteed to be truthy here
                    try:
                        size_bytes = len(resolved) if resolved else 0
                    except (TypeError, AttributeError):
                        size_bytes = 0
                    
                    span.add_event("Image Prepared", {
                        "image_index": idx,
                        "source": "content" if (img.imageContent is not None and img.imageContent) else "uri",
                        "size_bytes": size_bytes
                    })
            
            span.set_attribute("ocr.resolved_count", resolved_count)
            span.set_attribute("ocr.failed_count", len(request.image) - resolved_count)

            # Call Triton in a single batch for all non-empty images
            outputs: List[TextOutput] = []
            try:
                # For empty entries, we'll skip Triton and just return empty text
                non_empty_indices = [i for i, v in enumerate(images_b64) if v]
                non_empty_images = [images_b64[i] for i in non_empty_indices]

                ocr_results: List[dict] = []
                if non_empty_images:
                    # Business-level span: AI model processing
                    with tracer.start_as_current_span("AI Model Processing") as triton_span:
                        triton_span.set_attribute("purpose", "Runs the OCR AI model on prepared images to extract text")
                        triton_span.set_attribute("user_visible", True)
                        triton_span.set_attribute("impact_if_slow", "User waits longer for OCR results - this is typically the slowest step")
                        triton_span.set_attribute("owner", "AI Platform")
                        triton_span.set_attribute("ocr.batch_size", len(non_empty_images))
                        triton_span.add_event("AI Processing Started", {"batch_size": len(non_empty_images)})
                        batch_results = self.triton_client.run_ocr_batch(non_empty_images)
                        ocr_results = batch_results
                        triton_span.set_attribute("ocr.results_count", len(ocr_results))
                        # Count successful results
                        success_count = sum(1 for r in ocr_results if r.get("success", False))
                        triton_span.set_attribute("ocr.success_count", success_count)
                        triton_span.add_event("AI Processing Completed", {
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
                return OCRInferenceResponse(output=outputs, config=request.config.dict())

            # Business-level span: Response construction
            with tracer.start_as_current_span("Response Construction") as build_span:
                build_span.set_attribute("purpose", "Formats the OCR results into the final response structure")
                build_span.set_attribute("user_visible", False)
                build_span.set_attribute("impact_if_slow", "Minimal - this step is usually very fast")
                build_span.set_attribute("owner", "AI Platform")
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
            return OCRInferenceResponse(output=outputs, config=request.config.dict())

    def _run_inference_impl(self, request: OCRInferenceRequest) -> OCRInferenceResponse:
        """Fallback implementation when tracing is not available."""
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

        return OCRInferenceResponse(output=outputs, config=request.config.dict())


