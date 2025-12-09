"""
Core business logic for OCR inference.

This mirrors the behavior of Dhruva's /services/inference/ocr while fitting
into the microservice structure used by ASR/TTS/NMT in this repository.
"""

import base64
import logging
from typing import List, Optional

import requests

from models.ocr_request import OCRInferenceRequest, ImageInput
from models.ocr_response import OCRInferenceResponse, TextOutput
from utils.triton_client import TritonClient, TritonInferenceError

logger = logging.getLogger(__name__)


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

    def __init__(self, triton_client: TritonClient):
        self.triton_client = triton_client

    def _resolve_image_base64(self, image: ImageInput) -> Optional[str]:
        """
        Resolve an image into base64:

        - If imageContent is provided, use it directly
        - Else, download from imageUri and base64-encode it
        """
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

        # No content and no URI
        return None

    def run_inference(self, request: OCRInferenceRequest) -> OCRInferenceResponse:
        """
        Synchronous OCR inference entrypoint.

        NOTE: This is intentionally synchronous like ASR/TTS core services; the
        FastAPI router can call it from an async endpoint.
        """
        # Resolve all images to base64 first
        images_b64: List[str] = []
        for img in request.image:
            resolved = self._resolve_image_base64(img)
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


