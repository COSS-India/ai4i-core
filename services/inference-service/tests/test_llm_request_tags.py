"""Caller tags (OpenAI `user` / `metadata`) on LLM requests — AI4IDS-3266.

Scenario that failed before this change: a tenant calls /chat/completions with
`"user": "customer-8812"` and `"metadata": {"session_id": "s-77"}`. The trace
came back with tenantId/api_key_id/tier_id only — no end user, no metadata, no
app_id — and the whole body (tags included) was forwarded to vLLM. Invalid
metadata (17 keys, `orch_` keys, non-string values) was forwarded and billed
instead of rejected with 400, and the ai-inference span (the only one PPU
billing reads) had no model_name.

These tests drive the real route through FastAPI + the real RequestMiddleware
and a real TracerProvider; only MMS resolution and the upstream vLLM call are
mocked. That keeps contextvar propagation honest: RequestMiddleware runs the
app in a child task, and a StreamingResponse iterates its body in yet another
task, so tags set in the route must survive both hops to reach the spans.
"""
import contextvars
import sys
from unittest.mock import AsyncMock, patch

import httpx
import pytest
from fastapi import FastAPI
from opentelemetry.sdk.trace import TracerProvider
from opentelemetry.sdk.trace.export import SimpleSpanProcessor
from opentelemetry.sdk.trace.export.in_memory_span_exporter import InMemorySpanExporter

sys.path.insert(0, ".")

from ai4i_core.logging import RequestMiddleware

import routes.inference as inference_routes
import services.llm_service as llm_service_module
import trace.request_span as request_span_module
from trace.request_span import get_context_attributes
from ai4i_core.context import set_application_id, set_request_tags, set_tenant_id

SERVICE_ID = "deepseek-r1-8b/sep23"
UPSTREAM_MODEL = "deepseek-r1-8b"

GATEWAY_HEADERS = {
    "X-Tenant-Id": "181",
    "X-Auth-Type": "api_key",
    "X-API-Key-ID": "2465",
    "X-Tier-ID": "821ebccf-e332-460c-8d6b-507b52fbad28",
    "X-Application-ID": "app-42",
    # The API key's creator — must never end up as the end user.
    "X-User-ID": "11111111-2222-3333-4444-555555555555",
}

TAGGED_BODY = {
    "model": SERVICE_ID,
    "messages": [{"role": "user", "content": "Where is my order?"}],
    "user": "customer-8812",
    "metadata": {"session_id": "s-77", "feature": "order-help"},
}

SERVICE_INFO = {"adapter_config": {"model_name": UPSTREAM_MODEL}, "model_id": "mid-1", "tier_ids": []}
UPSTREAM_BODY = {
    "model": UPSTREAM_MODEL,
    "choices": [{"message": {"role": "assistant", "content": "On its way."}}],
    "usage": {"prompt_tokens": 22, "completion_tokens": 285},
}

ALL_SPANS = ("request", "model", "ai-inference")


@pytest.fixture
def exporter():
    exp = InMemorySpanExporter()
    provider = TracerProvider()
    provider.add_span_processor(SimpleSpanProcessor(exp))
    with patch.object(request_span_module, "tracer", new=provider.get_tracer("test-llm-request-tags")):
        yield exp


@pytest.fixture
def upstream():
    """Mock MMS + vLLM. Records every payload forwarded upstream."""
    sent = []

    async def fake_forward(url, payload, service_info=None):
        sent.append(payload)
        return 200, dict(UPSTREAM_BODY)

    async def fake_proxy_stream(path, payload, service_info):
        sent.append(payload)

        async def gen():
            yield 'data: {"choices":[{"delta":{"content":"On"}}]}\n'
            yield 'data: {"choices":[],"usage":{"prompt_tokens":22,"completion_tokens":285}}\n'
            yield "data: [DONE]\n"

        return "stream", 200, gen()

    cls = llm_service_module.OpenAIProxyService
    with patch.object(cls, "resolve_upstream_url",
                      new=AsyncMock(return_value=("http://vllm:8000/v1/chat/completions", SERVICE_INFO))), \
         patch.object(cls, "forward", new=AsyncMock(side_effect=fake_forward)), \
         patch.object(cls, "proxy_stream", new=AsyncMock(side_effect=fake_proxy_stream)):
        yield sent


def _app() -> FastAPI:
    app = FastAPI()
    app.add_middleware(RequestMiddleware)
    app.include_router(inference_routes.router)
    return app


async def _post(body, headers=GATEWAY_HEADERS, path="/chat/completions"):
    transport = httpx.ASGITransport(app=_app())
    async with httpx.AsyncClient(transport=transport, base_url="http://test") as client:
        return await client.post(path, json=body, headers=headers)


