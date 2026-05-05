"""Direct OpenAI-compatible proxy.

Two routes — ``POST /api/v1/chat/completions`` and ``POST /api/v1/completions`` —
resolve the upstream from ``LLM_MODEL_ENDPOINTS[body.model]`` (or
``LLM_DEFAULT_ENDPOINT``) and forward the JSON payload unchanged.
"""

import json
import logging
from typing import Any, Optional

import httpx
from fastapi import APIRouter, HTTPException, Request
from fastapi.responses import JSONResponse

from app.clients.proxy_client import InferenceProxyClient
from app.core.config import app_env

logger = logging.getLogger(__name__)

router = APIRouter(tags=["openai_proxy"])


def _resolve_upstream_url(model: Optional[str], path: str) -> str:
    base = (app_env.llm_model_endpoints or {}).get(model) if model else None
    base = (base or app_env.llm_default_endpoint or "").strip()
    if not base:
        raise ValueError(
            "No upstream endpoint configured. Set LLM_MODEL_ENDPOINTS for the requested "
            "model or LLM_DEFAULT_ENDPOINT as a fallback."
        )
    return f"{base.rstrip('/')}{path}"


async def _read_json_body(request: Request) -> Any:
    raw = await request.body()
    if not raw.strip():
        return {}
    try:
        return json.loads(raw.decode("utf-8"))
    except (UnicodeDecodeError, json.JSONDecodeError) as exc:
        raise HTTPException(status_code=400, detail="Request body must be valid JSON") from exc


async def _proxy(request: Request, path: str) -> JSONResponse:
    payload = await _read_json_body(request)
    model = payload.get("model") if isinstance(payload, dict) else None

    try:
        url = _resolve_upstream_url(model=model, path=path)
    except ValueError as exc:
        return JSONResponse(status_code=503, content={"detail": str(exc)})

    try:
        status_code, body = await InferenceProxyClient().forward(upstream_url=url, payload=payload)
    except httpx.RequestError as exc:
        logger.warning("Upstream %s proxy failed: %s", path, exc)
        return JSONResponse(
            status_code=502,
            content={"error": {"message": str(exc), "type": "upstream_error"}},
        )

    return JSONResponse(status_code=status_code, content=body)


@router.post("/chat/completions")
async def chat_completions(request: Request) -> JSONResponse:
    return await _proxy(request, path="/v1/chat/completions")


@router.post("/completions")
async def completions(request: Request) -> JSONResponse:
    return await _proxy(request, path="/v1/completions")
