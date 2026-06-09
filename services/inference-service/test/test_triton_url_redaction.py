#!/usr/bin/env python3
"""
Regression tests for AI4IDS-1871 — Triton endpoint URLs and API keys must
NOT appear in API responses, exception messages, or application logs.

Every test plants distinctive sentinel values in `service_info` (a fake
Triton URL and a fake API key) and exercises a failure or success path.
After the path runs, the test asserts that the sentinels do NOT appear
in any of:
  • the raised exception's message + str(e)
  • any captured log record (the leak vector when logs are ingested by
    fluent-bit → OpenSearch → Logs Dashboard)

If a sentinel ever leaks, the assertion message identifies which record
or message it came from, so the regression is easy to localise.
"""

import asyncio
import logging
import sys
from typing import List
from unittest.mock import AsyncMock, MagicMock, patch
from uuid import uuid4


logging.basicConfig(level=logging.DEBUG, format="%(name)s %(levelname)s %(message)s")
test_logger = logging.getLogger(__name__)


# ── Distinctive sentinels — if any of these appear anywhere visible, FAIL ──
# Values are computed at import time so they are never literal strings in
# source (avoids static-analysis credential-detection false positives).
SECRET_HOST = f"secret-triton-{uuid4().hex[:8]}.internal:9999"
SECRET_URL  = f"http://{SECRET_HOST}/v2/models/redact_me_model/infer"
SECRET_KEY  = f"INTERNAL_API_KEY_DO_NOT_LEAK_{uuid4().hex}"
SECRET_MMS  = f"https://internal-mms-{uuid4().hex[:8]}.example.local:11111"

SECRETS = (SECRET_HOST, SECRET_URL, SECRET_KEY, SECRET_MMS)


def _service_info() -> dict:
    """Resolved service_info with sentinel values planted into every
    field that historically carried URL / api_key info."""
    return {
        "service_id": "indictrans-v2-all",
        "name": "indictrans-gpu-t4",
        "endpoint": SECRET_URL,
        "api_key": SECRET_KEY,
        "adapter_config": None,
    }


class _CapturingHandler(logging.Handler):
    """Stores every formatted log record for post-hoc inspection."""

    def __init__(self) -> None:
        super().__init__(level=logging.DEBUG)
        self.records: List[str] = []
        self.setFormatter(logging.Formatter("%(name)s|%(levelname)s|%(message)s"))

    def emit(self, record: logging.LogRecord) -> None:
        try:
            self.records.append(self.format(record))
        except Exception:
            # A failing format shouldn't break the test — but the raw
            # message is still worth capturing for analysis.
            self.records.append(str(record.msg))


def _attach(logger_name: str) -> _CapturingHandler:
    """Attach a _CapturingHandler to ``logger_name`` and return it. Callers
    use ``handler.records`` after the test path completes."""
    handler = _CapturingHandler()
    target = logging.getLogger(logger_name)
    target.addHandler(handler)
    target.setLevel(logging.DEBUG)
    return handler


def _assert_no_secret_in(label: str, text: str) -> None:
    """Common assertion — fail loudly with the smoking-gun text."""
    for secret in SECRETS:
        assert secret not in text, (
            f"LEAK in {label}: found sentinel {secret!r} in:\n   {text!r}"
        )


def _assert_no_secret_in_records(label: str, records: List[str]) -> None:
    for i, rec in enumerate(records):
        _assert_no_secret_in(f"{label} record[{i}]", rec)


# ─────────────────────────────────────────────────────────────────────
# Tests — resolver
# ─────────────────────────────────────────────────────────────────────

