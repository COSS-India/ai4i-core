"""
Image model service implementations.

Each class inherits the full pipeline from ImageBase.
Model classes are minimal — they only add task-specific behaviour
on top of the ImageBase pipeline.
"""

from typing import Any, Dict, List, Optional, cast

from pydantic import BaseModel

from services.base.image_base import ImageBase
from models.schemas.ocr import (
    OCRInferenceRequest,
    OCRInferenceResponse,
    OCROutput,
)


class OCRDefaultModel(ImageBase):
    """
    Default OCR model service (surya_ocr_ensemble).

    Inherits the full image pipeline from ImageBase; overrides only the bits
    that differ for OCR:
      run_inference                → resolve → KServe v2 Triton call → postprocess
      postprocess_output           → decode bytes → unwrap Surya envelope → wrap in OCROutput
    """

    # Triton tensor names for the Surya OCR ensemble. Matches the curl contract.
    _IMAGE_INPUT_TENSOR = "IMAGE_DATA"
    _TEXT_OUTPUT_TENSOR = "OUTPUT_TEXT"

    async def run_inference(self, request: BaseModel) -> BaseModel:
        ocr_request = cast(OCRInferenceRequest, request)
        config = ocr_request.config

        service_id, model_name, triton_endpoint, api_key, _adapter = (
            await self._resolve_service_and_model(config)
        )
        self.logger.info(
            f"OCR resolved: service_id={service_id}, model={model_name}, "
            f"endpoint={triton_endpoint}"
        )

        # Resolve each image to base64 and build a [batch, 1] BYTES tensor.
        items_b64: List[str] = []
        for item in ocr_request.image:
            item_dict = item if isinstance(item, dict) else item.dict()
            items_b64.append(await self._resolve_image_base64(item_dict))

        triton_inputs = [
            {
                "name": self._IMAGE_INPUT_TENSOR,
                "datatype": "BYTES",
                "shape": [len(items_b64), 1],
                "data": [[b64] for b64 in items_b64],
            }
        ]
        triton_outputs = [self._TEXT_OUTPUT_TENSOR]

        raw_output = await self._call_triton_inference(
            triton_endpoint=triton_endpoint,
            triton_inputs=triton_inputs,
            triton_outputs=triton_outputs,
            api_key=api_key,
        )

        response_data = self._extract_text_outputs(raw_output)
        return await self.postprocess_output(response_data)

    def _extract_text_outputs(self, raw_output: Dict[str, Any]) -> List[Dict[str, Any]]:
        """Pull the OUTPUT_TEXT tensor out of a KServe v2 response, one dict per image."""
        outputs = raw_output.get("outputs") or []
        text_tensor: Optional[Dict[str, Any]] = next(
            (t for t in outputs if t.get("name") == self._TEXT_OUTPUT_TENSOR),
            None,
        )
        data: List[Any] = (text_tensor or {}).get("data", []) or []
        return [{"text": value} for value in data]

    async def postprocess_output(
        self, response_items: List[Dict[str, Any]], **kwargs: Any
    ) -> OCRInferenceResponse:
        """
        OCR postprocess:
          _decode_output_bytes → _unwrap_surya_envelope (per item) → _wrap_text_output
        """
        decoded = await self._decode_output_bytes(response_items)
        for item in decoded:
            if "text" in item:
                item["text"] = self._unwrap_surya_envelope(item["text"])
        return await self._wrap_text_output(decoded)

    async def _wrap_text_output(
        self, decoded_items: List[Dict[str, Any]]
    ) -> OCRInferenceResponse:
        output_list = [
            OCROutput(text=str(item.get("text", "")))
            for item in decoded_items
        ]
        return OCRInferenceResponse(output=output_list)


# ---------------------------------------------------------------------------
# Future image task default models — to be implemented in upcoming PRs
# ---------------------------------------------------------------------------

class DocumentLayoutDefaultModel(ImageBase):
    """
    Default Document Layout model service.
    Will override: postprocess_output (returns bounding boxes + text per region),
                   _empty_output (no regions).
    """
    pass


class VisionDefaultModel(ImageBase):
    """
    Default Vision (image classification / captioning) model service.
    Will override: preprocess_input (uses _decode_image + _resize_image),
                   postprocess_output (label / caption schema).
    """
    pass
