"""
HTTP probes for hosted model endpoints (Triton v2 first, then generic JSON POST).

Intended to be reusable from service create/update and from a future validation API.
"""

from __future__ import annotations

import json
from typing import Any, Dict, List, Optional
from urllib.parse import quote

import httpx

from logger import logger

from validation.model_metadata import (
    extract_model_name_from_inference_endpoint,
    extract_schema_request_response,
)
from validation.task_payloads import build_generic_probe_body
from validation.triton_payload import build_triton_infer_body
from validation.types import EndpointValidationFailure, EndpointValidationResult, ValidationStage
from validation.url import normalize_http_url


def _parse_response_body(text: str) -> Any:
    """Return parsed JSON when the server returns JSON; otherwise a truncated plain string."""
    raw = (text or "").strip()
    if not raw:
        return ""
    try:
        return json.loads(raw)
    except json.JSONDecodeError:
        return raw[:1500]


def _auth_headers(api_key: Optional[str]) -> Dict[str, str]:
    if not api_key:
        return {}
    return {"Authorization": f"Bearer {api_key}"}


async def _probe_triton(
    client: httpx.AsyncClient,
    base: str,
    model_name: str,
    headers: Dict[str, str],
    languages: Optional[List[Dict[str, Any]]] = None,
) -> EndpointValidationResult:
    """
    Triton v2 probe: model ready → metadata → test infer.

    1. ``GET /v2/models/{model}/ready`` → 200
    2. ``GET /v2/models/{model}`` → fetch input/output spec
    3. ``POST /v2/models/{model}/infer`` → task-aware dummy payload
    """
    enc = quote(model_name, safe="")

    # --- Model ready ---
    ready = await client.get(f"{base}/v2/models/{enc}/ready", headers=headers)
    if ready.status_code != 200:
        raise EndpointValidationFailure(
            ValidationStage.TRITON_MODEL_READY,
            f"Triton reports model '{model_name}' is not ready or not found.",
            details={
                "status_code": ready.status_code,
                "body": _parse_response_body(ready.text or ""),
            },
        )
    try:
        body = ready.json()
        if isinstance(body, dict) and body.get("ready") is False:
            raise EndpointValidationFailure(
                ValidationStage.TRITON_MODEL_READY,
                f"Triton model '{model_name}' is not ready.",
                details=body,
            )
    except EndpointValidationFailure:
        raise
    except Exception:
        pass

    # --- Model metadata (needed to build infer body) ---
    meta_resp = await client.get(f"{base}/v2/models/{enc}", headers=headers)
    if meta_resp.status_code != 200:
        logger.warning(
            "Triton model metadata GET failed; skipping infer probe.",
            extra={"status_code": meta_resp.status_code, "model": model_name},
        )
        return EndpointValidationResult(
            ok=True,
            stage=ValidationStage.TRITON_MODEL_READY,
            message=f"Triton model '{model_name}' is reachable and ready (infer probe skipped: metadata unavailable).",
            details={"model_name": model_name, "metadata_status": meta_resp.status_code},
        )

    try:
        metadata = meta_resp.json()
    except Exception as exc:
        logger.warning("Could not parse Triton model metadata JSON: %s", exc)
        return EndpointValidationResult(
            ok=True,
            stage=ValidationStage.TRITON_MODEL_READY,
            message=f"Triton model '{model_name}' is reachable and ready (infer probe skipped: metadata parse error).",
            details={"model_name": model_name},
        )

    # --- Build task-aware infer body ---
    infer_body = build_triton_infer_body(
        metadata if isinstance(metadata, dict) else {},
        languages=languages,
    )
    if not infer_body:
        return EndpointValidationResult(
            ok=True,
            stage=ValidationStage.TRITON_MODEL_READY,
            message=f"Triton model '{model_name}' is reachable and ready (infer probe skipped: no inputs in metadata).",
            details={"model_name": model_name},
        )

    # --- Infer ---
    infer_url = f"{base}/v2/models/{enc}/infer"
    infer = await client.post(
        infer_url,
        headers={**headers, "Content-Type": "application/json"},
        json=infer_body,
    )
    if infer.status_code != 200:
        body_preview = (infer.text or "")[:2000]
        logger.warning(
            "Triton infer probe failed: model_name=%s url=%s status=%s body=%s",
            model_name, infer_url, infer.status_code, body_preview,
        )
        raise EndpointValidationFailure(
            ValidationStage.TRITON_INFER,
            "Triton test inference failed for the hosted model.",
            details={
                "status_code": infer.status_code,
                "infer_url": infer_url,
                "body": _parse_response_body(infer.text or ""),
                "model_name": model_name,
            },
        )

    return EndpointValidationResult(
        ok=True,
        stage=ValidationStage.TRITON_INFER,
        message=f"Triton test inference succeeded for model '{model_name}'.",
        details={"model_name": model_name, "infer_url": infer_url},
    )


