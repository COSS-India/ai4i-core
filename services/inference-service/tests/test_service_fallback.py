"""Unit tests: Application service fallback (AI4IDS-3488).

Covers which failures move a request to a fallback (only an unreachable
model: timeout / connection error / 5xx), the Orchestrator's attempt loop,
the LLM proxy's fallback loop, the 503 mapping, and where the fallback map is
read from (local cache → Redis → auth-service).
"""

import asyncio
import sys
from unittest.mock import AsyncMock, MagicMock, patch

import httpx
import pytest

sys.path.insert(0, ".")

import services.service_fallback as service_fallback
from orchestrator.orchestrator import Orchestrator
from utils.failover import (
    AllServicesUnavailableError,
    UpstreamUnavailableError,
    classify_upstream_failure,
    failover_reason,
)
from utils.http_status import http_status_for


def _run(coro):
    return asyncio.run(coro)


# ── Which failures fail over ──────────────────────────────────────────────────

def _status_error(code: int) -> httpx.HTTPStatusError:
    request = httpx.Request("POST", "http://triton/infer")
    return httpx.HTTPStatusError("boom", request=request, response=httpx.Response(code, request=request))


@pytest.mark.parametrize(
    "exc, expected",
    [
        (httpx.ReadTimeout("t"), "timeout"),
        (httpx.ConnectError("c"), "unreachable"),
        (_status_error(503), "upstream_5xx"),
        (_status_error(500), "upstream_5xx"),
        (_status_error(400), None),
        (_status_error(422), None),
        (ValueError("bad input"), None),
        (LookupError("Triton endpoint not found"), None),
    ],
)
def test_classify_upstream_failure(exc, expected):
    assert classify_upstream_failure(exc) == expected


def test_classify_upstream_status_codes():
    assert classify_upstream_failure(status_code=502) == "upstream_5xx"
    assert classify_upstream_failure(status_code=429) is None
    assert classify_upstream_failure(status_code=200) is None


def test_failover_reason_walks_cause_chain():
    try:
        try:
            raise UpstreamUnavailableError("triton down", "timeout")
        except UpstreamUnavailableError as inner:
            raise RuntimeError("wrapped") from inner
    except RuntimeError as outer:
        assert failover_reason(outer) == "timeout"
    assert failover_reason(ValueError("bad input")) is None
    # A plain RuntimeError (e.g. Triton 4xx wrapped by _call_triton_inference) is not a failover.
    assert failover_reason(RuntimeError("Triton inference call failed")) is None


def test_all_services_unavailable_maps_to_503_with_body():
    exc = AllServicesUnavailableError("nmt-a", [("nmt-a", "timeout"), ("nmt-b", "upstream_5xx")])
    assert http_status_for(exc) == 503
    body = exc.to_body()
    assert body["code"] == "ALL_SERVICES_UNAVAILABLE"
    assert body["attempted"] == [
        {"service_id": "nmt-a", "reason": "timeout"},
        {"service_id": "nmt-b", "reason": "upstream_5xx"},
    ]


def test_upstream_unavailable_without_fallback_is_still_502():
    assert http_status_for(UpstreamUnavailableError("down", "timeout")) == 502


# ── Orchestrator attempt loop ─────────────────────────────────────────────────

def _make_orchestrator() -> Orchestrator:
    with patch("orchestrator.orchestrator.InferenceServerResolver"):
        return Orchestrator()


def _info(service_id: str) -> dict:
    return {"serviceId": service_id, "name": service_id, "class_instance": "X", "tier_ids": []}


def _task_service(result=None, exc=None) -> MagicMock:
    svc = MagicMock()
    svc.process = AsyncMock(side_effect=exc, return_value=result)
    return svc


def _wire(orch: Orchestrator, services: dict) -> None:
    """services: service_id -> task service mock; resolution returns _info(id)."""
    async def resolve(payload, attempt=0):
        sid = payload["config"]["serviceId"]
        if sid not in services:
            raise LookupError(f"Service {sid} not found")
        return _info(sid)

    orch._resolve_service_and_model = resolve
    orch._get_task_service = lambda info: services[info["serviceId"]]


