"""
Core business logic for NER inference.

This mirrors the behavior of Dhruva's /inference/ner while fitting
into the microservice structure used by ASR/TTS/NMT/OCR in this repo.
"""

import json
import logging
from typing import Any, Dict, List, Optional, Tuple

import numpy as np

from models.ner_request import NerInferenceRequest
from models.ner_response import (
    NerInferenceResponse,
    NerPrediction,
    NerTokenPrediction,
)
from utils.triton_client import TritonClient, TritonInferenceError
from ai4icore_model_management import ModelManagementClient

logger = logging.getLogger(__name__)


class ModelManagementError(Exception):
    """Error when fetching model configuration from model management service"""
    pass


class NerService:
    """
    NER inference service.

    Responsibilities:
    - Take NerInferenceRequest
    - Fetch model configuration from Model Management Service
    - Prepare Triton inputs (INPUT_TEXT, LANG_ID)
    - Call Triton NER model
    - Decode JSON output and align entities to tokens
    - Return NerInferenceResponse
    """

    def __init__(
        self,
        model_management_client: ModelManagementClient,
        redis_client=None
    ):
        self.model_management_client = model_management_client
        self.redis_client = redis_client
        # Cache: service_id -> (TritonClient, endpoint, model_name)
        self._triton_clients: Dict[str, Tuple[TritonClient, str, str]] = {}

    async def _get_triton_client(
        self,
        service_id: str,
        auth_headers: Optional[Dict[str, str]] = None
    ) -> Tuple[TritonClient, str]:
        """
        Get Triton client and model name for the given service ID from model management.
        
        Args:
            service_id: Service ID from request
            auth_headers: Auth headers to forward to model management service
            
        Returns:
            Tuple of (TritonClient, model_name)
            
        Raises:
            ModelManagementError: If service not found or configuration invalid
        """
        # Fetch service info from model management first to get current endpoint
        logger.info(f"Fetching service configuration for serviceId: {service_id}")
        service_info = await self.model_management_client.get_service(
            service_id=service_id,
            use_cache=False,  # Always fetch fresh to detect endpoint changes
            redis_client=self.redis_client,
            auth_headers=auth_headers
        )
        
        if not service_info:
            raise ModelManagementError(
                f"Service '{service_id}' not found in model management service. "
                f"Please verify the serviceId is correct and the service is registered in model management."
            )
        
        if not service_info.endpoint:
            raise ModelManagementError(
                f"Service '{service_id}' does not have a Triton endpoint configured in model management. "
                f"Please update the service configuration with a valid endpoint."
            )
        
        if not service_info.triton_model:
            raise ModelManagementError(
                f"Service '{service_id}' does not have a Triton model name configured in model management. "
                f"Please update the service configuration with a valid model name."
            )
        
        # Normalize endpoint for comparison
        current_endpoint = service_info.endpoint.replace("http://", "").replace("https://", "")
        
        # Check cache and validate endpoint hasn't changed
        cache_key = f"triton_client:{service_id}"
        if cache_key in self._triton_clients:
            cached_client, cached_endpoint, cached_model = self._triton_clients[cache_key]
            # Check if endpoint has changed - if so, invalidate cache
            if cached_endpoint != current_endpoint:
                logger.info(
                    f"Endpoint changed for {service_id}: {cached_endpoint} -> {current_endpoint}. "
                    f"Invalidating cache and creating new client."
                )
                del self._triton_clients[cache_key]
            else:
                # Endpoint unchanged, use cached client
                logger.debug(f"Using cached Triton client for {service_id} with endpoint {current_endpoint}")
                return cached_client, service_info.triton_model
        
        # Create Triton client with current endpoint
        triton_client = TritonClient(
            triton_url=service_info.endpoint,
            api_key=service_info.api_key
        )
        
        # Cache the client with endpoint and model name for validation
        self._triton_clients[cache_key] = (triton_client, current_endpoint, service_info.triton_model)
        
        logger.info(
            f"Using Triton endpoint: {service_info.endpoint}, "
            f"model: {service_info.triton_model} for service: {service_id}"
        )
        
        return triton_client, service_info.triton_model

    async def run_inference(
        self,
        request: NerInferenceRequest,
        auth_headers: Optional[Dict[str, str]] = None
    ) -> NerInferenceResponse:
        """
        Async NER inference entrypoint.

        Fetches model configuration from model management service and performs inference.
        
        Args:
            request: NER inference request
            auth_headers: Optional auth headers to forward to model management service
            
        Returns:
            NER inference response
            
        Raises:
            ModelManagementError: If service configuration cannot be fetched
            TritonInferenceError: If Triton inference fails
        """
        service_id = request.config.serviceId
        
        if not service_id:
            raise ValueError(
                "serviceId is required in request.config. "
                "Please provide a valid serviceId from model management."
            )
        
        # Get Triton client and model name from model management
        try:
            triton_client, model_name = await self._get_triton_client(
                service_id=service_id,
                auth_headers=auth_headers
            )
        except ModelManagementError as e:
            logger.error(f"Failed to get model configuration: {e}")
            raise
        except Exception as e:
            logger.error(f"Unexpected error fetching model configuration: {e}", exc_info=True)
            raise ModelManagementError(
                f"Failed to fetch model configuration for service '{service_id}': {e}"
            ) from e
        
        # Prepare input texts (normalize newlines/whitespace)
        input_texts: List[str] = []
        for text_input in request.input:
            normalized = (text_input.source or " ").replace("\n", " ").strip()
            if not normalized:
                logger.warning("Empty text input detected, skipping")
                continue
            input_texts.append(normalized)

        if not input_texts:
            raise ValueError(
                "No valid text inputs provided. All inputs are empty or invalid."
            )
        
        language = request.config.language.sourceLanguage
        
        if not language:
            raise ValueError(
                "sourceLanguage is required in request.config.language. "
                "Please provide a valid language code."
            )

        # Prepare Triton inputs/outputs
        try:
            inputs, outputs = triton_client.get_ner_io_for_triton(
                input_texts, language
            )

            response = triton_client.send_triton_request(
                model_name=model_name,
                inputs=inputs,
                outputs=outputs,
            )
        except TritonInferenceError:
            # Let TritonInferenceError bubble up to router for 503 mapping
            raise
        except Exception as exc:
            logger.error(
                f"Triton NER inference failed for service '{service_id}', model '{model_name}': {exc}",
                exc_info=True
            )
            raise TritonInferenceError(
                f"Triton NER inference failed for model '{model_name}': {exc}"
            ) from exc

        # Decode Triton OUTPUT_TEXT
        encoded_result = response.as_numpy("OUTPUT_TEXT")
        if encoded_result is None:
            encoded_result = np.array([np.array([])])

        encoded_result = encoded_result.tolist()
        raw_data = encoded_result[0] if isinstance(encoded_result, list) else encoded_result

        # Decode bytes to string
        if isinstance(raw_data, bytes):
            decoded_str = raw_data.decode("utf-8")
        else:
            decoded_str = str(raw_data)

        # Handle the case where Triton returns string like "[b'{...}']"
        if decoded_str.startswith("[b'") and decoded_str.endswith("']"):
            decoded_str = decoded_str[3:-2]
        elif decoded_str.startswith("[b\"") and decoded_str.endswith("\"]"):
            decoded_str = decoded_str[3:-2]

        # Decode escaped backslashes and unicode
        decoded_str = decoded_str.replace("\\\\", "\\")

        # Parse the JSON from Triton
        parsed_data = json.loads(decoded_str)

        # Normalize different response structures
        if isinstance(parsed_data, dict) and "output" in parsed_data:
            raw_output = parsed_data["output"]
        elif isinstance(parsed_data, dict):
            raw_output = [parsed_data]
        else:
            raw_output = parsed_data if isinstance(parsed_data, list) else [parsed_data]

        predictions: List[NerPrediction] = []

        for item in raw_output:
            source_text = item.get("source", "")
            ner_predictions_raw = item.get("nerPrediction", [])

            # Split source text into words and track character positions
            words = source_text.split()
            word_positions: List[Dict[str, Any]] = []
            pos = 0
            for word in words:
                word_start = source_text.find(word, pos)
                word_positions.append(
                    {
                        "word": word,
                        "start": word_start,
                        "end": word_start + len(word),
                    }
                )
                pos = word_start + len(word)

            # Create merged prediction groups (merge subword tokens starting with ##)
            prediction_groups: List[Dict[str, Any]] = []
            i = 0
            while i < len(ner_predictions_raw):
                pred = ner_predictions_raw[i]
                entity = pred.get("entity", "")
                tag = pred.get("class", "O")

                if not entity:
                    i += 1
                    continue

                # Merge subsequent "##" subword pieces (we only track first char + tag)
                j = i + 1
                while j < len(ner_predictions_raw):
                    next_entity = ner_predictions_raw[j].get("entity", "")
                    if next_entity.startswith("##"):
                        j += 1
                    else:
                        break

                prediction_groups.append(
                    {
                        "tag": tag,
                        "first_char": entity[0] if entity else "",
                    }
                )
                i = j

            # Map predictions to words using a simple first-character heuristic
            word_to_pred: Dict[int, Dict[str, Any]] = {}
            used_predictions = set()

            for pred_idx, pred_group in enumerate(prediction_groups):
                pred_first_char = pred_group["first_char"]

                for word_idx, word_info in enumerate(word_positions):
                    word = word_info["word"]
                    if (
                        word_idx not in word_to_pred
                        and word
                        and pred_first_char
                        and word[0] == pred_first_char
                        and pred_idx not in used_predictions
                    ):
                        word_to_pred[word_idx] = pred_group
                        used_predictions.add(pred_idx)
                        break

            # Build final NerTokenPrediction list
            token_predictions: List[NerTokenPrediction] = []
            for word_idx, word_info in enumerate(word_positions):
                word = word_info["word"]
                if word_idx in word_to_pred:
                    assigned_tag = word_to_pred[word_idx]["tag"]
                else:
                    assigned_tag = "O"

                token_predictions.append(
                    NerTokenPrediction(
                        token=word,
                        tag=assigned_tag,
                        tokenIndex=word_idx,
                        tokenStartIndex=word_info["start"],
                        tokenEndIndex=word_info["end"],
                    )
                )

            predictions.append(
                NerPrediction(source=source_text, nerPrediction=token_predictions)
            )

        return NerInferenceResponse(output=predictions)