async def _probe_generic_json(
    client: httpx.AsyncClient,
    url: str,
    headers: Dict[str, str],
    body: Dict[str, Any],
) -> None:
    """POST JSON to the configured URL (custom REST backends)."""
    merged = {**headers, "Content-Type": "application/json"}
    resp = await client.post(url, headers=merged, json=body)
    if resp.status_code >= 500:
        raise EndpointValidationFailure(
            ValidationStage.GENERIC_JSON_PROBE,
            "Inference endpoint returned a server error during probe.",
            details={
                "status_code": resp.status_code,
                "body": _parse_response_body(resp.text or ""),
            },
        )
    if resp.status_code >= 400:
        logger.info(
            "Generic JSON probe returned client error (acceptable for reachability check).",
            extra={"status_code": resp.status_code},
        )


async def validate_hosted_inference_endpoint(
    endpoint_url: str,
    api_key: Optional[str],
    inference_endpoint: Optional[Dict[str, Any]],
    task_type: str,
    *,
    languages: Optional[List[Dict[str, Any]]] = None,
    timeout_seconds: float = 10.0,
) -> EndpointValidationResult:
    """
    Level 1: URL shape validation.
    Level 2: Triton v2 (health → model ready → test infer), else generic JSON POST probe.
    """
    normalized = normalize_http_url(endpoint_url)
    headers = _auth_headers(api_key)
    base = normalized.rstrip("/")

    inference_endpoint = inference_endpoint if isinstance(inference_endpoint, dict) else {}
    schema_req, _ = extract_schema_request_response(inference_endpoint)
    model_name = extract_model_name_from_inference_endpoint(inference_endpoint)

    timeout = httpx.Timeout(timeout_seconds)
    async with httpx.AsyncClient(timeout=timeout, follow_redirects=False) as client:
        try:
            live = await client.get(f"{base}/v2/health/live", headers=headers)
            ready_health = await client.get(f"{base}/v2/health/ready", headers=headers)
        except httpx.RequestError as exc:
            raise EndpointValidationFailure(
                ValidationStage.CONNECTIVITY,
                f"Could not connect to endpoint: {exc}",
                details={"error": str(exc)},
            ) from exc

        is_triton = live.status_code == 200 or ready_health.status_code == 200

        if is_triton:
            if not model_name:
                raise EndpointValidationFailure(
                    ValidationStage.TRITON_MODEL_READY,
                    "Triton was detected but the model metadata is missing a model name "
                    "(set schema.model_name or model_name on the model's inference endpoint).",
                    details={},
                )
            return await _probe_triton(client, base, model_name, headers, languages=languages)

        if live.status_code in (502, 503, 504) or ready_health.status_code in (502, 503, 504):
            raise EndpointValidationFailure(
                ValidationStage.CONNECTIVITY,
                "Endpoint is unreachable or unhealthy (HTTP 502/503/504).",
                details={
                    "live_status": live.status_code,
                    "ready_status": ready_health.status_code,
                },
            )

        # Non-Triton: POST task-aware dummy JSON
        body = build_generic_probe_body(schema_req, task_type)
        try:
            await _probe_generic_json(client, normalized, headers, body)
        except httpx.RequestError as exc:
            raise EndpointValidationFailure(
                ValidationStage.CONNECTIVITY,
                f"Could not reach endpoint for JSON probe: {exc}",
                details={"error": str(exc)},
            ) from exc

        return EndpointValidationResult(
            ok=True,
            stage=ValidationStage.GENERIC_JSON_PROBE,
            message="Endpoint accepted a JSON probe (non-Triton).",
            details={"task_type": task_type},
        )