async def test_resolver_success_log_does_not_dump_service_info() -> None:
    """`logger.debug("Resolved service ...: <service_info>")` historically
    dumped the full dict (endpoint + api_key). Confirm the new format
    logs only safe identifiers."""
    from inference.inference_server_resolver import InferenceServerResolver

    handler = _attach("inference.inference_server_resolver")
    resolver = InferenceServerResolver()
    resolver._memory_cache.clear()

    # Flat-shape MMS response so resolver passes it through unmodified —
    # endpoint and api_key reach `service_info` with sentinel values intact,
    # so any debug log that dumps service_info will trip the assertions.
    fake_mms_response = {
        "name": "indictrans-gpu-t4",
        "endpoint": SECRET_URL,
        "api_key": SECRET_KEY,
        "adapter_config": None,
        "class_instance": "TextDefaultModel",
    }
    import os
    with patch.dict(os.environ, {"MODEL_MANAGEMENT_SERVICE_URL": "http://mms-host:9090"}):
        with patch(
            "utils.http_client.HTTPServiceClient.get_json",
            new=AsyncMock(return_value=fake_mms_response),
        ):
            info = await resolver.resolve_service("indictrans-v2-all")

    # Sanity check: resolver actually carries the sentinels through to
    # service_info — otherwise the log-leak assertion below is trivially
    # satisfied even if the redaction logic regressed.
    assert info["endpoint"] == SECRET_URL, f"resolver dropped endpoint: {info}"
    assert info["api_key"] == SECRET_KEY, f"resolver dropped api_key: {info}"
    _assert_no_secret_in_records("resolver-success-debug-log", handler.records)
    test_logger.info("[PASS] resolver success log does not dump service_info")


async def test_resolver_lookup_failure_log_redacted() -> None:
    """When MMS returns 404 / LookupError, the log must not include str(e)
    of any chained HTTP error (which embeds the URL)."""
    from inference.inference_server_resolver import InferenceServerResolver

    handler = _attach("inference.inference_server_resolver")
    resolver = InferenceServerResolver()
    resolver._memory_cache.clear()

    # Simulate an HTTP client raising a LookupError that itself carries the URL.
    class _UrlEmbeddedError(LookupError):
        def __str__(self) -> str:
            return f"GET {SECRET_MMS}/api/v1/services/foo returned 404"

    import os
    with patch.dict(os.environ, {"MODEL_MANAGEMENT_SERVICE_URL": SECRET_MMS}):
        with patch(
            "utils.http_client.HTTPServiceClient.get_json",
            new=AsyncMock(side_effect=_UrlEmbeddedError()),
        ):
            try:
                await resolver.resolve_service("unknown-service-id")
                raise AssertionError("Expected LookupError")
            except LookupError as e:
                _assert_no_secret_in("resolver-lookup-exception-message", str(e))
    _assert_no_secret_in_records("resolver-lookup-log", handler.records)
    test_logger.info("[PASS] resolver LookupError + log redacted")


async def test_resolver_connection_failure_log_redacted() -> None:
    """When MMS is unreachable, the log + raised ConnectionError must not
    embed str(e) of the underlying httpx error (which contains the URL)."""
    from inference.inference_server_resolver import InferenceServerResolver

    handler = _attach("inference.inference_server_resolver")
    resolver = InferenceServerResolver()
    resolver._memory_cache.clear()

    class _UrlEmbeddedError(Exception):
        def __str__(self) -> str:
            return f"Connection refused: tried {SECRET_MMS}/api/v1/services/x"

    import os
    with patch.dict(os.environ, {"MODEL_MANAGEMENT_SERVICE_URL": SECRET_MMS}):
        with patch(
            "utils.http_client.HTTPServiceClient.get_json",
            new=AsyncMock(side_effect=_UrlEmbeddedError()),
        ):
            try:
                await resolver.resolve_service("some-service")
                raise AssertionError("Expected ConnectionError")
            except ConnectionError as e:
                _assert_no_secret_in("resolver-conn-exception-message", str(e))
    _assert_no_secret_in_records("resolver-conn-log", handler.records)
    test_logger.info("[PASS] resolver ConnectionError + log redacted")


# ─────────────────────────────────────────────────────────────────────
# Tests — task_service
# ─────────────────────────────────────────────────────────────────────

