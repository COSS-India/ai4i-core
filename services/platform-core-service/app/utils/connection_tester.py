"""
"Try it" connection test for the service-creation form.

Unlike ``validate_endpoint`` (the gate that runs on create/update), this is
an optional, admin-triggered diagnostic. It never persists anything. It
reports *why* a probe failed, attributing the failure to one of:

  MODEL_JSON       the linked model card (task type, schema.request,
                   schema.response.triton, adapterConfig) is missing,
                   malformed, or produced a payload the endpoint rejected
  ENDPOINT         the service endpoint URL is malformed / SSRF-blocked /
                   unreachable / timed out / redirected / wrong path / 5xx
  PAYLOAD          the admin-supplied request payload is not valid JSON or
                   the endpoint rejected it (4xx)
  AUTH             the endpoint rejected the credentials (401/403)
  RESPONSE_FORMAT  the endpoint answered 2xx but the body is not JSON or
                   does not match the expected response shape

Success is stricter than the create-time gate: only a 2xx response (and a
matching response shape, where one is known) counts. The create-time gate
accepts any non-5xx because it only has to prove the server is alive; a
"try it" has to prove the configuration actually works.

It reuses the create-time SSRF guard, LLM path handling, probe-payload
builder and response-shape matcher, so the two can't drift apart. Redirects
are never followed: a redirect target never passed the SSRF check.
"""

import asyncio
import json
import logging
import time
from enum import Enum
from typing import Any, Dict, List, Optional, Tuple, Union

import httpx
from pydantic import BaseModel

from app.utils.endpoint_validator import (
    ValidationStatus,
    _build_probe_headers,
    _check_host_is_safe,
    _llm_endpoint_has_extra_path,
    _resolve_probe_endpoint,
    validate_response_shape,
)
from app.utils.probe_payloads import build_probe_payload, get_expected_response_shape
from app.utils.security import sanitize_url_for_log

logger = logging.getLogger(__name__)

# Response/request bodies echoed back to the UI are capped: a TTS response
# carries base64 audio that can run to megabytes.
MAX_ECHOED_BODY_CHARS = 20_000


class FailureCategory(str, Enum):
    MODEL_JSON = "MODEL_JSON"
    ENDPOINT = "ENDPOINT"
    PAYLOAD = "PAYLOAD"
    AUTH = "AUTH"
    RESPONSE_FORMAT = "RESPONSE_FORMAT"


class CheckStatus(str, Enum):
    PASSED = "passed"
    FAILED = "failed"
    WARNING = "warning"
    SKIPPED = "skipped"


class CheckName(str, Enum):
    MODEL_JSON = "model_json"
    REQUEST_PAYLOAD = "request_payload"
    ENDPOINT_URL = "endpoint_url"
    INFERENCE_CALL = "inference_call"
    RESPONSE_FORMAT = "response_format"


class ConnectionCheck(BaseModel):
    name: CheckName
    status: CheckStatus
    message: str


class ConnectionTestOutcome(BaseModel):
    success: bool
    message: str
    failureCategory: Optional[FailureCategory] = None
    failureReason: Optional[str] = None
    hint: Optional[str] = None
    probeEndpoint: Optional[str] = None
    payloadSource: Optional[str] = None  # "custom" | "model_json"
    payloadKind: Optional[str] = None  # "custom" | "ulca" | "triton_v2"
    requestPayload: Optional[Any] = None
    statusCode: Optional[int] = None
    latencyMs: Optional[int] = None
    responseBody: Optional[Any] = None
    responseTruncated: bool = False
    checks: List[ConnectionCheck] = []


class _Failure(Exception):
    """Internal short-circuit: carries the category/reason/hint of the
    first failing step up to ``run_connection_test``."""

    def __init__(self, category: FailureCategory, reason: str, hint: Optional[str] = None) -> None:
        super().__init__(reason)
        self.category = category
        self.reason = reason
        self.hint = hint


