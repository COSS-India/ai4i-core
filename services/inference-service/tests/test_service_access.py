"""Publish/Tier flags read fresh from Redis on every resolve.

The resolver keeps each service in memory for CACHE_TTL_SECONDS, so an
unpublish or Tier change used to keep working (and failing over) for up to
that long. platform-core now writes core:service:{id}:access =
{"is_published", "tier_ids"} whenever the service is saved; resolve_service
overrides the cached flags with it, so the existing publish and Tier gates
reject at once — for the requested service and for every fallback, since both
resolve through here.
"""

from unittest.mock import AsyncMock

import pytest

import inference.inference_server_resolver as resolver_module
from inference.inference_server_resolver import InferenceServerResolver

pytestmark = pytest.mark.asyncio

# The module's own reader, captured before conftest's autouse fixture replaces it.
_real_reader = resolver_module._read_service_access

_CACHED = {
    "name": "llm-a",
    "endpoint": "http://llm-a:8000",
    "is_published": True,
    "tier_ids": ["tier-1"],
}


def _resolver_with_cached(service_id: str = "llm-a/v1") -> InferenceServerResolver:
    """A resolver whose in-memory copy (fetched before the change) still says
    published and in tier-1."""
    resolver = InferenceServerResolver()
    resolver._query_model_management_service = AsyncMock(return_value=dict(_CACHED))
    return resolver


def _access(monkeypatch, value=None, raises=None):
    calls = []

    async def _read(service_id):
        calls.append(service_id)
        if raises is not None:
            raise raises
        return value

    monkeypatch.setattr(resolver_module, "_read_service_access", _read)
    return calls


async def test_unpublished_in_redis_overrides_a_cached_published_copy(monkeypatch):
    resolver = _resolver_with_cached()
    await resolver.resolve_service("llm-a/v1")  # warm the in-memory cache
    _access(monkeypatch, {"is_published": False, "tier_ids": ["tier-1"]})

    info = await resolver.resolve_service("llm-a/v1")

    assert info["is_published"] is False
    resolver._query_model_management_service.assert_awaited_once()  # still a cache hit


async def test_tier_change_in_redis_overrides_cached_tier_ids(monkeypatch):
    resolver = _resolver_with_cached()
    _access(monkeypatch, {"is_published": True, "tier_ids": ["tier-2"]})

    info = await resolver.resolve_service("llm-a/v1")

    assert info["tier_ids"] == ["tier-2"]


async def test_reads_the_key_for_the_requested_service(monkeypatch):
    calls = _access(monkeypatch, {"is_published": True, "tier_ids": []})

    await _resolver_with_cached().resolve_service("llm-a/v1")

    assert calls == ["llm-a/v1"]


async def test_missing_key_keeps_the_cached_flags(monkeypatch):
    _access(monkeypatch, None)

    info = await _resolver_with_cached().resolve_service("llm-a/v1")

    assert info["is_published"] is True and info["tier_ids"] == ["tier-1"]


async def test_override_does_not_change_the_in_memory_copy(monkeypatch):
    """Only the returned dict carries the Redis flags, so a later missing key
    falls back to what MMS said, not to an earlier request's override."""
    resolver = _resolver_with_cached()
    _access(monkeypatch, {"is_published": False, "tier_ids": []})
    await resolver.resolve_service("llm-a/v1")

    assert resolver._memory_cache["llm-a/v1"][0]["is_published"] is True


async def test_redis_read_failure_keeps_the_cached_flags(monkeypatch):
    """The real reader swallows errors; a Redis outage must not fail inference."""

    class _BrokenRedis:
        async def get(self, key):
            raise ConnectionError("redis down")

    monkeypatch.setattr(resolver_module, "_read_service_access", _real_reader)
    monkeypatch.setattr(resolver_module, "_get_access_redis", lambda: _BrokenRedis())

    info = await _resolver_with_cached().resolve_service("llm-a/v1")

    assert info["is_published"] is True


async def test_real_reader_parses_the_platform_core_value(monkeypatch):
    class _FakeRedis:
        async def get(self, key):
            assert key == "core:service:llm-a/v1:access"
            return '{"is_published": false, "tier_ids": ["tier-1"]}'

    monkeypatch.setattr(resolver_module, "_get_access_redis", lambda: _FakeRedis())

    assert await _real_reader("llm-a/v1") == {"is_published": False, "tier_ids": ["tier-1"]}


async def test_llm_primary_unpublished_in_redis_is_rejected_before_any_call(monkeypatch):
    """The existing LLM publish gate sees the fresh flag: LookupError (404),
    so the fallback chain never starts."""
    import services.llm_service as llm_module

    monkeypatch.setattr(llm_module, "_resolver", _resolver_with_cached())
    _access(monkeypatch, {"is_published": False, "tier_ids": ["tier-1"]})

    with pytest.raises(LookupError):
        await llm_module.OpenAIProxyService().resolve_upstream_url("llm-a/v1", "/v1/chat/completions")



async def test_llm_fallback_unpublished_in_redis_is_skipped(monkeypatch):
    """Primary fails with a 5xx; fallback llm-b is still cached as published
    but Redis says unpublished, so it is skipped and llm-c serves."""
    from unittest.mock import patch

    import services.llm_service as llm_module
    from services.guardrail import GuardrailContext

    resolver = InferenceServerResolver()

    async def _mms(service_id):
        return {**_CACHED, "name": service_id, "endpoint": f"http://{service_id}"}

    resolver._query_model_management_service = _mms
    monkeypatch.setattr(llm_module, "_resolver", resolver)
    flags = {"llm-b": {"is_published": False, "tier_ids": ["tier-1"]}}

    async def _read(service_id):
        return flags.get(service_id)

    monkeypatch.setattr(resolver_module, "_read_service_access", _read)

    proxy = llm_module.OpenAIProxyService()
    upstream = {"llm-a": (502, {}), "llm-c": (200, {"choices": []})}

    async def _forward(path, url, service_id, model_name, payload, service_info):
        return upstream[service_id]

    proxy._forward_traced = AsyncMock(side_effect=_forward)
    with patch("services.llm_service.get_fallbacks", AsyncMock(return_value=["llm-b", "llm-c"])), \
         patch("services.llm_service.build_guardrail_context", AsyncMock(return_value=GuardrailContext())), \
         patch("services.llm_service.set_llm_usage_model_id"):
        status, body = await proxy.proxy_traced("/v1/chat/completions", {"model": "llm-a", "messages": []}, None)

    assert (status, body) == (200, {"choices": []})
    assert [c.args[2] for c in proxy._forward_traced.call_args_list] == ["llm-a", "llm-c"]