PAYLOAD = {"task_type": "nmt", "config": {"serviceId": "nmt-a"}, "input": [{"source": "hi"}]}


def test_requested_service_success_never_touches_fallbacks():
    orch = _make_orchestrator()
    primary, fallback = _task_service({"output": ["a"]}), _task_service({"output": ["b"]})
    _wire(orch, {"nmt-a": primary, "nmt-b": fallback})

    _, response, served, attempts = _run(
        orch._run_with_fallbacks(PAYLOAD, _info("nmt-a"), ["nmt-b"], None)
    )

    assert response == {"output": ["a"]}
    assert served["serviceId"] == "nmt-a"
    assert attempts == []
    fallback.process.assert_not_called()


def test_unreachable_primary_moves_to_fallback():
    orch = _make_orchestrator()
    primary = _task_service(exc=UpstreamUnavailableError("down", "timeout"))
    fallback = _task_service({"output": ["b"]})
    _wire(orch, {"nmt-a": primary, "nmt-b": fallback})

    _, response, served, attempts = _run(
        orch._run_with_fallbacks(PAYLOAD, _info("nmt-a"), ["nmt-b"], None)
    )

    assert response == {"output": ["b"]}
    assert served["serviceId"] == "nmt-b"
    assert attempts == [("nmt-a", "timeout")]
    # The fallback is called with the payload aimed at itself.
    sent_payload = fallback.process.call_args.args[0]
    assert sent_payload["config"]["serviceId"] == "nmt-b"


def test_client_error_on_primary_is_returned_without_fallback():
    orch = _make_orchestrator()
    primary = _task_service(exc=ValueError("input payload is empty"))
    fallback = _task_service({"output": ["b"]})
    _wire(orch, {"nmt-a": primary, "nmt-b": fallback})

    with pytest.raises(ValueError, match="input payload is empty"):
        _run(orch._run_with_fallbacks(PAYLOAD, _info("nmt-a"), ["nmt-b"], None))
    fallback.process.assert_not_called()


def test_triton_4xx_on_primary_is_returned_without_fallback():
    orch = _make_orchestrator()
    primary = _task_service(exc=RuntimeError("Triton inference call failed"))
    fallback = _task_service({"output": ["b"]})
    _wire(orch, {"nmt-a": primary, "nmt-b": fallback})

    with pytest.raises(RuntimeError):
        _run(orch._run_with_fallbacks(PAYLOAD, _info("nmt-a"), ["nmt-b"], None))
    fallback.process.assert_not_called()


def test_unreachable_primary_without_fallbacks_raises_as_today():
    orch = _make_orchestrator()
    primary = _task_service(exc=UpstreamUnavailableError("down", "unreachable"))
    _wire(orch, {"nmt-a": primary})

    with pytest.raises(UpstreamUnavailableError):
        _run(orch._run_with_fallbacks(PAYLOAD, _info("nmt-a"), [], None))


def test_fallbacks_tried_in_order_and_ineligible_one_skipped():
    orch = _make_orchestrator()
    primary = _task_service(exc=UpstreamUnavailableError("down", "upstream_5xx"))
    second = _task_service({"output": ["c"]})
    # "nmt-gone" is configured but no longer resolvable (unpublished / deleted).
    _wire(orch, {"nmt-a": primary, "nmt-c": second})

    _, response, served, attempts = _run(
        orch._run_with_fallbacks(PAYLOAD, _info("nmt-a"), ["nmt-gone", "nmt-c"], None)
    )

    assert served["serviceId"] == "nmt-c"
    assert attempts == [("nmt-a", "upstream_5xx"), ("nmt-gone", "not_eligible")]


