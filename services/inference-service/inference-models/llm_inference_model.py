"""LLM (Large Language Model) InferenceModel converter."""

from typing import Any, Dict, List, Optional, Tuple

from inference_models.base_inference_model import InferenceModel, InferenceModelError


class LLMInferenceModel(InferenceModel):
    """
    InferenceModel for Large Language Model inference.
    Converts LLM request payloads to Triton format and back.
    Handles prompt formatting and text generation configuration.
    """

    def __init__(self, model_name: str, endpoint_schema: Optional[Dict[str, Any]] = None):
        """
        Initialize LLM inference model converter.

        Args:
            model_name: LLM model name in Triton
            endpoint_schema: Optional Triton endpoint schema
        """
        pass

    async def convert_payload_to_triton_format(
        self,
        input_data: List[Dict[str, Any]],
        config: Dict[str, Any],
    ) -> Tuple[Dict[str, Any], List[str]]:
        """
        Convert LLM request to Triton format.
        Prepares prompts with generation parameters for Triton.

        Args:
            input_data: List of TextInput dicts with 'source' field
            config: LLM config with generation params (temperature, max_tokens, etc.)

        Returns:
            Tuple of (triton_inputs, output_names)
        """
        pass

    async def convert_triton_output_to_task_format(
        self,
        triton_output: Dict[str, Any],
    ) -> List[Dict[str, Any]]:
        """
        Convert Triton output to LLM response format.
        Formats generated text as LLMOutput items.

        Args:
            triton_output: Raw Triton output with generated text

        Returns:
            List of LLMOutput dicts with 'input_text' and 'generated_text'
        """
        pass

    async def _prepare_prompt_for_triton(
        self,
        texts: List[str],
        system_prompt: Optional[str],
    ) -> Dict[str, Any]:
        """
        Prepare prompts in Triton format.
        Combines system prompt with user input.

        Args:
            texts: List of user input texts
            system_prompt: Optional system prompt/instruction

        Returns:
            Dict with 'PROMPT' tensor
        """
        pass

    async def _format_prompt(
        self,
        user_text: str,
        system_prompt: Optional[str],
    ) -> str:
        """
        Format final prompt with system message.

        Args:
            user_text: User input text
            system_prompt: Optional system prompt

        Returns:
            Formatted prompt string
        """
        pass

    async def _extract_generated_text_from_triton(
        self,
        triton_output: Dict[str, Any],
    ) -> List[str]:
        """
        Extract generated text from Triton output.

        Args:
            triton_output: Raw Triton output

        Returns:
            List of generated text strings
        """
        pass

    async def _extract_token_count_from_triton(
        self,
        triton_output: Dict[str, Any],
    ) -> Optional[List[int]]:
        """
        Extract token count from Triton output if available.

        Args:
            triton_output: Raw Triton output

        Returns:
            List of token counts or None if not available
        """
        pass
