"""
Two-level validation for inference endpoints.

  Level 1 — URL format check (synchronous, always runs)
  Level 2 — Live inference probe (async, task-type-aware payload)
             - sync endpoints: single POST, checked for reachability and
               (when an expected response schema is supplied) response shape
             - async endpoints: POST to submit, then poll a separate
               pollingUrl until the job completes, fails, or the poll
               budget runs out

Both levels also enforce SSRF protection: the hostname must resolve to a
publicly-routable IP (no private/loopback/link-local/etc. addresses).
"""

import asyncio
import logging
from enum import Enum
from typing import Any, Dict, List, Optional, Tuple
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
    RESPONSE_SHAPE = "response_shape"


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


# ── Level 2 — Response shape matching ──


def _type_name(v: Any) -> str:
    if v is None:
        return "null"
    if isinstance(v, bool):
        return "boolean"
    if isinstance(v, (int, float)):
        return "number"
    if isinstance(v, str):
        return "string"
    if isinstance(v, list):
        return "array"
    if isinstance(v, dict):
        return "object"
    return type(v).__name__


def _shape_mismatch(actual: Any, expected: Any, path: str = "response") -> Optional[str]:
    """Structurally compare *actual* against *expected* (a sample response
    object). Returns None if compatible, else a human-readable description
    of the first mismatch found. Only shape/type is compared — never values
    — and ``None``/``null`` anywhere in *expected* acts as a wildcard."""
    if expected is None:
        return None
    if isinstance(expected, dict):
        if not isinstance(actual, dict):
            return f"{path}: expected an object, got {_type_name(actual)}"
        for key, exp_val in expected.items():
            if key not in actual:
                return f"{path}.{key}: missing from response"
            mismatch = _shape_mismatch(actual[key], exp_val, f"{path}.{key}")
            if mismatch:
                return mismatch
        return None
    if isinstance(expected, list):
        if not isinstance(actual, list):
            return f"{path}: expected an array, got {_type_name(actual)}"
        if expected and not actual:
            return f"{path}: expected a non-empty array"
        if expected and actual:
            return _shape_mismatch(actual[0], expected[0], f"{path}[0]")
        return None
    if isinstance(expected, bool):
        if not isinstance(actual, bool):
            return f"{path}: expected boolean, got {_type_name(actual)}"
        return None
    if isinstance(expected, (int, float)):
        if isinstance(actual, bool) or not isinstance(actual, (int, float)):
            return f"{path}: expected number, got {_type_name(actual)}"
        return None
    if isinstance(expected, str):
        if not isinstance(actual, str):
            return f"{path}: expected string, got {_type_name(actual)}"
        return None
    return None


def validate_response_shape(response_body: Any, expected_schema: Dict[str, Any]) -> ValidationDetail:
    """Compare a parsed JSON response against an admin-supplied sample shape."""
    mismatch = _shape_mismatch(response_body, expected_schema)
    if mismatch:
        return ValidationDetail(
            level=ValidationLevel.RESPONSE_SHAPE,
            status=ValidationStatus.FAILED,
            message=f"Response did not match the expected schema — {mismatch}.",
        )
    return ValidationDetail(
        level=ValidationLevel.RESPONSE_SHAPE,
        status=ValidationStatus.PASSED,
        message="Response matched the expected schema.",
    )


# ── Level 2 — Live inference probe (sync) ──


# Both modes accept any response with status < 500 (i.e. any non-5xx).
#
# "strict" (< 400) was originally intended to require a successful 2xx/3xx
# response from the inference endpoint. In practice this is unworkable:
# inference servers routinely return 400/422 for probe payloads that don't
# match the exact model schema (wrong language pair, missing fields, etc.),
# even when the server is fully healthy. A 4xx response proves the server is
# alive and processing requests — only 5xx or a connection failure indicates
# a real problem. Keeping both thresholds at 500 preserves the config knob
# for backwards compatibility without silently accepting broken endpoints.
# Response *content* is no longer trusted just because the status passed —
# see validate_response_shape, applied by the orchestrator below.
_VALIDATION_MODE_THRESHOLDS: Dict[str, int] = {"lenient": 500, "strict": 500}


def _build_probe_headers(api_key: Optional[str]) -> Dict[str, str]:
    headers: Dict[str, str] = {"Content-Type": "application/json"}
    if api_key:
        headers["Authorization"] = f"Bearer {api_key}"
    return headers


