"""
Core business logic for OCR inference.
"""

import base64
import logging
import time
from typing import List, Optional

import requests

from app.schemas.inference import (
    OCRInferenceRequest,
    OCRInferenceResponse,
    ImageInput,
    TextOutput,
)
from app.repositories.ocr_repository import OCRRepository
from app.clients.triton_client import OCRTritonClient
from ai4icore_exceptions import TritonInferenceError
from ai4icore_telemetry import StandardSpanManager

logger = logging.getLogger(__name__)
_standard_spans = StandardSpanManager("ocr")


class OCRService:
    """
    OCR inference service.

    Responsibilities:
    - Take OCRInferenceRequest
    - For each image:
      - Resolve base64 content (direct or via imageUri download)
      - Call Triton (Surya OCR)
      - Map OCR model output to OCRInferenceResponse
    - Log requests and results to database
    """

    def __init__(self, repository: OCRRepository, triton_client: OCRTritonClient, model_name: str):
        self.repository = repository
        self.triton_client = triton_client
        self.model_name = model_name

    def _resolve_image_base64(self, image: ImageInput) -> Optional[str]:
        """Resolve an image into base64 (content or download from URI)."""
        if image.imageContent:
            return image.imageContent

        if image.imageUri:
            try:
                resp = requests.get(str(image.imageUri), timeout=30)
                resp.raise_for_status()
                return base64.b64encode(resp.content).decode("utf-8")
            except Exception as exc:
                logger.error(
                    "Failed to download image from %s: %s", image.imageUri, exc
                )
                return None

        return None

    @staticmethod
    def _approx_image_bytes_from_b64(b64: str) -> int:
        if not b64:
            return 0
        try:
            return len(base64.b64decode(b64))
        except Exception:
            return 0

    async def run_inference(
        self,
        request: OCRInferenceRequest,
        user_id: Optional[int] = None,
        api_key_id: Optional[int] = None,
        session_id: Optional[int] = None,
    ) -> OCRInferenceResponse:
        """
        Async OCR inference entrypoint.

        Standard 7-phase spans: preprocess → resolve_model → triton_inference → postprocess → persist.
        """
        start_time = time.time()
        request_id = None
        service_id = request.config.serviceId
        language = request.config.language.sourceLanguage
        input_count = len(request.image)
        model_name = self.model_name

        with _standard_spans.inference(
            service_id=service_id,
            model_name=None,
            input_count=input_count,
            input_type="image",
            user_id=user_id,
            api_key_id=api_key_id,
            session_id=session_id,
            extra_attrs={"ocr.source_language": language},
        ) as parent_span:
            try:
                images_b64: List[str] = []
                with _standard_spans.preprocess() as preprocess_span:
                    resolved_count = 0
                    total_image_bytes = 0
                    for img_idx, img in enumerate(request.image):
                        if img.imageContent:
                            preprocess_span.add_event(
                                "ocr.image.resolve",
                                {"image_index": img_idx, "source": "content"},
                            )
                        elif img.imageUri:
                            preprocess_span.add_event(
                                "ocr.image.resolve",
                                {
                                    "image_index": img_idx,
                                    "source": "uri",
                                    "uri": str(img.imageUri)[:200],
                                },
                            )
                        else:
                            preprocess_span.add_event(
                                "ocr.image.resolve",
                                {"image_index": img_idx, "source": "none"},
                            )

                        resolved = self._resolve_image_base64(img)
                        if not resolved:
                            images_b64.append("")
                        else:
                            images_b64.append(resolved)
                            resolved_count += 1
                            total_image_bytes += self._approx_image_bytes_from_b64(resolved)

                    preprocess_span.set_attribute("ocr.input_count", input_count)
                    preprocess_span.set_attribute("ocr.resolved_count", resolved_count)
                    preprocess_span.set_attribute(
                        "ocr.failed_count", input_count - resolved_count
                    )
                    preprocess_span.set_attribute(
                        "ocr.input.total_image_bytes", total_image_bytes
                    )
                    preprocess_span.set_attribute(
                        "ocr.input.image_count", input_count
                    )
                    if parent_span is not None:
                        try:
                            parent_span.set_attribute(
                                "ocr.input.image_count", input_count
                            )
                            parent_span.set_attribute(
                                "ocr.input.total_image_bytes", total_image_bytes
                            )
                        except Exception:
                            pass

                with _standard_spans.resolve_model() as resolve_span:
                    resolve_span.set_attribute("ocr.model_name", model_name)
                    if parent_span is not None:
                        try:
                            parent_span.set_attribute("ocr.model_name", model_name)
                        except Exception:
                            pass

                non_empty_indices = [i for i, v in enumerate(images_b64) if v]
                non_empty_images = [images_b64[i] for i in non_empty_indices]
                ocr_results: List[dict] = []

                if non_empty_images:
                    try:
                        with _standard_spans.triton_inference() as triton_span:
                            triton_span.set_attribute(
                                "ocr.batch_size", len(non_empty_images)
                            )
                            triton_span.add_event(
                                "ocr.prepare_triton_inputs.completed",
                                {"batch_size": len(non_empty_images)},
                            )
                            ocr_results = self.triton_client.run_ocr_batch(
                                non_empty_images
                            )
                            triton_span.set_attribute(
                                "ocr.results_count", len(ocr_results)
                            )
                            triton_span.add_event(
                                "ocr.extract_results.completed",
                                {"result_count": len(ocr_results)},
                            )
                    except TritonInferenceError as exc:
                        if parent_span is not None:
                            try:
                                parent_span.add_event(
                                    "ocr.triton_failed",
                                    {
                                        "error.type": type(exc).__name__,
                                        "error.message": str(exc),
                                    },
                                )
                            except Exception:
                                pass
                        logger.error("OCR Triton inference failed: %s", exc)
                        outputs = [
                            TextOutput(source="", target="")
                            for _ in request.image
                        ]
                        with _standard_spans.persist() as persist_span:
                            db_request = await self.repository.create_request(
                                model_id=service_id,
                                language=language,
                                image_count=len(request.image),
                                user_id=user_id,
                                api_key_id=api_key_id,
                                session_id=session_id,
                            )
                            request_id = db_request.id
                            persist_span.set_attribute(
                                "ocr.request_id", str(request_id)
                            )
                            await self.repository.update_request_status(
                                db_request.id,
                                "failed",
                                error_message=str(exc),
                            )
                        if parent_span is not None:
                            try:
                                parent_span.set_attribute(
                                    "ocr.output_count", len(outputs)
                                )
                            except Exception:
                                pass
                        return OCRInferenceResponse(
                            output=outputs, config=request.config.dict()
                        )

                result_map = {idx: {} for idx in range(len(images_b64))}
                for local_idx, global_idx in enumerate(non_empty_indices):
                    if local_idx < len(ocr_results):
                        result_map[global_idx] = ocr_results[local_idx] or {}

                outputs: List[TextOutput] = []
                with _standard_spans.postprocess() as build_span:
                    successful_outputs = 0
                    for idx in range(len(request.image)):
                        ocr_result = result_map.get(idx, {})
                        if (
                            not images_b64[idx]
                            or not ocr_result
                            or not ocr_result.get("success", False)
                        ):
                            outputs.append(TextOutput(source="", target=""))
                            continue

                        full_text = ocr_result.get("full_text", "") or ""
                        outputs.append(TextOutput(source=full_text, target=""))
                        if full_text:
                            successful_outputs += 1
                    build_span.set_attribute(
                        "ocr.successful_outputs", successful_outputs
                    )
                    if parent_span is not None:
                        try:
                            parent_span.set_attribute(
                                "ocr.output_count", len(outputs)
                            )
                        except Exception:
                            pass

                with _standard_spans.persist() as persist_span:
                    db_request = await self.repository.create_request(
                        model_id=service_id,
                        language=language,
                        image_count=len(request.image),
                        user_id=user_id,
                        api_key_id=api_key_id,
                        session_id=session_id,
                    )
                    request_id = db_request.id
                    persist_span.set_attribute("ocr.request_id", str(request_id))
                    persist_span.add_event(
                        "ocr.db.request_created",
                        {"request_id": str(request_id)},
                    )

                    for output in outputs:
                        if output.source:
                            await self.repository.create_result(
                                request_id=db_request.id,
                                extracted_text=output.source,
                                page_count=1,
                            )
                            persist_span.add_event(
                                "ocr.db.result.created",
                                {"request_id": str(request_id)},
                            )

                    processing_time = time.time() - start_time
                    await self.repository.update_request_status(
                        db_request.id, "completed", processing_time
                    )
                    persist_span.add_event(
                        "ocr.db.request_completed",
                        {
                            "request_id": str(request_id),
                            "processing_time_seconds": processing_time,
                        },
                    )

                logger.info(
                    "OCR inference completed in %.2fs (request %s)",
                    time.time() - start_time,
                    request_id,
                )
                return OCRInferenceResponse(
                    output=outputs, config=request.config.dict()
                )

            except Exception as e:
                logger.error("OCR inference failed: %s", e)
                if request_id:
                    try:
                        await self.repository.update_request_status(
                            request_id, "failed", error_message=str(e)
                        )
                    except Exception as update_error:
                        logger.error(
                            "Failed to update request status: %s", update_error
                        )
                else:
                    try:
                        dr = await self.repository.create_request(
                            model_id=service_id,
                            language=language,
                            image_count=len(request.image),
                            user_id=user_id,
                            api_key_id=api_key_id,
                            session_id=session_id,
                        )
                        await self.repository.update_request_status(
                            dr.id, "failed", error_message=str(e)
                        )
                    except Exception as db_err:
                        logger.error(
                            "OCR: failed to record failed request: %s", db_err
                        )
                raise
