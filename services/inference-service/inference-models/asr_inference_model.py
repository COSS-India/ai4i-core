"""ASR (Automatic Speech Recognition) InferenceModel converter."""

from typing import Any, Dict, List, Optional, Tuple

from inference_models.base_inference_model import InferenceModel, InferenceModelError


class ASRInferenceModel(InferenceModel):
    """
    InferenceModel for Automatic Speech Recognition.
    Converts ASR request payloads to Triton format and back.
    Handles audio encoding, resampling, and chunking.
    """

    def __init__(self, model_name: str, endpoint_schema: Optional[Dict[str, Any]] = None):
        """
        Initialize ASR inference model converter.

        Args:
            model_name: ASR model name in Triton
            endpoint_schema: Optional Triton endpoint schema
        """
        pass

    async def convert_payload_to_triton_format(
        self,
        input_data: List[Dict[str, Any]],
        config: Dict[str, Any],
    ) -> Tuple[Dict[str, Any], List[str]]:
        """
        Convert ASR request to Triton format.
        Prepares audio inputs with language and audio parameters for Triton.

        Args:
            input_data: List of AudioInput dicts with 'audio_content' or 'audio_uri'
            config: ASR config with language and audio parameters

        Returns:
            Tuple of (triton_inputs, output_names)
        """
        pass

    async def convert_triton_output_to_task_format(
        self,
        triton_output: Dict[str, Any],
    ) -> List[Dict[str, Any]]:
        """
        Convert Triton output to ASR response format.
        Formats transcriptions as TranscriptionOutput items.

        Args:
            triton_output: Raw Triton output with transcriptions

        Returns:
            List of TranscriptionOutput dicts with 'transcript' and optional 'alternatives'
        """
        pass

    async def _prepare_audio_for_triton(
        self,
        audio_bytes: bytes,
        sample_rate: int,
        target_sample_rate: int,
    ) -> Dict[str, Any]:
        """
        Prepare audio in Triton format.
        Resamples and chunks audio as needed.

        Args:
            audio_bytes: Raw audio data
            sample_rate: Current sample rate
            target_sample_rate: Target sample rate for Triton model

        Returns:
            Dict with 'AUDIO_DATA' and 'AUDIO_LENGTH' tensors
        """
        pass

    async def _extract_transcriptions_from_triton(
        self,
        triton_output: Dict[str, Any],
        n_best: int = 1,
    ) -> List[List[str]]:
        """
        Extract transcriptions from Triton output.

        Args:
            triton_output: Raw Triton output
            n_best: Number of best alternatives to extract

        Returns:
            List of [primary_transcript, alt1, alt2, ...] per audio
        """
        pass

    async def _resample_audio_chunk(
        self,
        audio_chunk: bytes,
        from_sr: int,
        to_sr: int,
    ) -> bytes:
        """
        Resample audio chunk to target sample rate.

        Args:
            audio_chunk: Audio data chunk
            from_sr: Source sample rate
            to_sr: Target sample rate

        Returns:
            Resampled audio bytes
        """
        pass

    async def _chunk_audio(
        self,
        audio_bytes: bytes,
        chunk_size_ms: int = 500,
    ) -> List[bytes]:
        """
        Chunk audio into overlapping segments for streaming inference.

        Args:
            audio_bytes: Full audio data
            chunk_size_ms: Chunk size in milliseconds

        Returns:
            List of audio chunks
        """
        pass