async def test_inference(
    endpoint: str,
    task_type: str,
    request_schema: Optional[Dict[str, Any]] = None,
    api_key: Optional[str] = None,
    timeout: float = 15.0,
    validation_mode: str = "lenient",
    skip_tls_verify: bool = False,
    triton_schema: Optional[Dict[str, Any]] = None,
) -> Tuple[ValidationDetail, Optional[Any]]:
    """POST a probe payload and check the response status.

    Returns ``(detail, parsed_json_body)``. *parsed_json_body* is only
    populated when the transport-level check passed — callers should treat
    it as the value to run a response-shape check against, and ignore it on
    failure.
    """
    fail_threshold = _VALIDATION_MODE_THRESHOLDS.get(
        validation_mode, _VALIDATION_MODE_THRESHOLDS["lenient"]
    )
    payload, payload_kind = build_probe_payload(task_type, request_schema, triton_schema)
    headers = _build_probe_headers(api_key)

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
            response_json: Optional[Any] = response.json()
        except Exception:
            response_json = None

        body_for_log = (
            json_body_for_log(response_json)
            if response_json is not None
            else (response.text or "(empty)")
        )

        logger.debug(
            "Inference probe ← %s status=%s body=%s",
            safe_endpoint,
            response.status_code,
            truncate_for_log(body_for_log, max_len=500),
        )

        if response.status_code < fail_threshold:
            return (
                ValidationDetail(
                    level=ValidationLevel.INFERENCE,
                    status=ValidationStatus.PASSED,
                    message=(
                        f"Inference endpoint is reachable and responded with "
                        f"HTTP {response.status_code} ({payload_kind} payload)."
                    ),
                ),
                response_json,
            )

        return (
            ValidationDetail(
                level=ValidationLevel.INFERENCE,
                status=ValidationStatus.FAILED,
                message=(
                    f"Inference endpoint returned HTTP {response.status_code} "
                    f"(validation_mode={validation_mode}): "
                    f"{truncate_for_log(body_for_log, max_len=500)}"
                ),
            ),
            None,
        )
    except httpx.ConnectError:
        return (
            ValidationDetail(
                level=ValidationLevel.INFERENCE,
                status=ValidationStatus.FAILED,
                message=f"Could not connect to endpoint: {endpoint}",
            ),
            None,
        )
    except httpx.TimeoutException:
        return (
            ValidationDetail(
                level=ValidationLevel.INFERENCE,
                status=ValidationStatus.FAILED,
                message=f"Request timed out after {timeout}s: {endpoint}",
            ),
            None,
        )
    except Exception as exc:
        return (
            ValidationDetail(
                level=ValidationLevel.INFERENCE,
                status=ValidationStatus.FAILED,
                message=f"Inference test error: {exc}",
            ),
            None,
        )


# ── Level 2 — Live inference probe (async / polling) ──


