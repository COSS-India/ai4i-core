"""GET /services?tier_ids= for non-admin callers (AI4IDS-3488).

The Application fallback picker lists the services mapped to the
Institution's Tier with the existing tier_ids filter — open to every caller,
though the tier column stays admin-only. A non-admin tier_ids query only ever
returns published services: auth-service rejects an unpublished fallback
(SERVICE_NOT_PUBLISHED), so offering one would only fail on save.
"""
import asyncio
import importlib.util
import inspect
import sys
from unittest.mock import AsyncMock, MagicMock

_spec = importlib.util.spec_from_file_location("app.routes.service", "app/routes/service.py")
_route = importlib.util.module_from_spec(_spec)
sys.modules["app.routes.service"] = _route
_spec.loader.exec_module(_route)

_ADMIN, _NON_ADMIN = "1", "50"


def _call(permission_ids, **filter_args):
    svc = MagicMock()
    svc.list_services = AsyncMock(return_value=([], 0))
    request = MagicMock()
    request.headers = {"X-Permission-IDS": permission_ids}
    asyncio.run(_route.list_services(
        request=request, response=MagicMock(headers={}), svc=svc, db=MagicMock(),
        filters=_route.ServiceListFilterParams(**filter_args),
        paging=_route.ServiceListSortParams(),
    ))
    return svc.list_services.call_args.kwargs


def test_non_admin_may_filter_by_tier():
    kwargs = _call(_NON_ADMIN, tier_ids="tier-gold")
    assert kwargs["filters"].tier_ids == ["tier-gold"]


def test_non_admin_tier_query_returns_published_only():
    assert _call(_NON_ADMIN, tier_ids="tier-gold")["is_published"] is True
    # Even an explicit is_published=false can't widen it.
    assert _call(_NON_ADMIN, tier_ids="tier-gold", is_published=False)["is_published"] is True


def test_admin_tier_query_is_not_forced_to_published():
    assert _call(_ADMIN, tier_ids="tier-gold")["is_published"] is None
    assert _call(_ADMIN, tier_ids="tier-gold", is_published=False)["is_published"] is False


def test_non_admin_without_tier_filter_is_unchanged():
    assert _call(_NON_ADMIN)["is_published"] is None


def test_no_parallel_tier_id_parameter():
    params = set(inspect.signature(_route.ServiceListFilterParams.__init__).parameters)
    assert "tier_id" not in params and "tier_ids" in params
