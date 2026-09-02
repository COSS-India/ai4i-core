"""app/services/pay_per_use/inference_type_service.py — catalogue CRUD.

Three things here are load-bearing and would fail quietly if broken:

**The response projection.** The table stores ``endpoint_patterns TEXT[]``, but
the wire shape is a scalar ``endpoint_pattern`` plus optional
``endpoint_aliases``. The frontend validates with zod
(``inferenceTypesService.ts`` declares ``endpoint_pattern: z.string()``,
required), so returning an array — or null — fails validation at runtime rather
than degrading. auth-service reads the same two fields.

**The referential guard.** Deleting or renaming a type that tier quotas or usage
rows still point at orphans them. The guard checks ``inference_name`` as well as
``inference_type_id``, because a row predating the backfill references the type
by string only and would otherwise slip straight past it.

**Cache rebuild after every mutation.** The DB commits first and the cache is
rebuilt second, with ``sweep=True`` — without the sweep a renamed or deleted
type leaves a per-name key still answering lookups.

No database — the session is faked.
"""

from __future__ import annotations

from unittest.mock import AsyncMock, MagicMock

import pytest
from fastapi import HTTPException
from sqlalchemy.exc import IntegrityError

from app.schemas.inference_types import InferenceTypeCreate, InferenceTypeUpdate
from app.services.pay_per_use import inference_type_service as svc


# ── fakes ────────────────────────────────────────────────────────────────────


def _row(id=2, name="asr", patterns=None, unit="audio_minutes", pricing="per_minute"):
    r = MagicMock()
    r.id = id
    r.name = name
    r.endpoint_patterns = ["/api/v1/asr/inference"] if patterns is None else patterns
    r.unit = unit
    r.pricing = pricing
    return r


class _Session:
    """Fake AsyncSession.

    ``found`` is the row a SELECT resolves to. ``referencing`` names the tables
    whose reference-check query should come back non-empty.
    """

    def __init__(self, found=None, referencing=(), commit_error=None):
        self.found = found
        self.referencing = set(referencing)
        self.commit_error = commit_error
        self.added, self.deleted = [], []
        self.commits = self.rollbacks = 0
        self._select_calls = 0

    async def execute(self, stmt):
        compiled = str(stmt)
        result = MagicMock()
        if "tier_quotas" in compiled or "quota_usage" in compiled:
            table = "tier_quotas" if "tier_quotas" in compiled else "quota_usage"
            result.first.return_value = (1,) if table in self.referencing else None
            return result
        self._select_calls += 1
        result.scalar_one_or_none.return_value = self.found
        return result

    def add(self, row):
        self.added.append(row)

    async def delete(self, row):
        self.deleted.append(row)

    async def commit(self):
        if self.commit_error is not None:
            raise self.commit_error
        self.commits += 1

    async def rollback(self):
        self.rollbacks += 1

    async def refresh(self, row):
        # A real refresh loads server-generated values back onto the instance.
        # id is a SERIAL, so it is None until the INSERT has been flushed.
        if getattr(row, "id", None) is None:
            row.id = 99


@pytest.fixture
def rebuilds(monkeypatch):
    """Capture every cache rebuild the service performs."""
    calls = []

    async def _rebuild(session, *, sweep=False):
        calls.append({"sweep": sweep})
        return []

    monkeypatch.setattr(svc.inference_type_cache, "rebuild", _rebuild)
    return calls


def _integrity_error():
    return IntegrityError("INSERT ...", {}, Exception("duplicate key"))


# ── the wire shape the frontend and auth-service depend on ───────────────────


class TestResponseProjection:
    def test_first_pattern_is_the_scalar_endpoint(self):
        item = svc._to_item(
            {"id": 1, "name": "llm", "unit": "tokens", "pricing": "per_million_tokens",
             "endpoint_patterns": ["/api/v1/chat", "/api/v1/chat/completions"]}
        )
        assert item.endpoint_pattern == "/api/v1/chat"

    def test_remaining_patterns_become_aliases(self):
        item = svc._to_item(
            {"id": 1, "name": "llm", "unit": "tokens", "pricing": "per_million_tokens",
             "endpoint_patterns": ["/api/v1/chat", "/api/v1/chat/completions"]}
        )
        assert item.endpoint_aliases == ["/api/v1/chat/completions"]

    def test_single_pattern_has_no_aliases(self):
        item = svc._to_item(
            {"id": 2, "name": "asr", "unit": "audio_minutes", "pricing": "per_minute",
             "endpoint_patterns": ["/api/v1/asr/inference"]}
        )
        assert item.endpoint_aliases is None

    def test_endpoint_pattern_is_a_string_even_with_no_patterns(self):
        # zod declares it required and non-null; None would fail validation in
        # the browser rather than degrade.
        item = svc._to_item(
            {"id": 3, "name": "x", "unit": "u", "pricing": "p", "endpoint_patterns": []}
        )
        assert item.endpoint_pattern == ""

    def test_it_is_never_an_array(self):
        item = svc._to_item(
            {"id": 1, "name": "llm", "unit": "tokens", "pricing": "per_million_tokens",
             "endpoint_patterns": ["/api/v1/chat", "/api/v1/chat/completions"]}
        )
        assert isinstance(item.endpoint_pattern, str)


