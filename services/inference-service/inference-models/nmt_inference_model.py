"""NMT (Neural Machine Translation) InferenceModel converter."""

from typing import Any, Dict, List, Optional, Tuple

from inference_models.base_inference_model import InferenceModel, InferenceModelError


class NMTInferenceModel(InferenceModel):
    """
    InferenceModel for Neural Machine Translation.
    Converts NMT request payloads to Triton format and back.
    """

    def __init__(self, model_name: str, endpoint_schema: Optional[Dict[str, Any]] = None):
        """
        Initialize NMT inference model converter.

        Args:
            model_name: NMT model name in Triton
            endpoint_schema: Optional Triton endpoint schema
        """
        pass

    async def convert_payload_to_triton_format(
        self,
        input_data: List[Dict[str, Any]],
        config: Dict[str, Any],
    ) -> Tuple[Dict[str, Any], List[str]]:
        """
        Convert NMT request to Triton format.
        Prepares text inputs with language pair information for Triton.

        Args:
            input_data: List of TextInput dicts with 'source' field
            config: NMT config with language pair

        Returns:
            Tuple of (triton_inputs, output_names)
        """
        pass

    async def convert_triton_output_to_task_format(
        self,
        triton_output: Dict[str, Any],
    ) -> List[Dict[str, Any]]:
        """
        Convert Triton output to NMT response format.
        Formats translations as TranslationOutput items.

        Args:
            triton_output: Raw Triton output with translated texts

        Returns:
            List of TranslationOutput dicts with 'source' and 'target'
        """
        pass

    async def _prepare_texts_for_triton(
        self,
        texts: List[str],
        source_lang: str,
        target_lang: str,
    ) -> Dict[str, Any]:
        """
        Prepare text inputs in Triton format.

        Args:
            texts: List of source texts
            source_lang: Source language code
            target_lang: Target language code

        Returns:
            Dict with 'INPUT_TEXT', 'INPUT_LANGUAGE_PAIR' tensors
        """
        pass

    async def _extract_translations_from_triton(
        self,
        triton_output: Dict[str, Any],
    ) -> List[str]:
        """
        Extract translated texts from Triton output.

        Args:
            triton_output: Raw Triton output

        Returns:
            List of translated texts
        """
        pass

    async def _handle_batch_processing(
        self,
        input_data: List[Dict[str, Any]],
    ) -> List[List[Dict[str, Any]]]:
        """
        Handle batching for NMT (max 90 items per batch).

        Args:
            input_data: Input data to batch

        Returns:
            List of batches
        """
        pass
