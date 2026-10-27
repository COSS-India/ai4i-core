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
    # Service ids only — the per-service reasons stay in the logs.
    assert body == {
        "code": "ALL_SERVICES_UNAVAILABLE",
        "message": "Service 'nmt-a' and its fallback service(s) are unavailable (tried: nmt-a, nmt-b)",
    }
    assert exc.to_openai_error() == {
        "error": {"message": body["message"], "type": "all_services_unavailable"}
    }


def test_upstream_unavailable_without_fallback_is_still_502():
    assert http_status_for(UpstreamUnavailableError("down", "timeout")) == 502


# ── Orchestrator attempt loop ─────────────────────────────────────────────────

def _make_orchestrator() -> Orchestrator:
    with patch("orchestrator.orchestrator.InferenceServerResolver"):
        return Orchestrator()


def _info(service_id: str) -> dict:
    return {"serviceId": service_id, "name": service_id, "class_instance": "X", "tier_ids": []}


def _task_service(result=None, exc=None, billed_groups=0) -> MagicMock:
    svc = MagicMock()
    svc.process = AsyncMock(side_effect=exc, return_value=result)
    # Groups already served (and billed) before the failure — see
    # BaseTaskService.billed_groups.
    svc.billed_groups = billed_groups
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


def test_fallback_rejecting_the_input_is_returned_to_the_client():
    orch = _make_orchestrator()
    primary = _task_service(exc=UpstreamUnavailableError("down", "timeout"))
    picky = _task_service(exc=ValueError("language pair not supported"))
    last = _task_service({"output": ["d"]})
    _wire(orch, {"nmt-a": primary, "nmt-b": picky, "nmt-d": last})

    with pytest.raises(ValueError, match="language pair not supported"):
        _run(orch._run_with_fallbacks(PAYLOAD, _info("nmt-a"), ["nmt-b", "nmt-d"], None))
    last.process.assert_not_called()


# ── LLM proxy fallback loop ───────────────────────────────────────────────────

def _llm_proxy():
    from services.llm_service import OpenAIProxyService

    proxy = OpenAIProxyService()

    async def prepare(path, payload, request=None):
        sid = payload["model"]
        return f"http://{sid}{path}", sid, f"{sid}-model", payload, {"serviceId": sid}

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
    proxy._forward_traced = AsyncMock(return_value=(200, {"choices": []}, None))
    request = MagicMock()
    with patch("services.llm_service.get_fallbacks", AsyncMock(return_value=["llm-b"])):
        status, body = _run(proxy._fallback_if_unreachable(
            "/v1/chat/completions", request, "llm-a", {"model": "llm-a-model"}, 502, {"detail": "down"}
        ))
    assert status == 200
    assert request.state.service_id == "llm-b"
    # The fallback gets its own upstream model name.
    forwarded_payload = proxy._forward_traced.call_args.args[4]
    assert forwarded_payload["model"] == "llm-b-model"


def test_llm_every_service_failing_returns_503():
    proxy = _llm_proxy()
    proxy._forward_traced = AsyncMock(return_value=(500, {"detail": "boom"}, "upstream_5xx"))
    with patch("services.llm_service.get_fallbacks", AsyncMock(return_value=["llm-b"])):
        status, body = _run(proxy._fallback_if_unreachable(
            "/v1/chat/completions", MagicMock(), "llm-a", {"model": "x"}, 502, {"detail": "down"}
        ))
    assert status == 503
    # OpenAI shape: clients read error.message.
    assert body["error"]["type"] == "all_services_unavailable"
    assert "llm-a" in body["error"]["message"]
    assert "attempted" not in body["error"]


# ── Where the fallback map comes from ─────────────────────────────────────────

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


def test_get_fallbacks_reads_redis_on_every_call():
    redis = AsyncMock(return_value={"nmt-a": ["nmt-b"]})
    with patch.object(service_fallback, "_read_redis", redis):
        _run(service_fallback.get_fallbacks("nmt-a", app_id="42"))
        _run(service_fallback.get_fallbacks("nmt-a", app_id="42"))
    assert redis.await_count == 2


def test_redis_read_uses_the_guardrail_client():
    client = MagicMock()
    client.get = AsyncMock(return_value='{"nmt-a": ["nmt-b"]}')
    with patch("services.guardrail._get_redis", return_value=client):
        assert _run(service_fallback._read_redis("42")) == {"nmt-a": ["nmt-b"]}
    client.get.assert_awaited_once_with("auth:app:42:service_fallbacks")


