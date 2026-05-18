"""TTS (Text-to-Speech) InferenceModel converter."""

from typing import Any, Dict, List, Optional, Tuple

from inference_models.base_inference_model import InferenceModel, InferenceModelError


class TTSInferenceModel(InferenceModel):
    """
    InferenceModel for Text-to-Speech.
    Converts TTS request payloads to Triton format and back.
    Handles audio synthesis parameters and base64 encoding.
    """

    def __init__(self, model_name: str, endpoint_schema: Optional[Dict[str, Any]] = None):
        """
        Initialize TTS inference model converter.

        Args:
            model_name: TTS model name in Triton
            endpoint_schema: Optional Triton endpoint schema
        """
        pass

    async def convert_payload_to_triton_format(
        self,
        input_data: List[Dict[str, Any]],
        config: Dict[str, Any],
    ) -> Tuple[Dict[str, Any], List[str]]:
        """
        Convert TTS request to Triton format.
        Prepares text and voice parameters for speech synthesis.

        Args:
            input_data: List of TextInput dicts with 'source' field
            config: TTS config with language, voice, and audio params

        Returns:
            Tuple of (triton_inputs, output_names)
        """
        pass

    async def convert_triton_output_to_task_format(
        self,
        triton_output: Dict[str, Any],
    ) -> List[Dict[str, Any]]:
        """
        Convert Triton output to TTS response format.
        Formats synthesized audio as TTSOutput items.

        Args:
            triton_output: Raw Triton output with audio data

        Returns:
            List of TTSOutput dicts with 'audio_content' (base64) and metadata
        """
        pass

    async def _prepare_text_for_triton(
        self,
        texts: List[str],
        voice_params: Dict[str, Any],
    ) -> Dict[str, Any]:
        """
        Prepare text inputs in Triton format.

        Args:
            texts: List of texts to synthesize
            voice_params: Voice parameters (voice_id, language, etc.)

        Returns:
            Dict with 'INPUT_TEXT' and voice parameter tensors
        """
        pass

    async def _extract_audio_from_triton(
        self,
        triton_output: Dict[str, Any],
    ) -> List[bytes]:
        """
        Extract audio data from Triton output.

        Args:
            triton_output: Raw Triton output

        Returns:
            List of audio byte arrays
        """
        pass

    async def _encode_audio_to_base64(
        self,
        audio_bytes: bytes,
    ) -> str:
        """
        Encode audio bytes to base64 string.

        Args:
            audio_bytes: Raw audio data

        Returns:
            Base64 encoded audio string
        """
        pass

    async def _extract_audio_metadata_from_triton(
        self,
        triton_output: Dict[str, Any],
    ) -> Dict[str, Any]:
        """
        Extract audio metadata (duration, sample rate, etc.) from Triton output.

        Args:
            triton_output: Raw Triton output

        Returns:
            Dict with duration_ms, sample_rate, num_channels
        """
        pass
