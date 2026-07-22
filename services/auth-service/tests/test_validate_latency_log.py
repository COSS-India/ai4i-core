"""
The /auth/validate timing log.

These assert the log contract that OpenSearch queries depend on: the fields
live under "context" (matching RequestMiddleware's shape) and the line is
emitted even when the handler exits by raising.
"""

import base64
import json
import logging
from types import SimpleNamespace

import pytest

from app.core.exceptions import AuthenticationRequiredError
from app.routes.validation import validate_token
from app.services.api_key_service import APIKeyService


class _FakeState:
    permission_checker = None


class _FakeApp:
    state = _FakeState()


class _FakeRequest:
    """Only what validate_token touches: headers, app.state, and request.state."""

    def __init__(self, headers=None):
        self.headers = headers or {}
        self.app = _FakeApp()
        self.state = SimpleNamespace()


class _FakeResponse:
    """Only what the per-type validators touch: a dict-like headers store."""

    def __init__(self):
        self.headers = {}


def _log_context(caplog):
    for record in caplog.records:
        if getattr(record, "context", {}).get("event") == "auth_validate":
            return record.context
    return None


@pytest.mark.asyncio
async def test_logs_timing_when_anonymous_call_is_rejected(caplog):
    """The anonymous path exits by raising, so the log must come from finally."""
    request = _FakeRequest()

    with caplog.at_level(logging.INFO):
        with pytest.raises(AuthenticationRequiredError):
            await validate_token(request=request, response=None, redis=None)

    ctx = _log_context(caplog)
    assert ctx is not None, "no auth_validate log emitted on the raising path"
    assert ctx["auth_type"] == "anonymous"
    assert ctx["validate_duration_ms"] >= 0


@pytest.mark.asyncio
async def test_log_carries_upstream_request_under_context(caplog):
    """Query string is stripped from upstream_path to keep cardinality sane."""
    request = _FakeRequest({
        "X-Original-Method": "POST",
        "X-Original-URI": "/api/v1/nmt/inference?source=en&target=hi",
    })

    with caplog.at_level(logging.INFO):
        with pytest.raises(AuthenticationRequiredError):
            await validate_token(request=request, response=None, redis=None)

    ctx = _log_context(caplog)
    assert ctx["upstream_method"] == "POST"
    assert ctx["upstream_path"] == "/api/v1/nmt/inference"


@pytest.mark.asyncio
async def test_timing_fields_do_not_collide_with_request_middleware(caplog):
    """RequestMiddleware owns method/path/duration_ms; this log must not reuse them."""
    request = _FakeRequest()

    with caplog.at_level(logging.INFO):
        with pytest.raises(AuthenticationRequiredError):
            await validate_token(request=request, response=None, redis=None)

    ctx = _log_context(caplog)
    assert not {"method", "path", "duration_ms"} & set(ctx)


@pytest.mark.asyncio
async def test_key_validation_duration_isolated_from_authz_and_headers(caplog, monkeypatch):
    """key_validation_duration_ms times only the Redis lookup; jwt field stays None."""

    async def fake_validate_api_key(self, token):
        return {"valid": True, "user_id": "u1", "tenant_id": "t1", "permission_ids": []}

    monkeypatch.setattr(APIKeyService, "validate_api_key", fake_validate_api_key)

    request = _FakeRequest({"Authorization": "Bearer somehexapikeytoken"})
    response = _FakeResponse()

    with caplog.at_level(logging.INFO):
        await validate_token(request=request, response=response, redis=None)

    ctx = _log_context(caplog)
    assert ctx["auth_type"] == "api_key"
    assert ctx["key_validation_duration_ms"] >= 0
    assert ctx["jwt_validation_duration_ms"] is None


@pytest.mark.asyncio
async def test_jwt_validation_duration_isolated_from_authz_and_headers(caplog, monkeypatch):
    """jwt_validation_duration_ms times only signature verification; key field stays None."""

    class _FakeVerifier:
        async def verify(self, token):
            return SimpleNamespace(
                token_id=None,
                token_type="access",
                permission_ids=[],
                user_id="11111111-1111-1111-1111-111111111111",
                username="alice",
                tenant_id="22222222-2222-2222-2222-222222222222",
                roles=[],
            )

    monkeypatch.setattr("app.routes.validation.get_jwt_verifier", lambda: _FakeVerifier())

    header = base64.urlsafe_b64encode(json.dumps({"alg": "RS256"}).encode()).decode().rstrip("=")
    jwt_token = f"{header}.payload.signature"
    request = _FakeRequest({"Authorization": f"Bearer {jwt_token}"})
    response = _FakeResponse()

    with caplog.at_level(logging.INFO):
        await validate_token(request=request, response=response, redis=None)

    ctx = _log_context(caplog)
    assert ctx["auth_type"] == "jwt"
    assert ctx["jwt_validation_duration_ms"] >= 0
    assert ctx["key_validation_duration_ms"] is None
