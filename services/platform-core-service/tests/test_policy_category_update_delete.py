"""app/routes/policy.py and the category/sub-category services —
PATCH and DELETE on /policies/categories/{category_id} and
/policies/sub-categories/{sub_category_id}.

Covers the acceptance criteria that live in the API: an Adopter Admin can
rename a category or sub-category, change its description and move a
sub-category to another category; only the fields sent change; a name
already taken in any case is 409 and a move to a missing category is 404;
a rename or move re-caches the affected policies; a delete is refused with
409 (naming how many children block it) while anything sits under the row
and is 204 otherwise; an unknown id is 404, and only an Adopter Admin gets in.

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
    AppError,
    DuplicateEntityError,
    EntityNotFoundError,
    InsufficientPermissionsError,
)
from app.models.policy_management.category import Category
from app.models.policy_management.policy import Policy
from app.models.policy_management.sub_category import SubCategory
from app.schemas.policy_management.category import CategoryItem, CategoryUpdate
from app.schemas.policy_management.sub_category import SubCategoryItem, SubCategoryUpdate
from app.services.policy_management import category_service, sub_category_service

_spec = importlib.util.spec_from_file_location("app.routes.policy", "app/routes/policy.py")
_policy_routes = importlib.util.module_from_spec(_spec)
sys.modules["app.routes.policy"] = _policy_routes
_spec.loader.exec_module(_policy_routes)


def _request(*, is_admin: bool = True) -> MagicMock:
    request = MagicMock()
    request.headers = {"X-Permission-IDS": "1" if is_admin else "5", "X-User-Id": "42"}
    return request


def _result(*, first=None, rows=()) -> MagicMock:
    result = MagicMock()
    result.first.return_value = first
    result.scalars.return_value.all.return_value = list(rows)
    result.all.return_value = list(rows)
    return result


def _session(*gets, results=(), count=0, commit_side_effect=None) -> MagicMock:
    """AsyncSession stub: ``get`` returns ``gets`` in order, each ``execute``
    the next of ``results``, and ``scalar`` the child count."""
    session = MagicMock()
    session.get = AsyncMock(side_effect=list(gets))
    session.execute = AsyncMock(side_effect=list(results) or None)
    session.scalar = AsyncMock(return_value=count)
    session.commit = AsyncMock(side_effect=commit_side_effect)
    session.rollback = AsyncMock()
    session.refresh = AsyncMock()
    session.delete = AsyncMock()
    return session


def _category() -> Category:
    return Category(id=1, name="Security & Privacy", description="Keep", is_active=True)


def _sub_category() -> SubCategory:
    return SubCategory(id=3, name="PII Guardrails", description="Keep", category_id=1, is_active=True)


def _integrity_error(constraint: str) -> IntegrityError:
    return IntegrityError("stmt", {}, Exception(constraint))


_FOUND = _result(first=(1,))
_MISSING = _result(first=None)


# ── Schemas ──────────────────────────────────────────────────────────────────


class TestCategoryUpdateSchema:
    def test_only_the_fields_sent_are_set(self):
        assert CategoryUpdate(name="X").model_fields_set == {"name"}

    def test_empty_body_is_rejected(self):
        with pytest.raises(PydanticValidationError, match="At least one"):
            CategoryUpdate()

    @pytest.mark.parametrize("name", ["", "   ", "​", None])
    def test_blank_or_null_name_is_rejected(self, name):
        with pytest.raises(PydanticValidationError, match="Category Name"):
            CategoryUpdate(name=name)

    def test_name_longer_than_column_is_rejected(self):
        with pytest.raises(PydanticValidationError):
            CategoryUpdate(name="x" * 101)

    def test_name_and_description_are_trimmed(self):
        body = CategoryUpdate(name="  Safety  ", description="  New  ")
        assert (body.name, body.description) == ("Safety", "New")

    @pytest.mark.parametrize("description", [None, "", "   "])
    def test_blank_description_clears_it(self, description):
        body = CategoryUpdate(description=description)
        assert body.model_fields_set == {"description"} and body.description is None


class TestSubCategoryUpdateSchema:
    def test_empty_body_is_rejected(self):
        with pytest.raises(PydanticValidationError, match="At least one"):
            SubCategoryUpdate()

    @pytest.mark.parametrize("name", ["", "   ", None])
    def test_blank_or_null_name_is_rejected(self, name):
        with pytest.raises(PydanticValidationError, match="Sub-Category Name"):
            SubCategoryUpdate(name=name)

    def test_null_category_is_rejected(self):
        with pytest.raises(PydanticValidationError, match="category_id cannot be null"):
            SubCategoryUpdate(category_id=None)

    @pytest.mark.parametrize("category_id", [0, -1, True, "3", 2_147_483_648])
    def test_category_id_must_be_a_valid_integer(self, category_id):
        with pytest.raises(PydanticValidationError):
            SubCategoryUpdate(category_id=category_id)

    def test_name_longer_than_column_is_rejected(self):
        with pytest.raises(PydanticValidationError):
            SubCategoryUpdate(name="x" * 101)


# ── Category service ─────────────────────────────────────────────────────────


@pytest.mark.asyncio
class TestUpdateCategoryService:
    async def test_renames_and_sets_audit_fields(self):
        row = _category()
        session = _session(row, results=[_MISSING])
        item = await category_service.update_category(
            session, 1, CategoryUpdate(name="Safety"), updated_by="42"
        )
        session.get.assert_awaited_once_with(Category, 1, with_for_update=True)
        assert (row.name, row.description, row.updated_by) == ("Safety", "Keep", "42")
        assert row.updated_at is not None
        session.commit.assert_awaited_once()
        assert item == CategoryItem(id=1, name="Safety", description="Keep", is_active=True)

    async def test_description_only_skips_the_name_check(self):
        row = _category()
        session = _session(row)
        await category_service.update_category(session, 1, CategoryUpdate(description=None))
        session.execute.assert_not_awaited()
        assert (row.name, row.description) == ("Security & Privacy", None)

    async def test_duplicate_check_is_case_insensitive_and_skips_itself(self):
        session = _session(_category(), results=[_MISSING])
        await category_service.update_category(session, 1, CategoryUpdate(name="Safety"))
        sql = str(session.execute.await_args.args[0].compile(compile_kwargs={"literal_binds": True}))
        assert "lower(category.name) = lower('Safety')" in sql
        assert "category.id != 1" in sql

    async def test_name_taken_in_another_case_is_a_conflict(self):
        row = _category()
        session = _session(row, results=[_FOUND])
        with pytest.raises(DuplicateEntityError):
            await category_service.update_category(session, 1, CategoryUpdate(name="pii"))
        session.commit.assert_not_awaited()
        session.rollback.assert_awaited_once()
        assert row.name == "Security & Privacy"

    async def test_integrity_error_on_commit_is_a_duplicate(self):
        session = _session(
            _category(), results=[_MISSING],
            commit_side_effect=_integrity_error("uq_category_name_lower"),
        )
        with pytest.raises(DuplicateEntityError):
            await category_service.update_category(session, 1, CategoryUpdate(name="Safety"))
        session.rollback.assert_awaited_once()

    async def test_unknown_id_is_not_found(self):
        session = _session(None)
        with pytest.raises(EntityNotFoundError):
            await category_service.update_category(session, 99, CategoryUpdate(name="X"))
        session.commit.assert_not_awaited()

    async def test_rename_recaches_policies(self, monkeypatch):
        cache = AsyncMock()
        monkeypatch.setattr(
            "app.services.policy_management.policy_cache.cache_policy", cache
        )
        policy, sub = Policy(id=7), _sub_category()
        row = _category()
        session = _session(row, results=[_MISSING, _result(rows=[(policy, sub)])])
        await category_service.update_category(
            session, 1, CategoryUpdate(name="Safety"), redis=MagicMock()
        )
        cache.assert_awaited_once()
        assert cache.await_args.kwargs == {"sub_cat": sub, "category": row}

    async def test_description_change_does_not_recache(self, monkeypatch):
        cache = AsyncMock()
        monkeypatch.setattr(
            "app.services.policy_management.policy_cache.cache_policy", cache
        )
        session = _session(_category())
        await category_service.update_category(
            session, 1, CategoryUpdate(description="New"), redis=MagicMock()
        )
        cache.assert_not_awaited()


@pytest.mark.asyncio
class TestDeleteCategoryService:
    async def test_deletes_an_empty_category(self):
        session = _session(_category(), count=0)
        await category_service.delete_category(session, 1)
        session.get.assert_awaited_once_with(Category, 1, with_for_update=True)
        sql = str(session.execute.await_args.args[0])
        assert sql.startswith("DELETE FROM category")
        session.commit.assert_awaited_once()

    @pytest.mark.parametrize("count,noun", [(1, "1 sub-category"), (3, "3 sub-categories")])
    async def test_category_with_sub_categories_is_a_conflict(self, count, noun):
        session = _session(_category(), count=count)
        with pytest.raises(AppError) as exc:
            await category_service.delete_category(session, 1)
        assert exc.value.status_code == 409
        assert noun in exc.value.message
        session.execute.assert_not_awaited()
        session.commit.assert_not_awaited()
        session.rollback.assert_awaited_once()

    async def test_sub_category_added_meanwhile_is_a_conflict(self):
        session = _session(
            _category(), count=0, commit_side_effect=_integrity_error("fk_sub_category_category_id")
        )
        with pytest.raises(AppError) as exc:
            await category_service.delete_category(session, 1)
        assert exc.value.status_code == 409
        session.rollback.assert_awaited_once()

    async def test_unknown_id_is_not_found(self):
        session = _session(None)
        with pytest.raises(EntityNotFoundError):
            await category_service.delete_category(session, 99)
        session.execute.assert_not_awaited()


# ── Sub-category service ─────────────────────────────────────────────────────


@pytest.mark.asyncio
class TestUpdateSubCategoryService:
    async def test_renames_moves_and_sets_audit_fields(self):
        row = _sub_category()
        session = _session(row, results=[_FOUND, _MISSING])
        item = await sub_category_service.update_sub_category(
            session, 3, SubCategoryUpdate(name="Toxicity", category_id=2), updated_by="42"
        )
        session.get.assert_awaited_once_with(SubCategory, 3, with_for_update=True)
        assert (row.name, row.category_id, row.description, row.updated_by) == (
            "Toxicity", 2, "Keep", "42"
        )
        assert row.updated_at is not None
        assert item == SubCategoryItem(
            id=3, name="Toxicity", description="Keep", category_id=2, is_active=True
        )

    async def test_description_only_runs_no_checks(self):
        row = _sub_category()
        session = _session(row)
        await sub_category_service.update_sub_category(
            session, 3, SubCategoryUpdate(description="New")
        )
        session.execute.assert_not_awaited()
        assert (row.name, row.category_id, row.description) == ("PII Guardrails", 1, "New")

    async def test_duplicate_check_is_case_insensitive_and_skips_itself(self):
        session = _session(_sub_category(), results=[_MISSING])
        await sub_category_service.update_sub_category(session, 3, SubCategoryUpdate(name="Toxicity"))
        sql = str(session.execute.await_args.args[0].compile(compile_kwargs={"literal_binds": True}))
        assert "lower(sub_category.name) = lower('Toxicity')" in sql
        assert "sub_category.id != 3" in sql

    async def test_name_taken_is_a_conflict(self):
        row = _sub_category()
        session = _session(row, results=[_FOUND])
        with pytest.raises(DuplicateEntityError):
            await sub_category_service.update_sub_category(session, 3, SubCategoryUpdate(name="toxicity"))
        session.commit.assert_not_awaited()
        session.rollback.assert_awaited_once()
        assert row.name == "PII Guardrails"

    async def test_move_to_missing_category_is_not_found(self):
        row = _sub_category()
        session = _session(row, results=[_MISSING])
        with pytest.raises(EntityNotFoundError, match="Category 42"):
            await sub_category_service.update_sub_category(session, 3, SubCategoryUpdate(category_id=42))
        session.commit.assert_not_awaited()
        session.rollback.assert_awaited_once()
        assert row.category_id == 1

    @pytest.mark.parametrize(
        "constraint,error",
        [
            ("uq_sub_category_name_lower", DuplicateEntityError),
            ("fk_sub_category_category_id", EntityNotFoundError),
            ("some_other_constraint", IntegrityError),
        ],
    )
    async def test_integrity_errors_on_commit(self, constraint, error):
        session = _session(
            _sub_category(), results=[_FOUND, _MISSING],
            commit_side_effect=_integrity_error(constraint),
        )
        with pytest.raises(error):
            await sub_category_service.update_sub_category(
                session, 3, SubCategoryUpdate(name="Toxicity", category_id=2)
            )
        session.rollback.assert_awaited_once()

    async def test_unknown_id_is_not_found(self):
        session = _session(None)
        with pytest.raises(EntityNotFoundError):
            await sub_category_service.update_sub_category(session, 99, SubCategoryUpdate(name="X"))

    async def test_move_recaches_policies_with_the_new_category(self, monkeypatch):
        cache = AsyncMock()
        monkeypatch.setattr(
            "app.services.policy_management.policy_cache.cache_policy", cache
        )
        row, new_parent, policy = _sub_category(), Category(id=2, name="Safety"), Policy(id=7)
        session = _session(row, new_parent, results=[_FOUND, _result(rows=[policy])])
        await sub_category_service.update_sub_category(
            session, 3, SubCategoryUpdate(category_id=2), redis=MagicMock()
        )
        assert session.get.await_args_list[1].args == (Category, 2)
        cache.assert_awaited_once()
        assert cache.await_args.args[0] is policy
        assert cache.await_args.kwargs == {"sub_cat": row, "category": new_parent}


@pytest.mark.asyncio
class TestDeleteSubCategoryService:
    async def test_deletes_an_unused_sub_category(self):
        session = _session(_sub_category(), count=0)
        await sub_category_service.delete_sub_category(session, 3)
        session.get.assert_awaited_once_with(SubCategory, 3, with_for_update=True)
        sql = str(session.execute.await_args.args[0])
        assert sql.startswith("DELETE FROM sub_category")
        session.commit.assert_awaited_once()

    @pytest.mark.parametrize("count,noun", [(1, "1 policy"), (4, "4 policies")])
    async def test_sub_category_with_policies_is_a_conflict(self, count, noun):
        session = _session(_sub_category(), count=count)
        with pytest.raises(AppError) as exc:
            await sub_category_service.delete_sub_category(session, 3)
        assert exc.value.status_code == 409
        assert noun in exc.value.message
        session.execute.assert_not_awaited()
        session.commit.assert_not_awaited()

    async def test_policy_added_meanwhile_is_a_conflict(self):
        session = _session(
            _sub_category(), count=0, commit_side_effect=_integrity_error("fk_policy_sub_category_id")
        )
        with pytest.raises(AppError) as exc:
            await sub_category_service.delete_sub_category(session, 3)
        assert exc.value.status_code == 409

    async def test_unknown_id_is_not_found(self):
        session = _session(None)
        with pytest.raises(EntityNotFoundError):
            await sub_category_service.delete_sub_category(session, 99)


# ── Routes ───────────────────────────────────────────────────────────────────


_ROUTES = [
    ("update_category", "category_service", "update_category", "category_id",
     lambda: CategoryUpdate(name="Safety")),
    ("update_sub_category", "sub_category_service", "update_sub_category", "sub_category_id",
     lambda: SubCategoryUpdate(name="Toxicity")),
    ("delete_category", "category_service", "delete_category", "category_id", None),
    ("delete_sub_category", "sub_category_service", "delete_sub_category", "sub_category_id", None),
]


def _call(route, id_param, payload, request):
    kwargs = {"request": request, id_param: 1, "session": MagicMock()}
    if payload is not None:
        kwargs.update(payload=payload(), redis=MagicMock())
    return getattr(_policy_routes, route)(**kwargs)


@pytest.mark.asyncio
class TestRoutes:
    async def test_update_category_returns_the_item_with_a_message(self, monkeypatch):
        stub = AsyncMock(return_value=CategoryItem(id=1, name="Safety", is_active=True))
        monkeypatch.setattr(_policy_routes.category_service, "update_category", stub)
        resp = await _call("update_category", "category_id", _ROUTES[0][4], _request())
        assert stub.await_args.kwargs["updated_by"] == "42"
        assert resp.meta.message == "Category 'Safety' updated."

    async def test_update_sub_category_returns_the_item_with_a_message(self, monkeypatch):
        stub = AsyncMock(
            return_value=SubCategoryItem(id=1, name="Toxicity", category_id=2, is_active=True)
        )
        monkeypatch.setattr(_policy_routes.sub_category_service, "update_sub_category", stub)
        resp = await _call("update_sub_category", "sub_category_id", _ROUTES[1][4], _request())
        assert stub.await_args.kwargs["updated_by"] == "42"
        assert resp.data.category_id == 2
        assert resp.meta.message == "Sub-category 'Toxicity' updated."

    @pytest.mark.parametrize("route,module,fn,id_param", [r[:4] for r in _ROUTES[2:]])
    async def test_delete_returns_204(self, monkeypatch, route, module, fn, id_param):
        stub = AsyncMock()
        monkeypatch.setattr(getattr(_policy_routes, module), fn, stub)
        resp = await _call(route, id_param, None, _request())
        stub.assert_awaited_once()
        assert resp.status_code == 204 and resp.body == b""

    @pytest.mark.parametrize("route,module,fn,id_param,payload", _ROUTES)
    async def test_non_admin_is_rejected(self, monkeypatch, route, module, fn, id_param, payload):
        stub = AsyncMock()
        monkeypatch.setattr(getattr(_policy_routes, module), fn, stub)
        with pytest.raises(InsufficientPermissionsError):
            await _call(route, id_param, payload, _request(is_admin=False))
        stub.assert_not_awaited()


class TestRouteShape:
    @pytest.mark.parametrize("path", ["/policies/categories/{category_id}",
                                      "/policies/sub-categories/{sub_category_id}"])
    def test_patch_and_delete_are_registered(self, path):
        routes = {(r.path, m) for r in _policy_routes.router.routes for m in r.methods}
        assert {(path, "PATCH"), (path, "DELETE")} <= routes

    @pytest.mark.parametrize("path", ["/policies/categories/{category_id}",
                                      "/policies/sub-categories/{sub_category_id}"])
    def test_delete_returns_204_and_documents_errors(self, path):
        route = next(
            r for r in _policy_routes.router.routes if r.path == path and "DELETE" in r.methods
        )
        assert route.status_code == 204
        assert {403, 404, 409} <= set(route.responses)