def _spans_by_name(exporter):
    spans = {}
    for span in exporter.get_finished_spans():
        spans.setdefault(span.name, []).append(span)
    return spans


def _kv(attrs):
    """The metadata_kv span attribute as a list (OTel stores sequences as tuples)."""
    return list(attrs.get("metadata_kv", ()))


def _assert_tagged(span):
    attrs = span.attributes
    assert attrs.get("enduser.id") == "customer-8812", span.name
    assert _kv(attrs) == ["session_id=s-77", "feature=order-help"], span.name
    assert attrs.get("app_id") == "app-42", span.name
    # Platform-derived tags still present alongside the caller's.
    assert attrs.get("tenantId") == "181", span.name
    assert attrs.get("api_key_id") == "2465", span.name
    assert attrs.get("tier_id") == GATEWAY_HEADERS["X-Tier-ID"], span.name
    assert attrs.get("correlation_id"), span.name
    # The key creator's X-User-ID must not masquerade as the end user.
    assert attrs.get("userId") is None, span.name


# ── The exact ticket scenario ────────────────────────────────────────────────

@pytest.mark.asyncio
@pytest.mark.parametrize("stream", [False, True], ids=["consolidated", "stream"])
async def test_tagged_request_puts_tags_on_every_span_and_strips_them_upstream(exporter, upstream, stream):
    body = {**TAGGED_BODY, "stream": True} if stream else TAGGED_BODY

    response = await _post(body)

    assert response.status_code == 200
    spans = _spans_by_name(exporter)
    for name in ALL_SPANS:
        assert len(spans.get(name, [])) == 1, f"expected one {name!r} span, got {spans.get(name)}"
        _assert_tagged(spans[name][0])

    # One request id across all three spans (the metering join key).
    assert len({spans[n][0].attributes["correlation_id"] for n in ALL_SPANS}) == 1

    # Metering record = the ai-inference span: tokens + model must sit next to the tags.
    infer = spans["ai-inference"][0].attributes
    assert infer["model_name"] == UPSTREAM_MODEL
    assert infer["input_tokens"] == 22
    assert infer["output_tokens"] == 285

    # vLLM gets neither tag; everything else passes through.
    assert len(upstream) == 1
    forwarded = upstream[0]
    assert "user" not in forwarded and "metadata" not in forwarded
    assert forwarded["messages"] == TAGGED_BODY["messages"]
    assert forwarded["model"] == UPSTREAM_MODEL


@pytest.mark.asyncio
async def test_untagged_request_succeeds_with_platform_tags_only(exporter, upstream):
    body = {"model": SERVICE_ID, "messages": TAGGED_BODY["messages"]}

    response = await _post(body)

    assert response.status_code == 200
    for span in exporter.get_finished_spans():
        attrs = span.attributes
        assert "enduser.id" not in attrs, span.name
        assert "metadata_kv" not in attrs, span.name
        assert attrs.get("tenantId") == "181", span.name
        assert attrs.get("app_id") == "app-42", span.name
    assert upstream[0]["messages"] == body["messages"]


@pytest.mark.asyncio
async def test_null_user_and_metadata_are_treated_as_absent(exporter, upstream):
    response = await _post({**TAGGED_BODY, "user": None, "metadata": None})

    assert response.status_code == 200
    for span in exporter.get_finished_spans():
        assert "enduser.id" not in span.attributes
    assert "user" not in upstream[0] and "metadata" not in upstream[0]


@pytest.mark.asyncio
async def test_tags_do_not_leak_into_the_next_request_in_the_same_context(exporter, upstream):
    """httpx's ASGITransport runs every request in the calling task, so a
    contextvar left over from request A is still visible to request B unless
    the route overwrites it. B must come back untagged."""
    await _post(TAGGED_BODY)
    exporter.clear()

    response = await _post({"model": SERVICE_ID, "messages": TAGGED_BODY["messages"]})

    assert response.status_code == 200
    for span in exporter.get_finished_spans():
        assert "enduser.id" not in span.attributes, span.name
        assert "metadata_kv" not in span.attributes, span.name


@pytest.mark.asyncio
@pytest.mark.parametrize("path", ["/chat", "/llm/try-it"])
async def test_every_llm_route_applies_the_tags(exporter, upstream, path):
    response = await _post(TAGGED_BODY, path=path)

    assert response.status_code == 200
    _assert_tagged(_spans_by_name(exporter)["ai-inference"][0])
    assert "user" not in upstream[0] and "metadata" not in upstream[0]


# ── 400 rejections ───────────────────────────────────────────────────────────

