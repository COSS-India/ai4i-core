"""Direct proxy: POST /api/v1/chat/completions → configured upstream OpenAI-compatible URL."""

import json
import logging
from typing import Any

import httpx
from fastapi import APIRouter, HTTPException, Request
from fastapi.responses import JSONResponse

from app.clients.proxy_client import InferenceProxyClient
from app.core.config import app_env

logger = logging.getLogger(__name__)

router = APIRouter(tags=["chat_completions"])


async def _read_json_body(request: Request) -> Any:
    raw = await request.body()
    if not raw.strip():
        return {}
    try:
        return json.loads(raw.decode("utf-8"))
    except (UnicodeDecodeError, json.JSONDecodeError) as exc:
        raise HTTPException(status_code=400, detail="Request body must be valid JSON") from exc


@router.post("/chat/completions")
async def chat_completions(request: Request):
    """
    Proxy to ``CHAT_COMPLETIONS_ENDPOINT``.

    Forwards the JSON body unchanged (caller supplies ``model``, ``messages``, etc.).
    """
    url = (app_env.chat_completions_endpoint or "").strip()
    if not url:
        return JSONResponse(
            status_code=503,
            content={"detail": "Direct chat completions proxy is not configured (CHAT_COMPLETIONS_ENDPOINT)."},
        )

    payload = await _read_json_body(request)
    client = InferenceProxyClient()
    try:
        status_code, body = await client.forward(upstream_url=url, payload=payload)
    except httpx.RequestError as exc:
        logger.warning("Upstream chat/completions proxy failed: %s", exc)
        return JSONResponse(
            status_code=502,
            content={"error": {"message": str(exc), "type": "upstream_error"}},
        )
    except ValueError as exc:
        return JSONResponse(status_code=503, content={"detail": str(exc)})

    return JSONResponse(status_code=status_code, content=body)
