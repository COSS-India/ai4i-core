"""Application service fallback (AI4IDS-3488): which failures fail over, the
Orchestrator and LLM proxy retry loops, the 503 mapping, and the Redis read."""

import asyncio
import sys
from unittest.mock import AsyncMock, MagicMock, patch

import httpx
import pytest

sys.path.insert(0, ".")

import services.service_fallback as service_fallback
from orchestrator.orchestrator import Orchestrator
from utils.failover import AllServicesUnavailableError, UpstreamUnavailableError, is_unavailable
from utils.http_status import http_status_for


def _run(coro):
    return asyncio.run(coro)


def _status_error(code: int) -> httpx.HTTPStatusError:
    request = httpx.Request("POST", "http://triton/infer")
    return httpx.HTTPStatusError("boom", request=request, response=httpx.Response(code, request=request))


# ── Which failures fail over ──────────────────────────────────────────────────

@pytest.mark.parametrize(
    "exc, expected",
    [
        (httpx.ReadTimeout("t"), True),
        (httpx.ConnectError("c"), True),
        (_status_error(503), True),
        (_status_error(400), False),
        (ValueError("bad input"), False),
        (LookupError("Triton endpoint not found"), False),
    ],
)
def test_is_unavailable(exc, expected):
    assert is_unavailable(exc) is expected


def test_status_mapping():
    assert http_status_for(UpstreamUnavailableError("x")) == 502  # no fallback → as before
    assert http_status_for(AllServicesUnavailableError("nmt-a", ["nmt-a", "nmt-b"])) == 503


# ── Orchestrator loop ─────────────────────────────────────────────────────────

def _orchestrator() -> Orchestrator:
    with patch("orchestrator.orchestrator.InferenceServerResolver"):
        return Orchestrator()


def _info(service_id: str, tier_ids=()) -> dict:
    return {"serviceId": service_id, "name": service_id, "tier_ids": list(tier_ids)}


def _task_service(result=None, exc=None, completed_groups=0) -> MagicMock:
    svc = MagicMock(completed_groups=completed_groups)
    svc.process = AsyncMock(side_effect=exc, return_value=result)
    return svc


def _wire(orch: Orchestrator, services: dict, infos: dict | None = None) -> None:
    async def resolve(payload):
        sid = payload["config"]["serviceId"]
        if sid not in services:
            raise LookupError(f"Service {sid} not found")
        return (infos or {}).get(sid) or _info(sid)

    orch._resolve_service_and_model = resolve
    orch._get_task_service = lambda info: services[info["serviceId"]]


def _unreachable():
    return UpstreamUnavailableError("nmt: Triton inference call failed")


PAYLOAD = {"task_type": "nmt", "config": {"serviceId": "nmt-a"}, "input": [{"source": "hi"}]}


def _run_loop(orch, fallbacks, request=None):
    with patch("orchestrator.orchestrator.get_fallbacks", AsyncMock(return_value=fallbacks)) as get:
        return _run(orch._run_with_fallbacks(PAYLOAD, _info("nmt-a"), request)), get


def test_success_never_reads_the_fallback_map():
    orch = _orchestrator()
    _wire(orch, {"nmt-a": _task_service({"output": ["a"]}), "nmt-b": _task_service({"output": ["b"]})})
    (served, _, response), get = _run_loop(orch, ["nmt-b"])
    assert served["serviceId"] == "nmt-a" and response == {"output": ["a"]}
    get.assert_not_called()


def test_unreachable_primary_moves_to_fallback():
    orch = _orchestrator()
    fallback = _task_service({"output": ["b"]})
    _wire(orch, {"nmt-a": _task_service(exc=_unreachable()), "nmt-b": fallback})
    (served, svc, response), _ = _run_loop(orch, ["nmt-b"])
    assert served["serviceId"] == "nmt-b" and svc is fallback and response == {"output": ["b"]}
    assert fallback.process.call_args.args[0]["config"]["serviceId"] == "nmt-b"


