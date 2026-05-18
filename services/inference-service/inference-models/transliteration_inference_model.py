"""Transliteration InferenceModel converter."""

from typing import Any, Dict, List, Optional, Tuple

from inference_models.base_inference_model import InferenceModel, InferenceModelError


class TransliterationInferenceModel(InferenceModel):
    """
    InferenceModel for Transliteration.
    Converts transliteration request payloads to Triton format and back.
    Handles script conversion and optional multi-variant output.
    """

    def __init__(self, model_name: str, endpoint_schema: Optional[Dict[str, Any]] = None):
        """
        Initialize transliteration inference model converter.

        Args:
            model_name: Transliteration model name in Triton
            endpoint_schema: Optional Triton endpoint schema
        """
        pass

    async def convert_payload_to_triton_format(
        self,
        input_data: List[Dict[str, Any]],
        config: Dict[str, Any],
    ) -> Tuple[Dict[str, Any], List[str]]:
        """
        Convert transliteration request to Triton format.
        Prepares text with source and target script information.

        Args:
            input_data: List of TextInput dicts with 'source' field
            config: Transliteration config with source/target language and scripts

        Returns:
            Tuple of (triton_inputs, output_names)
        """
        pass

    async def convert_triton_output_to_task_format(
        self,
        triton_output: Dict[str, Any],
    ) -> List[Dict[str, Any]]:
        """
        Convert Triton output to transliteration response format.
        Formats transliterated text as TransliterationOutput items.

        Args:
            triton_output: Raw Triton output with transliterated text

        Returns:
            List of TransliterationOutput dicts with 'source' and 'target'
        """
        pass

    async def _prepare_text_for_triton(
        self,
        texts: List[str],
        source_script: str,
        target_script: str,
    ) -> Dict[str, Any]:
        """
        Prepare text inputs in Triton format.

        Args:
            texts: List of source texts
            source_script: Source script code
            target_script: Target script code

        Returns:
            Dict with 'INPUT_TEXT', 'SOURCE_SCRIPT', 'TARGET_SCRIPT' tensors
        """
        pass

    async def _extract_transliteration_from_triton(
        self,
        triton_output: Dict[str, Any],
    ) -> List[str]:
        """
        Extract transliterated text from Triton output.

        Args:
            triton_output: Raw Triton output

        Returns:
            List of transliterated texts
        """
        pass

    async def _handle_variants_from_triton(
        self,
        triton_output: Dict[str, Any],
    ) -> Optional[List[List[str]]]:
        """
        Extract optional transliteration variants from Triton output.

        Args:
            triton_output: Raw Triton output

        Returns:
            List of variant lists or None if not available
        """
        pass