def _cap_body(body: Any) -> Tuple[Any, bool]:
    """Return *body* unchanged if its JSON form fits the echo budget,
    otherwise a truncated string rendering of it."""
    if body is None:
        return None, False
    text = body if isinstance(body, str) else json.dumps(body, ensure_ascii=False, default=str)
    if len(text) <= MAX_ECHOED_BODY_CHARS:
        return body, False
    return text[:MAX_ECHOED_BODY_CHARS] + "…(truncated)", True


def _parse_custom_payload(raw: Union[Dict[str, Any], str]) -> Dict[str, Any]:
    """Accept either an already-parsed object or the raw text the admin
    typed, and pinpoint JSON syntax errors by line/column."""
    if isinstance(raw, dict):
        if not raw:
            raise _Failure(FailureCategory.PAYLOAD, "Request payload is an empty JSON object.",
                           "Provide the JSON body the endpoint expects, or clear the field to use the model's schema.")
        return raw
    text = raw.strip()
    try:
        parsed = json.loads(text)
    except json.JSONDecodeError as exc:
        raise _Failure(
            FailureCategory.PAYLOAD,
            f"Request payload is not valid JSON: {exc.msg} (line {exc.lineno}, column {exc.colno}).",
            "Fix the JSON syntax, e.g. quotes around keys, no trailing commas.",
        )
    if not isinstance(parsed, dict) or not parsed:
        raise _Failure(
            FailureCategory.PAYLOAD,
            "Request payload must be a non-empty JSON object ({...}).",
            "Wrap the request body in an object, e.g. {\"input\": [{\"source\": \"hello\"}]}.",
        )
    return parsed


def _check_model_json(
    task_type: Optional[str],
    params: Dict[str, Any],
    *,
    has_custom_payload: bool,
    checks: List[ConnectionCheck],
) -> None:
    """Validate the parts of the model card the probe depends on."""
    if not task_type:
        raise _Failure(
            FailureCategory.MODEL_JSON,
            "The model JSON has no task type (task.type).",
            "Update the model so task.type is set (e.g. nmt, asr, tts, llm).",
        )

    request_schema = params.get("request_schema")
    triton_schema = params.get("triton_schema")
    problems: List[str] = []

    if request_schema is not None and not isinstance(request_schema, dict):
        problems.append("schema.request must be a JSON object")
    if triton_schema is not None:
        inputs = triton_schema.get("inputs") if isinstance(triton_schema, dict) else None
        if not isinstance(inputs, list) or not inputs or not all(isinstance(i, dict) for i in inputs):
            problems.append("schema.response.triton must contain a non-empty 'inputs' list of objects")

    if problems:
        reason = "The model JSON is malformed: " + "; ".join(problems) + "."
        if has_custom_payload:
            # The custom payload replaces the model's request schema for
            # this test, but the same card will drive the create-time probe.
            checks.append(ConnectionCheck(
                name=CheckName.MODEL_JSON, status=CheckStatus.WARNING,
                message=reason + " Ignored for this test because a custom request payload was supplied, "
                "but service creation will still probe with the model JSON.",
            ))
            return
        raise _Failure(FailureCategory.MODEL_JSON, reason,
                       "Fix the model's inference endpoint schema, or supply a custom request payload.")

    if task_type == "llm" and not params.get("model_name"):
        checks.append(ConnectionCheck(
            name=CheckName.MODEL_JSON, status=CheckStatus.WARNING,
            message="Model JSON has no adapterConfig.model_name; the probe cannot set the real LLM model name.",
        ))
        return

    checks.append(ConnectionCheck(
        name=CheckName.MODEL_JSON, status=CheckStatus.PASSED,
        message=f"Model JSON is usable (task type '{task_type}').",
    ))