async def test_inference_async(
    endpoint: str,
    polling_url: str,
    poll_interval_ms: Optional[int],
    task_type: str,
    request_schema: Optional[Dict[str, Any]] = None,
    api_key: Optional[str] = None,
    timeout: float = 15.0,
    skip_tls_verify: bool = False,
    triton_schema: Optional[Dict[str, Any]] = None,
    max_poll_attempts: int = 10,
    max_poll_wait_seconds: float = 60.0,
) -> Tuple[ValidationDetail, Optional[Any]]:
    """Submit a probe request, then poll *polling_url* until the async job
    completes (HTTP 200), fails, or the poll budget runs out.

    Mirrors ULCA's ``validateAsyncUrl``: POST the sample payload to
    *endpoint*, then repeatedly re-POST whatever JSON body came back to
    *polling_url* every ``poll_interval_ms`` until it returns 200 (done) or
    a non-202 failure. Bounded by both ``max_poll_attempts`` and
    ``max_poll_wait_seconds`` (whichever is hit first) — unlike the
    reference implementation's unbounded loop, a stuck partner endpoint
    cannot hang this check forever.
    """
    payload, payload_kind = build_probe_payload(task_type, request_schema, triton_schema)
    headers = _build_probe_headers(api_key)
    safe_endpoint = sanitize_url_for_log(endpoint)
    safe_polling_url = sanitize_url_for_log(polling_url)
    interval_s = max((poll_interval_ms or 1000) / 1000.0, 0.1)

    try:
        async with httpx.AsyncClient(timeout=timeout, verify=not skip_tls_verify) as client:
            submit_response = await client.post(endpoint, json=payload, headers=headers)

            if submit_response.status_code >= 500:
                return (
                    ValidationDetail(
                        level=ValidationLevel.INFERENCE,
                        status=ValidationStatus.FAILED,
                        message=(
                            f"Async endpoint returned HTTP "
                            f"{submit_response.status_code} on submit "
                            f"({payload_kind} payload)."
                        ),
                    ),
                    None,
                )

            try:
                poll_body: Any = submit_response.json()
            except Exception:
                poll_body = {}

            elapsed = 0.0
            for attempt in range(1, max_poll_attempts + 1):
                if elapsed >= max_poll_wait_seconds:
                    break
                slept = min(interval_s, max_poll_wait_seconds - elapsed)
                await asyncio.sleep(slept)
                elapsed += slept

                poll_response = await client.post(polling_url, json=poll_body, headers=headers)
                if poll_response.status_code == 202:
                    continue
                if poll_response.status_code == 200:
                    try:
                        final_body = poll_response.json()
                    except Exception as exc:
                        return (
                            ValidationDetail(
                                level=ValidationLevel.INFERENCE,
                                status=ValidationStatus.FAILED,
                                message=(
                                    "Async endpoint's polled result was not "
                                    f"valid JSON: {exc}"
                                ),
                            ),
                            None,
                        )
                    return (
                        ValidationDetail(
                            level=ValidationLevel.INFERENCE,
                            status=ValidationStatus.PASSED,
                            message=(
                                f"Async endpoint completed after {attempt} "
                                f"poll(s) ({payload_kind} payload)."
                            ),
                        ),
                        final_body,
                    )
                return (
                    ValidationDetail(
                        level=ValidationLevel.INFERENCE,
                        status=ValidationStatus.FAILED,
                        message=(
                            f"Polling {safe_polling_url} returned HTTP "
                            f"{poll_response.status_code}."
                        ),
                    ),
                    None,
                )

            return (
                ValidationDetail(
                    level=ValidationLevel.INFERENCE,
                    status=ValidationStatus.FAILED,
                    message=(
                        f"Async endpoint {safe_endpoint} did not complete "
                        f"within {max_poll_wait_seconds}s "
                        f"({max_poll_attempts} poll attempts against "
                        f"{safe_polling_url})."
                    ),
                ),
                None,
            )
    except httpx.ConnectError:
        return (
            ValidationDetail(
                level=ValidationLevel.INFERENCE,
                status=ValidationStatus.FAILED,
                message=f"Could not connect to endpoint: {endpoint}",
            ),
            None,
        )
    except httpx.TimeoutException:
        return (
            ValidationDetail(
                level=ValidationLevel.INFERENCE,
                status=ValidationStatus.FAILED,
                message=f"Request timed out after {timeout}s: {endpoint}",
            ),
            None,
        )
    except Exception as exc:
        return (
            ValidationDetail(
                level=ValidationLevel.INFERENCE,
                status=ValidationStatus.FAILED,
                message=f"Async inference test error: {exc}",
            ),
            None,
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
    expected_response_schema: Optional[Dict[str, Any]] = None,
    is_sync_api: Optional[bool] = None,
    polling_url: Optional[str] = None,
    poll_interval_ms: Optional[int] = None,
    max_poll_attempts: int = 10,
    max_poll_wait_seconds: float = 60.0,
) -> EndpointValidationResult:
    """Run all validation levels against an inference endpoint.

    Dispatches to the async (poll-until-done) probe when the model declares
    ``isSyncApi=False`` and a ``pollingUrl``; otherwise runs the sync probe.
    When *expected_response_schema* is supplied and the probe is reachable,
    the actual response is also checked structurally against it.
    """
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
        use_async = is_sync_api is False and bool(polling_url)
        if use_async:
            inference_result, response_body = await test_inference_async(
                endpoint=endpoint,
                polling_url=polling_url,
                poll_interval_ms=poll_interval_ms,
                task_type=task_type,
                request_schema=request_schema,
                api_key=api_key,
                timeout=timeout,
                skip_tls_verify=skip_tls_verify,
                triton_schema=triton_schema,
                max_poll_attempts=max_poll_attempts,
                max_poll_wait_seconds=max_poll_wait_seconds,
            )
        else:
            inference_result, response_body = await test_inference(
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
            "Endpoint validation [%s] for %s (task=%s, async=%s): %s",
            inference_result.status.value,
            endpoint,
            task_type,
            use_async,
            inference_result.message,
        )

        if inference_result.status == ValidationStatus.PASSED and expected_response_schema:
            shape_result = validate_response_shape(response_body, expected_response_schema)
            details.append(shape_result)
            logger.info(
                "Response-shape validation [%s] for %s: %s",
                shape_result.status.value,
                endpoint,
                shape_result.message,
            )
    elif run_inference_test:
        details.append(
            ValidationDetail(
                level=ValidationLevel.INFERENCE,
                status=ValidationStatus.SKIPPED,
                message="Inference test skipped: task_type not provided.",
            )
        )

    is_valid = all(d.status == ValidationStatus.PASSED for d in details)
    return EndpointValidationResult(is_valid=is_valid, endpoint=endpoint, details=details)
