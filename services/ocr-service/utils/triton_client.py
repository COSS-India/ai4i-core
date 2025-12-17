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

    def __init__(self, triton_url: str, api_key: Optional[str] = None, model_name: str = None):
        """
        :param triton_url: Triton server URL (host:port or http://host:port).
        :param api_key: Optional Bearer token for Authorization header.
        :param model_name: Model name to use for inference (should be resolved by Model Management).
        """
        self.triton_url = self._normalize_url(triton_url)
        self.api_key = api_key
        self.model_name = model_name or "surya_ocr"  # Fallback only if not provided
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

    def run_ocr_batch(self, images_base64: List[str]) -> List[Dict]:
        """
        Run OCR on a batch of base64-encoded images.

        Returns a list of parsed JSON objects from the OCR model, one per input.
        If a particular result cannot be parsed, an empty dict is returned in
        that position.
        """
        if not images_base64:
            return []

        inputs, outputs = self.get_ocr_io_for_triton(images_base64)

        headers: Dict[str, str] = {}
        if self.api_key:
            headers["Authorization"] = f"Bearer {self.api_key}"

        try:
            response = self.client.infer(
                model_name=self.model_name,
                inputs=inputs,
                outputs=outputs,
                headers=headers or None,
            )
        except Exception as exc:  # pragma: no cover - external failure path
            logger.error("Triton OCR inference failed: %s", exc, exc_info=True)
            raise TritonInferenceError(f"Triton OCR inference failed: {exc}") from exc

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


