"""app/routes/policy.py and app/services/policy_management/category_service.py
— GET/POST /policies/categories.

Covers the acceptance criteria that live in the API: a blank Category Name
is rejected, a duplicate name (case-insensitive) is rejected, a created
category comes back in the envelope, and only an Adopter Admin gets in.

The route module is loaded by file path for the same reason
test_notification_catalog_routes.py does: app/routes/__init__.py eagerly
imports ai4i_core.bootstrap.versioning, which conftest does not stub.
"""

from __future__ import annotations

import importlib.util
import sys
from unittest.mock import AsyncMock, MagicMock

import pytest
from pydantic import ValidationError as PydanticValidationError
from sqlalchemy.exc import IntegrityError

from app.core.exceptions import DuplicateEntityError, InsufficientPermissionsError
from app.schemas.policy_management.category import CategoryCreate, CategoryItem
from app.services.policy_management import category_service

_spec = importlib.util.spec_from_file_location("app.routes.policy", "app/routes/policy.py")
_policy_routes = importlib.util.module_from_spec(_spec)
sys.modules["app.routes.policy"] = _policy_routes
_spec.loader.exec_module(_policy_routes)


def _request(*, is_admin: bool = True) -> MagicMock:
    request = MagicMock()
    request.headers = {"X-Permission-IDS": "1"} if is_admin else {"X-Permission-IDS": "5"}
    return request


def _item(id=1, name="Security & Privacy", description=None, is_active=False) -> CategoryItem:
    return CategoryItem(id=id, name=name, description=description, is_active=is_active)


def _session(*, existing=None, commit_side_effect=None) -> MagicMock:
    """AsyncSession stub: ``execute`` returns ``existing`` from ``.first()``."""
    session = MagicMock()
    result = MagicMock()
    result.first.return_value = existing
    session.execute = AsyncMock(return_value=result)
    session.commit = AsyncMock(side_effect=commit_side_effect)
    session.rollback = AsyncMock()

    async def _refresh(row):
        row.id = 7
        row.is_active = False

    session.refresh = AsyncMock(side_effect=_refresh)
    return session


class TestCategoryCreateSchema:
    def test_name_is_required(self):
        with pytest.raises(PydanticValidationError):
            CategoryCreate()

    @pytest.mark.parametrize("name", ["", "   "])
    def test_blank_name_is_rejected(self, name):
        with pytest.raises(PydanticValidationError, match="Category Name is required"):
            CategoryCreate(name=name)

    def test_name_longer_than_column_is_rejected(self):
        with pytest.raises(PydanticValidationError):
            CategoryCreate(name="x" * 101)

    def test_padding_does_not_count_toward_max_length(self):
        assert CategoryCreate(name="  " + "x" * 100 + "  ").name == "x" * 100

    def test_non_string_name_is_rejected(self):
        with pytest.raises(PydanticValidationError):
            CategoryCreate(name=123)

    def test_name_and_description_are_trimmed(self):
        body = CategoryCreate(name="  Safety  ", description="  Harm filters  ")
        assert body.name == "Safety"
        assert body.description == "Harm filters"

    @pytest.mark.parametrize("name", ["\u200b", " \u200b\ufeff "])
    def test_name_with_nothing_visible_is_rejected(self, name):
        with pytest.raises(PydanticValidationError, match="Category Name is required"):
            CategoryCreate(name=name)

    def test_zero_width_characters_are_trimmed_from_the_ends(self):
        assert CategoryCreate(name="\u200bSafety\u200b").name == "Safety"

    def test_zero_width_joiner_inside_a_name_is_kept(self):
        assert CategoryCreate(name="ക\u200dഷ").name == "ക\u200dഷ"

    @pytest.mark.parametrize("description", [None, "", "   ", "\u200b"])
    def test_description_is_optional(self, description):
        assert CategoryCreate(name="Safety", description=description).description is None

    def test_description_longer_than_limit_is_rejected(self):
        with pytest.raises(PydanticValidationError):
            CategoryCreate(name="Safety", description="x" * 1001)

    def test_description_padding_does_not_count_toward_limit(self):
        assert CategoryCreate(name="Safety", description=" " + "x" * 1000 + " ").description == "x" * 1000