_INVALID = [
    ("17 keys", {"metadata": {f"k{i}": "v" for i in range(17)}}, "metadata"),
    ("65-char key", {"metadata": {"k" * 65: "v"}}, "metadata"),
    ("513-char value", {"metadata": {"k": "v" * 513}}, "metadata"),
    ("int value", {"metadata": {"k": 5}}, "metadata"),
    ("bool value", {"metadata": {"k": True}}, "metadata"),
    ("null value", {"metadata": {"k": None}}, "metadata"),
    ("nested value", {"metadata": {"k": {"a": "b"}}}, "metadata"),
    ("orch_ prefix", {"metadata": {"orch_tenant_id": "999"}}, "metadata"),
    ("empty key", {"metadata": {"": "v"}}, "metadata"),
    ("= in key", {"metadata": {"a=b": "c"}}, "metadata"),
    ("metadata not an object", {"metadata": ["a", "b"]}, "metadata"),
    ("metadata string", {"metadata": "session=s-77"}, "metadata"),
    ("user not a string", {"user": 8812}, "user"),
    ("user too long", {"user": "u" * 257}, "user"),
]


@pytest.mark.asyncio
@pytest.mark.parametrize("stream", [False, True], ids=["consolidated", "stream"])
@pytest.mark.parametrize("case, override, param", _INVALID, ids=[c[0] for c in _INVALID])
async def test_invalid_tags_return_openai_400_and_are_never_proxied_or_billed(
    exporter, upstream, case, override, param, stream,
):
    body = {**TAGGED_BODY, **override, "stream": stream}

    response = await _post(body)

    assert response.status_code == 400, response.text
    error = response.json()["error"]
    assert error["type"] == "invalid_request_error"
    assert error["param"] == param
    assert error["message"]

    assert upstream == [], "invalid request was forwarded to vLLM"
    spans = _spans_by_name(exporter)
    assert "ai-inference" not in spans, "a rejected request must not produce a billable span"
    # Still visible in the trace dashboard as a failed LLM request.
    assert spans["request"][0].attributes["status_code"] == 400
    model = spans["model"][0].attributes
    assert model["task_type"] == "LLM"
    assert model["status"] == "failure"
    assert model["status_code"] == 400
    # Rejected tags must not reach the spans either.
    for span in exporter.get_finished_spans():
        assert "enduser.id" not in span.attributes
        assert "metadata_kv" not in span.attributes
    # ...but the platform-derived app_id must: it comes from the gateway, not
    # the rejected body, so the failure is still attributable to the app.
    assert spans["request"][0].attributes.get("app_id") == "app-42"
    assert model.get("app_id") == "app-42"


@pytest.mark.asyncio
async def test_values_exactly_at_every_limit_are_accepted(exporter, upstream):
    metadata = {f"k{i:02d}": "v" for i in range(15)}
    metadata["k" * 64] = "v" * 512
    body = {**TAGGED_BODY, "user": "u" * 256, "metadata": metadata}

    response = await _post(body)

    assert response.status_code == 200
    attrs = _spans_by_name(exporter)["ai-inference"][0].attributes
    assert attrs["enduser.id"] == "u" * 256
    assert "k" * 64 + "=" + "v" * 512 in _kv(attrs)
    assert len(_kv(attrs)) == 16


# ── Tenant keys must never become OpenSearch field names ─────────────────────

@pytest.mark.asyncio
async def test_new_metadata_keys_never_add_new_span_attribute_names(exporter, upstream):
    """The reviewer's scenario: every span attribute name becomes a field in the
    shared daily traces-* index (limit 1000), so if each distinct metadata key
    were its own attribute, tenants sending fresh keys would exhaust it and
    every later span introducing a new field would be rejected — for all
    tenants. Two requests with 16 entirely different keys each must produce
    exactly the same set of attribute names."""
    first = {f"tenantA_key_{i}": f"v{i}" for i in range(16)}
    second = {f"tenantB_other_{i}": f"w{i}" for i in range(16)}

    await _post({**TAGGED_BODY, "metadata": first})
    await _post({**TAGGED_BODY, "metadata": second})

    infer = _spans_by_name(exporter)["ai-inference"]
    assert len(infer) == 2
    names_a, names_b = set(infer[0].attributes), set(infer[1].attributes)
    assert names_a == names_b, f"tenant input changed field names: {names_a ^ names_b}"
    assert not [n for n in names_a if "tenantA" in n or "tenantB" in n]
    assert _kv(infer[0].attributes) == [f"{k}={v}" for k, v in first.items()]
    assert _kv(infer[1].attributes) == [f"{k}={v}" for k, v in second.items()]


