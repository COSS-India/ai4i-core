"""Tests for the model-name -> service_id resolver.

The sample payload mirrors the real platform-core GET /services envelope
(`{"success": true, "data": {"services": [...]}}`) with the actual demo values,
so the mapping google/gemma-4-31B-it -> f1fd6f96... is exercised end to end.
"""

import httpx
import pytest

from services import service_registry
from services.service_registry import ServiceIdResolver


# Real shape + real demo values (from mm_services).
_SERVICES_ENVELOPE = {
    "success": True,
    "data": {
        "services": [
            {"serviceId": "f1fd6f964a44beb68078f7db9c6fa897", "name": "google/gemma-4-31B-it", "isPublished": True},
            {"serviceId": "8e588907767a26835acbf29d83de9e31", "name": "google/gemma-4-E4B-it", "isPublished": True},
            {"serviceId": "30622e0a5b1cfb70dd008281adfd7d8c", "name": "agrinet-model", "isPublished": True},
        ]
    },
    "meta": {"total": 3},
}


def _resolver_with(handler) -> ServiceIdResolver:
    """Build a resolver whose HTTP client is backed by a MockTransport."""
    r = ServiceIdResolver()
    r._url = "http://platform-core-service:8095/services"

    real_client = httpx.AsyncClient

    def _client_factory(*args, **kwargs):
        kwargs["transport"] = httpx.MockTransport(handler)
        return real_client(*args, **kwargs)

    # Patch the AsyncClient used inside _refresh for this instance's calls.
    service_registry.httpx.AsyncClient = _client_factory  # type: ignore[attr-defined]
    r._restore = lambda: setattr(service_registry.httpx, "AsyncClient", real_client)
    return r


@pytest.fixture(autouse=True)
def _restore_httpx():
    original = httpx.AsyncClient
    yield
    service_registry.httpx.AsyncClient = original


async def test_resolves_model_name_to_registered_service_id():
    calls = {"n": 0}

    def handler(request: httpx.Request) -> httpx.Response:
        calls["n"] += 1
        assert request.url.params.get("is_published") == "true"
        return httpx.Response(200, json=_SERVICES_ENVELOPE)

    r = _resolver_with(handler)
    assert await r.resolve("google/gemma-4-31B-it") == "f1fd6f964a44beb68078f7db9c6fa897"
    assert await r.resolve("google/gemma-4-E4B-it") == "8e588907767a26835acbf29d83de9e31"
    # Second lookup for an already-cached name must not trigger another fetch.
    assert calls["n"] == 1


async def test_unknown_model_returns_empty():
    def handler(request: httpx.Request) -> httpx.Response:
        return httpx.Response(200, json=_SERVICES_ENVELOPE)

    r = _resolver_with(handler)
    assert await r.resolve("does/not-exist") == ""


async def test_empty_model_name_short_circuits():
    def handler(request: httpx.Request) -> httpx.Response:  # pragma: no cover
        raise AssertionError("must not fetch for empty model name")

    r = _resolver_with(handler)
    assert await r.resolve("") == ""


async def test_fetch_failure_fails_open():
    def handler(request: httpx.Request) -> httpx.Response:
        return httpx.Response(503, json={"error": "down"})

    r = _resolver_with(handler)
    # Registry unreachable -> "" (request proceeds unbilled), no exception raised.
    assert await r.resolve("google/gemma-4-31B-it") == ""


async def test_no_mms_url_returns_empty():
    r = ServiceIdResolver()
    r._url = ""
    assert await r.resolve("google/gemma-4-31B-it") == ""


def test_url_targets_api_v1_services(monkeypatch):
    """The MMS is mounted under /api/v1 — the resolver must target that path."""
    monkeypatch.setattr(
        service_registry.settings, "MODEL_MANAGEMENT_SERVICE_URL",
        "http://platform-core-service:8095/", raising=False,
    )
    r = ServiceIdResolver()
    assert r._url == "http://platform-core-service:8095/api/v1/services"
