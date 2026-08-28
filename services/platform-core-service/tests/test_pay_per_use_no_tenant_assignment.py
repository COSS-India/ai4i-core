"""Regression guard: routes/pay_per_use.py must not import the
tenant_assignment_service/schema module #1488 deleted (tenant-tier and
tenant-budget endpoints moved to auth-service).

Bug scenario this guards against: a stale branch merge silently resurrected
app/services/pay_per_use/tenant_assignment_service.py,
app/schemas/pay_per_use/tenant_assignment.py, and
tests/test_tenant_assignment_service.py, while routes/pay_per_use.py kept
importing from them. The resurrected service module imported
app.models.pay_per_use.ppu_tenant_tier_assignment, which #1488 also removed —
so the whole test SUITE failed to collect (ModuleNotFoundError), not just
the resurrected file's own tests. A static per-file check wouldn't catch
this either: each file was internally self-consistent with the others that
came back with it: only importing the actual route module (the same
technique test_metering_routes.py / test_service_rbac_filtering.py use to
avoid app/routes/__init__.py's eager, fully-stubbed import chain) proves the
real import graph is clean.
"""

import importlib.util
import sys


def _load_pay_per_use_route_module():
    spec = importlib.util.spec_from_file_location(
        "app.routes.pay_per_use", "app/routes/pay_per_use.py"
    )
    module = importlib.util.module_from_spec(spec)
    sys.modules["app.routes.pay_per_use"] = module
    spec.loader.exec_module(module)
    return module


class TestPayPerUseRouteDoesNotImportDeletedTenantAssignment:
    def test_route_module_imports_cleanly(self) -> None:
        """The exact bug scenario: a resurrected tenant_assignment_service.py
        import chain broke collection of the whole test suite, not just its
        own tests."""
        module = _load_pay_per_use_route_module()
        assert module is not None

    def test_route_module_does_not_reference_tenant_assignment_service(self) -> None:
        module = _load_pay_per_use_route_module()
        assert not hasattr(module, "tenant_assignment_service")

    def test_tenant_assignment_service_module_does_not_exist(self) -> None:
        # NOT pytest.raises(ModuleNotFoundError) on import_module(): the
        # resurrected file itself raises ModuleNotFoundError too (it imports
        # app.models.pay_per_use.ppu_tenant_tier_assignment, also deleted by
        # #1488) — same exception type as "file doesn't exist", so that
        # assertion would pass in both the fixed state and the resurrected
        # state. find_spec resolves whether the file is present on the
        # import path without executing it, so it actually discriminates.
        assert (
            importlib.util.find_spec("app.services.pay_per_use.tenant_assignment_service")
            is None
        )

    def test_tenant_assignment_schema_module_does_not_exist(self) -> None:
        assert (
            importlib.util.find_spec("app.schemas.pay_per_use.tenant_assignment") is None
        )