# ── reads ────────────────────────────────────────────────────────────────────


@pytest.mark.asyncio
class TestReads:
    async def test_list_projects_every_entry(self, monkeypatch):
        monkeypatch.setattr(
            svc.inference_type_cache, "get_all",
            AsyncMock(return_value=[
                {"id": 2, "name": "asr", "unit": "audio_minutes",
                 "pricing": "per_minute", "endpoint_patterns": ["/api/v1/asr/inference"]},
            ]),
        )
        items = await svc.list_inference_types(_Session())
        assert [i.name for i in items] == ["asr"]
        assert items[0].endpoint_pattern == "/api/v1/asr/inference"

    async def test_get_returns_the_item(self, monkeypatch):
        monkeypatch.setattr(
            svc.inference_type_cache, "get_by_name",
            AsyncMock(return_value={
                "id": 2, "name": "asr", "unit": "audio_minutes",
                "pricing": "per_minute", "endpoint_patterns": ["/api/v1/asr/inference"]}),
        )
        assert (await svc.get_inference_type(_Session(), "asr")).id == 2

    async def test_get_unknown_is_404(self, monkeypatch):
        monkeypatch.setattr(
            svc.inference_type_cache, "get_by_name", AsyncMock(return_value=None)
        )
        with pytest.raises(HTTPException) as exc:
            await svc.get_inference_type(_Session(), "nope")
        assert exc.value.status_code == 404


# ── create ───────────────────────────────────────────────────────────────────


@pytest.mark.asyncio
class TestCreate:
    _BODY = InferenceTypeCreate(
        name="vad", endpoint_patterns=["/api/v1/vad/inference"],
        unit="audio_minutes", pricing="per_minute",
    )

    async def test_persists_the_row(self, rebuilds):
        session = _Session()
        await svc.create_inference_type(self._BODY, session, created_by="u1")
        assert len(session.added) == 1 and session.commits == 1

    async def test_stamps_the_caller(self, rebuilds):
        session = _Session()
        await svc.create_inference_type(self._BODY, session, created_by="u1")
        row = session.added[0]
        assert row.created_by == "u1" and row.updated_by == "u1"

    async def test_returns_the_projected_item(self, rebuilds):
        item = await svc.create_inference_type(self._BODY, _Session())
        assert item.name == "vad" and item.endpoint_pattern == "/api/v1/vad/inference"

    async def test_duplicate_name_is_409_not_500(self, rebuilds):
        session = _Session(commit_error=_integrity_error())
        with pytest.raises(HTTPException) as exc:
            await svc.create_inference_type(self._BODY, session)
        assert exc.value.status_code == 409

    async def test_duplicate_rolls_back(self, rebuilds):
        session = _Session(commit_error=_integrity_error())
        with pytest.raises(HTTPException):
            await svc.create_inference_type(self._BODY, session)
        assert session.rollbacks == 1

    async def test_rebuilds_the_cache_with_sweep(self, rebuilds):
        await svc.create_inference_type(self._BODY, _Session())
        assert rebuilds == [{"sweep": True}]

    async def test_no_rebuild_when_the_write_failed(self, rebuilds):
        # The cache must never advertise a type the DB rejected.
        with pytest.raises(HTTPException):
            await svc.create_inference_type(self._BODY, _Session(commit_error=_integrity_error()))
        assert rebuilds == []


# ── update, and the rename guard ─────────────────────────────────────────────


