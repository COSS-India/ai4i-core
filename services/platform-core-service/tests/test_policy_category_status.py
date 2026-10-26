"""app/routes/policy.py and the category/sub-category services —
PATCH /policies/categories/{category_id}/status and
PATCH /policies/sub-categories/{sub_category_id}/status.

Covers the acceptance criteria that live in the API: an Adopter Admin can
enable or disable a category or sub-category, the row is updated in place
rather than deleted, a toggle changes only its own row so each child's own
state survives a parent disable/re-enable, a toggle of a sub-category leaves
its parent alone, a sub-category cannot be enabled under a disabled category,
an unknown id is 404, and only an Adopter Admin gets in.

The route module is loaded by file path for the same reason
test_policy_category.py does.
"""

from __future__ import annotations

import importlib.util
import sys
from unittest.mock import AsyncMock, MagicMock, call

import pytest
from pydantic import ValidationError as PydanticValidationError

from app.core.exceptions import AppError, EntityNotFoundError, InsufficientPermissionsError
from app.models.policy_management.category import Category
from app.models.policy_management.sub_category import SubCategory
from app.schemas.policy_management.category import CategoryItem, CategoryStatusUpdate
from app.schemas.policy_management.sub_category import SubCategoryItem, SubCategoryStatusUpdate
from app.services.policy_management import category_service, sub_category_service

_spec = importlib.util.spec_from_file_location("app.routes.policy", "app/routes/policy.py")
_policy_routes = importlib.util.module_from_spec(_spec)
sys.modules["app.routes.policy"] = _policy_routes
_spec.loader.exec_module(_policy_routes)


def _request(*, is_admin: bool = True) -> MagicMock:
    request = MagicMock()
    request.headers = {"X-Permission-IDS": "1" if is_admin else "5", "X-User-Id": "42"}
    return request


def _session(*gets) -> MagicMock:
    """AsyncSession stub: each ``get`` returns the next of ``gets``. A
    sub-category toggle reads the row, locks its parent, then re-reads the
    row under its own lock, so it takes ``(row, parent, row)``."""
    session = MagicMock()
    session.get = AsyncMock(side_effect=list(gets) or [None])
    session.execute = AsyncMock()
    session.commit = AsyncMock()
    session.rollback = AsyncMock()
    session.refresh = AsyncMock()
    session.delete = AsyncMock()
    return session


def _category(is_active=True) -> Category:
    return Category(id=1, name="Security & Privacy", description="Keep", is_active=is_active)


def _sub_category(is_active=True) -> SubCategory:
    return SubCategory(id=3, name="PII Guardrails", description="Keep", category_id=1, is_active=is_active)


class TestStatusUpdateSchema:
    @pytest.mark.parametrize("model", [CategoryStatusUpdate, SubCategoryStatusUpdate])
    def test_is_active_is_required(self, model):
        with pytest.raises(PydanticValidationError, match="is_active"):
            model()

    @pytest.mark.parametrize("model", [CategoryStatusUpdate, SubCategoryStatusUpdate])
    @pytest.mark.parametrize("value", ["maybe", "false", "true", 0, 1, None])
    def test_is_active_must_be_a_real_boolean(self, model, value):
        with pytest.raises(PydanticValidationError):
            model(is_active=value)


@pytest.mark.asyncio
class TestUpdateCategoryStatusService:
    @pytest.mark.parametrize("before,after", [(True, False), (False, True)])
    async def test_flips_the_flag_in_place(self, before, after):
        row = _category(is_active=before)
        session = _session(row)
        item = await category_service.update_category_status(
            session, 1, CategoryStatusUpdate(is_active=after)
        )
        session.get.assert_awaited_once_with(Category, 1, with_for_update=True)
        session.commit.assert_awaited_once()
        session.delete.assert_not_called()
        assert row.is_active is after
        assert item == CategoryItem(id=1, name="Security & Privacy", description="Keep", is_active=after)

    @pytest.mark.parametrize("is_active", [True, False])
    async def test_leaves_sub_categories_and_policies_alone(self, is_active):
        row = _category(is_active=not is_active)
        session = _session(row)
        await category_service.update_category_status(
            session, 1, CategoryStatusUpdate(is_active=is_active), updated_by="42"
        )
        assert row.updated_by == "42"
        session.execute.assert_not_awaited()
        session.commit.assert_awaited_once()

    @pytest.mark.parametrize("is_active", [True, False])
    async def test_same_state_changes_nothing(self, is_active):
        row = _category(is_active=is_active)
        session = _session(row)
        item = await category_service.update_category_status(
            session, 1, CategoryStatusUpdate(is_active=is_active), updated_by="42"
        )
        assert item.is_active is is_active
        assert row.updated_by is None
        session.execute.assert_not_awaited()
        session.commit.assert_not_awaited()
        session.rollback.assert_awaited_once()

    async def test_unknown_category_is_not_found(self):
        session = _session(None)
        with pytest.raises(EntityNotFoundError):
            await category_service.update_category_status(
                session, 42, CategoryStatusUpdate(is_active=False)
            )
        session.execute.assert_not_awaited()
        session.commit.assert_not_awaited()


