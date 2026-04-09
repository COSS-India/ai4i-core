"""
Endpoint Validation Module
~~~~~~~~~~~~~~~~~~~~~~~~~~

Two-level validation for inference endpoints:

  Level 1 – URL format check  (synchronous, always runs)
  Level 2 – Live inference probe (async, uses task-type-aware payloads)
"""

import httpx
import asyncio
import ipaddress
import socket
from enum import Enum
from typing import Optional, Dict, Any, List
from urllib.parse import urlparse

from pydantic import BaseModel

from logger import get_logger
from utils.probe_payloads import build_probe_payload

logger = get_logger("endpoint-validator")


# ---------------------------------------------------------------------------
# Result models
# ---------------------------------------------------------------------------

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


# ---------------------------------------------------------------------------
# Level 1 – URL format
# ---------------------------------------------------------------------------

_ALLOWED_SCHEMES = {"http", "https"}


def _looks_like_cluster_internal_hostname(hostname: str) -> bool:
    h = hostname.strip(".").lower()
    if h in {"localhost", "kubernetes.default.svc"}:
        return True
    if h.endswith(".svc") or h.endswith(".svc.cluster.local") or h.endswith(".cluster.local"):
        return True
    return False


def _is_disallowed_ip(ip: ipaddress._BaseAddress) -> bool:
    # Block internal/unsafe destinations to mitigate SSRF.
    return bool(
        ip.is_private
        or ip.is_loopback
        or ip.is_link_local
        or ip.is_reserved
        or ip.is_multicast
        or ip.is_unspecified
    )


async def _is_safe_host(hostname: str, *, resolve_timeout_s: float = 2.0) -> bool:
    """
    Resolve *hostname* and ensure it does not map to private/link-local/loopback/etc.
    If resolution fails or times out, treat it as unsafe (fail closed).
    """
    if not hostname:
        return False

    if _looks_like_cluster_internal_hostname(hostname):
        return False

    try:
        # If user supplied an IP literal, validate it directly.
        ip_literal = ipaddress.ip_address(hostname)
        return not _is_disallowed_ip(ip_literal)
    except ValueError:
        pass

    try:
        loop = asyncio.get_running_loop()
        infos = await asyncio.wait_for(
            loop.getaddrinfo(hostname, None, type=socket.SOCK_STREAM),
            timeout=resolve_timeout_s,
        )
    except Exception:
        return False

    for info in infos:
        try:
            ip = ipaddress.ip_address(info[4][0])
        except Exception:
            return False
        if _is_disallowed_ip(ip):
            return False

    return True


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


# ---------------------------------------------------------------------------
# Level 2 – Live inference probe
# ---------------------------------------------------------------------------

_VALIDATION_MODE_THRESHOLDS: Dict[str, int] = {
    "lenient": 500,
    "strict":  400,
}


async def test_inference(
    endpoint: str,
    task_type: str,
    request_schema: Optional[Dict[str, Any]] = None,
    api_key: Optional[str] = None,
    timeout: float = 15.0,
    validation_mode: str = "lenient",
    triton_schema: Optional[Dict[str, Any]] = None,
) -> ValidationDetail:
    """POST a probe payload and check the response status.

    Uses a native Triton V2 payload when *triton_schema* is available,
    otherwise a ULCA payload built from *request_schema* or built-in dummy.
    """
    fail_threshold = _VALIDATION_MODE_THRESHOLDS.get(
        validation_mode, _VALIDATION_MODE_THRESHOLDS["lenient"]
    )

    payload, payload_kind = build_probe_payload(task_type, request_schema, triton_schema)

    headers: Dict[str, str] = {"Content-Type": "application/json"}
    if api_key:
        headers["Authorization"] = f"Bearer {api_key}"

    logger.info(
        "Inference probe → %s  task_type=%s  mode=%s  kind=%s  payload=%s",
        endpoint, task_type, validation_mode, payload_kind, payload,
    )

    try:
        async with httpx.AsyncClient(timeout=timeout, verify=False) as client:
            response = await client.post(endpoint, json=payload, headers=headers)

        try:
            body = response.json()
        except Exception:
            body = response.text[:500] or "(empty)"

        logger.info(
            "Inference probe ← %s  status=%s  body=%s",
            endpoint, response.status_code, body,
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
                f"(validation_mode={validation_mode}): {body}"
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


# ---------------------------------------------------------------------------
# Orchestrator
# ---------------------------------------------------------------------------

async def validate_endpoint(
    endpoint: str,
    task_type: Optional[str] = None,
    request_schema: Optional[Dict[str, Any]] = None,
    api_key: Optional[str] = None,
    run_inference_test: bool = True,
    timeout: float = 15.0,
    validation_mode: str = "lenient",
    triton_schema: Optional[Dict[str, Any]] = None,
) -> EndpointValidationResult:
    """Run all validation levels against an inference *endpoint*."""
    details: List[ValidationDetail] = []

    url_result = validate_url_format(endpoint)
    details.append(url_result)

    if url_result.status == ValidationStatus.FAILED:
        return EndpointValidationResult(
            is_valid=False, endpoint=endpoint, details=details,
        )

    parsed = urlparse(endpoint)
    hostname = parsed.hostname or ""
    if not await _is_safe_host(hostname):
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
        return EndpointValidationResult(
            is_valid=False, endpoint=endpoint, details=details,
        )

    if run_inference_test and task_type:
        inference_result = await test_inference(
            endpoint=endpoint,
            task_type=task_type,
            request_schema=request_schema,
            api_key=api_key,
            timeout=timeout,
            validation_mode=validation_mode,
            triton_schema=triton_schema,
        )
        details.append(inference_result)
        logger.info(
            "Endpoint validation [%s] for %s (task=%s): %s",
            inference_result.status.value, endpoint, task_type,
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
        d.status in (ValidationStatus.PASSED, ValidationStatus.SKIPPED)
        for d in details
    )
    return EndpointValidationResult(
        is_valid=is_valid, endpoint=endpoint, details=details,
    )
