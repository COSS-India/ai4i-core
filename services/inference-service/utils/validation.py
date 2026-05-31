"""Utility functions for request validation and transformation."""

from typing import Any, Dict, List, Optional
from pydantic import ValidationError


class ValidationUtility:
    """Utility class for request validation."""

    @staticmethod
    async def validate_polymorphic_input(
        payload: Dict[str, Any],
        expected_input_key: str,
    ) -> List[Dict[str, Any]]:
        """
        Validate and extract polymorphic input from payload.

        Args:
            payload: Request payload
            expected_input_key: Expected input key (input, audio, or image)

        Returns:
            List of input items

        Raises:
            ValueError: If input key doesn't match or is empty
        """
        pass

    @staticmethod
    async def validate_config_schema(
        config: Dict[str, Any],
        config_model: type,
    ) -> Any:
        """
        Validate config against task-specific model.

        Args:
            config: Config dictionary to validate
            config_model: Pydantic config model class

        Returns:
            Validated config model instance

        Raises:
            ValidationError: If validation fails
        """
        pass

    @staticmethod
    async def validate_input_count(
        input_data: List[Dict[str, Any]],
        max_items: Optional[int] = None,
        min_items: int = 1,
    ) -> None:
        """
        Validate input item count.

        Args:
            input_data: Input items to validate
            max_items: Optional maximum items (None for unlimited)
            min_items: Minimum items (default 1)

        Raises:
            ValueError: If count is invalid
        """
        pass

    @staticmethod
    async def extract_required_fields(
        obj: Dict[str, Any],
        required_fields: List[str],
    ) -> Dict[str, Any]:
        """
        Extract required fields from object.

        Args:
            obj: Object to extract from
            required_fields: List of required field names

        Returns:
            Dict with required fields

        Raises:
            ValueError: If any required field is missing
        """
        pass


class PayloadTransformer:
    """Utility class for payload transformation."""

    @staticmethod
    async def transform_request_to_task_format(
        generic_payload: Dict[str, Any],
        request_model: type,
    ) -> Any:
        """
        Transform generic payload to task-specific request model.

        Args:
            generic_payload: Generic payload dictionary
            request_model: Target task-specific request model class

        Returns:
            Task-specific request model instance
        """
        pass

    @staticmethod
    async def transform_response_to_generic_format(
        task_response: Any,
        task_type: str,
        smr_response: Optional[Dict[str, Any]] = None,
    ) -> Dict[str, Any]:
        """
        Transform task-specific response to generic format.

        Args:
            task_response: Task-specific response model
            task_type: Task type for response metadata
            smr_response: Optional SMR routing metadata

        Returns:
            Generic response dictionary
        """
        pass
