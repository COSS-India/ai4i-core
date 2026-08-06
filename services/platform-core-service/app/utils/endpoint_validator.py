"""
Two-level validation for inference endpoints.

  Level 1 — URL format check (synchronous, always runs)
  Level 2 — Live inference probe (async, task-type-aware payload)
             - sync endpoints: single POST, checked for reachability and
               (when an expected response schema is available) response shape
             - async endpoints: POST to submit, then poll a separate
               pollingUrl until the job completes, fails, or the poll
               budget runs out

Both the endpoint and — for async models — the pollingUrl are subject to
SSRF protection: the hostname must resolve to a publicly-routable IP (no
private/loopback/link-local/etc. addresses). Neither host gets a live
network call until it has passed this check.
"""

import asyncio
import logging
import time
from enum import Enum
from typing import Any, Dict, List, Optional, Tuple
from urllib.parse import urlparse

import httpx
from pydantic import BaseModel

from app.utils.probe_payloads import build_probe_payload, get_expected_response_shape
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


async def _check_host_is_safe(url: str, *, label: str) -> List[ValidationDetail]:
    """Run the URL-format + SSRF check against *url*, returning the
    ValidationDetail entries produced (one if the format check fails, two —
    format then SSRF — if it passes). Any FAILED entry means *url* must not
    be probed.

    *label* ("Endpoint" / "Polling endpoint") only affects the SSRF-block
    message text: with ``label="Endpoint"`` the message is byte-identical
    to the pre-existing single-endpoint check, so this refactor doesn't
    change that message for the primary endpoint; a non-primary URL (the
    async pollingUrl) gets its own label folded in instead.
    """
    details: List[ValidationDetail] = [validate_url_format(url)]
    if details[0].status == ValidationStatus.FAILED:
        return details
    hostname = urlparse(url).hostname or ""
    if not await is_safe_host(hostname):
        details.append(
            ValidationDetail(
                level=ValidationLevel.URL_FORMAT,
                status=ValidationStatus.FAILED,
                message=(
                    f"{label} host is not allowed for probing (SSRF protection). "
                    f"Blocked hostname: '{hostname or '(empty)'}'"
                ),
            )
        )
    return details


# ── LLM-only: auto-attach the OpenAI chat-completions path ──

# For task_type == "llm" the admin supplies just host:port (no path) — every
# other task type's endpoint is a full URL the admin fully controls, and is
# used exactly as given. This is a validation-time-only convenience: the
# stored Service.endpoint stays whatever the admin typed; only the URL the
# live probe actually POSTs to gets this appended.
_LLM_CHAT_COMPLETIONS_PATH = "/v1/chat/completions"


def _resolve_probe_endpoint(endpoint: str, task_type: Optional[str]) -> str:
    """Return the URL the live probe should actually POST to."""
    if task_type != "llm":
        return endpoint
    trimmed = endpoint.rstrip("/")
    if trimmed.endswith(_LLM_CHAT_COMPLETIONS_PATH):
        return trimmed  # admin already included it — don't double-append
    return trimmed + _LLM_CHAT_COMPLETIONS_PATH


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
    """Compare a parsed JSON response against a sample expected shape —
    either an admin-supplied override or the task-type default (see
    ``get_expected_response_shape``)."""
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


# ── Shared result/error helpers (keeps the two probes below DRY) ──


def _infer_pass(message: str, body: Optional[Any] = None) -> Tuple[ValidationDetail, Optional[Any]]:
    return (
        ValidationDetail(level=ValidationLevel.INFERENCE, status=ValidationStatus.PASSED, message=message),
        body,
    )


def _infer_fail(message: str) -> Tuple[ValidationDetail, None]:
    return (
        ValidationDetail(level=ValidationLevel.INFERENCE, status=ValidationStatus.FAILED, message=message),
        None,
    )


def _transport_error_message(exc: Exception, url: str, timeout: float, *, prefix: str = "Inference") -> str:
    """Translate a transport-layer exception into the same message text
    regardless of which probe (sync/async) raised it."""
    if isinstance(exc, httpx.ConnectError):
        return f"Could not connect to endpoint: {url}"
    if isinstance(exc, httpx.TimeoutException):
        return f"Request timed out after {timeout}s: {url}"
    return f"{prefix} test error: {exc}"


def _build_probe_headers(api_key: Optional[str]) -> Dict[str, str]:
    headers: Dict[str, str] = {"Content-Type": "application/json"}
    if api_key:
        headers["Authorization"] = f"Bearer {api_key}"
    return headers


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


