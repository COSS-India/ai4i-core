"""
Triton Inference Server client wrapper for OCR (Surya OCR).

This is a focused client for sending base64-encoded images to a Triton
deployment of the Surya OCR model and parsing its JSON output.
"""

import json
import logging
from typing import Dict, List, Optional, Tuple

import numpy as np
import tritonclient.http as http_client
from tritonclient.utils import np_to_triton_dtype

logger = logging.getLogger(__name__)


class TritonInferenceError(Exception):
    """Custom exception for Triton inference errors."""

    pass


class TritonClient:
    """Triton Inference Server client for OCR operations."""

    def __init__(self, triton_url: str, api_key: Optional[str] = None):
        """
        :param triton_url: Triton server URL (host:port or http://host:port).
        :param api_key: Optional Bearer token for Authorization header.
        """
        self.triton_url = self._normalize_url(triton_url)
        self.api_key = api_key
        self._client: Optional[http_client.InferenceServerClient] = None

    @staticmethod
    def _normalize_url(url: str) -> str:
        """Normalize Triton URL to host:port format."""
        url = url.strip()
        if url.startswith("http://"):
            url = url[7:]
        elif url.startswith("https://"):
            url = url[8:]
        return url

    @property
    def client(self) -> http_client.InferenceServerClient:
        """Lazy initialization of Triton HTTP client."""
        if self._client is None:
            logger.info("Initializing Triton client for OCR with URL: %s", self.triton_url)
            try:
                self._client = http_client.InferenceServerClient(
                    url=self.triton_url,
                    verbose=False,
                )
            except Exception as exc:  # pragma: no cover - connectivity error path
                logger.error(
                    "Failed to initialize Triton client with URL '%s': %s",
                    self.triton_url,
                    exc,
                    exc_info=True,
                )
                raise TritonInferenceError(
                    f"Failed to initialize Triton client: {exc}"
                ) from exc
        return self._client

    def _get_string_tensor(
        self, values: List[List[str]], tensor_name: str
    ) -> http_client.InferInput:
        """
        Create a BYTES/string tensor input.

        values should be a nested list shaped like [[value1], [value2], ...]
        so that the final shape is [batch_size, 1].
        """
        arr = np.array(values, dtype=object)
        inp = http_client.InferInput(
            tensor_name,
            arr.shape,
            np_to_triton_dtype(arr.dtype),
        )
        inp.set_data_from_numpy(arr)
        return inp

    def get_ocr_io_for_triton(
        self, images_base64: List[str]
    ) -> Tuple[List[http_client.InferInput], List[http_client.InferRequestedOutput]]:
        """
        Prepare inputs and outputs for Surya OCR Triton inference.

        We send a batch of images; each image is a base64 string placed in a
        [batch_size, 1] BYTES tensor named IMAGE_DATA. The model returns a
        BYTES tensor named OUTPUT_TEXT, each entry being a JSON string.
        """
        # Convert list[str] -> list[[str]] to get shape [batch_size, 1]
        nested = [[img] for img in images_base64]
        inputs = [self._get_string_tensor(nested, "IMAGE_DATA")]
        outputs = [http_client.InferRequestedOutput("OUTPUT_TEXT")]
        return inputs, outputs

    def list_models(self) -> List[str]:
        """List all available models on the Triton server."""
        try:
            models = self.client.get_model_repository_index()
            model_names = []
            if models:
                for model in models:
                    model_names.append(model.get('name', ''))
            logger.info(f"Found {len(model_names)} models at '{self.triton_url}': {model_names}")
            return model_names
        except Exception as e:
            logger.error(f"Failed to list models from Triton server at '{self.triton_url}': {e}", exc_info=True)
            return []

    def run_ocr_batch(self, images_base64: List[str], model_name: str = "surya_ocr") -> List[Dict]:
        """
        Run OCR on a batch of base64-encoded images.

        Args:
            images_base64: List of base64-encoded images
            model_name: Triton model name (default: "surya_ocr")

        Returns:
            List of parsed JSON objects from the OCR model, one per input.
        If a particular result cannot be parsed, an empty dict is returned in
        that position.
            
        Raises:
            TritonInferenceError: If Triton inference fails
        """
        if not images_base64:
            return []

        inputs, outputs = self.get_ocr_io_for_triton(images_base64)

        headers: Dict[str, str] = {}
        if self.api_key:
            headers["Authorization"] = f"Bearer {self.api_key}"

        try:
            # Check server health
            if not self.client.is_server_ready():
                raise TritonInferenceError(
                    f"Triton server at '{self.triton_url}' is not ready. "
                    f"Please verify the endpoint is correct and the server is running."
                )
            
            response = self.client.infer(
                model_name=model_name,
                inputs=inputs,
                outputs=outputs,
                headers=headers or None,
            )
        except TritonInferenceError:
            # Re-raise TritonInferenceError as-is
            raise
        except Exception as exc:
            error_msg = str(exc)
            logger.error(
                f"Triton OCR inference request failed for model '{model_name}' at '{self.triton_url}': {exc}",
                exc_info=True
            )
            # Provide more helpful error messages
            if "404" in error_msg or "Not Found" in error_msg or "model" in error_msg.lower() and "not found" in error_msg.lower():
                # Try to list available models to provide helpful error message
                try:
                    available_models = self.list_models()
                    if available_models:
                        raise TritonInferenceError(
                            f"Triton model '{model_name}' not found at endpoint '{self.triton_url}'. "
                            f"Available models: {', '.join(available_models)}. "
                            f"Please verify the model name (service ID) is correct."
                        )
                    else:
                        raise TritonInferenceError(
                            f"Triton model '{model_name}' not found at endpoint '{self.triton_url}'. "
                            f"Could not retrieve available models. Please verify the model name (service ID) and endpoint are correct."
                        )
                except Exception:
                    # If listing models fails, just provide the basic error
                    raise TritonInferenceError(
                        f"Triton model '{model_name}' not found at endpoint '{self.triton_url}'. "
                        f"Please verify the model name (service ID) and endpoint are correct."
                    )
            elif "Connection" in error_msg or "connect" in error_msg.lower() or "refused" in error_msg.lower():
                raise TritonInferenceError(
                    f"Cannot connect to Triton server at endpoint '{self.triton_url}'. "
                    f"Please verify the endpoint is correct and the server is running."
                )
            elif "timeout" in error_msg.lower():
                raise TritonInferenceError(
                    f"Triton inference request timed out for model '{model_name}' at endpoint '{self.triton_url}'. "
                    f"The server may be overloaded or the request is too large."
                )
            raise TritonInferenceError(
                f"Triton OCR inference request failed for model '{model_name}' at endpoint '{self.triton_url}': {exc}"
            ) from exc

        result = response.as_numpy("OUTPUT_TEXT")
        if result is None:
            return [{} for _ in images_base64]

        # result is expected to have shape [batch_size, 1]
        outputs_json: List[Dict] = []
        for idx in range(len(images_base64)):
            try:
                result_bytes = result[idx][0]
            except Exception:
                outputs_json.append({})
                continue

            if isinstance(result_bytes, bytes):
                result_str = result_bytes.decode("utf-8")
            else:
                result_str = str(result_bytes)

            logger.debug(
                "OCR Triton response[%d] preview=%s",
                idx,
                result_str[:200],
            )

            try:
                outputs_json.append(json.loads(result_str))
            except json.JSONDecodeError:
                logger.exception("Failed to parse OCR JSON from Triton for index %d", idx)
                outputs_json.append({})

        return outputs_json


