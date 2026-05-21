"""OCR (Optical Character Recognition) InferenceModel converter."""

from typing import Any, Dict, List, Optional, Tuple

from inference_models.base_inference_model import InferenceModel, InferenceModelError


class OCRInferenceModel(InferenceModel):
    """
    InferenceModel for Optical Character Recognition.
    Converts OCR request payloads to Triton format and back.
    Handles image decoding, normalization, and layout extraction.
    """

    def __init__(self, model_name: str, endpoint_schema: Optional[Dict[str, Any]] = None):
        """
        Initialize OCR inference model converter.

        Args:
            model_name: OCR model name in Triton
            endpoint_schema: Optional Triton endpoint schema
        """
        pass

    async def convert_payload_to_triton_format(
        self,
        input_data: List[Dict[str, Any]],
        config: Dict[str, Any],
    ) -> Tuple[Dict[str, Any], List[str]]:
        """
        Convert OCR request to Triton format.
        Prepares image inputs with language hint for Triton.

        Args:
            input_data: List of ImageInput dicts with 'image_content' or 'image_uri'
            config: OCR config with optional language hint

        Returns:
            Tuple of (triton_inputs, output_names)
        """
        pass

    async def convert_triton_output_to_task_format(
        self,
        triton_output: Dict[str, Any],
    ) -> List[Dict[str, Any]]:
        """
        Convert Triton output to OCR response format.
        Formats extracted text and layout as OCROutput items.

        Args:
            triton_output: Raw Triton output with OCR results

        Returns:
            List of OCROutput dicts with 'text' and optional 'layout'
        """
        pass

    async def _prepare_image_for_triton(
        self,
        image_bytes: bytes,
        target_size: Optional[Tuple[int, int]] = None,
    ) -> Dict[str, Any]:
        """
        Prepare image in Triton format.
        Resizes and normalizes image as needed.

        Args:
            image_bytes: Raw image data
            target_size: Optional target (height, width) for resizing

        Returns:
            Dict with 'IMAGE_DATA' tensor
        """
        pass

    async def _normalize_image_dimensions(
        self,
        image_bytes: bytes,
        target_width: Optional[int],
        target_height: Optional[int],
    ) -> bytes:
        """
        Normalize image dimensions for OCR model.

        Args:
            image_bytes: Image data
            target_width: Optional target width
            target_height: Optional target height

        Returns:
            Normalized image bytes
        """
        pass

    async def _extract_text_from_triton(
        self,
        triton_output: Dict[str, Any],
    ) -> str:
        """
        Extract text from Triton OCR output.

        Args:
            triton_output: Raw Triton output

        Returns:
            Extracted text string
        """
        pass

    async def _extract_layout_from_triton(
        self,
        triton_output: Dict[str, Any],
    ) -> Optional[Dict[str, Any]]:
        """
        Extract layout/bounding box information from Triton output.

        Args:
            triton_output: Raw Triton output

        Returns:
            Layout dict with bounding boxes or None
        """
        pass
