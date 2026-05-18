"""Speaker Diarization InferenceModel converter."""

from typing import Any, Dict, List, Optional, Tuple

from inference_models.base_inference_model import InferenceModel, InferenceModelError


class SpeakerDiarizationInferenceModel(InferenceModel):
    """
    InferenceModel for Speaker Diarization.
    Converts speaker diarization request payloads to Triton format and back.
    Handles audio segmentation with speaker labels and timing.
    """

    def __init__(self, model_name: str, endpoint_schema: Optional[Dict[str, Any]] = None):
        """
        Initialize speaker diarization inference model converter.

        Args:
            model_name: Speaker diarization model name in Triton
            endpoint_schema: Optional Triton endpoint schema
        """
        pass

    async def convert_payload_to_triton_format(
        self,
        input_data: List[Dict[str, Any]],
        config: Dict[str, Any],
    ) -> Tuple[Dict[str, Any], List[str]]:
        """
        Convert speaker diarization request to Triton format.
        Prepares audio inputs with optional num_speakers for diarization.

        Args:
            input_data: List of AudioInput dicts with 'audio_content' or 'audio_uri'
            config: Speaker diarization config with optional num_speakers

        Returns:
            Tuple of (triton_inputs, output_names)
        """
        pass

    async def convert_triton_output_to_task_format(
        self,
        triton_output: Dict[str, Any],
    ) -> List[Dict[str, Any]]:
        """
        Convert Triton output to speaker diarization response format.
        Formats speaker segments with timing and grouping.

        Args:
            triton_output: Raw Triton output with diarization segments

        Returns:
            List of SpeakerDiarizationOutput dicts with segments and speaker groups
        """
        pass

    async def _prepare_audio_for_triton(
        self,
        audio_bytes: bytes,
        sample_rate: int,
        num_speakers: Optional[int] = None,
    ) -> Dict[str, Any]:
        """
        Prepare audio in Triton format.

        Args:
            audio_bytes: Raw audio data
            sample_rate: Audio sample rate
            num_speakers: Optional expected number of speakers

        Returns:
            Dict with 'AUDIO_DATA' and optional 'NUM_SPEAKERS' tensors
        """
        pass

    async def _extract_segments_from_triton(
        self,
        triton_output: Dict[str, Any],
    ) -> List[Dict[str, Any]]:
        """
        Extract speaker segments with timing from Triton output.

        Args:
            triton_output: Raw Triton output

        Returns:
            List of segments with start_time_ms, end_time_ms, speaker_id, confidence
        """
        pass

    async def _group_segments_by_speaker(
        self,
        segments: List[Dict[str, Any]],
    ) -> List[Dict[str, Any]]:
        """
        Group segments by speaker_id.

        Args:
            segments: List of speaker segments

        Returns:
            List of speaker groups with aggregated stats (total_duration, etc.)
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
