"""Audio Language Detection InferenceModel converter."""

from typing import Any, Dict, List, Optional, Tuple

from inference_models.base_inference_model import InferenceModel, InferenceModelError


class AudioLanguageDetectionInferenceModel(InferenceModel):
    """
    InferenceModel for Audio Language Detection.
    Converts audio language detection request payloads to Triton format and back.
    """

    def __init__(self, model_name: str, endpoint_schema: Optional[Dict[str, Any]] = None):
        """
        Initialize audio language detection inference model converter.

        Args:
            model_name: Audio language detection model name in Triton
            endpoint_schema: Optional Triton endpoint schema
        """
        pass

    async def convert_payload_to_triton_format(
        self,
        input_data: List[Dict[str, Any]],
        config: Dict[str, Any],
    ) -> Tuple[Dict[str, Any], List[str]]:
        """
        Convert audio language detection request to Triton format.
        Prepares audio inputs for language classification.

        Args:
            input_data: List of AudioInput dicts with 'audio_content' or 'audio_uri'
            config: Audio language detection config

        Returns:
            Tuple of (triton_inputs, output_names)
        """
        pass

    async def convert_triton_output_to_task_format(
        self,
        triton_output: Dict[str, Any],
    ) -> List[Dict[str, Any]]:
        """
        Convert Triton output to audio language detection response format.
        Formats language predictions with confidence scores.

        Args:
            triton_output: Raw Triton output with language predictions

        Returns:
            List of AudioLanguageDetectionOutput dicts with language predictions
        """
        pass

    async def _prepare_audio_for_triton(
        self,
        audio_bytes: bytes,
        sample_rate: int,
    ) -> Dict[str, Any]:
        """
        Prepare audio in Triton format.

        Args:
            audio_bytes: Raw audio data
            sample_rate: Audio sample rate

        Returns:
            Dict with 'AUDIO_DATA' tensor
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
            List of [(lang_code, confidence), ...] per audio
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

    async def _extract_duration_from_triton(
        self,
        triton_output: Dict[str, Any],
    ) -> Optional[float]:
        """
        Extract audio duration from Triton output if available.

        Args:
            triton_output: Raw Triton output

        Returns:
            Duration in milliseconds or None
        """
        pass