def test_redis_unavailable_reads_as_a_miss():
    with patch("services.guardrail._get_redis", return_value=None):
        assert _run(service_fallback._read_redis("42")) is None


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


# ── The failover log line (what the Jira asks for) ───────────────────────────

def test_orchestrator_logs_each_failover():
    orch = _make_orchestrator()
    _wire(orch, {
        "nmt-a": _task_service(exc=UpstreamUnavailableError("down", "timeout")),
        "nmt-b": _task_service({"output": ["b"]}),
    })
    with patch("orchestrator.orchestrator.log_failover") as log:
        _run(orch._run_with_fallbacks(PAYLOAD, _info("nmt-a"), ["nmt-b"], None))
    log.assert_called_once_with(
        requested="nmt-a", failed="nmt-a", next_service="nmt-b", reason="timeout", attempt=1,
    )


def test_llm_logs_each_failover_and_records_served_service():
    proxy = _llm_proxy()
    proxy._forward_traced = AsyncMock(return_value=(200, {"choices": []}, None))
    request = MagicMock()
    with patch("services.llm_service.get_fallbacks", AsyncMock(return_value=["llm-b"])),          patch("services.llm_service.log_failover") as log:
        _run(proxy._fallback_if_unreachable(
            "/v1/chat/completions", request, "llm-a", {"model": "x"}, 502, {"detail": "down"}
        ))
    log.assert_called_once_with(
        requested="llm-a", failed="llm-a", next_service="llm-b", reason="upstream_5xx", attempt=1,
    )
    assert request.state.service_id == "llm-b"


# ── Shared LLM fallback loop (_run_fallbacks), as both callers use it ────────

def test_run_fallbacks_stream_style_first_open_wins():
    proxy = _llm_proxy()
    calls = []

    async def attempt(fallback_id, url, model_name, payload, info, index):
        # Streaming caller: ok means the stream opened.
        calls.append((fallback_id, payload["model"], index))
        ok = fallback_id == "llm-c"
        return ok, (200 if ok else 503), "stream-or-error", (None if ok else "upstream_5xx")

    outcome = _run(proxy._run_fallbacks(
        "/v1/chat/completions", MagicMock(), "llm-a", "upstream_5xx", ["llm-b", "llm-c"], {"model": "x"}, attempt,
    ))
    assert calls == [("llm-b", "llm-b-model", 1), ("llm-c", "llm-c-model", 2)]
    assert outcome.ok and outcome.served_id == "llm-c"
    assert outcome.model_name == "llm-c-model"
    assert outcome.payload["model"] == "llm-c-model"


def test_run_fallbacks_all_failing_returns_503_for_the_requested_service():
    proxy = _llm_proxy()

    async def attempt(*args):
        return False, 502, {"detail": "down"}, "unreachable"

    outcome = _run(proxy._run_fallbacks(
        "/v1/chat/completions", MagicMock(), "llm-a", "upstream_5xx", ["llm-b"], {"model": "x"}, attempt,
    ))
    assert not outcome.ok
    assert outcome.served_id == "llm-a" and outcome.status_code == 503
    assert outcome.result["error"]["type"] == "all_services_unavailable"


def test_run_fallbacks_returns_a_fallbacks_4xx_without_trying_the_next():
    proxy = _llm_proxy()
    calls = []

    async def attempt(fallback_id, *args):
        calls.append(fallback_id)
        return False, 400, {"error": {"message": "context too long"}}, None

    outcome = _run(proxy._run_fallbacks(
        "/v1/chat/completions", MagicMock(), "llm-a", "timeout", ["llm-b", "llm-c"], {"model": "x"}, attempt,
    ))
    assert calls == ["llm-b"]
    assert not outcome.ok
    assert (outcome.served_id, outcome.status_code) == ("llm-b", 400)
    assert outcome.result == {"error": {"message": "context too long"}}


def test_run_fallbacks_all_failing_keeps_the_requested_model_id_label():
    from ai4i_core.context import get_llm_usage_model_id, set_llm_usage_model_id

    proxy = _llm_proxy()
    plain_prepare = proxy._prepare_request

    async def prepare(path, payload, request=None):
        # Like the real _prepare_request: the label follows each resolved service.
        set_llm_usage_model_id(f"{payload['model']}-model-id")
        return await plain_prepare(path, payload, request)

    proxy._prepare_request = prepare

    async def attempt(*args):
        return False, 502, {"detail": "down"}, "unreachable"

    async def scenario():
        set_llm_usage_model_id("llm-a-model-id")  # set when the requested service resolved
        await proxy._run_fallbacks(
            "/v1/chat/completions", MagicMock(), "llm-a", "timeout", ["llm-b", "llm-c"], {"model": "x"}, attempt,
        )
        return get_llm_usage_model_id()

    assert _run(scenario()) == "llm-a-model-id"


