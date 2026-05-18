"""PII (Personally Identifiable Information) InferenceModel converter."""

from typing import Any, Dict, List, Optional, Tuple

from inference_models.base_inference_model import InferenceModel, InferenceModelError


class PIIInferenceModel(InferenceModel):
    """
    InferenceModel for PII Detection and Redaction.
    Converts PII detection request payloads to Triton format and back.
    Handles entity detection and redaction application.
    """

    def __init__(self, model_name: str, endpoint_schema: Optional[Dict[str, Any]] = None):
        """
        Initialize PII inference model converter.

        Args:
            model_name: PII model name in Triton
            endpoint_schema: Optional Triton endpoint schema
        """
        pass

    async def convert_payload_to_triton_format(
        self,
        input_data: List[Dict[str, Any]],
        config: Dict[str, Any],
    ) -> Tuple[Dict[str, Any], List[str]]:
        """
        Convert PII detection request to Triton format.
        Prepares text inputs with language and optional domain filters.

        Args:
            input_data: List of TextInput dicts with 'source' field
            config: PII config with language and optional domain filters

        Returns:
            Tuple of (triton_inputs, output_names)
        """
        pass

    async def convert_triton_output_to_task_format(
        self,
        triton_output: Dict[str, Any],
    ) -> List[Dict[str, Any]]:
        """
        Convert Triton output to PII detection response format.
        Formats detected entities as PIIOutput items with redaction applied.

        Args:
            triton_output: Raw Triton output with detected PII entities

        Returns:
            List of PIIOutput dicts with redacted text and entity details
        """
        pass

    async def _prepare_text_for_triton(
        self,
        texts: List[str],
        language: str,
        domains: Optional[List[str]] = None,
    ) -> Dict[str, Any]:
        """
        Prepare text inputs in Triton format.

        Args:
            texts: List of source texts
            language: Language code for PII detection
            domains: Optional list of domains to detect (e.g., email, phone)

        Returns:
            Dict with 'INPUT_TEXT' and optional domain filter tensors
        """
        pass

    async def _extract_entities_from_triton(
        self,
        triton_output: Dict[str, Any],
    ) -> List[List[Dict[str, Any]]]:
        """
        Extract detected PII entities from Triton output.

        Args:
            triton_output: Raw Triton output

        Returns:
            List of entity lists (one per input) with type, position, and text
        """
        pass

    async def _apply_redaction(
        self,
        original_text: str,
        entities: List[Dict[str, Any]],
        redaction_mode: str,
    ) -> tuple:
        """
        Apply redaction to text based on detected entities.

        Args:
            original_text: Original input text
            entities: List of detected PII entities with positions
            redaction_mode: Redaction mode (mask, replace, remove)

        Returns:
            Tuple of (redacted_text, redacted_entities)
        """
        pass

    async def _apply_masking(
        self,
        text: str,
        entity_positions: List[tuple],
        mask_char: str = "*",
    ) -> str:
        """
        Apply masking redaction.

        Args:
            text: Original text
            entity_positions: List of (start, end) positions
            mask_char: Character to use for masking

        Returns:
            Masked text
        """
        pass

    async def _apply_removal(
        self,
        text: str,
        entity_positions: List[tuple],
    ) -> str:
        """
        Apply removal redaction.

        Args:
            text: Original text
            entity_positions: List of (start, end) positions

        Returns:
            Text with entities removed
        """
        pass

    async def _apply_replacement(
        self,
        text: str,
        entity_positions: List[tuple],
        replacements: Dict[str, str],
    ) -> str:
        """
        Apply replacement redaction.

        Args:
            text: Original text
            entity_positions: List of (start, end) positions
            replacements: Dict mapping entity_type to replacement text

        Returns:
            Text with entities replaced
        """
        pass