def test_client_error_is_returned_without_fallback():
    orch = _orchestrator()
    _wire(orch, {"nmt-a": _task_service(exc=ValueError("bad input")), "nmt-b": _task_service({})})
    with pytest.raises(ValueError):
        _run_loop(orch, ["nmt-b"])


def test_no_fallback_configured_raises_as_today():
    orch = _orchestrator()
    _wire(orch, {"nmt-a": _task_service(exc=_unreachable())})
    with pytest.raises(UpstreamUnavailableError):
        _run_loop(orch, [])


def test_already_answered_groups_are_never_rerun():
    # per_item tasks: group 1 was billed, group 2 failed → no fallback, no double billing
    orch = _orchestrator()
    _wire(orch, {"nmt-a": _task_service(exc=_unreachable(), completed_groups=1), "nmt-b": _task_service({})})
    with pytest.raises(UpstreamUnavailableError):
        (_, get) = _run_loop(orch, ["nmt-b"])


def test_fallbacks_tried_in_order_and_ineligible_one_skipped():
    orch = _orchestrator()
    second = _task_service({"output": ["c"]})
    request = MagicMock(headers={"X-Tier-ID": "gold"})
    _wire(
        orch,
        {"nmt-a": _task_service(exc=_unreachable()), "nmt-b": _task_service({}), "nmt-c": second},
        infos={"nmt-b": _info("nmt-b", tier_ids=["silver"])},  # out of the caller's Tier
    )
    (served, _, _), _ = _run_loop(orch, ["nmt-unknown", "nmt-b", "nmt-c"], request)
    assert served["serviceId"] == "nmt-c"


def test_fallback_rejecting_the_input_returns_that_error():
    orch = _orchestrator()
    _wire(orch, {"nmt-a": _task_service(exc=_unreachable()), "nmt-b": _task_service(exc=ValueError("too long"))})
    with pytest.raises(ValueError):
        _run_loop(orch, ["nmt-b"])


def test_every_service_failing_is_503():
    orch = _orchestrator()
    _wire(orch, {"nmt-a": _task_service(exc=_unreachable()), "nmt-b": _task_service(exc=_unreachable())})
    with pytest.raises(AllServicesUnavailableError) as exc:
        _run_loop(orch, ["nmt-b"])
    assert "nmt-a, nmt-b" in str(exc.value)


# ── Redis read ────────────────────────────────────────────────────────────────

def _redis(value=None, exc=None):
    redis = MagicMock()
    redis.get = AsyncMock(return_value=value, side_effect=exc)
    return redis


def test_get_fallbacks_reads_the_application_key():
    with patch.object(service_fallback, "get_application_id", return_value="42"), \
            patch.object(service_fallback, "_get_redis", return_value=_redis('{"nmt-a": ["nmt-b", "nmt-a", ""]}')) as r:
        assert _run(service_fallback.get_fallbacks("nmt-a")) == ["nmt-b"]
        assert _run(service_fallback.get_fallbacks("nmt-x")) == []
    r.return_value.get.assert_called_with("auth:app:42:service_fallbacks")


def test_get_fallbacks_without_application_or_redis_is_empty():
    with patch.object(service_fallback, "get_application_id", return_value=None):
        assert _run(service_fallback.get_fallbacks("nmt-a")) == []
    with patch.object(service_fallback, "get_application_id", return_value="42"), \
            patch.object(service_fallback, "_get_redis", return_value=_redis(exc=ConnectionError("down"))):
        assert _run(service_fallback.get_fallbacks("nmt-a")) == []


# ── LLM proxy: buffered and streaming ─────────────────────────────────────────

PATH = "/v1/chat/completions"


