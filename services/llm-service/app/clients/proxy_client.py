"""Thin HTTP proxy for direct OpenAI-compatible upstream inference."""

from __future__ import annotations

from typing import Any, Tuple

import httpx

from app.core.config import app_env


class InferenceProxyClient:
    """
    Forwards the caller's JSON value to the upstream URL exactly as received.
    Does not inject, modify, or remove any fields (including ``model``).
    """

    def __init__(self) -> None:
        self.timeout = float(app_env.inference_timeout)

    async def forward(self, upstream_url: str, payload: Any) -> Tuple[int, Any]:
        if not (upstream_url or "").strip():
            raise ValueError("upstream URL is not configured")

        async with httpx.AsyncClient(timeout=self.timeout) as client:
            response = await client.post(
                upstream_url.strip(),
                json=payload,
                headers={"Content-Type": "application/json"},
            )

        try:
            body = response.json()
        except Exception:
            body = {"raw": response.text}

        return response.status_code, body