async def test_triton_call_failure_log_and_exception_redacted() -> None:
    """When the Triton HTTP call fails, the RuntimeError + log must not
    include the endpoint URL or any underlying httpx error string."""
    from services.base.task_service import BaseTaskService

    handler = _attach("services.base.task_service")
    svc = BaseTaskService(service_info=_service_info())

    # Simulate an httpx-style transport error whose str() embeds the URL.
    class _UrlEmbeddedError(Exception):
        def __str__(self) -> str:
            return f"Connection refused while POSTing to {SECRET_URL}"

    with patch(
        "utils.http_client.HTTPServiceClient.post_json",
        new=AsyncMock(side_effect=_UrlEmbeddedError()),
    ):
        try:
            await svc._call_triton_inference(
                triton_endpoint=SECRET_URL,
                triton_inputs=[{"name": "x"}],
                triton_outputs=["y"],
                api_key=SECRET_KEY,
            )
            raise AssertionError("Expected RuntimeError")
        except RuntimeError as e:
            _assert_no_secret_in("triton-call-exception-message", str(e))
            # Sanity check: the original cause IS available for server-side
            # debugging via __cause__, but its message is NOT in the user-visible
            # exception args.
            assert e.__cause__ is not None
    _assert_no_secret_in_records("triton-call-log", handler.records)
    test_logger.info("[PASS] _call_triton_inference exception + log redacted")


async def test_triton_call_debug_log_redacted() -> None:
    """On successful Triton calls, the debug-level 'Calling Triton...'
    log line must not include the endpoint URL."""
    from services.base.task_service import BaseTaskService

    handler = _attach("services.base.task_service")
    svc = BaseTaskService(service_info=_service_info())

    with patch(
        "utils.http_client.HTTPServiceClient.post_json",
        new=AsyncMock(return_value={"outputs": []}),
    ):
        await svc._call_triton_inference(
            triton_endpoint=SECRET_URL,
            triton_inputs=[{"name": "x"}],
            triton_outputs=["y"],
            api_key=SECRET_KEY,
        )

    _assert_no_secret_in_records("triton-call-debug-log", handler.records)
    test_logger.info("[PASS] _call_triton_inference debug log redacted")


# ─────────────────────────────────────────────────────────────────────
# Tests — orchestrator
# ─────────────────────────────────────────────────────────────────────

async def test_orchestrator_resolve_failure_log_and_exception_redacted() -> None:
    """When the resolver raises any exception, the orchestrator's
    RuntimeError + log must not embed the chained exception's str(e)."""
    from orchestrator.orchestrator import Orchestrator

    handler = _attach("orchestrator.orchestrator")
    orch = Orchestrator()

    class _UrlEmbeddedError(Exception):
        def __str__(self) -> str:
            return f"Resolver failed talking to {SECRET_MMS}; remote returned {SECRET_URL}"

    # Patch the resolver's resolve_service on the orchestrator instance.
    with patch.object(
        orch.inference_server_resolver,
        "resolve_service",
        new=AsyncMock(side_effect=_UrlEmbeddedError()),
    ):
        payload = {"task_type": "NMT", "config": {"serviceId": "some-svc"}}
        try:
            await orch._resolve_service_and_model(payload)
            raise AssertionError("Expected RuntimeError")
        except RuntimeError as e:
            _assert_no_secret_in("orch-resolve-exception-message", str(e))
            assert e.__cause__ is not None
    _assert_no_secret_in_records("orch-resolve-log", handler.records)
    test_logger.info("[PASS] orchestrator resolve failure exception + log redacted")


# ─────────────────────────────────────────────────────────────────────
# Tests — exception chain at the route layer (final HTTP envelope)
# ─────────────────────────────────────────────────────────────────────

def test_route_http_envelope_uses_generic_message_for_runtime_errors() -> None:
    """`_http_error_for` is what shapes the HTTP error response body.
    Confirm that for RuntimeError chains carrying URL-embedded messages,
    the resulting HTTPException.detail is a fixed, generic string — never
    the underlying str(e)."""
    from routes.inference import _http_error_for

    # Simulate the chain that would form if Triton failed inside task_service.
    inner = ConnectionError(f"refused at {SECRET_URL}")
    middle = RuntimeError(f"Triton inference call failed at {SECRET_URL}")
    middle.__cause__ = inner
    outer = RuntimeError(f"Orchestrator: route_inference fell over: {middle}")
    outer.__cause__ = middle

    http_exc = _http_error_for(outer, task_type="NMT")
    assert http_exc.status_code == 502
    detail = str(http_exc.detail)
    _assert_no_secret_in("http-envelope-detail", detail)
    # Confirm the generic message we DO want is what's returned.
    assert "upstream inference dependency failed" in detail
    test_logger.info("[PASS] HTTPException envelope detail is generic")