def test_run_fallbacks_success_labels_the_fallbacks_model_id():
    from ai4i_core.context import get_llm_usage_model_id, set_llm_usage_model_id

    proxy = _llm_proxy()
    plain_prepare = proxy._prepare_request

    async def prepare(path, payload, request=None):
        set_llm_usage_model_id(f"{payload['model']}-model-id")
        return await plain_prepare(path, payload, request)

    proxy._prepare_request = prepare

    async def attempt(*args):
        return True, 200, {"ok": True}, None

    async def scenario():
        set_llm_usage_model_id("llm-a-model-id")
        await proxy._run_fallbacks(
            "/v1/chat/completions", MagicMock(), "llm-a", "timeout", ["llm-b"], {"model": "x"}, attempt,
        )
        return get_llm_usage_model_id()

    assert _run(scenario()) == "llm-b-model-id"


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
        return True, 200, "ok", None

    outcome = _run(proxy._run_fallbacks(
        "/v1/chat/completions", MagicMock(), "llm-a", "upstream_5xx", ["llm-gone", "llm-b"], {"model": "x"}, attempt,
    ))
    assert outcome.served_id == "llm-b"


# ── No failover once part of the payload was billed (per_item groups) ───────

def test_no_failover_after_a_group_was_billed():
    orch = _make_orchestrator()
    primary = _task_service(exc=UpstreamUnavailableError("down", "timeout"), billed_groups=1)
    fallback = _task_service({"output": ["b"]})
    _wire(orch, {"nmt-a": primary, "nmt-b": fallback})

    with patch("orchestrator.orchestrator.get_fallbacks", AsyncMock(return_value=["nmt-b"])):
        with pytest.raises(UpstreamUnavailableError):
            _run(orch._run_with_fallbacks(PAYLOAD, _info("nmt-a"), None, None))
    fallback.process.assert_not_called()


def test_partly_billed_fallback_stops_the_chain():
    orch = _make_orchestrator()
    primary = _task_service(exc=UpstreamUnavailableError("down", "timeout"))
    partial = _task_service(exc=UpstreamUnavailableError("down", "upstream_5xx"), billed_groups=1)
    last = _task_service({"output": ["c"]})
    _wire(orch, {"nmt-a": primary, "nmt-b": partial, "nmt-c": last})

    with pytest.raises(AllServicesUnavailableError) as exc_info:
        _run(orch._run_with_fallbacks(PAYLOAD, _info("nmt-a"), ["nmt-b", "nmt-c"], None))
    assert exc_info.value.attempts == [("nmt-a", "timeout"), ("nmt-b", "upstream_5xx")]
    last.process.assert_not_called()


def test_run_inference_counts_only_completed_groups():
    from services.base.task_service import BaseTaskService

    class _PerItem(BaseTaskService):
        payload_key = "input"
        TRITON_CALL_MODE = "per_item"

    svc = _PerItem()
    svc.convert_payload_to_triton_format = AsyncMock(return_value=([{"name": "IN"}], ["OUT"]))
    svc.convert_triton_output_to_task_format = AsyncMock(return_value=[{"target": "x"}])
    svc._call_triton_inference = AsyncMock(
        side_effect=[{"outputs": []}, UpstreamUnavailableError("down", "timeout")]
    )
    payload = {"task_type": "TTS", "input": [{"source": "a"}, {"source": "b"}], "config": {}}
    info = {"name": "tts", "endpoint": "http://triton/infer", "serviceId": "tts-a", "adapter_config": {}}

    with patch("trace.span_attributes.get_unit_type", AsyncMock(return_value="character")),          patch("trace.span_attributes.count_input_tokens", return_value=1),          patch("trace.span_attributes.count_output_tokens", return_value=1):
        with pytest.raises(UpstreamUnavailableError):
            _run(svc.run_inference(payload, info))
    assert svc.billed_groups == 1


# ── LLM audio uploads (proxy_multipart) fail over too ────────────────────────

_AUDIO_PATH = "/v1/audio/transcriptions"
_FILES = {"file": ("a.wav", b"RIFF-bytes", "audio/wav")}


