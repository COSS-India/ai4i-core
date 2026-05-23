"""
Main inference router with unified /inference endpoint.
Handles all inference requests regardless of task type.
Integrates orchestration, factory, and telemetry.
"""

from typing import Any, Dict, Optional
from fastapi import APIRouter, Request, HTTPException, Depends
import logging

from orchestrator import Orchestrator, OrchestratorError
from models.common import GenericInferenceRequest, GenericInferenceResponse
from models.task_types import task_registry


logger = logging.getLogger(__name__)
router = APIRouter(tags=["inference"])


class InferenceRouterError(Exception):
    """Base exception for routing errors."""

    pass


async def get_orchestrator() -> Orchestrator:
    """
    Dependency for Orchestrator instance.
    Can be overridden in tests.
    """
    return Orchestrator()


def _make_dedicated_endpoint(task_type_value: str):
    """Helper that builds a dedicated-endpoint handler for a given task_type."""
    async def handler(
        payload: Dict[str, Any],
        orchestrator: Orchestrator = Depends(get_orchestrator),
    ) -> Dict[str, Any]:
        import time
        start_time = time.time()
        try:
            request_payload = payload.copy()
            if not request_payload.get("task_type"):
                request_payload["task_type"] = task_type_value
            task_type = request_payload["task_type"].upper()
            logger.info(f"Inference request: task_type={task_type}")
            result = await orchestrator.route_inference(payload=request_payload)
            duration_ms = (time.time() - start_time) * 1000
            logger.info(f"✓ Inference completed: task_type={task_type}, duration_ms={duration_ms:.2f}ms")
            return result
        except Exception as e:
            duration_ms = (time.time() - start_time) * 1000
            logger.error(f"✗ Inference failed: {str(e)}, duration_ms={duration_ms:.2f}ms")
            raise HTTPException(status_code=400, detail=str(e))
    return handler


@router.post(
    "/inference",
    response_model=GenericInferenceResponse,
    summary="Unified Inference Endpoint",
    description="Route inference requests to appropriate TaskService based on task_type",
)
async def run_inference(
    payload: Dict[str, Any],
    orchestrator: Orchestrator = Depends(get_orchestrator),
) -> Dict[str, Any]:
    """
    Unified inference endpoint accepting requests for all task types.
    Routes to appropriate TaskService via Orchestrator.
    """
    import time
    start_time = time.time()

    try:
        task_type = payload.get("task_type", "").upper()
        logger.info(f"Inference request: task_type={task_type}")
        result = await orchestrator.route_inference(payload=payload)
        duration_ms = (time.time() - start_time) * 1000
        logger.info(f"✓ Inference completed: task_type={task_type}, duration_ms={duration_ms:.2f}ms")
        return result

    except Exception as e:
        duration_ms = (time.time() - start_time) * 1000
        logger.error(f"✗ Inference failed: {str(e)}, duration_ms={duration_ms:.2f}ms")
        raise HTTPException(status_code=400, detail=str(e))


# ---------------------------------------------------------------------------
# Dedicated task endpoints — mirror old per-service paths for existing clients
# ---------------------------------------------------------------------------

@router.post("/nmt/inference", response_model=GenericInferenceResponse,
             summary="NMT Inference Endpoint")
async def run_nmt_inference(
    payload: Dict[str, Any],
    orchestrator: Orchestrator = Depends(get_orchestrator),
) -> Dict[str, Any]:
    """Dedicated NMT endpoint — injects task_type automatically."""
    return await _make_dedicated_endpoint("NMT")(payload, orchestrator)


@router.post("/asr/inference", response_model=GenericInferenceResponse,
             summary="ASR Inference Endpoint",
             description="Mirrors the old asr-service path so existing clients work without changes.")
async def run_asr_inference(
    payload: Dict[str, Any],
    orchestrator: Orchestrator = Depends(get_orchestrator),
) -> Dict[str, Any]:
    """Dedicated ASR endpoint — injects task_type automatically."""
    return await _make_dedicated_endpoint("ASR")(payload, orchestrator)


@router.post("/ner/inference", response_model=GenericInferenceResponse,
             summary="NER Inference Endpoint")
async def run_ner_inference(
    payload: Dict[str, Any],
    orchestrator: Orchestrator = Depends(get_orchestrator),
) -> Dict[str, Any]:
    """Dedicated NER endpoint — injects task_type automatically."""
    return await _make_dedicated_endpoint("NER")(payload, orchestrator)


@router.post("/transliteration/inference", response_model=GenericInferenceResponse,
             summary="Transliteration Inference Endpoint")
async def run_transliteration_inference(
    payload: Dict[str, Any],
    orchestrator: Orchestrator = Depends(get_orchestrator),
) -> Dict[str, Any]:
    """Dedicated Transliteration endpoint — injects task_type automatically."""
    return await _make_dedicated_endpoint("TRANSLITERATION")(payload, orchestrator)


@router.post("/language-detection/inference", response_model=GenericInferenceResponse,
             summary="Language Detection Inference Endpoint")
async def run_language_detection_inference(
    payload: Dict[str, Any],
    orchestrator: Orchestrator = Depends(get_orchestrator),
) -> Dict[str, Any]:
    """Dedicated Language Detection endpoint — injects task_type automatically."""
    return await _make_dedicated_endpoint("LANGUAGE_DETECTION")(payload, orchestrator)


@router.post("/audio-lang-detection/inference", response_model=GenericInferenceResponse,
             summary="Audio Language Detection Inference Endpoint",
             description="Mirrors the old audio-lang-detection-service path so existing clients work without changes.")
async def run_audio_lang_detection_inference(
    payload: Dict[str, Any],
    orchestrator: Orchestrator = Depends(get_orchestrator),
) -> Dict[str, Any]:
    """Dedicated ALD endpoint — injects task_type automatically."""
    return await _make_dedicated_endpoint("AUDIO_LANGUAGE_DETECTION")(payload, orchestrator)


# ---------------------------------------------------------------------------
# Utility endpoints
# ---------------------------------------------------------------------------

@router.get(
    "/inference/health",
    summary="Health Check",
    description="Check if inference service is healthy",
)
async def health_check() -> Dict[str, str]:
    return {"status": "healthy", "message": "Inference service is operational"}


@router.get(
    "/inference/tasks",
    summary="List Available Tasks",
    description="Get list of supported inference task types",
)
async def list_available_tasks() -> Dict[str, list]:
    return {"tasks": [
        "NMT", "ASR", "NER", "OCR", "LLM", "TTS", "PII",
        "LANGUAGE_DETECTION", "SPEAKER_DIARIZATION", "TRANSLITERATION",
        "AUDIO_LANGUAGE_DETECTION", "LANGUAGE_DIARIZATION", "SMR",
    ]}
