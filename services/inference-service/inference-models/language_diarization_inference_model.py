"""Language Diarization InferenceModel converter."""

from typing import Any, Dict, List, Optional, Tuple

from inference_models.base_inference_model import InferenceModel, InferenceModelError


class LanguageDiarizationInferenceModel(InferenceModel):
    """
    InferenceModel for Language Diarization.
    Converts language diarization request payloads to Triton format and back.
    Handles audio segmentation with language labels and timing.
    """

    def __init__(self, model_name: str, endpoint_schema: Optional[Dict[str, Any]] = None):
        """
        Initialize language diarization inference model converter.

        Args:
            model_name: Language diarization model name in Triton
            endpoint_schema: Optional Triton endpoint schema
        """
        pass

    async def convert_payload_to_triton_format(
        self,
        input_data: List[Dict[str, Any]],
        config: Dict[str, Any],
    ) -> Tuple[Dict[str, Any], List[str]]:
        """
        Convert language diarization request to Triton format.
        Prepares audio inputs for diarization processing.

        Args:
            input_data: List of AudioInput dicts with 'audio_content' or 'audio_uri'
            config: Language diarization config

        Returns:
            Tuple of (triton_inputs, output_names)
        """
        pass

    async def convert_triton_output_to_task_format(
        self,
        triton_output: Dict[str, Any],
    ) -> List[Dict[str, Any]]:
        """
        Convert Triton output to language diarization response format.
        Formats language segments with timing as LanguageDiarizationOutput items.

        Args:
            triton_output: Raw Triton output with diarization segments

        Returns:
            List of LanguageDiarizationOutput dicts with segments and timing
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
            Dict with 'AUDIO_DATA' and 'SAMPLE_RATE' tensors
        """
        pass

    async def _extract_segments_from_triton(
        self,
        triton_output: Dict[str, Any],
    ) -> List[Dict[str, Any]]:
        """
        Extract language segments with timing from Triton output.

        Args:
            triton_output: Raw Triton output

        Returns:
            List of segments with start_time_ms, end_time_ms, language, confidence
        """
        pass

    async def _calculate_segment_timing(
        self,
        segment_indices: List[tuple],
        sample_rate: int,
    ) -> List[tuple]:
        """
        Calculate millisecond timing for segments.

        Args:
            segment_indices: List of (start_index, end_index) tuples
            sample_rate: Audio sample rate

        Returns:
            List of (start_ms, end_ms) tuples
        """
        pass