def _classify_http_status(
    status: int, body_text: str, *, task_type: str, payload_category: FailureCategory,
) -> _Failure:
    """Map a non-2xx status to the most likely culprit."""
    snippet = (body_text or "").strip()[:300]
    detail = f" Response: {snippet}" if snippet else ""
    payload_label = "custom request payload" if payload_category == FailureCategory.PAYLOAD else "payload built from the model JSON"

    if status in (401, 403):
        return _Failure(FailureCategory.AUTH,
                        f"Endpoint rejected the credentials (HTTP {status}).{detail}",
                        "Check the authentication token / API key for this endpoint.")
    if 300 <= status < 400:
        return _Failure(FailureCategory.ENDPOINT,
                        f"Endpoint redirected (HTTP {status}); redirects are not followed.{detail}",
                        "Use the final URL the endpoint redirects to.")
    if status == 404 and task_type == "llm" and "model" in snippet.lower():
        return _Failure(payload_category,
                        f"Endpoint does not recognise the model named in the {payload_label} (HTTP 404).{detail}",
                        "Check the 'model' field (adapterConfig.model_name on the model JSON).")
    if status in (404, 405):
        return _Failure(FailureCategory.ENDPOINT,
                        f"Endpoint path not found or does not accept POST (HTTP {status}).{detail}",
                        "Check the endpoint URL path.")
    if 400 <= status < 500:
        return _Failure(payload_category,
                        f"Endpoint rejected the {payload_label} (HTTP {status}).{detail}",
                        "Compare the request payload with what the endpoint expects; the response above usually names the bad field.")
    return _Failure(FailureCategory.ENDPOINT,
                    f"Endpoint returned a server error (HTTP {status}).{detail}",
                    "The inference server is down or failing. If it is otherwise healthy, "
                    "the payload may have crashed it; check the response body.")


def _transport_failure(exc: Exception, url: str, timeout: float) -> _Failure:
    safe = sanitize_url_for_log(url)
    if isinstance(exc, httpx.TimeoutException):
        return _Failure(FailureCategory.ENDPOINT, f"Request to {safe} timed out after {timeout}s.",
                        "Check the endpoint is up and reachable from the platform, and not overloaded.")
    if isinstance(exc, httpx.ConnectError):
        return _Failure(FailureCategory.ENDPOINT, f"Could not connect to {safe}: {exc}",
                        "Check the host/port, that the server is running, and TLS settings.")
    return _Failure(FailureCategory.ENDPOINT, f"Request to {safe} failed: {exc}")


async def _post_sync(
    client: httpx.AsyncClient, url: str, payload: Dict[str, Any], headers: Dict[str, str], timeout: float,
) -> httpx.Response:
    return await client.post(url, json=payload, headers=headers, timeout=timeout)


async def _post_async_and_poll(
    client: httpx.AsyncClient,
    url: str,
    polling_url: str,
    payload: Dict[str, Any],
    headers: Dict[str, str],
    *,
    timeout: float,
    poll_interval_ms: Optional[int],
    max_poll_attempts: int,
    max_poll_wait_seconds: float,
) -> httpx.Response:
    """Submit, then re-POST the submit response body to *polling_url*
    until it stops returning 202 (same protocol as the create-time probe).
    Returns the final response; raises _Failure when the poll budget runs
    out."""
    deadline = time.monotonic() + max_poll_wait_seconds
    interval_s = max((poll_interval_ms or 1000) / 1000.0, 0.1)
    response = await client.post(url, json=payload, headers=headers, timeout=timeout)
    if response.status_code >= 300:
        return response
    try:
        poll_body: Any = response.json()
    except Exception:
        poll_body = {}
    for _ in range(max_poll_attempts):
        remaining = deadline - time.monotonic()
        if remaining <= 0:
            break
        await asyncio.sleep(min(interval_s, remaining))
        response = await client.post(
            polling_url, json=poll_body, headers=headers,
            timeout=min(timeout, max(deadline - time.monotonic(), 0.001)),
        )
        if response.status_code != 202:
            return response
    raise _Failure(
        FailureCategory.ENDPOINT,
        f"Async job did not complete within {max_poll_wait_seconds}s "
        f"({max_poll_attempts} polls against {sanitize_url_for_log(polling_url)}).",
        "Check the async inference server is processing jobs, and the model's asyncApiDetails.pollingUrl.",
    )