def _audio_proxy(post_results):
    proxy = _llm_proxy()
    proxy.resolve_upstream_url = AsyncMock(return_value=(
        f"http://asr-a{_AUDIO_PATH}", {"adapter_config": {"model_name": "whisper-a"}, "tier_ids": []},
    ))
    # (status, body) → (status, body, reason), as _post_multipart classifies it.
    proxy._post_multipart = AsyncMock(side_effect=[
        (sc, body, classify_upstream_failure(status_code=sc)) for sc, body in post_results
    ])
    return proxy


def _upload(proxy, request=None):
    return _run(proxy.proxy_multipart(
        _AUDIO_PATH, files=_FILES, data={"model": "asr-a", "language": "hi"}, request=request,
    ))


def test_audio_upload_unreachable_moves_to_fallback_with_the_same_file():
    proxy = _audio_proxy([(502, {"error": {"message": "down"}}), (200, {"text": "namaste"})])
    request = MagicMock()
    request.headers = {}
    with patch("services.llm_service.get_fallbacks", AsyncMock(return_value=["asr-b"])):
        status, body = _upload(proxy, request)

    assert (status, body) == (200, {"text": "namaste"})
    requested_call, fallback_call = proxy._post_multipart.call_args_list
    assert requested_call.args[1] == f"http://asr-a{_AUDIO_PATH}"
    assert requested_call.args[3]["model"] == "whisper-a"
    assert fallback_call.args[1] == f"http://asr-b{_AUDIO_PATH}"
    assert fallback_call.args[2] is _FILES                    # same upload
    assert fallback_call.args[3]["model"] == "asr-b-model"     # fallback's upstream model
    assert fallback_call.args[3]["language"] == "hi"           # other form fields kept
    assert request.state.service_id == "asr-b"


def test_audio_upload_4xx_is_returned_without_fallback():
    proxy = _audio_proxy([(400, {"error": {"message": "bad file"}})])
    with patch("services.llm_service.get_fallbacks", AsyncMock(return_value=["asr-b"])) as gf:
        status, _ = _upload(proxy, MagicMock(headers={}))
    assert status == 400
    gf.assert_not_called()
    assert proxy._post_multipart.await_count == 1


def test_audio_upload_all_failing_returns_503_in_the_openai_envelope():
    proxy = _audio_proxy([(503, {"error": {}}), (500, {"error": {}})])
    with patch("services.llm_service.get_fallbacks", AsyncMock(return_value=["asr-b"])):
        status, body = _upload(proxy, MagicMock(headers={}))
    assert status == 503
    assert body["error"]["type"] == "all_services_unavailable"
    assert "asr-a" in body["error"]["message"] and "asr-b" in body["error"]["message"]


def test_audio_upload_without_fallbacks_is_unchanged():
    proxy = _audio_proxy([(502, {"error": {"message": "down"}})])
    with patch("services.llm_service.get_fallbacks", AsyncMock(return_value=[])):
        status, body = _upload(proxy, MagicMock(headers={}))
    assert (status, body) == (502, {"error": {"message": "down"}})


# ── LLM failover reasons come from the exception, not the 502 ───────────────

def _transport_error(exc):
    async def raise_(*a, **k):
        raise exc
    return raise_


def test_llm_timeout_is_classified_as_timeout_not_5xx():
    proxy = _llm_proxy()
    proxy.forward = _transport_error(httpx.ReadTimeout("slow"))
    status, body, reason = _run(proxy._forward_traced(
        "/v1/chat/completions", "http://llm-a/v1/chat/completions", "llm-a", "m", {"model": "m"}, {},
    ))
    assert (status, reason) == (502, "timeout")


def test_llm_connection_error_is_classified_as_unreachable():
    proxy = _llm_proxy()
    proxy.forward = _transport_error(httpx.ConnectError("refused"))
    _, _, reason = _run(proxy._forward_traced(
        "/v1/chat/completions", "http://llm-a/v1/chat/completions", "llm-a", "m", {"model": "m"}, {},
    ))
    assert reason == "unreachable"


def test_llm_failover_logs_the_real_reason():
    proxy = _llm_proxy()
    proxy._forward_traced = AsyncMock(return_value=(503, {"detail": "boom"}, "upstream_5xx"))
    with patch("services.llm_service.get_fallbacks", AsyncMock(return_value=["llm-b"])), \
         patch("services.llm_service.log_failover") as log, \
         patch("services.llm_service.log_all_failed") as all_failed:
        _run(proxy._fallback_if_unreachable(
            "/v1/chat/completions", MagicMock(), "llm-a", {"model": "x"}, 502, {"detail": "down"}, "timeout",
        ))
    assert log.call_args.kwargs["reason"] == "timeout"
    assert all_failed.call_args.kwargs["attempts"] == [("llm-a", "timeout"), ("llm-b", "upstream_5xx")]


