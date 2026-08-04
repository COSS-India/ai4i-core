"""Unit tests: _set_tenant_headers percent-encodes a non-latin-1 organisation
name before setting X-Tenant-Name, since Starlette encodes header values as
latin-1 and _check_org_chars (schemas/tenant.py) accepts any Unicode letter —
without this, a Devanagari/Tamil org name 500s the whole /validate call.
"""
from urllib.parse import unquote

import pytest
from fastapi import Response

from app.routes.validation import _set_tenant_headers
from app.services.tenant_name_cache import tenant_name_cache


@pytest.fixture(autouse=True)
def _reset_tenant_name_cache():
    tenant_name_cache._names = {}
    yield
    tenant_name_cache._names = {}


class TestSetTenantHeaders:
    def test_ascii_name_passed_through_unescaped(self):
        tenant_name_cache.set_name(1, "Acme Corp")
        response = Response()
        _set_tenant_headers(response, 1)
        assert response.headers["X-Tenant-Name"] == "Acme Corp"
        assert response.headers["X-Tenant-ID"] == "1"

    def test_cache_miss_falls_back_to_id_for_both_headers(self):
        response = Response()
        _set_tenant_headers(response, 42)
        assert response.headers["X-Tenant-Name"] == "42"
        assert response.headers["X-Tenant-ID"] == "42"

    def test_non_latin1_name_does_not_raise_and_is_latin1_safe(self):
        """Devanagari org name — this used to raise UnicodeEncodeError when
        Starlette tried to encode the header value as latin-1."""
        tenant_name_cache.set_name(2, "टाटा समूह")
        response = Response()
        _set_tenant_headers(response, 2)  # must not raise

        encoded = response.headers["X-Tenant-Name"]
        encoded.encode("latin-1")  # must not raise either
        assert encoded != "टाटा समूह"

    def test_non_latin1_name_round_trips_via_unquote(self):
        """The observability middleware's _tenant_label() undoes this
        encoding — confirm it's a lossless round trip."""
        tenant_name_cache.set_name(3, "टाटा समूह")
        response = Response()
        _set_tenant_headers(response, 3)
        assert unquote(response.headers["X-Tenant-Name"]) == "टाटा समूह"

    def test_accented_latin1_name_passed_through_unescaped(self):
        """Accented Latin (e.g. French) IS latin-1 encodable — no encoding needed."""
        tenant_name_cache.set_name(4, "Société Générale")
        response = Response()
        _set_tenant_headers(response, 4)
        assert response.headers["X-Tenant-Name"] == "Société Générale"

    def test_non_numeric_tenant_id_does_not_raise(self):
        """Defensive: a non-numeric tenant_id (shouldn't happen in practice)
        must fall back cleanly rather than raise from the int() cast."""
        response = Response()
        _set_tenant_headers(response, "not-an-id")
        assert response.headers["X-Tenant-Name"] == "not-an-id"
        assert response.headers["X-Tenant-ID"] == "not-an-id"
