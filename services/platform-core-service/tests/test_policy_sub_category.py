"""app/routes/policy.py and app/services/policy_management/sub_category_service.py
— GET/POST /policies/sub-categories.

Covers the acceptance criteria that live in the API: a blank Sub-Category
Name or missing parent Category is rejected, the parent must exist, a
duplicate name (case-insensitive) is rejected, and a created sub-category
is listed under its parent. Only an Adopter Admin gets in.

The route module is loaded by file path for the same reason
test_policy_category.py does.
"""

from __future__ import annotations

import importlib.util
import sys
from unittest.mock import AsyncMock, MagicMock

import pytest
from pydantic import ValidationError as PydanticValidationError
from sqlalchemy.exc import IntegrityError

from app.core.exceptions import (
    DuplicateEntityError,
    EntityNotFoundError,
    InsufficientPermissionsError,
)
from app.models.policy_management.sub_category import SubCategory
from app.schemas.policy_management.sub_category import SubCategoryCreate, SubCategoryItem
from app.services.policy_management import sub_category_service

_spec = importlib.util.spec_from_file_location("app.routes.policy", "app/routes/policy.py")
_policy_routes = importlib.util.module_from_spec(_spec)
sys.modules["app.routes.policy"] = _policy_routes
_spec.loader.exec_module(_policy_routes)


def _request(*, is_admin: bool = True) -> MagicMock:
    request = MagicMock()
    request.headers = {"X-Permission-IDS": "1"} if is_admin else {"X-Permission-IDS": "5"}
    return request


def _item(id=1, name="PII Guardrails", category_id=1) -> SubCategoryItem:
    return SubCategoryItem(id=id, name=name, description=None, category_id=category_id, is_active=False)


def _result(*, first=None, rows=()) -> MagicMock:
    result = MagicMock()
    result.first.return_value = first
    result.scalars.return_value.all.return_value = list(rows)
    return result


def _session(*results, commit_side_effect=None) -> MagicMock:
    """AsyncSession stub: each ``execute`` call returns the next of ``results``."""
    session = MagicMock()
    session.execute = AsyncMock(side_effect=list(results))
    session.commit = AsyncMock(side_effect=commit_side_effect)
    session.rollback = AsyncMock()

    async def _refresh(row):
        row.id = 9
        row.is_active = False

    session.refresh = AsyncMock(side_effect=_refresh)
    return session


_CATEGORY_FOUND = _result(first=(1,))
_CATEGORY_MISSING = _result(first=None)
_NAME_FREE = _result(first=None)
_NAME_TAKEN = _result(first=(3,))


class TestSubCategoryCreateSchema:
    def test_category_is_required(self):
        with pytest.raises(PydanticValidationError, match="category_id"):
            SubCategoryCreate(name="Toxicity")

    @pytest.mark.parametrize("category_id", [0, -1])
    def test_category_id_must_be_positive(self, category_id):
        with pytest.raises(PydanticValidationError):
            SubCategoryCreate(name="Toxicity", category_id=category_id)

    def test_category_id_must_fit_the_integer_column(self):
        with pytest.raises(PydanticValidationError):
            SubCategoryCreate(name="Toxicity", category_id=2_147_483_648)

    def test_name_is_required(self):
        with pytest.raises(PydanticValidationError, match="name"):
            SubCategoryCreate(category_id=1)

    @pytest.mark.parametrize("name", ["", "   "])
    def test_blank_name_is_rejected(self, name):
        with pytest.raises(PydanticValidationError, match="Sub-Category Name is required"):
            SubCategoryCreate(name=name, category_id=1)

    def test_name_longer_than_column_is_rejected(self):
        with pytest.raises(PydanticValidationError):
            SubCategoryCreate(name="x" * 101, category_id=1)

    def test_padding_does_not_count_toward_max_length(self):
        assert SubCategoryCreate(name="  " + "x" * 100 + "  ", category_id=1).name == "x" * 100

    def test_name_and_description_are_trimmed(self):
        body = SubCategoryCreate(name="  Toxicity  ", description="  Hate  ", category_id=1)
        assert (body.name, body.description) == ("Toxicity", "Hate")

    @pytest.mark.parametrize("description", [None, "", "   "])
    def test_description_is_optional(self, description):
        assert SubCategoryCreate(name="Toxicity", description=description, category_id=1).description is None


