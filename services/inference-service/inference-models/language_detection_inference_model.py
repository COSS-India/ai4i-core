"""Language Detection InferenceModel converter."""

from typing import Any, Dict, List, Optional, Tuple

from inference_models.base_inference_model import InferenceModel, InferenceModelError


class LanguageDetectionInferenceModel(InferenceModel):
    """
    InferenceModel for Language Detection.
    Converts language detection request payloads to Triton format and back.
    """

    def __init__(self, model_name: str, endpoint_schema: Optional[Dict[str, Any]] = None):
        """
        Initialize language detection inference model converter.

        Args:
            model_name: Language detection model name in Triton
            endpoint_schema: Optional Triton endpoint schema
        """
        pass

    async def convert_payload_to_triton_format(
        self,
        input_data: List[Dict[str, Any]],
        config: Dict[str, Any],
    ) -> Tuple[Dict[str, Any], List[str]]:
        """
        Convert language detection request to Triton format.
        Prepares text inputs for language classification.

        Args:
            input_data: List of TextInput dicts with 'source' field
            config: Language detection config

        Returns:
            Tuple of (triton_inputs, output_names)
        """
        pass

    async def convert_triton_output_to_task_format(
        self,
        triton_output: Dict[str, Any],
    ) -> List[Dict[str, Any]]:
        """
        Convert Triton output to language detection response format.
        Formats language predictions with confidence scores.

        Args:
            triton_output: Raw Triton output with language predictions

        Returns:
            List of LanguageDetectionOutput dicts with language predictions
        """
        pass

    async def _prepare_text_for_triton(
        self,
        texts: List[str],
    ) -> Dict[str, Any]:
        """
        Prepare text inputs in Triton format.

        Args:
            texts: List of source texts

        Returns:
            Dict with 'INPUT_TEXT' tensor
        """
        pass

    async def _extract_language_predictions_from_triton(
        self,
        triton_output: Dict[str, Any],
    ) -> List[List[tuple]]:
        """
        Extract language predictions from Triton output.
        Returns language codes with confidence scores.

        Args:
            triton_output: Raw Triton output

        Returns:
            List of [(lang_code, confidence), ...] per input
        """
        pass

    async def _format_language_predictions(
        self,
        predictions: List[tuple],
        return_all: bool = False,
    ) -> tuple:
        """
        Format language predictions into response structure.

        Args:
            predictions: List of (lang_code, confidence) tuples
            return_all: Whether to include all predictions or just top-1

        Returns:
            Tuple of (primary_prediction, all_predictions)
        """
        pass