@pytest.mark.asyncio
async def test_dotted_metadata_key_is_accepted_now_that_keys_are_values(exporter, upstream):
    """Dots were rejected only because a key became a field path; as a value
    inside metadata_kv a dot is harmless."""
    response = await _post({**TAGGED_BODY, "metadata": {"order.id": "55", "order": "A1"}})

    assert response.status_code == 200
    assert _kv(_spans_by_name(exporter)["ai-inference"][0].attributes) == ["order.id=55", "order=A1"]


@pytest.mark.asyncio
async def test_exported_span_carries_metadata_kv_as_a_json_array(exporter, upstream):
    """What actually reaches Kafka -> Fluent-Bit -> OpenSearch: the real
    KafkaSpanExporter, serialized the way its producer serializes."""
    import json
    from unittest.mock import MagicMock

    await _post(TAGGED_BODY)
    span = _spans_by_name(exporter)["ai-inference"][0]

    producer = MagicMock()
    with patch("trace.setup.settings") as s, patch("kafka.KafkaProducer", return_value=producer):
        s.KAFKA_ENABLED, s.KAFKA_TOPIC_OTEL_TRACE = True, "kafka-topic-otel-trace"
        s.KAFKA_SERVER, s.SERVICE_NAME = "localhost:9092", "inference-service"
        from trace.setup import KafkaSpanExporter
        KafkaSpanExporter().export([span])

    sent = json.loads(json.dumps(producer.send.call_args.kwargs["value"], default=str))
    assert sent["attributes"]["metadata_kv"] == ["session_id=s-77", "feature=order-help"]
    assert not [k for k in sent["attributes"] if k.startswith("metadata.")]


# ── app_id is platform identity: every request, every task type ──────────────

@pytest.mark.asyncio
async def test_jwt_call_without_application_header_has_no_app_id(exporter, upstream):
    headers = {k: v for k, v in GATEWAY_HEADERS.items() if k != "X-Application-ID"}
    headers["X-Auth-Type"] = "jwt"

    response = await _post(TAGGED_BODY, headers=headers)

    assert response.status_code == 200
    for span in exporter.get_finished_spans():
        assert "app_id" not in span.attributes, span.name
        assert span.attributes.get("enduser.id") == "customer-8812", span.name


@pytest.mark.asyncio
async def test_caller_metadata_cannot_spoof_app_id(exporter, upstream):
    """A tenant sending metadata `app_id` must not override the gateway's value."""
    body = {**TAGGED_BODY, "metadata": {"app_id": "someone-elses-app"}}

    response = await _post(body)

    assert response.status_code == 200
    for span in exporter.get_finished_spans():
        assert span.attributes.get("app_id") == "app-42", span.name
        assert _kv(span.attributes) == ["app_id=someone-elses-app"], span.name


@pytest.mark.asyncio
async def test_non_llm_request_spans_carry_app_id_but_no_caller_tags(exporter):
    """An API-key NMT call through the real RequestMiddleware and orchestrator:
    app_id is gateway identity like tenantId, so it belongs on every task type's
    spans — matching the Prometheus application_id label, which already covers
    all tasks. Caller tags are LLM-only and must stay absent."""
    resolver = inference_routes._orchestrator.inference_server_resolver
    with patch.object(resolver, "resolve_service",
                      new=AsyncMock(return_value={"is_published": False})):
        await _post(
            {"serviceId": "indictrans-v2", "input": [{"source": "hello"}],
             "config": {"language": {"sourceLanguage": "en", "targetLanguage": "hi"}}},
            path="/nmt/inference",
        )

    spans = _spans_by_name(exporter)
    for name in ("request", "model"):
        attrs = spans[name][0].attributes
        assert attrs.get("app_id") == "app-42", name
        assert attrs.get("tenantId") == "181", name
        assert "enduser.id" not in attrs, name
        assert "metadata_kv" not in attrs, name


# ── Non-LLM requests are unaffected ──────────────────────────────────────────

def test_context_attributes_carry_no_tags_when_none_were_set():
    """ASR/NMT/... spans also call get_context_attributes(); in a request that
    never went through the LLM route the tag contextvar is unset."""
    attrs = contextvars.Context().run(get_context_attributes)
    assert not [k for k in attrs if k in ("app_id", "enduser.id", "metadata_kv")]


def test_tag_attributes_cannot_overwrite_platform_attributes():
    """A tenant key named like a platform attribute is only a value in metadata_kv."""
    def run():
        set_tenant_id("181")
        set_application_id("app-42")
        set_request_tags(user=None, metadata={"tenantId": "999", "api_key_id": "1", "app_id": "x"})
        return get_context_attributes()

    attrs = contextvars.Context().run(run)
    assert attrs["tenantId"] == "181"
    assert attrs["app_id"] == "app-42"
    assert attrs["metadata_kv"] == ["tenantId=999", "api_key_id=1", "app_id=x"]