def test_fallback_out_of_tier_is_skipped():
    orch = _make_orchestrator()
    primary = _task_service(exc=UpstreamUnavailableError("down", "timeout"))
    fallback = _task_service({"output": ["b"]})
    _wire(orch, {"nmt-a": primary, "nmt-b": fallback})

    async def resolve(payload, attempt=0):
        info = _info(payload["config"]["serviceId"])
        if info["serviceId"] == "nmt-b":
            info["tier_ids"] = ["other-tier"]
        return info

    orch._resolve_service_and_model = resolve
    request = MagicMock()
    request.headers = {"X-Tier-ID": "my-tier"}

    with pytest.raises(AllServicesUnavailableError) as exc_info:
        _run(orch._run_with_fallbacks(PAYLOAD, _info("nmt-a"), ["nmt-b"], request))
    assert exc_info.value.attempts == [("nmt-a", "timeout"), ("nmt-b", "not_eligible")]
    fallback.process.assert_not_called()


def test_every_service_failing_raises_all_services_unavailable():
    orch = _make_orchestrator()
    primary = _task_service(exc=UpstreamUnavailableError("down", "timeout"))
    fallback = _task_service(exc=UpstreamUnavailableError("down", "upstream_5xx"))
    _wire(orch, {"nmt-a": primary, "nmt-b": fallback})

    with pytest.raises(AllServicesUnavailableError) as exc_info:
        _run(orch._run_with_fallbacks(PAYLOAD, _info("nmt-a"), ["nmt-b"], None))
    assert exc_info.value.attempts == [("nmt-a", "timeout"), ("nmt-b", "upstream_5xx")]


def test_fallback_rejecting_the_input_is_skipped():
    orch = _make_orchestrator()
    primary = _task_service(exc=UpstreamUnavailableError("down", "timeout"))
    picky = _task_service(exc=ValueError("language pair not supported"))
    last = _task_service({"output": ["d"]})
    _wire(orch, {"nmt-a": primary, "nmt-b": picky, "nmt-d": last})

    _, _, served, attempts = _run(
        orch._run_with_fallbacks(PAYLOAD, _info("nmt-a"), ["nmt-b", "nmt-d"], None)
    )
    assert served["serviceId"] == "nmt-d"
    assert attempts == [("nmt-a", "timeout"), ("nmt-b", "fallback_rejected")]


# ── LLM proxy fallback loop ───────────────────────────────────────────────────

def _llm_proxy():
    from services.llm_service import OpenAIProxyService

    proxy = OpenAIProxyService()

    async def prepare(path, payload, request=None):
        sid = payload["model"]
        return f"http://{sid}/v1/chat/completions", sid, f"{sid}-model", payload, {"serviceId": sid}

    proxy._prepare_request = prepare
    return proxy


def test_llm_success_is_returned_untouched():
    proxy = _llm_proxy()
    request = MagicMock()
    with patch("services.llm_service.get_fallbacks", AsyncMock(return_value=["llm-b"])) as gf:
        status, body = _run(proxy._fallback_if_unreachable(
            "/v1/chat/completions", request, "llm-a", {"model": "x"}, 200, {"ok": True}
        ))
    assert (status, body) == (200, {"ok": True})
    gf.assert_not_called()
    assert request.state.service_id == "llm-a"
    assert request.state.fallback_used is False


def test_llm_4xx_is_returned_without_fallback():
    proxy = _llm_proxy()
    with patch("services.llm_service.get_fallbacks", AsyncMock(return_value=["llm-b"])) as gf:
        status, _ = _run(proxy._fallback_if_unreachable(
            "/v1/chat/completions", MagicMock(), "llm-a", {"model": "x"}, 400, {"detail": "bad"}
        ))
    assert status == 400
    gf.assert_not_called()


def test_llm_unreachable_moves_to_fallback():
    proxy = _llm_proxy()
    proxy._forward_traced = AsyncMock(return_value=(200, {"choices": []}))
    request = MagicMock()
    with patch("services.llm_service.get_fallbacks", AsyncMock(return_value=["llm-b"])):
        status, body = _run(proxy._fallback_if_unreachable(
            "/v1/chat/completions", request, "llm-a", {"model": "llm-a-model"}, 502, {"detail": "down"}
        ))
    assert status == 200
    assert request.state.service_id == "llm-b"
    assert request.state.requested_service_id == "llm-a"
    assert request.state.fallback_used is True
    # The fallback gets its own upstream model name.
    forwarded_payload = proxy._forward_traced.call_args.args[4]
    assert forwarded_payload["model"] == "llm-b-model"


