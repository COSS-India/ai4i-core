"""OCR-specific Triton client extending shared base."""

import json
import logging
from typing import Dict, List, Tuple

from tritonclient.http import InferInput, InferRequestedOutput

from ai4icore_model_management import TritonClient
from ai4icore_exceptions import TritonInferenceError

logger = logging.getLogger(__name__)


class OCRTritonClient(TritonClient):
    """Triton client with OCR-specific I/O preparation and batch inference."""

    def __init__(self, triton_url: str, api_key: str = None, model_name: str = None):
        """
        Initialize OCR Triton client.

        Args:
            triton_url: Triton server URL (host:port or http://host:port).
            api_key: Optional Bearer token for Authorization header.
            model_name: Triton model name (REQUIRED - resolved via Model Management).
        """
        if not model_name:
            raise ValueError("model_name is required and must be resolved via Model Management")
        super().__init__(triton_url, api_key=api_key)
        self.model_name = model_name

    def get_ocr_io_for_triton(
        self, images_base64: List[str]
    ) -> Tuple[List[InferInput], List[InferRequestedOutput]]:
        """
        Prepare inputs and outputs for Surya OCR Triton inference.

        Sends a batch of images; each image is a base64 string placed in a
        [batch_size, 1] BYTES tensor named IMAGE_DATA. The model returns a
        BYTES tensor named OUTPUT_TEXT, each entry being a JSON string.
        """
        inputs = [self._get_string_tensor(images_base64, "IMAGE_DATA")]
        outputs = [InferRequestedOutput("OUTPUT_TEXT")]
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
        except Exception as exc:
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
