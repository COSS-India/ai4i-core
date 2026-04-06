"""Extract model name and schema from model_management ``inference_endpoint`` JSON."""

from __future__ import annotations

from typing import Any, Dict, Optional


def extract_model_name_from_inference_endpoint(inference_endpoint: Optional[Dict[str, Any]]) -> Optional[str]:
    """
    Resolve Triton / hosted model name from stored inference metadata.

    Mirrors the resolution order used in ai4icore_model_management middleware.
    """
    if not inference_endpoint or not isinstance(inference_endpoint, dict):
        return None

    schema = inference_endpoint.get("schema")
    if isinstance(schema, dict):
        name = schema.get("model_name") or schema.get("modelName") or schema.get("name")
        if name:
            return str(name)

    name = (
        inference_endpoint.get("model_name")
        or inference_endpoint.get("modelName")
        or inference_endpoint.get("model")
    )
    if name:
        return str(name)
    return None


def extract_schema_request_response(
    inference_endpoint: Optional[Dict[str, Any]],
) -> tuple[Dict[str, Any], Dict[str, Any]]:
    """Return ``(request, response)`` dicts from nested schema, defaulting to empty dicts."""
    if not inference_endpoint or not isinstance(inference_endpoint, dict):
        return {}, {}
    schema = inference_endpoint.get("schema")
    if not isinstance(schema, dict):
        return {}, {}
    req = schema.get("request")
    resp = schema.get("response")
    return (
        req if isinstance(req, dict) else {},
        resp if isinstance(resp, dict) else {},
    )
