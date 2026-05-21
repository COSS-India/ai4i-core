"""NER (Named Entity Recognition) InferenceModel converter."""

from typing import Any, Dict, List, Optional, Tuple

from inference_models.base_inference_model import InferenceModel, InferenceModelError


class NERInferenceModel(InferenceModel):
    """
    InferenceModel for Named Entity Recognition.
    Converts NER request payloads to Triton format and back.
    Handles token classification and entity boundary extraction.
    """

    def __init__(self, model_name: str, endpoint_schema: Optional[Dict[str, Any]] = None):
        """
        Initialize NER inference model converter.

        Args:
            model_name: NER model name in Triton
            endpoint_schema: Optional Triton endpoint schema
        """
        pass

    async def convert_payload_to_triton_format(
        self,
        input_data: List[Dict[str, Any]],
        config: Dict[str, Any],
    ) -> Tuple[Dict[str, Any], List[str]]:
        """
        Convert NER request to Triton format.
        Prepares text inputs with language for Triton token classification.

        Args:
            input_data: List of TextInput dicts with 'source' field
            config: NER config with language

        Returns:
            Tuple of (triton_inputs, output_names)
        """
        pass

    async def convert_triton_output_to_task_format(
        self,
        triton_output: Dict[str, Any],
    ) -> List[Dict[str, Any]]:
        """
        Convert Triton output to NER response format.
        Extracts entities from token-level predictions.

        Args:
            triton_output: Raw Triton output with token labels

        Returns:
            List of NEROutput dicts with 'source' and 'tokens' (entities)
        """
        pass

    async def _prepare_text_for_triton(
        self,
        texts: List[str],
    ) -> Dict[str, Any]:
        """
        Prepare text inputs in Triton format.
        Tokenizes texts for NER model.

        Args:
            texts: List of source texts

        Returns:
            Dict with 'INPUT_TEXT' and 'INPUT_IDS' tensors
        """
        pass

    async def _tokenize_for_ner(
        self,
        text: str,
    ) -> tuple:
        """
        Tokenize text for NER model.

        Args:
            text: Input text

        Returns:
            Tuple of (tokens, token_ids, token_to_char_map)
        """
        pass

    async def _extract_entities_from_token_labels(
        self,
        tokens: List[str],
        labels: List[str],
        token_to_char_map: Dict[int, tuple],
        text: str,
    ) -> List[Dict[str, Any]]:
        """
        Extract entities from token-level BIO labels.

        Args:
            tokens: List of tokens
            labels: Token labels (BIO format)
            token_to_char_map: Mapping from token index to character positions
            text: Original text for extracting entity spans

        Returns:
            List of entity dicts with text, type, start_pos, end_pos
        """
        pass

    async def _extract_labels_from_triton(
        self,
        triton_output: Dict[str, Any],
    ) -> List[str]:
        """
        Extract entity labels from Triton output.

        Args:
            triton_output: Raw Triton output with token predictions

        Returns:
            List of entity labels (BIO or similar format)
        """
        pass