async def test_route_logs_exc_chain_types_without_messages() -> None:
    """The route layer logs the exception CHAIN type-names ("RuntimeError
    →ConnectionError→OSError") so a developer triaging a 502 has the
    failure depth — but it must NOT include any chained str(e), which
    is the URL-leak vector."""
    from routes.inference import _run_inference

    handler = _attach("routes.inference")

    # Build a chain whose str() values all contain sentinels.
    inner = OSError(f"connect to {SECRET_URL} failed")
    middle = ConnectionError(f"talking to {SECRET_MMS} failed")
    middle.__cause__ = inner
    outer = RuntimeError(f"upstream blew up at {SECRET_URL}")
    outer.__cause__ = middle

    fake_orchestrator = MagicMock()
    fake_orchestrator.route_inference = AsyncMock(side_effect=outer)
    fake_request = MagicMock()
    fake_request.url.path = "/api/v1/nmt/inference"
    fake_request.method = "POST"

    try:
        await _run_inference(
            request=fake_request,
            payload={"task_type": "NMT", "config": {"serviceId": "x"}},
            orchestrator=fake_orchestrator,
        )
        raise AssertionError("Expected HTTPException")
    except Exception as e:
        # _http_error_for raises HTTPException — verify detail is generic AND
        # has no leak. (Already covered above; here we focus on the LOG.)
        from fastapi import HTTPException
        assert isinstance(e, HTTPException), f"Expected HTTPException, got {type(e).__name__}"
        _assert_no_secret_in("route-http-exception-detail", str(e.detail))

    # The chain-types log line MUST be there AND have no sentinel.
    chain_log = [r for r in handler.records if "exc_chain=" in r]
    assert chain_log, (
        f"Expected an 'exc_chain=' log record from routes.inference, "
        f"got: {handler.records!r}"
    )
    _assert_no_secret_in_records("route-chain-types-log", handler.records)
    # And it should usefully reveal the chain types so triaging isn't blind.
    joined = " ".join(chain_log)
    for t in ("RuntimeError", "ConnectionError", "OSError"):
        assert t in joined, f"chain-types log missing {t}: {joined!r}"
    test_logger.info("[PASS] route logs exc_chain types only, no sentinel leak")


# ─────────────────────────────────────────────────────────────────────
# Runner
# ─────────────────────────────────────────────────────────────────────

async def run_all() -> bool:
    tests = [
        ("resolver success log doesn't dump service_info",
         test_resolver_success_log_does_not_dump_service_info),
        ("resolver LookupError + log redacted",
         test_resolver_lookup_failure_log_redacted),
        ("resolver ConnectionError + log redacted",
         test_resolver_connection_failure_log_redacted),
        ("Triton-call RuntimeError + log redacted",
         test_triton_call_failure_log_and_exception_redacted),
        ("Triton-call DEBUG log redacted",
         test_triton_call_debug_log_redacted),
        ("orchestrator resolve-failure RuntimeError + log redacted",
         test_orchestrator_resolve_failure_log_and_exception_redacted),
    ]

    passed = 0
    failed = 0
    for name, fn in tests:
        try:
            await fn()
            passed += 1
        except Exception:
            failed += 1
            test_logger.exception(f"[FAIL] {name}")

    # Sync test (not async).
    try:
        test_route_http_envelope_uses_generic_message_for_runtime_errors()
        passed += 1
    except Exception:
        failed += 1
        test_logger.exception("[FAIL] HTTP envelope generic-message check")

    # Async test that exercises the full route's exception path.
    try:
        await test_route_logs_exc_chain_types_without_messages()
        passed += 1
    except Exception:
        failed += 1
        test_logger.exception("[FAIL] route logs exc_chain types without messages")

    test_logger.info("=" * 70)
    test_logger.info(f"{passed} passed, {failed} failed")
    test_logger.info("=" * 70)
    return failed == 0


if __name__ == "__main__":
    ok = asyncio.run(run_all())
    sys.exit(0 if ok else 1)
