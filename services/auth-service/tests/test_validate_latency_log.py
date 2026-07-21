"""
The /auth/validate timing log.

These assert the log contract that OpenSearch queries depend on: the fields
live under "context" (matching RequestMiddleware's shape) and the line is
emitted even when the handler exits by raising.
"""

import logging

import pytest

from app.core.exceptions import AuthenticationRequiredError
from app.routes.validation import validate_token


class _FakeState:
    permission_checker = None


class _FakeApp:
    state = _FakeState()


class _FakeRequest:
    """Only what validate_token touches: headers and app.state."""

    def __init__(self, headers=None):
        self.headers = headers or {}
        self.app = _FakeApp()


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
