"""UsageEventsMeteringService's tenant scope fails closed: a scope that names
a tenant but has no usable id raises instead of running platform-wide (these
queries filter on the id only)."""
import pytest

from app.services.metering_service_usage_events import _tenant_pk


def test_numeric_id_filters():
    assert _tenant_pk("7") == 7 and _tenant_pk(7, "Acme") == 7


def test_no_tenant_at_all_is_platform_wide():
    assert _tenant_pk(None) is None and _tenant_pk(None, None) is None


@pytest.mark.parametrize(("tenant_id", "tenant"), [(None, "Acme Corp"), ("abc", None), ("", "Acme Corp")])
def test_named_tenant_without_a_usable_id_raises(tenant_id, tenant):
    with pytest.raises(PermissionError):
        _tenant_pk(tenant_id, tenant)