def _proxy(upstreams: dict):
    """upstreams: service_id -> (status, body) of its upstream; a service not
    listed does not resolve (LLMProxyError 404 from _prepare_request)."""
    from services.guardrail import GuardrailContext
    from services.llm_service import LLMProxyError, OpenAIProxyService

    proxy = OpenAIProxyService()

    async def prepare(path, payload, request=None):
        sid = payload["model"]
        if sid not in upstreams:
            raise LLMProxyError(404, {"detail": f"Service '{sid}' not found"}, service_id=sid)
        return f"http://{sid}/v1", sid, f"{sid}-model", {**payload, "model": f"{sid}-model"}, {"id": sid}

    async def forward(path, url, service_id, model_name, payload, service_info):
        return upstreams[service_id]

    async def stream(path, payload, service_info):
        status, body = upstreams[service_info["id"]]
        return ("stream", 200, body) if status == 200 else ("error", status, body)

    proxy._prepare_request = prepare
    proxy._forward_traced = AsyncMock(side_effect=forward)
    proxy.proxy_stream = AsyncMock(side_effect=stream)
    patches = [
        patch("services.llm_service.build_guardrail_context", AsyncMock(return_value=GuardrailContext())),
        patch("services.llm_service.set_llm_usage_model_id"),
    ]
    return proxy, patches


def _with(patches, fallbacks, coro):
    with patch("services.llm_service.get_fallbacks", AsyncMock(return_value=fallbacks)) as get:
        for p in patches:
            p.start()
        try:
            return _run(coro), get
        finally:
            for p in patches:
                p.stop()


def test_llm_buffered_moves_to_fallback_on_5xx():
    proxy, patches = _proxy({"llm-a": (502, {"detail": "down"}), "llm-b": (200, {"choices": []})})
    request = MagicMock()
    (status, body), _ = _with(patches, ["llm-b"], proxy.proxy_traced(PATH, {"model": "llm-a", "messages": []}, request))
    assert (status, body) == (200, {"choices": []})
    assert request.state.service_id == "llm-b"
    assert [c.args[2] for c in proxy._forward_traced.call_args_list] == ["llm-a", "llm-b"]
    assert proxy._forward_traced.call_args_list[1].args[4]["model"] == "llm-b-model"


def test_llm_buffered_4xx_never_reads_the_fallback_map():
    proxy, patches = _proxy({"llm-a": (400, {"detail": "bad"}), "llm-b": (200, {})})
    (status, body), get = _with(patches, ["llm-b"], proxy.proxy_traced(PATH, {"model": "llm-a", "messages": []}, None))
    assert (status, body) == (400, {"detail": "bad"})
    get.assert_not_called()


def test_llm_buffered_unresolvable_fallback_is_skipped_and_all_failing_is_503():
    proxy, patches = _proxy({"llm-a": (502, {}), "llm-c": (503, {})})
    (status, body), _ = _with(patches, ["llm-b", "llm-c"], proxy.proxy_traced(PATH, {"model": "llm-a", "messages": []}, None))
    assert status == 503 and body["error"]["type"] == "all_services_unavailable"
    assert [c.args[2] for c in proxy._forward_traced.call_args_list] == ["llm-a", "llm-c"]


def test_llm_stream_moves_to_fallback_before_first_byte():
    proxy, patches = _proxy({"llm-a": (502, {"error": "down"}), "llm-b": (200, "sse-generator")})
    request = MagicMock()
    (kind, status, result, _), _ = _with(
        patches, ["llm-b"], proxy.proxy_traced_stream(PATH, {"model": "llm-a", "messages": [], "stream": True}, request)
    )
    assert (kind, status) == ("stream", 200)
    assert request.state.service_id == "llm-b"
    assert proxy.proxy_stream.call_args_list[1].kwargs["payload"]["model"] == "llm-b-model"


def test_llm_stream_all_failing_is_503():
    proxy, patches = _proxy({"llm-a": (502, {}), "llm-b": (502, {})})
    (kind, status, result, _), _ = _with(
        patches, ["llm-b"], proxy.proxy_traced_stream(PATH, {"model": "llm-a", "messages": [], "stream": True}, None)
    )
    assert (kind, status) == ("error", 503) and result["error"]["type"] == "all_services_unavailable"