def test_llm_every_service_failing_returns_503():
    proxy = _llm_proxy()
    proxy._forward_traced = AsyncMock(return_value=(500, {"detail": "boom"}))
    with patch("services.llm_service.get_fallbacks", AsyncMock(return_value=["llm-b"])):
        status, body = _run(proxy._fallback_if_unreachable(
            "/v1/chat/completions", MagicMock(), "llm-a", {"model": "x"}, 502, {"detail": "down"}
        ))
    assert status == 503
    assert body["code"] == "ALL_SERVICES_UNAVAILABLE"
    assert [a["service_id"] for a in body["attempted"]] == ["llm-a", "llm-b"]


# ── Where the fallback map comes from ─────────────────────────────────────────

@pytest.fixture(autouse=True)
def _clear_local_cache():
    service_fallback._local_cache.clear()
    yield
    service_fallback._local_cache.clear()


def test_get_fallbacks_reads_redis():
    with patch.object(service_fallback, "_read_redis", AsyncMock(return_value={"nmt-a": ["nmt-b"]})), \
         patch.object(service_fallback, "_read_auth_service", AsyncMock()) as auth:
        assert _run(service_fallback.get_fallbacks("nmt-a", app_id="42")) == ["nmt-b"]
    auth.assert_not_called()


def test_get_fallbacks_loads_from_auth_service_on_redis_miss():
    with patch.object(service_fallback, "_read_redis", AsyncMock(return_value=None)), \
         patch.object(service_fallback, "_read_auth_service", AsyncMock(return_value={"nmt-a": ["nmt-c"]})) as auth:
        assert _run(service_fallback.get_fallbacks("nmt-a", app_id="42")) == ["nmt-c"]
    auth.assert_awaited_once_with("42")


def test_get_fallbacks_uses_local_cache():
    redis = AsyncMock(return_value={"nmt-a": ["nmt-b"]})
    with patch.object(service_fallback, "_read_redis", redis):
        _run(service_fallback.get_fallbacks("nmt-a", app_id="42"))
        _run(service_fallback.get_fallbacks("nmt-a", app_id="42"))
    assert redis.await_count == 1


def test_get_fallbacks_without_application_is_empty():
    with patch.object(service_fallback, "_read_redis", AsyncMock()) as redis, \
         patch.object(service_fallback, "get_application_id", return_value=None):
        assert _run(service_fallback.get_fallbacks("nmt-a")) == []
    redis.assert_not_called()


def test_get_fallbacks_for_unconfigured_service_is_empty():
    with patch.object(service_fallback, "_read_redis", AsyncMock(return_value={"nmt-a": ["nmt-b"]})):
        assert _run(service_fallback.get_fallbacks("asr-x", app_id="42")) == []


def test_auth_service_failure_means_no_fallback(monkeypatch):
    monkeypatch.setattr(service_fallback.settings, "AUTH_SERVICE_URL", "http://auth:8081")

    class _Boom:
        def __init__(self, *a, **k): pass
        async def __aenter__(self): return self
        async def __aexit__(self, *a): return False
        async def get(self, url): raise httpx.ConnectError("auth down")

    with patch.object(service_fallback.httpx, "AsyncClient", _Boom):
        assert _run(service_fallback._read_auth_service("42")) == {}


# ── The Triton call marks only an unreachable model ──────────────────────────

def _triton_call(client):
    from services.base.task_service import BaseTaskService

    svc = BaseTaskService(service_info={"name": "nmt-a"})
    with patch("services.base.task_service._get_triton_client", return_value=client):
        return _run(svc._call_triton_inference("http://triton/infer", [{"name": "IN"}], ["OUT"]))


def test_triton_connect_error_is_marked_for_failover():
    client = MagicMock()
    client.post = AsyncMock(side_effect=httpx.ConnectError("refused"))
    with pytest.raises(UpstreamUnavailableError) as exc_info:
        _triton_call(client)
    assert exc_info.value.reason == "unreachable"


