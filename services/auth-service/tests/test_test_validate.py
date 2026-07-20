"""Unit tests for the bare /test API-key validation endpoint (test_validate.py)."""

import secrets
from unittest.mock import AsyncMock

import pytest
from fastapi import FastAPI
from fastapi.testclient import TestClient

from app.core.redis import get_redis
from app.routes.test_validate import router
from app.services.cache_service import CacheService


@pytest.fixture
def client(monkeypatch):
    app = FastAPI()
    app.include_router(router)

    async def _fake_get_redis():
        yield None

    app.dependency_overrides[get_redis] = _fake_get_redis
    return TestClient(app)


def test_missing_authorization_header_is_invalid(client):
    resp = client.get("/auth/test")
    assert resp.status_code == 200
    body = resp.json()
    assert body["valid"] is False
    assert isinstance(body["validation_time_ms"], (int, float))


def test_non_hex_token_is_invalid_format(client):
    resp = client.get("/auth/test", headers={"Authorization": "Bearer not-a-valid-key"})
    assert resp.status_code == 200
    assert resp.json()["valid"] is False


def test_valid_hex_key_found_in_cache_is_valid(client, monkeypatch):
    token = secrets.token_hex(16)
    monkeypatch.setattr(
        CacheService, "get_api_key_cache", AsyncMock(return_value={"user_id": "1", "tenant_id": "1"})
    )
    resp = client.get("/auth/test", headers={"Authorization": f"Bearer {token}"})
    assert resp.status_code == 200
    body = resp.json()
    assert body["valid"] is True
    assert body["validation_time_ms"] >= 0


def test_valid_hex_key_not_in_cache_is_invalid(client, monkeypatch):
    token = secrets.token_hex(16)
    monkeypatch.setattr(CacheService, "get_api_key_cache", AsyncMock(return_value=None))
    resp = client.get("/auth/test", headers={"Authorization": f"Bearer {token}"})
    assert resp.status_code == 200
    assert resp.json()["valid"] is False


def test_no_auth_dependency_required_to_reach_endpoint(client):
    """No permission/tier/quota headers, no 401/403 — just the raw validation result."""
    resp = client.get("/auth/test")
    assert resp.status_code == 200
    assert set(resp.json().keys()) == {"valid", "validation_time_ms"}


def test_valid_key_via_query_param_is_valid(client, monkeypatch):
    token = secrets.token_hex(16)
    monkeypatch.setattr(
        CacheService, "get_api_key_cache", AsyncMock(return_value={"user_id": "1", "tenant_id": "1"})
    )
    resp = client.get("/auth/test", params={"api_key": token})
    assert resp.status_code == 200
    assert resp.json()["valid"] is True


def test_missing_query_param_and_header_is_invalid(client):
    resp = client.get("/auth/test", params={"api_key": ""})
    assert resp.status_code == 200
    assert resp.json()["valid"] is False


def test_authorization_header_takes_precedence_over_query_param(client, monkeypatch):
    """Header wins when both are present: header key is valid, query key is bogus."""
    header_token = secrets.token_hex(16)

    async def _fake_cache(self, api_key: str):
        return {"user_id": "1"} if api_key == header_token else None

    monkeypatch.setattr(CacheService, "get_api_key_cache", _fake_cache)
    resp = client.get(
        "/auth/test",
        headers={"Authorization": f"Bearer {header_token}"},
        params={"api_key": "deadbeefdeadbeefdeadbeefdeadbeef"},
    )
    assert resp.status_code == 200
    assert resp.json()["valid"] is True
