"""Language-Detection-specific Triton client extending shared base."""

from typing import Any, Dict, List, Optional, Tuple, Union

import numpy as np
from tritonclient.http import InferInput, InferRequestedOutput
from tritonclient.utils import np_to_triton_dtype

from ai4icore_model_management import TritonClient


class LanguageDetectionTritonClient(TritonClient):
    """Triton client with Language-Detection-specific I/O preparation."""

    def send_triton_request(  # type: ignore[override]
        self,
        model_name: str,
        inputs: List[InferInput],
        outputs: List[InferRequestedOutput],
        headers: Optional[Dict[str, str]] = None,
        model_version: str = "1",
        *,
        trace_attributes: Optional[Dict[str, Union[str, int, float, bool]]] = None,
        **kwargs: Any,
    ):
        """
        Backward-compatible wrapper.

        Some deployments still run an older `ai4icore_model_management.TritonClient`
        without the `trace_attributes=` keyword. In that case, we retry without it.
        """
        try:
            return super().send_triton_request(
                model_name,
                inputs,
                outputs,
                headers=headers,
                model_version=model_version,
                trace_attributes=trace_attributes,
                **kwargs,
            )
        except TypeError:
            return super().send_triton_request(
                model_name,
                inputs,
                outputs,
                headers=headers,
                model_version=model_version,
                **kwargs,
            )

    def get_language_detection_io_for_triton(
        self,
        input_texts: List[str],
    ) -> Tuple[List[InferInput], List[InferRequestedOutput]]:
        """Prepare language detection inputs and outputs for Triton.

        IndicLID expects shape [batch_size, 1] for INPUT_TEXT.
        """
        nested_texts = [[text] for text in input_texts]
        inputs = [
            self._get_string_tensor_2d(nested_texts, "INPUT_TEXT"),
        ]
        outputs = [InferRequestedOutput("OUTPUT_TEXT")]
        return inputs, outputs

    # ------------------------------------------------------------------
    # Helper for 2D string tensors (IndicLID expects [batch, 1])
    # ------------------------------------------------------------------
    @staticmethod
    def _get_string_tensor_2d(
        string_values: List[List[str]], tensor_name: str
    ) -> InferInput:
        """Create 2D string tensor for Triton input (for IndicLID)."""
        np_array = np.array(string_values, dtype=object)
        input_tensor = InferInput(
            tensor_name,
            np_array.shape,
            np_to_triton_dtype(np_array.dtype),
        )
        input_tensor.set_data_from_numpy(np_array)
        return input_tensor