@pytest.mark.asyncio
class TestCreateSubCategoryService:
    async def test_creates_under_the_parent_and_returns_the_row(self):
        session = _session(_CATEGORY_FOUND, _NAME_FREE)
        item = await sub_category_service.create_sub_category(
            session, SubCategoryCreate(name="Toxicity", description="Hate", category_id=1)
        )
        added = session.add.call_args.args[0]
        assert (added.name, added.description, added.category_id) == ("Toxicity", "Hate", 1)
        session.commit.assert_awaited_once()
        assert item == SubCategoryItem(
            id=9, name="Toxicity", description="Hate", category_id=1, is_active=False
        )

    async def test_missing_parent_category_is_not_found(self):
        session = _session(_CATEGORY_MISSING)
        with pytest.raises(EntityNotFoundError):
            await sub_category_service.create_sub_category(
                session, SubCategoryCreate(name="Toxicity", category_id=42)
            )
        session.add.assert_not_called()

    async def test_existing_name_is_rejected_before_insert(self):
        session = _session(_CATEGORY_FOUND, _NAME_TAKEN)
        with pytest.raises(DuplicateEntityError):
            await sub_category_service.create_sub_category(
                session, SubCategoryCreate(name="pii guardrails", category_id=1)
            )
        session.add.assert_not_called()

    async def test_duplicate_check_is_case_insensitive(self):
        session = _session(_CATEGORY_FOUND, _NAME_FREE)
        await sub_category_service.create_sub_category(
            session, SubCategoryCreate(name="Toxicity", category_id=1)
        )
        stmt = session.execute.await_args_list[1].args[0]
        sql = str(stmt.compile(compile_kwargs={"literal_binds": True}))
        assert "lower(sub_category.name) = lower('Toxicity')" in sql

    async def test_integrity_error_on_commit_is_a_duplicate(self):
        session = _session(
            _CATEGORY_FOUND, _NAME_FREE,
            commit_side_effect=IntegrityError("insert", {}, Exception("uq_sub_category_name_lower")),
        )
        with pytest.raises(DuplicateEntityError):
            await sub_category_service.create_sub_category(
                session, SubCategoryCreate(name="Toxicity", category_id=1)
            )
        session.rollback.assert_awaited_once()


@pytest.mark.asyncio
class TestListSubCategoriesService:
    async def test_lists_all_without_a_filter(self):
        row = SubCategory(id=1, name="PII Guardrails", category_id=1, is_active=True)
        session = _session(_result(rows=[row]))
        items = await sub_category_service.list_sub_categories(session)
        assert [i.name for i in items] == ["PII Guardrails"]
        sql = str(session.execute.await_args.args[0])
        assert "WHERE" not in sql

    async def test_filters_by_category(self):
        session = _session(_CATEGORY_FOUND, _result(rows=[]))
        await sub_category_service.list_sub_categories(session, category_id=1)
        sql = str(session.execute.await_args_list[1].args[0])
        assert "sub_category.category_id = " in sql

    async def test_unknown_category_filter_is_not_found(self):
        session = _session(_CATEGORY_MISSING)
        with pytest.raises(EntityNotFoundError):
            await sub_category_service.list_sub_categories(session, category_id=42)


@pytest.mark.asyncio
class TestListSubCategoriesRoute:
    async def test_wraps_items_and_forwards_the_filter(self, monkeypatch):
        stub = AsyncMock(return_value=[_item()])
        monkeypatch.setattr(_policy_routes.sub_category_service, "list_sub_categories", stub)
        resp = await _policy_routes.list_sub_categories(
            request=_request(), category_id=1, session=MagicMock()
        )
        assert stub.await_args.args[1] == 1
        assert resp.success is True
        assert [i.name for i in resp.data.items] == ["PII Guardrails"]

    async def test_non_admin_is_rejected(self, monkeypatch):
        stub = AsyncMock(return_value=[])
        monkeypatch.setattr(_policy_routes.sub_category_service, "list_sub_categories", stub)
        with pytest.raises(InsufficientPermissionsError):
            await _policy_routes.list_sub_categories(
                request=_request(is_admin=False), category_id=None, session=MagicMock()
            )
        stub.assert_not_awaited()


@pytest.mark.asyncio
class TestCreateSubCategoryRoute:
    async def test_returns_the_created_item_with_a_message(self, monkeypatch):
        stub = AsyncMock(return_value=_item(id=2, name="Toxicity"))
        monkeypatch.setattr(_policy_routes.sub_category_service, "create_sub_category", stub)
        payload = SubCategoryCreate(name="Toxicity", category_id=1)
        resp = await _policy_routes.create_sub_category(
            payload=payload, request=_request(), session=MagicMock()
        )
        assert stub.await_args.args[1] is payload
        assert resp.data.id == 2
        assert resp.meta.message == "Sub-category 'Toxicity' created."

    @pytest.mark.parametrize(
        "error", [EntityNotFoundError("Category 42"), DuplicateEntityError("Sub-category 'X'")]
    )
    async def test_service_errors_propagate(self, monkeypatch, error):
        monkeypatch.setattr(
            _policy_routes.sub_category_service, "create_sub_category", AsyncMock(side_effect=error)
        )
        with pytest.raises(type(error)):
            await _policy_routes.create_sub_category(
                payload=SubCategoryCreate(name="X", category_id=42), request=_request(), session=MagicMock()
            )

    async def test_non_admin_is_rejected(self, monkeypatch):
        stub = AsyncMock()
        monkeypatch.setattr(_policy_routes.sub_category_service, "create_sub_category", stub)
        with pytest.raises(InsufficientPermissionsError):
            await _policy_routes.create_sub_category(
                payload=SubCategoryCreate(name="X", category_id=1),
                request=_request(is_admin=False),
                session=MagicMock(),
            )
        stub.assert_not_awaited()


class TestRouteShape:
    def test_paths_and_methods(self):
        routes = {(r.path, m) for r in _policy_routes.router.routes for m in r.methods}
        assert ("/policies/sub-categories", "GET") in routes
        assert ("/policies/sub-categories", "POST") in routes

    def test_post_returns_201(self):
        route = next(
            r for r in _policy_routes.router.routes
            if r.path == "/policies/sub-categories" and "POST" in r.methods
        )
        assert route.status_code == 201