@pytest.mark.asyncio
class TestUpdate:
    async def test_unknown_name_is_404(self, rebuilds):
        with pytest.raises(HTTPException) as exc:
            await svc.update_inference_type("nope", InferenceTypeUpdate(unit="x"), _Session(found=None))
        assert exc.value.status_code == 404

    async def test_lookup_is_case_insensitive(self, rebuilds):
        session = _Session(found=_row())
        await svc.update_inference_type("ASR", InferenceTypeUpdate(unit="x"), session)
        assert session.commits == 1

    async def test_updates_only_the_fields_supplied(self, rebuilds):
        row = _row(unit="audio_minutes", pricing="per_minute")
        await svc.update_inference_type("asr", InferenceTypeUpdate(unit="seconds"), _Session(found=row))
        assert row.unit == "seconds"
        assert row.pricing == "per_minute", "an omitted field must not be cleared"

    async def test_patterns_can_be_replaced(self, rebuilds):
        row = _row()
        await svc.update_inference_type(
            "asr", InferenceTypeUpdate(endpoint_patterns=["/a", "/b"]), _Session(found=row)
        )
        assert row.endpoint_patterns == ["/a", "/b"]

    async def test_stamps_the_caller(self, rebuilds):
        row = _row()
        await svc.update_inference_type(
            "asr", InferenceTypeUpdate(unit="x"), _Session(found=row), updated_by="u2"
        )
        assert row.updated_by == "u2"

    async def test_rename_of_an_unreferenced_type_is_allowed(self, rebuilds):
        row = _row()
        await svc.update_inference_type("asr", InferenceTypeUpdate(name="asr2"), _Session(found=row))
        assert row.name == "asr2"

    async def test_rename_is_blocked_while_referenced(self, rebuilds):
        # A rename orphans every row still matching by string, so it is guarded
        # exactly like a delete.
        session = _Session(found=_row(), referencing={"tier_quotas"})
        with pytest.raises(HTTPException) as exc:
            await svc.update_inference_type("asr", InferenceTypeUpdate(name="asr2"), session)
        assert exc.value.status_code == 409
        assert "tier_quotas" in exc.value.detail

    async def test_a_referenced_type_can_still_change_its_unit(self, rebuilds):
        # Only the name is dangerous; the guard must not block everything else.
        row = _row()
        session = _Session(found=row, referencing={"tier_quotas"})
        await svc.update_inference_type("asr", InferenceTypeUpdate(unit="seconds"), session)
        assert row.unit == "seconds"

    async def test_renaming_to_the_same_name_is_not_treated_as_a_rename(self, rebuilds):
        session = _Session(found=_row(name="asr"), referencing={"tier_quotas"})
        await svc.update_inference_type("asr", InferenceTypeUpdate(name="asr"), session)
        assert session.commits == 1

    async def test_rebuilds_the_cache_with_sweep(self, rebuilds):
        # Without the sweep, a rename leaves the old per-name key answering.
        await svc.update_inference_type("asr", InferenceTypeUpdate(unit="x"), _Session(found=_row()))
        assert rebuilds == [{"sweep": True}]

    async def test_duplicate_new_name_is_409(self, rebuilds):
        session = _Session(found=_row(), commit_error=_integrity_error())
        with pytest.raises(HTTPException) as exc:
            await svc.update_inference_type("asr", InferenceTypeUpdate(unit="x"), session)
        assert exc.value.status_code == 409 and session.rollbacks == 1


# ── delete, and the referential guard ────────────────────────────────────────


@pytest.mark.asyncio
class TestDelete:
    async def test_unknown_name_is_404(self, rebuilds):
        with pytest.raises(HTTPException) as exc:
            await svc.delete_inference_type("nope", _Session(found=None))
        assert exc.value.status_code == 404

    async def test_unreferenced_type_is_removed(self, rebuilds):
        row = _row()
        session = _Session(found=row)
        await svc.delete_inference_type("asr", session)
        assert session.deleted == [row] and session.commits == 1

    async def test_blocked_by_tier_quotas(self, rebuilds):
        session = _Session(found=_row(), referencing={"tier_quotas"})
        with pytest.raises(HTTPException) as exc:
            await svc.delete_inference_type("asr", session)
        assert exc.value.status_code == 409
        assert "tier_quotas" in exc.value.detail

    async def test_blocked_by_quota_usage(self, rebuilds):
        session = _Session(found=_row(), referencing={"quota_usage"})
        with pytest.raises(HTTPException) as exc:
            await svc.delete_inference_type("asr", session)
        assert "quota_usage" in exc.value.detail

    async def test_names_every_referencing_table(self, rebuilds):
        session = _Session(found=_row(), referencing={"tier_quotas", "quota_usage"})
        with pytest.raises(HTTPException) as exc:
            await svc.delete_inference_type("asr", session)
        assert "tier_quotas" in exc.value.detail and "quota_usage" in exc.value.detail

    async def test_a_blocked_delete_removes_nothing(self, rebuilds):
        session = _Session(found=_row(), referencing={"tier_quotas"})
        with pytest.raises(HTTPException):
            await svc.delete_inference_type("asr", session)
        assert session.deleted == [] and session.commits == 0


@pytest.mark.asyncio
class TestReferentialGuard:
    """The guard checks the legacy name column as well as the FK.

    quota_usage keeps nullable ids for rows written before the catalogue
    existed. Those reference their type by string only, so a guard that looked
    at inference_type_id alone would let a delete orphan them.
    """

    async def test_checks_both_tables(self):
        session = _Session()
        captured = []
        original = session.execute

        async def _spy(stmt):
            captured.append(str(stmt))
            return await original(stmt)

        session.execute = _spy
        await svc._referencing_tables(session, 2, "asr")
        assert any("tier_quotas" in c for c in captured)
        assert any("quota_usage" in c for c in captured)

    async def test_matches_on_the_name_as_well_as_the_id(self):
        session = _Session()
        captured = []

        async def _spy(stmt):
            captured.append(str(stmt))
            result = MagicMock()
            result.first.return_value = None
            return result

        session.execute = _spy
        await svc._referencing_tables(session, 2, "asr")
        joined = " ".join(captured)
        assert "inference_type_id" in joined
        assert "inference_name" in joined, (
            "a pre-catalogue row references its type by string only"
        )
        assert "lower(" in joined.lower(), "the name comparison must be case-insensitive"

    async def test_clean_type_reports_no_tables(self):
        assert await svc._referencing_tables(_Session(), 2, "asr") == []