def test_stream_open_timeout_is_classified_as_timeout():
    proxy = _llm_proxy()
    proxy.open_stream = _transport_error(httpx.ConnectTimeout("slow"))
    kind, status, _ = _run(proxy.proxy_stream("http://llm-a/v1/chat/completions", {}, {}))
    assert (kind, status) == ("error", 502)
    assert proxy._last_stream_failure_reason == "timeout"


# ── A hung stream start times out (and so can fail over) ─────────────────────

class _HangingClient:
    """httpx.AsyncClient stand-in whose send() never returns."""
    def __init__(self, *a, **k):
        self.closed = False
    def build_request(self, *a, **k):
        return MagicMock()
    async def send(self, *a, **k):
        await asyncio.sleep(10)
    async def aclose(self):
        self.closed = True


def test_stream_without_response_headers_times_out():
    from services.llm_service import OpenAIProxyService

    proxy = OpenAIProxyService()
    proxy.timeout = 0.05
    with patch("services.llm_service.httpx.AsyncClient", _HangingClient):
        kind, status, body = _run(proxy.proxy_stream("http://llm-a/v1/chat/completions", {}, {}))
    assert (kind, status) == ("error", 502)
    assert proxy._last_stream_failure_reason == "timeout"


def _open_stream_with(lines_coro):
    client, response = MagicMock(), MagicMock()
    client.aclose = AsyncMock()
    response.aclose = AsyncMock()
    response.aiter_lines = lines_coro
    return client, response


def test_stream_without_a_first_line_times_out_and_closes():
    from services.llm_service import OpenAIProxyService

    async def never():
        await asyncio.sleep(10)
        yield "data: late"

    proxy = OpenAIProxyService()
    proxy.timeout = 0.05
    client, response = _open_stream_with(never)
    proxy.open_stream = AsyncMock(return_value=(client, response))
    kind, status, body = _run(proxy.proxy_stream("http://llm-a/v1/chat/completions", {}, {}))
    assert (kind, status) == ("error", 502)
    assert body["error"]["type"] == "upstream_error"
    assert proxy._last_stream_failure_reason == "timeout"
    response.aclose.assert_awaited()
    client.aclose.assert_awaited()


def test_stream_that_starts_passes_every_line_through():
    from services.llm_service import OpenAIProxyService

    async def sse():
        yield "data: one"
        yield ""
        yield "data: [DONE]"

    proxy = OpenAIProxyService()
    client, response = _open_stream_with(sse)
    proxy.open_stream = AsyncMock(return_value=(client, response))
    # Open and drain in one event loop, as the route does — a second
    # asyncio.run would find the upstream generator already shut down.
    async def open_and_drain():
        kind, status, gen = await proxy.proxy_stream("http://llm-a/v1/chat/completions", {}, {})
        return kind, status, [chunk async for chunk in gen]

    kind, status, chunks = _run(open_and_drain())
    assert (kind, status) == ("stream", 200)
    assert chunks == ["data: one\n", "\n", "data: [DONE]\n"]
    client.aclose.assert_awaited()


def test_patched_proxy_stream_still_yields_a_reason():
    # Callers/tests that replace proxy_stream leave no recorded reason; the
    # status code then decides it.
    from services.llm_service import OpenAIProxyService

    proxy = OpenAIProxyService()
    proxy._last_stream_failure_reason = None
    assert proxy._stream_failure_reason(503) == "upstream_5xx"
    assert proxy._stream_failure_reason(400) is None


def test_audio_upload_timeout_is_classified_as_timeout():
    from services.llm_service import OpenAIProxyService

    class _Client:
        def __init__(self, *a, **k): pass
        async def __aenter__(self): return self
        async def __aexit__(self, *a): return False
        async def post(self, *a, **k): raise httpx.ReadTimeout("slow")

    with patch("services.llm_service.httpx.AsyncClient", _Client):
        status, _, reason = _run(OpenAIProxyService()._post_multipart(
            _AUDIO_PATH, f"http://asr-a{_AUDIO_PATH}", _FILES, {"model": "m"}, {},
        ))
    assert (status, reason) == (502, "timeout")