@pytest.mark.asyncio
class TestCreateCategoryService:
    async def test_creates_and_returns_the_row(self):
        session = _session(existing=None)
        item = await category_service.create_category(
            session, CategoryCreate(name="Safety", description="Harm filters")
        )
        added = session.add.call_args.args[0]
        assert (added.name, added.description) == ("Safety", "Harm filters")
        session.commit.assert_awaited_once()
        assert item == CategoryItem(id=7, name="Safety", description="Harm filters", is_active=False)

    async def test_existing_name_is_rejected_before_insert(self):
        session = _session(existing=(1,))
        with pytest.raises(DuplicateEntityError):
            await category_service.create_category(session, CategoryCreate(name="safety"))
        session.add.assert_not_called()
        session.commit.assert_not_awaited()

    async def test_duplicate_check_is_case_insensitive(self):
        session = _session(existing=None)
        await category_service.create_category(session, CategoryCreate(name="Safety"))
        sql = str(session.execute.await_args.args[0].compile(compile_kwargs={"literal_binds": True}))
        assert "lower(category.name) = lower('Safety')" in sql

    async def test_integrity_error_on_commit_is_a_duplicate(self):
        session = _session(
            existing=None, commit_side_effect=IntegrityError("insert", {}, Exception("uq_category_name_lower"))
        )
        with pytest.raises(DuplicateEntityError):
            await category_service.create_category(session, CategoryCreate(name="Safety"))
        session.rollback.assert_awaited_once()

    async def test_other_integrity_errors_are_not_reported_as_duplicates(self):
        error = IntegrityError("insert", {}, Exception("some_other_constraint"))
        session = _session(existing=None, commit_side_effect=error)
        with pytest.raises(IntegrityError):
            await category_service.create_category(session, CategoryCreate(name="Safety"))
        session.rollback.assert_awaited_once()


@pytest.mark.asyncio
class TestListCategoriesRoute:
    async def test_wraps_items_in_the_envelope(self, monkeypatch):
        monkeypatch.setattr(
            _policy_routes.category_service, "list_categories", AsyncMock(return_value=[_item()])
        )
        resp = await _policy_routes.list_categories(request=_request(), session=MagicMock())
        assert resp.success is True
        assert [i.name for i in resp.data.items] == ["Security & Privacy"]

    async def test_non_admin_is_rejected(self, monkeypatch):
        stub = AsyncMock(return_value=[])
        monkeypatch.setattr(_policy_routes.category_service, "list_categories", stub)
        with pytest.raises(InsufficientPermissionsError):
            await _policy_routes.list_categories(request=_request(is_admin=False), session=MagicMock())
        stub.assert_not_awaited()


@pytest.mark.asyncio
class TestCreateCategoryRoute:
    async def test_returns_the_created_item_with_a_message(self, monkeypatch):
        stub = AsyncMock(return_value=_item(id=2, name="Safety"))
        monkeypatch.setattr(_policy_routes.category_service, "create_category", stub)
        payload = CategoryCreate(name="Safety")
        resp = await _policy_routes.create_category(
            payload=payload, request=_request(), session=MagicMock()
        )
        assert stub.await_args.args[1] is payload
        assert resp.data.id == 2
        assert resp.meta.message == "Category 'Safety' created."

    async def test_duplicate_propagates(self, monkeypatch):
        monkeypatch.setattr(
            _policy_routes.category_service, "create_category",
            AsyncMock(side_effect=DuplicateEntityError("Category 'Safety'")),
        )
        with pytest.raises(DuplicateEntityError):
            await _policy_routes.create_category(
                payload=CategoryCreate(name="Safety"), request=_request(), session=MagicMock()
            )

    async def test_non_admin_is_rejected(self, monkeypatch):
        stub = AsyncMock()
        monkeypatch.setattr(_policy_routes.category_service, "create_category", stub)
        with pytest.raises(InsufficientPermissionsError):
            await _policy_routes.create_category(
                payload=CategoryCreate(name="Safety"), request=_request(is_admin=False), session=MagicMock()
            )
        stub.assert_not_awaited()


class TestRouteShape:
    def test_paths_and_methods(self):
        routes = {(r.path, m) for r in _policy_routes.router.routes for m in r.methods}
        assert ("/policies/categories", "GET") in routes
        assert ("/policies/categories", "POST") in routes

    def test_post_returns_201(self):
        route = next(r for r in _policy_routes.router.routes if "POST" in r.methods)
        assert route.status_code == 201
