"""Regression guard: app.models.Base.metadata must not declare a table for
ppu_tenant_tier_assignments (dropped from the DB by AI4IDS-2923).

Exact bug scenario this guards against: TenantTierAssignment stayed
registered on Base as an ORM class after its table was dropped. Alembic's
`env.py` builds target_metadata from `app.models.Base.metadata` (see
migration_registry._load_core_service_metadata) and `include_object` only
filters *reflected* objects missing from that metadata — a model-declared
table with no matching object in the live DB (reflected=False,
compare_to=None) falls through to `include_object`'s final `return True`.
The next `alembic revision --autogenerate -x db=ai4iplatform_core` would
therefore emit `op.create_table("ppu_tenant_tier_assignments", ...)` plus its
two indexes, silently resurrecting a table an earlier migration
(a1b3c5d7e9f0_drop_ppu_tenant_tier_assignments) intentionally removed.
"""
import importlib.util


class TestDroppedTableNotInModelMetadata:
    def test_ppu_tenant_tier_assignments_not_in_base_metadata(self) -> None:
        # No importlib.reload here: app.models' submodule imports are cached
        # in sys.modules, so reloading only the package re-runs its own
        # top-level statements (including `Base = declarative_base()`, a
        # BRAND NEW empty Base/metadata) without re-executing the cached
        # submodules against it — every model class stays attached to
        # whichever Base object was live when it was first imported this
        # process, not the freshly reloaded one. That silently made this
        # assertion pass against an empty metadata regardless of the real
        # bug. A plain import reflects whatever's actually on disk, since
        # each pytest run is its own fresh process.
        import app.models as models

        assert "ppu_tenant_tier_assignments" not in models.Base.metadata.tables

    def test_tenant_tier_assignment_class_no_longer_exists(self) -> None:
        assert (
            importlib.util.find_spec("app.models.pay_per_use.tenant_tier_assignment")
            is None
        )

    def test_tier_no_longer_exposes_tenant_assignments_relationship(self) -> None:
        """Tier.tenant_assignments back_populated the deleted class — an
        un-mapped relationship left on Tier would raise
        InvalidRequestError the first time any mapper is configured."""
        from app.models.pay_per_use.tier import Tier

        assert not hasattr(Tier, "tenant_assignments")

    def test_models_package_does_not_export_tenant_tier_assignment(self) -> None:
        import app.models as models

        assert "TenantTierAssignment" not in models.__all__
        assert not hasattr(models, "TenantTierAssignment")
