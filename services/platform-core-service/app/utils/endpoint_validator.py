"""
Two-level validation for inference endpoints.

  Level 1 — URL format check (synchronous, always runs)
  Level 2 — Live inference probe (async, task-type-aware payload)

Both levels also enforce SSRF protection: the hostname must resolve to a
publicly-routable IP (no private/loopback/link-local/etc. addresses).
"""

import logging
from enum import Enum
from typing import Any, Dict, List, Optional
from urllib.parse import urlparse

import httpx
from pydantic import BaseModel

from app.utils.probe_payloads import build_probe_payload
from app.utils.security import (
    is_safe_host,
    json_body_for_log,
    sanitize_url_for_log,
    truncate_for_log,
)

logger = logging.getLogger(__name__)


# ── Result models ──


class ValidationLevel(str, Enum):
    URL_FORMAT = "url_format"
    INFERENCE = "inference"


class ValidationStatus(str, Enum):
    PASSED = "passed"
    FAILED = "failed"
    SKIPPED = "skipped"


class ValidationDetail(BaseModel):
    level: ValidationLevel
    status: ValidationStatus
    message: str


class EndpointValidationResult(BaseModel):
    is_valid: bool
    endpoint: str
    details: List[ValidationDetail]


# ── Level 1 — URL format ──


_ALLOWED_SCHEMES = {"http", "https"}


def validate_url_format(url: str) -> ValidationDetail:
    """Validate that *url* is a well-formed HTTP(S) URL."""
    try:
        parsed = urlparse(url)
        if not parsed.scheme:
            return ValidationDetail(
                level=ValidationLevel.URL_FORMAT,
                status=ValidationStatus.FAILED,
                message=f"URL missing scheme (http/https). Got: '{url}'",
            )
        if parsed.scheme.lower() not in _ALLOWED_SCHEMES:
            return ValidationDetail(
                level=ValidationLevel.URL_FORMAT,
                status=ValidationStatus.FAILED,
                message=f"URL scheme must be http or https. Got: '{parsed.scheme}'",
            )
        if not parsed.netloc:
            return ValidationDetail(
                level=ValidationLevel.URL_FORMAT,
                status=ValidationStatus.FAILED,
                message=f"URL missing host. Got: '{url}'",
            )
        if parsed.username or parsed.password:
            return ValidationDetail(
                level=ValidationLevel.URL_FORMAT,
                status=ValidationStatus.FAILED,
                message="URL must not contain embedded credentials (userinfo).",
            )
        return ValidationDetail(
            level=ValidationLevel.URL_FORMAT,
            status=ValidationStatus.PASSED,
            message="URL format is valid.",
        )
    except Exception as exc:
        return ValidationDetail(
            level=ValidationLevel.URL_FORMAT,
            status=ValidationStatus.FAILED,
            message=f"URL parsing error: {exc}",
        )


# ── Level 2 — Live inference probe ──


_VALIDATION_MODE_THRESHOLDS: Dict[str, int] = {"lenient": 500, "strict": 400}