@pytest.mark.asyncio
class TestUpdateSubCategoryStatusService:
    @pytest.mark.parametrize("before,after", [(True, False), (False, True)])
    async def test_flips_the_flag_in_place(self, before, after):
        row = _sub_category(is_active=before)
        session = _session(row, _category(is_active=True), row)
        item = await sub_category_service.update_sub_category_status(
            session, 3, SubCategoryStatusUpdate(is_active=after), updated_by="42"
        )
        assert session.get.await_args_list[0].args == (SubCategory, 3)
        assert row.updated_by == "42"
        session.commit.assert_awaited_once()
        session.delete.assert_not_called()
        assert row.is_active is after
        assert item == SubCategoryItem(
            id=3, name="PII Guardrails", description="Keep", category_id=1, is_active=after
        )
        session.execute.assert_not_awaited()  # policies keep their own state

    async def test_cannot_enable_under_a_disabled_category(self):
        row = _sub_category(is_active=False)
        session = _session(row, _category(is_active=False), row)
        with pytest.raises(AppError) as exc:
            await sub_category_service.update_sub_category_status(
                session, 3, SubCategoryStatusUpdate(is_active=True)
            )
        assert exc.value.status_code == 409
        assert session.get.await_args_list[1] == call(Category, 1, with_for_update=True)
        assert row.is_active is False
        session.execute.assert_not_awaited()
        session.commit.assert_not_awaited()

    async def test_can_disable_under_a_disabled_category(self):
        row = _sub_category(is_active=True)
        session = _session(row, _category(is_active=False), row)
        await sub_category_service.update_sub_category_status(
            session, 3, SubCategoryStatusUpdate(is_active=False)
        )
        assert row.is_active is False
        session.commit.assert_awaited_once()

    @pytest.mark.parametrize("is_active", [True, False])
    async def test_locks_the_parent_category(self, is_active):
        row = _sub_category(is_active=not is_active)
        session = _session(row, _category(is_active=True), row)
        await sub_category_service.update_sub_category_status(
            session, 3, SubCategoryStatusUpdate(is_active=is_active)
        )
        assert session.get.await_args_list[1] == call(Category, 1, with_for_update=True)

    async def test_rereads_the_row_after_taking_the_lock(self):
        """A toggle that committed while we waited for the lock must be seen,
        or a disable could take the no-op path on a stale is_active."""
        stale = _sub_category(is_active=False)
        fresh = _sub_category(is_active=True)  # committed by the other toggle while we waited
        session = _session(stale, _category(is_active=True), fresh)
        item = await sub_category_service.update_sub_category_status(
            session, 3, SubCategoryStatusUpdate(is_active=False)
        )
        assert session.get.await_args_list == [
            call(SubCategory, 3),
            call(Category, 1, with_for_update=True),
            call(SubCategory, 3, with_for_update=True, populate_existing=True),
        ]
        assert item.is_active is False
        session.commit.assert_awaited_once()

    async def test_relocks_when_a_move_changed_the_parent_meanwhile(self):
        """A move to a disabled category that committed before the lock was
        held must not let an enable through under the old, enabled parent."""
        row = _sub_category(is_active=False)
        moved = SubCategory(id=3, name="PII Guardrails", category_id=2, is_active=False)
        disabled = Category(id=2, name="Safety", is_active=False)
        session = _session(row, _category(is_active=True), moved, disabled, moved)
        with pytest.raises(AppError) as exc:
            await sub_category_service.update_sub_category_status(
                session, 3, SubCategoryStatusUpdate(is_active=True)
            )
        assert (exc.value.status_code, exc.value.code) == (409, "CATEGORY_DISABLED")
        assert session.get.await_args_list[3] == call(Category, 2, with_for_update=True)
        session.rollback.assert_awaited_once()  # released the old parent's lock
        session.commit.assert_not_awaited()

    async def test_deleted_while_waiting_for_the_lock_is_not_found(self):
        session = _session(_sub_category(), _category(), None)
        with pytest.raises(EntityNotFoundError, match="Sub-category 3"):
            await sub_category_service.update_sub_category_status(
                session, 3, SubCategoryStatusUpdate(is_active=False)
            )
        session.rollback.assert_awaited_once()
        session.commit.assert_not_awaited()

    @pytest.mark.parametrize("is_active", [True, False])
    async def test_same_state_changes_nothing(self, is_active):
        row = _sub_category(is_active=is_active)
        session = _session(row, _category(is_active=True), row)
        item = await sub_category_service.update_sub_category_status(
            session, 3, SubCategoryStatusUpdate(is_active=is_active), updated_by="42"
        )
        assert item.is_active is is_active
        assert row.updated_by is None
        session.execute.assert_not_awaited()
        session.commit.assert_not_awaited()
        session.rollback.assert_awaited_once()

    async def test_unknown_sub_category_is_not_found(self):
        session = _session(None)
        with pytest.raises(EntityNotFoundError):
            await sub_category_service.update_sub_category_status(
                session, 42, SubCategoryStatusUpdate(is_active=False)
            )
        session.commit.assert_not_awaited()


