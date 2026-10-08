"""app/routes/policy.py and the category/sub-category services —
PUT /policies/categories/{category_id} and
PUT /policies/sub-categories/{sub_category_id}.

Covers the acceptance criteria that live in the API: an Adopter Admin can
enable or disable a category or sub-category, the row is updated in place
rather than deleted, toggling a category applies the same flag to every
sub-category and policy under it, toggling a sub-category applies it to its
policies and leaves its parent alone, a
sub-category cannot be enabled under a disabled category, an unknown id is 404, and only an Adopter Admin gets in.

The route module is loaded by file path for the same reason
test_policy_category.py does.
"""

from __future__ import annotations

import importlib.util
import sys
from unittest.mock import AsyncMock, MagicMock

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
    request.headers = {"X-Permission-IDS": "1"} if is_admin else {"X-Permission-IDS": "5"}
    return request


def _session(row=None, parent=None) -> MagicMock:
    """AsyncSession stub: ``get`` returns ``row``, then ``parent``."""
    session = MagicMock()
    session.get = AsyncMock(side_effect=[row, parent])
    session.execute = AsyncMock()
    session.commit = AsyncMock()
    session.refresh = AsyncMock()
    session.delete = AsyncMock()
    return session


def _sql(stmt) -> str:
    return str(stmt.compile(compile_kwargs={"literal_binds": True}))


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
    def test_is_active_must_be_boolean(self, model):
        with pytest.raises(PydanticValidationError):
            model(is_active="maybe")


@pytest.mark.asyncio
class TestUpdateCategoryStatusService:
    @pytest.mark.parametrize("before,after", [(True, False), (False, True)])
    async def test_flips_the_flag_in_place(self, before, after):
        row = _category(is_active=before)
        session = _session(row)
        item = await category_service.update_category_status(
            session, 1, CategoryStatusUpdate(is_active=after)
        )
        session.get.assert_awaited_once_with(Category, 1)
        session.commit.assert_awaited_once()
        session.delete.assert_not_called()
        assert row.is_active is after
        assert item == CategoryItem(id=1, name="Security & Privacy", description="Keep", is_active=after)

    @pytest.mark.parametrize("is_active", [True, False])
    async def test_applies_the_flag_to_its_sub_categories(self, is_active):
        session = _session(_category(is_active=not is_active))
        await category_service.update_category_status(
            session, 1, CategoryStatusUpdate(is_active=is_active)
        )
        sub_stmt, policy_stmt = (c.args[0] for c in session.execute.await_args_list)
        sql = _sql(sub_stmt)
        assert sql.startswith("UPDATE sub_category SET is_active=")
        assert sql.endswith("WHERE sub_category.category_id = 1")
        assert sub_stmt.compile().params["is_active"] is is_active
        sql = _sql(policy_stmt)
        assert sql.startswith("UPDATE policy SET is_active=")
        assert "WHERE policy.sub_category_id IN (SELECT sub_category.id" in sql
        assert "WHERE sub_category.category_id = 1)" in sql
        assert policy_stmt.compile().params["is_active"] is is_active

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
        session = _session(row, _category(is_active=True))
        item = await sub_category_service.update_sub_category_status(
            session, 3, SubCategoryStatusUpdate(is_active=after)
        )
        assert session.get.await_args_list[0].args == (SubCategory, 3)
        session.commit.assert_awaited_once()
        session.delete.assert_not_called()
        assert row.is_active is after
        assert item == SubCategoryItem(
            id=3, name="PII Guardrails", description="Keep", category_id=1, is_active=after
        )
        stmt = session.execute.await_args.args[0]
        assert _sql(stmt) == f"UPDATE policy SET is_active={str(after).lower()} WHERE policy.sub_category_id = 3"

    async def test_cannot_enable_under_a_disabled_category(self):
        row = _sub_category(is_active=False)
        session = _session(row, _category(is_active=False))
        with pytest.raises(AppError) as exc:
            await sub_category_service.update_sub_category_status(
                session, 3, SubCategoryStatusUpdate(is_active=True)
            )
        assert exc.value.status_code == 409
        assert session.get.await_args_list[1].args == (Category, 1)
        assert row.is_active is False
        session.execute.assert_not_awaited()
        session.commit.assert_not_awaited()

    async def test_can_disable_under_a_disabled_category(self):
        row = _sub_category(is_active=True)
        session = _session(row)
        await sub_category_service.update_sub_category_status(
            session, 3, SubCategoryStatusUpdate(is_active=False)
        )
        assert row.is_active is False
        session.get.assert_awaited_once()

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
    def test_paths_and_methods(self):
        routes = {(r.path, m) for r in _policy_routes.router.routes for m in r.methods}
        assert ("/policies/categories/{category_id}", "PUT") in routes
        assert ("/policies/sub-categories/{sub_category_id}", "PUT") in routes