async def test_inference(
    endpoint: str,
    task_type: str,
    request_schema: Optional[Dict[str, Any]] = None,
    api_key: Optional[str] = None,
    timeout: float = 15.0,
    validation_mode: str = "lenient",
    skip_tls_verify: bool = False,
    triton_schema: Optional[Dict[str, Any]] = None,
) -> ValidationDetail:
    """POST a probe payload and check the response status."""
    fail_threshold = _VALIDATION_MODE_THRESHOLDS.get(
        validation_mode, _VALIDATION_MODE_THRESHOLDS["lenient"]
    )
    payload, payload_kind = build_probe_payload(task_type, request_schema, triton_schema)

    headers: Dict[str, str] = {"Content-Type": "application/json"}
    if api_key:
        headers["Authorization"] = f"Bearer {api_key}"

    safe_endpoint = sanitize_url_for_log(endpoint)
    logger.debug(
        "Inference probe → %s task_type=%s mode=%s kind=%s",
        safe_endpoint,
        task_type,
        validation_mode,
        payload_kind,
    )

    try:
        if skip_tls_verify:
            logger.warning("Endpoint probe TLS verification disabled.")
        async with httpx.AsyncClient(
            timeout=timeout, verify=not skip_tls_verify
        ) as client:
            response = await client.post(endpoint, json=payload, headers=headers)

        try:
            body_for_log = json_body_for_log(response.json())
        except Exception:
            body_for_log = response.text or "(empty)"

        logger.debug(
            "Inference probe ← %s status=%s body=%s",
            safe_endpoint,
            response.status_code,
            truncate_for_log(body_for_log, max_len=500),
        )

        if response.status_code < fail_threshold:
            return ValidationDetail(
                level=ValidationLevel.INFERENCE,
                status=ValidationStatus.PASSED,
                message=(
                    f"Inference endpoint is reachable and responded with "
                    f"HTTP {response.status_code} ({payload_kind} payload)."
                ),
            )

        return ValidationDetail(
            level=ValidationLevel.INFERENCE,
            status=ValidationStatus.FAILED,
            message=(
                f"Inference endpoint returned HTTP {response.status_code} "
                f"(validation_mode={validation_mode}): "
                f"{truncate_for_log(body_for_log, max_len=500)}"
            ),
        )
    except httpx.ConnectError:
        return ValidationDetail(
            level=ValidationLevel.INFERENCE,
            status=ValidationStatus.FAILED,
            message=f"Could not connect to endpoint: {endpoint}",
        )
    except httpx.TimeoutException:
        return ValidationDetail(
            level=ValidationLevel.INFERENCE,
            status=ValidationStatus.FAILED,
            message=f"Request timed out after {timeout}s: {endpoint}",
        )
    except Exception as exc:
        return ValidationDetail(
            level=ValidationLevel.INFERENCE,
            status=ValidationStatus.FAILED,
            message=f"Inference test error: {exc}",
        )


# ── Orchestrator ──


async def validate_endpoint(
    endpoint: str,
    task_type: Optional[str] = None,
    request_schema: Optional[Dict[str, Any]] = None,
    api_key: Optional[str] = None,
    run_inference_test: bool = True,
    timeout: float = 15.0,
    validation_mode: str = "lenient",
    skip_tls_verify: bool = False,
    triton_schema: Optional[Dict[str, Any]] = None,
) -> EndpointValidationResult:
    """Run all validation levels against an inference endpoint."""
    details: List[ValidationDetail] = []

    url_result = validate_url_format(endpoint)
    details.append(url_result)
    if url_result.status == ValidationStatus.FAILED:
        return EndpointValidationResult(is_valid=False, endpoint=endpoint, details=details)

    parsed = urlparse(endpoint)
    hostname = parsed.hostname or ""
    if not await is_safe_host(hostname):
        details.append(
            ValidationDetail(
                level=ValidationLevel.URL_FORMAT,
                status=ValidationStatus.FAILED,
                message=(
                    "Endpoint host is not allowed for probing (SSRF protection). "
                    f"Blocked hostname: '{hostname or '(empty)'}'"
                ),
            )
        )
        return EndpointValidationResult(is_valid=False, endpoint=endpoint, details=details)

    if run_inference_test and task_type:
        inference_result = await test_inference(
            endpoint=endpoint,
            task_type=task_type,
            request_schema=request_schema,
            api_key=api_key,
            timeout=timeout,
            validation_mode=validation_mode,
            skip_tls_verify=skip_tls_verify,
            triton_schema=triton_schema,
        )
        details.append(inference_result)
        logger.info(
            "Endpoint validation [%s] for %s (task=%s): %s",
            inference_result.status.value,
            endpoint,
            task_type,
            inference_result.message,
        )
    elif run_inference_test:
        details.append(
            ValidationDetail(
                level=ValidationLevel.INFERENCE,
                status=ValidationStatus.SKIPPED,
                message="Inference test skipped: task_type not provided.",
            )
        )

    is_valid = all(
        d.status in (ValidationStatus.PASSED, ValidationStatus.SKIPPED) for d in details
    )
    return EndpointValidationResult(is_valid=is_valid, endpoint=endpoint, details=details)
