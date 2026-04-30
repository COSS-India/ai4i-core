"""NER-specific Triton client extending shared base."""

from typing import Any, Dict, List, Optional, Tuple, Union

from tritonclient.http import InferInput, InferRequestedOutput

from ai4icore_model_management import TritonClient


class NERTritonClient(TritonClient):
    """Triton client with NER-specific I/O preparation."""

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

    def get_ner_io_for_triton(
        self,
        input_texts: List[str],
        language: str,
    ) -> Tuple[List[InferInput], List[InferRequestedOutput]]:
        """Prepare NER inputs (INPUT_TEXT + LANG_ID) and outputs (OUTPUT_TEXT)."""
        input_text_tensor = self._get_string_tensor(input_texts, "INPUT_TEXT")
        lang_tensor = self._get_string_tensor([language] * len(input_texts), "LANG_ID")
        output = InferRequestedOutput("OUTPUT_TEXT")
        return [input_text_tensor, lang_tensor], [output]