@pytest.mark.asyncio
class TestUpdateCategoryStatusRoute:
    @pytest.mark.parametrize("is_active,word", [(True, "enabled"), (False, "disabled")])
    async def test_returns_the_item_with_a_message(self, monkeypatch, is_active, word):
        item = CategoryItem(id=1, name="Safety", description=None, is_active=is_active)
        stub = AsyncMock(return_value=item)
        monkeypatch.setattr(_policy_routes.category_service, "update_category_status", stub)
        payload = CategoryStatusUpdate(is_active=is_active)
        resp = await _policy_routes.update_category_status(
            payload=payload, request=_request(), category_id=1, session=MagicMock()
        )
        assert stub.await_args.args[1:] == (1, payload)
        assert stub.await_args.kwargs["updated_by"] == "42"
        assert resp.data == item
        assert resp.meta.message == f"Category 'Safety' {word}."

    async def test_not_found_propagates(self, monkeypatch):
        monkeypatch.setattr(
            _policy_routes.category_service,
            "update_category_status",
            AsyncMock(side_effect=EntityNotFoundError("Category 42")),
        )
        with pytest.raises(EntityNotFoundError):
            await _policy_routes.update_category_status(
                payload=CategoryStatusUpdate(is_active=False),
                request=_request(),
                category_id=42,
                session=MagicMock(),
            )

    async def test_non_admin_is_rejected(self, monkeypatch):
        stub = AsyncMock()
        monkeypatch.setattr(_policy_routes.category_service, "update_category_status", stub)
        with pytest.raises(InsufficientPermissionsError):
            await _policy_routes.update_category_status(
                payload=CategoryStatusUpdate(is_active=False),
                request=_request(is_admin=False),
                category_id=1,
                session=MagicMock(),
            )
        stub.assert_not_awaited()


@pytest.mark.asyncio
class TestUpdateSubCategoryStatusRoute:
    @pytest.mark.parametrize("is_active,word", [(True, "enabled"), (False, "disabled")])
    async def test_returns_the_item_with_a_message(self, monkeypatch, is_active, word):
        item = SubCategoryItem(id=3, name="Toxicity", description=None, category_id=1, is_active=is_active)
        stub = AsyncMock(return_value=item)
        monkeypatch.setattr(_policy_routes.sub_category_service, "update_sub_category_status", stub)
        payload = SubCategoryStatusUpdate(is_active=is_active)
        resp = await _policy_routes.update_sub_category_status(
            payload=payload, request=_request(), sub_category_id=3, session=MagicMock()
        )
        assert stub.await_args.args[1:] == (3, payload)
        assert stub.await_args.kwargs["updated_by"] == "42"
        assert resp.data == item
        assert resp.meta.message == f"Sub-category 'Toxicity' {word}."

    async def test_not_found_propagates(self, monkeypatch):
        monkeypatch.setattr(
            _policy_routes.sub_category_service,
            "update_sub_category_status",
            AsyncMock(side_effect=EntityNotFoundError("Sub-category 42")),
        )
        with pytest.raises(EntityNotFoundError):
            await _policy_routes.update_sub_category_status(
                payload=SubCategoryStatusUpdate(is_active=False),
                request=_request(),
                sub_category_id=42,
                session=MagicMock(),
            )

    async def test_non_admin_is_rejected(self, monkeypatch):
        stub = AsyncMock()
        monkeypatch.setattr(_policy_routes.sub_category_service, "update_sub_category_status", stub)
        with pytest.raises(InsufficientPermissionsError):
            await _policy_routes.update_sub_category_status(
                payload=SubCategoryStatusUpdate(is_active=False),
                request=_request(is_admin=False),
                sub_category_id=3,
                session=MagicMock(),
            )
        stub.assert_not_awaited()


class TestRouteShape:
    @pytest.mark.parametrize(
        "path,param",
        [
            ("/policies/categories/{category_id}/status", "category_id"),
            ("/policies/sub-categories/{sub_category_id}/status", "sub_category_id"),
        ],
    )
    def test_id_must_fit_the_integer_column(self, path, param):
        route = next(r for r in _policy_routes.router.routes if r.path == path and "PATCH" in r.methods)
        field = next(p for p in route.dependant.path_params if p.name == param)
        bounds = {type(m).__name__: m for m in field.field_info.metadata}
        assert (bounds["Gt"].gt, bounds["Le"].le) == (0, 2_147_483_647)

    def test_paths_and_methods(self):
        routes = {(r.path, m) for r in _policy_routes.router.routes for m in r.methods}
        assert ("/policies/categories/{category_id}/status", "PATCH") in routes
        assert ("/policies/sub-categories/{sub_category_id}/status", "PATCH") in routes
