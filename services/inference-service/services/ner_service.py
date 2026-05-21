"""NER (Named Entity Recognition) TaskService implementation."""

from typing import Any, Dict, List, Optional

from interfaces.task_service import BaseTaskService
from models.schemas.ner import (
    NERInferenceRequest,
    NERInferenceResponse,
    NERConfig,
)


class NERTaskService(BaseTaskService):
    """
    TaskService for Named Entity Recognition inference.
    Handles entity extraction from text.
    """

    def __init__(self, **dependencies: Any):
        """
        Initialize NER task service.

        Args:
            **dependencies: Injected dependencies
                - redis_client: Redis client for caching
                - model_management_client: Client for model/endpoint resolution
                - inference_server_resolver: Resolver for Triton endpoints
                - inference_model_factory: Factory for InferenceModel converters
        """
        pass

    async def validate_request(self, request: NERInferenceRequest) -> None:
        """
        Validate NER inference request.
        Checks input text, language support, etc.

        Args:
            request: NER request to validate

        Raises:
            ValueError: If request is invalid
        """
        pass

    async def preprocess_input(self, input_data: List[Dict[str, Any]]) -> List[Dict[str, Any]]:
        """
        Preprocess text inputs for NER.
        Handles text normalization, tokenization, etc.

        Args:
            input_data: List of text inputs

        Returns:
            Preprocessed input data
        """
        pass

    async def run_inference(
        self,
        request: NERInferenceRequest,
        user_id: Optional[int] = None,
        api_key_id: Optional[int] = None,
        session_id: Optional[str] = None,
    ) -> NERInferenceResponse:
        """
        Execute end-to-end NER inference pipeline.
        Resolves service -> preprocesses -> calls Triton -> postprocesses -> returns response.

        Args:
            request: NER inference request
            user_id: Optional user ID
            api_key_id: Optional API key ID
            session_id: Optional session ID

        Returns:
            NER inference response with recognized entities
        """
        pass

    async def postprocess_output(
        self, raw_triton_output: Dict[str, Any]
    ) -> Dict[str, Any]:
        """
        Post-process raw Triton output for NER.
        Formats entities, extracts confidence scores, etc.

        Args:
            raw_triton_output: Raw output from Triton server

        Returns:
            Formatted output dictionary
        """
        pass

    async def _resolve_service_and_model(
        self, config: NERConfig, session_id: Optional[str]
    ) -> tuple:
        """
        Resolve inference service and model information.

        Args:
            config: NER config with required service_id
            session_id: Optional session ID for tracing

        Returns:
            Tuple of (service_id, model_name, triton_endpoint, triton_api_key)
        """
        pass

    async def _tokenize_text(self, text: str) -> List[str]:
        """
        Tokenize text for NER model.

        Args:
            text: Input text to tokenize

        Returns:
            List of tokens
        """
        pass

    async def _extract_entities_from_tokens(
        self, tokens: List[str], token_labels: List[str]
    ) -> List[Dict[str, Any]]:
        """
        Extract entity boundaries from token-level labels.

        Args:
            tokens: List of tokens
            token_labels: Label for each token

        Returns:
            List of entity dictionaries with start/end positions and types
        """
        pass

    async def _call_triton_inference(
        self,
        triton_endpoint: str,
        model_name: str,
        triton_inputs: Dict[str, Any],
        triton_outputs: List[str],
        api_key: Optional[str] = None,
    ) -> Dict[str, Any]:
        """
        Call Triton inference server with prepared inputs.

        Args:
            triton_endpoint: Triton server URL
            model_name: Model name in Triton
            triton_inputs: Formatted inputs for Triton
            triton_outputs: Expected output names
            api_key: Optional Triton API key

        Returns:
            Raw output from Triton
        """
        pass