async def test_inference(
    endpoint: str,
    task_type: str,
    request_schema: Optional[Dict[str, Any]] = None,
    api_key: Optional[str] = None,
    timeout: float = 15.0,
    validation_mode: str = "lenient",
    skip_tls_verify: bool = False,
    triton_schema: Optional[Dict[str, Any]] = None,
    model_name: Optional[str] = None,
) -> Tuple[ValidationDetail, Optional[Any], str]:
    """POST a probe payload and check the response status.

    Returns ``(detail, parsed_json_body, payload_kind)``. *parsed_json_body*
    is only populated when the transport-level check passed — callers
    should treat it as the value to run a response-shape check against, and
    ignore it on failure. *payload_kind* ("ulca" or "triton_v2", from
    ``build_probe_payload``) tells the caller whether the built-in
    per-task-type default response shape even applies — it's a ULCA
    convention and never matches a raw Triton response. *model_name* is the
    model card's authoritative ``adapterConfig.model_name`` (see
    ``build_ulca_payload``).
    """
    fail_threshold = _VALIDATION_MODE_THRESHOLDS.get(
        validation_mode, _VALIDATION_MODE_THRESHOLDS["lenient"]
    )
    payload, payload_kind = build_probe_payload(task_type, request_schema, triton_schema, model_name)
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
            return _infer_pass(
                f"Inference endpoint is reachable and responded with "
                f"HTTP {response.status_code} ({payload_kind} payload).",
                response_json,
            ) + (payload_kind,)

        return _infer_fail(
            f"Inference endpoint returned HTTP {response.status_code} "
            f"(validation_mode={validation_mode}): "
            f"{truncate_for_log(body_for_log, max_len=500)}"
        ) + (payload_kind,)
    except Exception as exc:
        return _infer_fail(_transport_error_message(exc, endpoint, timeout)) + (payload_kind,)


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
    model_name: Optional[str] = None,
) -> Tuple[ValidationDetail, Optional[Any], str]:
    """Submit a probe request, then poll *polling_url* until the async job
    completes (HTTP 200), fails, or the poll budget runs out.

    Mirrors ULCA's ``validateAsyncUrl``: POST the sample payload to
    *endpoint*, then repeatedly re-POST whatever JSON body came back to
    *polling_url* every ``poll_interval_ms`` until it returns 200 (done) or
    a non-202 failure.

    Bounded by both ``max_poll_attempts`` and ``max_poll_wait_seconds`` —
    the latter is a real wall-clock deadline (tracked via ``time.monotonic``)
    that covers the submit call, every sleep, *and* every poll HTTP call
    (each request's own timeout is capped to whatever's left of the budget),
    so a slow/stuck endpoint can't hold the caller past the configured
    budget no matter how long any individual HTTP call takes. Unlike the
    reference implementation's unbounded ``while(true)`` loop, this always
    returns within ``max_poll_wait_seconds`` (plus the setup/parse overhead
    outside the timed calls).

    Returns ``(detail, parsed_json_body, payload_kind)`` — see
    ``test_inference`` for what *payload_kind* is used for by the caller.
    """
    payload, payload_kind = build_probe_payload(task_type, request_schema, triton_schema, model_name)
    headers = _build_probe_headers(api_key)
    safe_endpoint = sanitize_url_for_log(endpoint)
    safe_polling_url = sanitize_url_for_log(polling_url)
    interval_s = max((poll_interval_ms or 1000) / 1000.0, 0.1)

    deadline = time.monotonic() + max_poll_wait_seconds

    def _remaining() -> float:
        return deadline - time.monotonic()

    try:
        async with httpx.AsyncClient(verify=not skip_tls_verify) as client:
            submit_timeout = min(timeout, max(_remaining(), 0.001))
            submit_response = await client.post(
                endpoint, json=payload, headers=headers, timeout=submit_timeout
            )

            if submit_response.status_code >= 500:
                return _infer_fail(
                    f"Async endpoint returned HTTP {submit_response.status_code} "
                    f"on submit ({payload_kind} payload)."
                ) + (payload_kind,)

            try:
                poll_body: Any = submit_response.json()
            except Exception:
                poll_body = {}

            for attempt in range(1, max_poll_attempts + 1):
                remaining = _remaining()
                if remaining <= 0:
                    break
                await asyncio.sleep(min(interval_s, remaining))
                remaining = _remaining()
                if remaining <= 0:
                    break

                try:
                    poll_response = await client.post(
                        polling_url,
                        json=poll_body,
                        headers=headers,
                        timeout=min(timeout, max(remaining, 0.001)),
                    )
                except httpx.TimeoutException:
                    break  # budget exhausted mid-request — falls to the timeout message below
                except Exception as exc:
                    # Attribute failures on THIS call to polling_url, not the
                    # submit endpoint — a bare `except Exception` at the
                    # function's outer scope would otherwise report a
                    # polling-host ConnectError as if `endpoint` had failed.
                    return _infer_fail(
                        _transport_error_message(
                            exc, polling_url, timeout, prefix="Async inference"
                        )
                    ) + (payload_kind,)

                if poll_response.status_code == 202:
                    continue
                if poll_response.status_code == 200:
                    try:
                        final_body = poll_response.json()
                    except Exception as exc:
                        return _infer_fail(
                            f"Async endpoint's polled result was not valid JSON: {exc}"
                        ) + (payload_kind,)
                    return _infer_pass(
                        f"Async endpoint completed after {attempt} poll(s) "
                        f"({payload_kind} payload).",
                        final_body,
                    ) + (payload_kind,)
                return _infer_fail(
                    f"Polling {safe_polling_url} returned HTTP "
                    f"{poll_response.status_code}."
                ) + (payload_kind,)

            return _infer_fail(
                f"Async endpoint {safe_endpoint} did not complete within "
                f"{max_poll_wait_seconds}s ({max_poll_attempts} poll attempts "
                f"against {safe_polling_url})."
            ) + (payload_kind,)
    except Exception as exc:
        # Anything raised before the poll loop (client construction, the
        # submit call itself) genuinely is about `endpoint`.
        return _infer_fail(
            _transport_error_message(exc, endpoint, timeout, prefix="Async inference")
        ) + (payload_kind,)


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
    model_name: Optional[str] = None,
) -> EndpointValidationResult:
    """Run all validation levels against an inference endpoint.

    Dispatches to the async (poll-until-done) probe when the model declares
    ``isSyncApi=False`` and a ``pollingUrl``; otherwise runs the sync probe.
    The ``pollingUrl`` host goes through the same URL-format + SSRF check as
    *endpoint* before any request is made to it — a model card cannot use
    an internal ``pollingUrl`` to route platform-core's outbound probe
    around the SSRF guard.

    The actual response is checked structurally against
    *expected_response_schema* when supplied — regardless of payload kind,
    since an explicit override is a deliberate admin choice. Absent that,
    it falls back to the built-in default for *task_type* (see
    ``get_expected_response_shape``), but ONLY when the probe actually sent
    a ULCA-style payload (``build_probe_payload`` returns "triton_v2"
    whenever the model card carries ``schema.response.triton`` — a raw
    Triton response like ``{"model_name": ..., "outputs": [...]}`` has no
    ULCA "output" envelope and would never match, incorrectly failing every
    Triton-backed service that doesn't hand-supply a schema). Task types
    with no known ULCA default, and every Triton-backed probe without an
    explicit override, simply skip this check.

    *model_name* is the model card's ``inferenceEndPoint.adapterConfig.model_name``
    — for ``task_type == "llm"`` this is the authoritative real model
    identifier and always overrides/fills the probe payload's ``model``
    field, regardless of what (if anything) ``schema.request`` itself
    declares (see ``build_ulca_payload``).

    For ``task_type == "llm"`` specifically, *endpoint* is expected to be
    just ``host:port`` — the admin does not supply the inference path — so
    the actual probe POSTs to *endpoint* with ``/v1/chat/completions``
    appended (see ``_resolve_probe_endpoint``). Every other task type's
    endpoint is used exactly as given, and the SSRF/format check below
    always runs against the admin-supplied value, not the resolved one
    (the hostname is identical either way).
    """
    details: List[ValidationDetail] = []

    endpoint_checks = await _check_host_is_safe(endpoint, label="Endpoint")
    details.extend(endpoint_checks)
    if any(d.status == ValidationStatus.FAILED for d in endpoint_checks):
        return EndpointValidationResult(is_valid=False, endpoint=endpoint, details=details)

    probe_endpoint = _resolve_probe_endpoint(endpoint, task_type)

    if run_inference_test and task_type:
        use_async = is_sync_api is False and bool(polling_url)

        if use_async:
            # The pollingUrl comes from the model card, not the service's own
            # (already-checked) endpoint — a model registered with a safe
            # endpoint but an internal pollingUrl must not let platform-core
            # issue an internal POST during the poll loop. Same check, same
            # fail-closed behavior, applied here before any request to it.
            polling_checks = await _check_host_is_safe(polling_url, label="Polling endpoint")
            details.extend(polling_checks)
            if any(d.status == ValidationStatus.FAILED for d in polling_checks):
                return EndpointValidationResult(is_valid=False, endpoint=endpoint, details=details)

            inference_result, response_body, payload_kind = await test_inference_async(
                endpoint=probe_endpoint,
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
                model_name=model_name,
            )
        else:
            inference_result, response_body, payload_kind = await test_inference(
                endpoint=probe_endpoint,
                task_type=task_type,
                request_schema=request_schema,
                api_key=api_key,
                timeout=timeout,
                validation_mode=validation_mode,
                skip_tls_verify=skip_tls_verify,
                triton_schema=triton_schema,
                model_name=model_name,
            )
        details.append(inference_result)
        logger.info(
            "Endpoint validation [%s] for %s (task=%s, async=%s, payload=%s): %s",
            inference_result.status.value,
            probe_endpoint,
            task_type,
            use_async,
            payload_kind,
            inference_result.message,
        )

        default_shape = get_expected_response_shape(task_type) if payload_kind == "ulca" else None
        effective_expected_schema = expected_response_schema or default_shape
        if inference_result.status == ValidationStatus.PASSED and effective_expected_schema:
            shape_result = validate_response_shape(response_body, effective_expected_schema)
            details.append(shape_result)
            logger.info(
                "Response-shape validation [%s] for %s: %s",
                shape_result.status.value,
                probe_endpoint,
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
