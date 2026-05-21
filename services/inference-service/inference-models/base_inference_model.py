"""
Abstract base class for InferenceModel converters.
Converts task-specific payloads to Triton-compatible format.
"""

from abc import ABC, abstractmethod
from typing import Any, Dict, List, Optional, Tuple


class InferenceModelError(Exception):
    """Base exception for inference model errors."""

    pass


class InferenceModel(ABC):
    """
    Abstract base class for inference model payload converters.
    Converts task-specific request payloads to Triton-compatible input format.
    """

    def __init__(self, model_name: str, endpoint_schema: Optional[Dict[str, Any]] = None):
        """
        Initialize inference model converter.

        Args:
            model_name: Name of model in Triton
            endpoint_schema: Optional Triton endpoint schema defining I/O
        """
        pass

    @abstractmethod
    async def convert_payload_to_triton_format(
        self,
        input_data: List[Dict[str, Any]],
        config: Dict[str, Any],
    ) -> Tuple[Dict[str, Any], List[str]]:
        """
        Convert task-specific request payload to Triton inference format.
        Returns prepared inputs and expected output names.

        Args:
            input_data: Task-specific input data (list of input items)
            config: Task-specific configuration

        Returns:
            Tuple of (triton_inputs, output_names)
                - triton_inputs: Dict with input names mapping to tensors
                - output_names: List of expected output tensor names

        Raises:
            InferenceModelError: If conversion fails
        """
        pass

    @abstractmethod
    async def convert_triton_output_to_task_format(
        self,
        triton_output: Dict[str, Any],
    ) -> List[Dict[str, Any]]:
        """
        Convert raw Triton output to task-specific output format.

        Args:
            triton_output: Raw output from Triton server

        Returns:
            List of task-specific output items

        Raises:
            InferenceModelError: If conversion fails
        """
        pass

    async def validate_input_schema(
        self,
        input_data: List[Dict[str, Any]],
    ) -> None:
        """
        Validate input data against expected schema.

        Args:
            input_data: Input data to validate

        Raises:
            InferenceModelError: If validation fails
        """
        pass

    async def validate_output_schema(
        self,
        output_data: Dict[str, Any],
    ) -> None:
        """
        Validate Triton output against expected schema.

        Args:
            output_data: Output data to validate

        Raises:
            InferenceModelError: If validation fails
        """
        pass

    def _get_input_name(self, key: str) -> str:
        """Get Triton input tensor name from schema or key."""
        pass

    def _get_output_name(self, key: str) -> str:
        """Get Triton output tensor name from schema or key."""
        pass

    def _log_conversion_error(self, stage: str, error_msg: str) -> None:
        """Log inference model conversion error."""
        pass
