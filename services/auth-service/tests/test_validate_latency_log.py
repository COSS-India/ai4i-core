"""
The /auth/validate timing log.

Only successful validations are timed: a rejected token exits on a different
code path, so its duration is not the cost the gateway paid for a real
validation. These assert that rule and the field contract OpenSearch queries
depend on.
"""

import logging

import pytest

from app.core.exceptions import AuthenticationRequiredError
from app.routes.validation import validate_token


class _FakeChecker:
    """Stands in for app.state.permission_checker."""

    def __init__(self, required=None):
        self._required = required

    def get_required_permission(self, method, path):
        return self._required


class _FakeState:
    permission_checker = None


class _FakeApp:
    def __init__(self):
        self.state = _FakeState()


class _FakeRequest:
    """Only what validate_token touches: headers and app.state."""

    def __init__(self, headers=None, checker=None):
        self.headers = headers or {}
        self.app = _FakeApp()
        self.app.state.permission_checker = checker


def _public_endpoint_request():
    """Anonymous call at a public endpoint: the one success path needing no token."""
    return _FakeRequest(
        headers={
            "X-Original-Method": "POST",
            "X-Original-URI": "/api/v1/nmt/inference?source=en&target=hi",
        },
        checker=_FakeChecker(required=None),
    )


def _log_context(caplog):
    for record in caplog.records:
        if getattr(record, "context", {}).get("event") == "auth_validate":
            return record.context
    return None


@pytest.mark.asyncio
async def test_successful_validation_is_timed(caplog):
    with caplog.at_level(logging.INFO):
        await validate_token(request=_public_endpoint_request(), response=None, redis=None)

    ctx = _log_context(caplog)
    assert ctx is not None, "no auth_validate log emitted on the success path"
    assert ctx["auth_type"] == "anonymous"
    assert ctx["validate_duration_ms"] >= 0


@pytest.mark.asyncio
async def test_rejected_validation_is_not_timed(caplog):
    """No X-Original-* means no public endpoint, so the call is rejected."""
    with caplog.at_level(logging.INFO):
        with pytest.raises(AuthenticationRequiredError):
            await validate_token(request=_FakeRequest(), response=None, redis=None)

    assert _log_context(caplog) is None, "rejected call should not be timed"


@pytest.mark.asyncio
async def test_log_carries_upstream_request(caplog):
    """Query string is stripped from upstream_path to keep cardinality sane."""
    with caplog.at_level(logging.INFO):
        await validate_token(request=_public_endpoint_request(), response=None, redis=None)

    ctx = _log_context(caplog)
    assert ctx["upstream_method"] == "POST"
    assert ctx["upstream_path"] == "/api/v1/nmt/inference"


@pytest.mark.asyncio
async def test_fields_do_not_collide_with_request_middleware(caplog):
    """RequestMiddleware owns method/path/duration_ms; this log must not reuse them."""
    with caplog.at_level(logging.INFO):
        await validate_token(request=_public_endpoint_request(), response=None, redis=None)

    assert not {"method", "path", "duration_ms"} & set(_log_context(caplog))