def test_triton_5xx_is_marked_for_failover():
    request = httpx.Request("POST", "http://triton/infer")
    client = MagicMock()
    client.post = AsyncMock(return_value=httpx.Response(503, request=request))
    with pytest.raises(UpstreamUnavailableError) as exc_info:
        _triton_call(client)
    assert exc_info.value.reason == "upstream_5xx"


@pytest.mark.parametrize("code", [400, 404, 422])
def test_triton_4xx_is_not_marked_for_failover(code):
    request = httpx.Request("POST", "http://triton/infer")
    client = MagicMock()
    client.post = AsyncMock(return_value=httpx.Response(code, request=request))
    with pytest.raises(RuntimeError) as exc_info:
        _triton_call(client)
    assert not isinstance(exc_info.value, UpstreamUnavailableError)
    assert failover_reason(exc_info.value) is None


# ── The fallback map is read only after a failover-worthy failure ────────────

def test_healthy_request_never_reads_the_fallback_map():
    orch = _make_orchestrator()
    _wire(orch, {"nmt-a": _task_service({"output": ["a"]})})
    with patch("orchestrator.orchestrator.get_fallbacks", AsyncMock()) as gf:
        _run(orch._run_with_fallbacks(PAYLOAD, _info("nmt-a"), None, None))
    gf.assert_not_called()


def test_client_error_never_reads_the_fallback_map():
    orch = _make_orchestrator()
    _wire(orch, {"nmt-a": _task_service(exc=ValueError("bad input"))})
    with patch("orchestrator.orchestrator.get_fallbacks", AsyncMock()) as gf:
        with pytest.raises(ValueError):
            _run(orch._run_with_fallbacks(PAYLOAD, _info("nmt-a"), None, None))
    gf.assert_not_called()


def test_unreachable_primary_reads_the_map_then_fails_over():
    orch = _make_orchestrator()
    _wire(orch, {
        "nmt-a": _task_service(exc=UpstreamUnavailableError("down", "timeout")),
        "nmt-b": _task_service({"output": ["b"]}),
    })
    with patch("orchestrator.orchestrator.get_fallbacks", AsyncMock(return_value=["nmt-b"])) as gf:
        _, _, served, _ = _run(orch._run_with_fallbacks(PAYLOAD, _info("nmt-a"), None, None))
    gf.assert_awaited_once_with("nmt-a")
    assert served["serviceId"] == "nmt-b"


# ── A "fallback" span per fallback attempt ───────────────────────────────────

def _record_spans():
    """Patch traced_span so each opened span's (name, attrs) is captured."""
    from contextlib import contextmanager

    spans = []

    @contextmanager
    def fake_span(name, **kwargs):
        attrs = {}
        spans.append((name, attrs))
        yield attrs

    return spans, patch("trace.request_span.traced_span", fake_span)


def test_fallback_span_records_success():
    orch = _make_orchestrator()
    _wire(orch, {
        "nmt-a": _task_service(exc=UpstreamUnavailableError("down", "timeout")),
        "nmt-b": _task_service({"output": ["b"]}),
    })
    spans, patcher = _record_spans()
    with patcher:
        _run(orch._run_with_fallbacks(PAYLOAD, _info("nmt-a"), ["nmt-b"], None))

    fallback = [attrs for name, attrs in spans if name == "fallback request"]
    assert len(fallback) == 1
    assert fallback[0]["requested_service_id"] == "nmt-a"
    assert fallback[0]["failed_service_id"] == "nmt-a"
    assert fallback[0]["failover_reason"] == "timeout"
    assert fallback[0]["fallback_service_id"] == "nmt-b"
    assert fallback[0]["attempt"] == 1
    assert fallback[0]["outcome"] == "success"


def test_fallback_spans_record_skip_and_failure():
    orch = _make_orchestrator()
    _wire(orch, {
        "nmt-a": _task_service(exc=UpstreamUnavailableError("down", "timeout")),
        "nmt-c": _task_service(exc=UpstreamUnavailableError("down", "upstream_5xx")),
    })
    spans, patcher = _record_spans()
    with patcher, pytest.raises(AllServicesUnavailableError):
        _run(orch._run_with_fallbacks(PAYLOAD, _info("nmt-a"), ["nmt-gone", "nmt-c"], None))

    fallback = [attrs for name, attrs in spans if name == "fallback request"]
    assert [(f["fallback_service_id"], f["outcome"]) for f in fallback] == [
        ("nmt-gone", "not_eligible"),
        ("nmt-c", "failed"),
    ]
    assert fallback[1]["failed_service_id"] == "nmt-gone"
    assert fallback[1]["error_reason"] == "upstream_5xx"