async def run_connection_test(
    *,
    endpoint: str,
    task_type: Optional[str],
    model_params: Dict[str, Any],
    custom_payload: Optional[Union[Dict[str, Any], str]] = None,
    api_key: Optional[str] = None,
    expected_response_schema: Optional[Dict[str, Any]] = None,
    timeout: float = 15.0,
    skip_tls_verify: bool = False,
    max_poll_attempts: int = 10,
    max_poll_wait_seconds: float = 60.0,
) -> ConnectionTestOutcome:
    """Probe *endpoint* once and explain the outcome.

    *model_params* is ``_extract_validation_params(model.inference_endpoint)``.
    When *custom_payload* is supplied it is sent verbatim; otherwise the
    payload is built from the model JSON exactly as the create-time probe
    builds it.
    """
    checks: List[ConnectionCheck] = []
    outcome = ConnectionTestOutcome(success=False, message="")
    has_custom = custom_payload is not None and not (isinstance(custom_payload, str) and not custom_payload.strip())
    outcome.payloadSource = "custom" if has_custom else "model_json"
    payload_category = FailureCategory.PAYLOAD if has_custom else FailureCategory.MODEL_JSON
    current_check = CheckName.MODEL_JSON

    try:
        # 1. Model JSON
        _check_model_json(task_type, model_params, has_custom_payload=has_custom, checks=checks)

        # 2. Request payload
        current_check = CheckName.REQUEST_PAYLOAD
        if has_custom:
            payload = _parse_custom_payload(custom_payload)
            payload_kind = "custom"
            checks.append(ConnectionCheck(name=current_check, status=CheckStatus.PASSED,
                                          message="Custom request payload is valid JSON."))
        else:
            try:
                payload, payload_kind = build_probe_payload(
                    task_type, model_params.get("request_schema"),
                    model_params.get("triton_schema"), model_params.get("model_name"),
                )
            except Exception as exc:
                current_check = CheckName.MODEL_JSON
                raise _Failure(FailureCategory.MODEL_JSON,
                               f"Could not build a request payload from the model JSON: {exc}",
                               "Fix the model's schema.request / schema.response.triton, or supply a custom request payload.")
            checks.append(ConnectionCheck(name=current_check, status=CheckStatus.PASSED,
                                          message=f"Request payload built from the model JSON ({payload_kind})."))
        outcome.payloadKind = payload_kind
        outcome.requestPayload, _ = _cap_body(payload)

        # 3. Endpoint URL (format + SSRF + LLM path rule)
        current_check = CheckName.ENDPOINT_URL
        for detail in await _check_host_is_safe(endpoint, label="Endpoint"):
            if detail.status == ValidationStatus.FAILED:
                raise _Failure(FailureCategory.ENDPOINT, detail.message,
                               "Use a public http(s) URL for the inference server.")
        extra_path = _llm_endpoint_has_extra_path(endpoint, task_type)
        if extra_path:
            raise _Failure(FailureCategory.ENDPOINT, extra_path.message,
                           "Remove the path and keep only scheme://host:port.")
        probe_endpoint = _resolve_probe_endpoint(endpoint, task_type)
        outcome.probeEndpoint = sanitize_url_for_log(probe_endpoint)

        polling_url = model_params.get("polling_url")
        use_async = model_params.get("is_sync_api") is False and bool(polling_url)
        if use_async:
            for detail in await _check_host_is_safe(polling_url, label="Polling endpoint"):
                if detail.status == ValidationStatus.FAILED:
                    raise _Failure(FailureCategory.MODEL_JSON, detail.message,
                                   "Fix asyncApiDetails.pollingUrl on the model JSON.")
        checks.append(ConnectionCheck(name=current_check, status=CheckStatus.PASSED,
                                      message="Endpoint URL is well-formed and allowed."))

        # 4. Live call
        current_check = CheckName.INFERENCE_CALL
        headers = _build_probe_headers(api_key)
        started = time.monotonic()
        try:
            async with httpx.AsyncClient(verify=not skip_tls_verify, follow_redirects=False) as client:
                if use_async:
                    response = await _post_async_and_poll(
                        client, probe_endpoint, polling_url, payload, headers,
                        timeout=timeout,
                        poll_interval_ms=model_params.get("poll_interval_ms"),
                        max_poll_attempts=max_poll_attempts,
                        max_poll_wait_seconds=max_poll_wait_seconds,
                    )
                else:
                    response = await _post_sync(client, probe_endpoint, payload, headers, timeout)
        except _Failure:
            outcome.latencyMs = int((time.monotonic() - started) * 1000)
            raise
        except Exception as exc:
            outcome.latencyMs = int((time.monotonic() - started) * 1000)
            raise _transport_failure(exc, probe_endpoint, timeout)
        outcome.latencyMs = int((time.monotonic() - started) * 1000)
        outcome.statusCode = response.status_code

        try:
            body: Any = response.json()
            is_json = True
        except Exception:
            body = response.text or None
            is_json = False
        outcome.responseBody, outcome.responseTruncated = _cap_body(body)

        if not 200 <= response.status_code < 300:
            raise _classify_http_status(
                response.status_code, response.text, task_type=task_type, payload_category=payload_category,
            )
        checks.append(ConnectionCheck(name=current_check, status=CheckStatus.PASSED,
                                      message=f"Endpoint responded with HTTP {response.status_code} in {outcome.latencyMs} ms."))

        # 5. Response format
        current_check = CheckName.RESPONSE_FORMAT
        if not is_json:
            raise _Failure(FailureCategory.RESPONSE_FORMAT, "Endpoint returned a non-JSON response body.",
                           "Check the endpoint is an inference API and not, e.g., an HTML page or proxy.")
        # The built-in default shape is a ULCA convention: never applies to raw Triton.
        default_shape = None if payload_kind == "triton_v2" or model_params.get("triton_schema") else get_expected_response_shape(task_type)
        expected = expected_response_schema or default_shape
        if expected:
            shape = validate_response_shape(body, expected)
            if shape.status == ValidationStatus.FAILED:
                raise _Failure(FailureCategory.RESPONSE_FORMAT, shape.message,
                               f"The endpoint answered, but not in the format expected for a '{task_type}' service. "
                               "Check the endpoint serves this model and that the model JSON's task type is correct.")
            checks.append(ConnectionCheck(name=current_check, status=CheckStatus.PASSED, message=shape.message))
        else:
            checks.append(ConnectionCheck(name=current_check, status=CheckStatus.SKIPPED,
                                          message="No expected response shape is known for this task type."))

        outcome.success = True
        outcome.message = "Connection successful: the endpoint accepted the request and returned a valid response."
    except _Failure as failure:
        checks.append(ConnectionCheck(name=current_check, status=CheckStatus.FAILED, message=failure.reason))
        outcome.failureCategory = failure.category
        outcome.failureReason = failure.reason
        outcome.hint = failure.hint
        outcome.message = {
            FailureCategory.MODEL_JSON: "Connection test failed: problem with the model JSON.",
            FailureCategory.ENDPOINT: "Connection test failed: problem with the service endpoint.",
            FailureCategory.PAYLOAD: "Connection test failed: problem with the request payload.",
            FailureCategory.AUTH: "Connection test failed: authentication was rejected.",
            FailureCategory.RESPONSE_FORMAT: "Connection test failed: unexpected response format.",
        }[failure.category]

    outcome.checks = checks
    logger.info(
        "Connection test %s for %s (task=%s, source=%s, status=%s, category=%s)",
        "passed" if outcome.success else "failed",
        sanitize_url_for_log(endpoint), task_type, outcome.payloadSource,
        outcome.statusCode, outcome.failureCategory.value if outcome.failureCategory else None,
    )
    return outcome