def test_no_fallback_span_when_requested_service_answers():
    orch = _make_orchestrator()
    _wire(orch, {"nmt-a": _task_service({"output": ["a"]})})
    spans, patcher = _record_spans()
    with patcher:
        _run(orch._run_with_fallbacks(PAYLOAD, _info("nmt-a"), ["nmt-b"], None))
    assert not [name for name, _ in spans if name == "fallback request"]


def test_llm_fallback_span_records_success():
    proxy = _llm_proxy()
    proxy._forward_traced = AsyncMock(return_value=(200, {"choices": []}))
    spans, patcher = _record_spans()
    with patcher, patch("services.llm_service.get_fallbacks", AsyncMock(return_value=["llm-b"])):
        _run(proxy._fallback_if_unreachable(
            "/v1/chat/completions", MagicMock(), "llm-a", {"model": "x"}, 502, {"detail": "down"}
        ))
    fallback = [attrs for name, attrs in spans if name == "fallback request"]
    assert len(fallback) == 1
    assert fallback[0]["fallback_service_id"] == "llm-b"
    assert fallback[0]["model_name"] == "llm-b-model"
    assert fallback[0]["status_code"] == 200
    assert fallback[0]["outcome"] == "success"


# ── Shared LLM fallback loop (_run_fallbacks), as both callers use it ────────

def test_run_fallbacks_stream_style_first_open_wins():
    proxy = _llm_proxy()
    calls = []

    async def attempt(fallback_id, url, model_name, payload, info, index):
        # Streaming caller: ok means the stream opened.
        calls.append((fallback_id, payload["model"], index))
        return (fallback_id == "llm-c"), (200 if fallback_id == "llm-c" else 503), "stream-or-error"

    outcome = _run(proxy._run_fallbacks(
        "/v1/chat/completions", MagicMock(), "llm-a", "upstream_5xx", ["llm-b", "llm-c"], {"model": "x"}, attempt,
    ))
    assert calls == [("llm-b", "llm-b-model", 1), ("llm-c", "llm-c-model", 2)]
    assert outcome.ok and outcome.served_id == "llm-c" and outcome.attempt == 2
    assert outcome.model_name == "llm-c-model"
    assert outcome.payload["model"] == "llm-c-model"


def test_run_fallbacks_all_failing_returns_503_for_the_requested_service():
    proxy = _llm_proxy()

    async def attempt(*args):
        return False, 502, {"detail": "down"}

    outcome = _run(proxy._run_fallbacks(
        "/v1/chat/completions", MagicMock(), "llm-a", "upstream_5xx", ["llm-b"], {"model": "x"}, attempt,
    ))
    assert not outcome.ok
    assert outcome.served_id == "llm-a" and outcome.status_code == 503
    assert [a["service_id"] for a in outcome.result["attempted"]] == ["llm-a", "llm-b"]


def test_run_fallbacks_skips_a_fallback_that_cannot_be_resolved():
    from services.llm_service import LLMProxyError

    proxy = _llm_proxy()
    resolve = proxy._prepare_request

    async def prepare(path, payload, request=None):
        if payload["model"] == "llm-gone":
            raise LLMProxyError(404, {"detail": "not found"}, service_id="llm-gone")
        return await resolve(path, payload, request)

    proxy._prepare_request = prepare

    async def attempt(fallback_id, *args):
        return True, 200, "ok"

    outcome = _run(proxy._run_fallbacks(
        "/v1/chat/completions", MagicMock(), "llm-a", "upstream_5xx", ["llm-gone", "llm-b"], {"model": "x"}, attempt,
    ))
    assert outcome.served_id == "llm-b" and outcome.attempt == 2
