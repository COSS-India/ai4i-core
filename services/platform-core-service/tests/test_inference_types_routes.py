"""app/routes/inference_types.py — the catalogue CRUD surface.

The service layer is covered in test_inference_type_service.py. What is left to
pin here is the wiring, which is exactly what a refactor drops silently:

* the envelope shape — the frontend unwraps ``data.inference_types``, so a
  response nested one level differently returns an empty list rather than an
  error;
* the status codes — 201 on create and a bodyless 204 on delete are declared on
  the decorators, not in the service, so they are only true if the route says so;
* ``X-User-Id`` reaching ``created_by``/``updated_by``, which nothing downstream
  would notice going missing until an audit column came back empty;
* HTTPExceptions from the service propagating untouched, rather than being
  swallowed into a 200.

Route modules are loaded by file path because ``app/routes/__init__.py`` eagerly
imports every route plus ``ai4i_core.bootstrap.versioning``, which this suite's
conftest does not stub — the same approach test_service_rbac_filtering.py takes.
"""

from __future__ import annotations

import importlib.util
import sys
from unittest.mock import AsyncMock, MagicMock

import pytest
from fastapi import HTTPException, status

from app.schemas.inference_types import (
    InferenceTypeCreate,
    InferenceTypeItem,
    InferenceTypeUpdate,
)

_spec = importlib.util.spec_from_file_location(
    "app.routes.inference_types", "app/routes/inference_types.py"
)
_routes = importlib.util.module_from_spec(_spec)
sys.modules["app.routes.inference_types"] = _routes
_spec.loader.exec_module(_routes)


def _item(name="asr", id=2, patterns=("/api/v1/asr/inference",)) -> InferenceTypeItem:
    return InferenceTypeItem(
        id=id,
        name=name,
        endpoint_pattern=patterns[0],
        endpoint_aliases=list(patterns[1:]) or None,
        unit="audio_minutes",
        pricing="per_minute",
    )


def _request(user_id: str | None = "u1") -> MagicMock:
    request = MagicMock()
    request.headers = {"X-User-Id": user_id} if user_id is not None else {}
    return request


@pytest.fixture
def service(monkeypatch):
    """Stub the whole service layer; these tests are about the wiring."""
    stub = MagicMock()
    stub.list_inference_types = AsyncMock(return_value=[_item()])
    stub.get_inference_type = AsyncMock(return_value=_item())
    stub.create_inference_type = AsyncMock(return_value=_item(name="vad", id=13))
    stub.update_inference_type = AsyncMock(return_value=_item())
    stub.delete_inference_type = AsyncMock(return_value=None)
    monkeypatch.setattr(_routes, "inference_type_service", stub)
    return stub


_SESSION = MagicMock()


@pytest.mark.asyncio
class TestList:
    async def test_wraps_items_in_the_envelope_the_frontend_unwraps(self, service):
        # inferenceTypesService.ts reads data.inference_types; anything else
        # deserialises to an empty list instead of failing loudly.
        resp = await _routes.list_inference_types(session=_SESSION)
        assert resp.success is True
        assert [i.name for i in resp.data.inference_types] == ["asr"]

    async def test_empty_catalogue_is_an_empty_list_not_an_error(self, service):
        service.list_inference_types = AsyncMock(return_value=[])
        resp = await _routes.list_inference_types(session=_SESSION)
        assert resp.data.inference_types == []

    async def test_endpoint_pattern_stays_a_string_on_the_wire(self, service):
        service.list_inference_types = AsyncMock(
            return_value=[_item("llm", 1, ("/api/v1/chat", "/api/v1/chat/completions"))]
        )
        resp = await _routes.list_inference_types(session=_SESSION)
        item = resp.data.inference_types[0]
        assert isinstance(item.endpoint_pattern, str)
        assert item.endpoint_aliases == ["/api/v1/chat/completions"]


@pytest.mark.asyncio
class TestGet:
    async def test_returns_the_item(self, service):
        resp = await _routes.get_inference_type(name="asr", session=_SESSION)
        assert resp.success is True and resp.data.name == "asr"

    async def test_passes_the_name_through_unchanged(self, service):
        # Normalisation is the service's job, not the route's — the route must
        # not lowercase it and hide a bug there.
        await _routes.get_inference_type(name="ASR", session=_SESSION)
        assert service.get_inference_type.await_args.args[1] == "ASR"

    async def test_404_propagates(self, service):
        service.get_inference_type = AsyncMock(
            side_effect=HTTPException(status_code=404, detail="not found")
        )
        with pytest.raises(HTTPException) as exc:
            await _routes.get_inference_type(name="nope", session=_SESSION)
        assert exc.value.status_code == 404


@pytest.mark.asyncio
class TestCreate:
    _BODY = InferenceTypeCreate(
        name="vad", endpoint_patterns=["/api/v1/vad/inference"],
        unit="audio_minutes", pricing="per_minute",
    )

    async def test_declares_201(self):
        # Asserted off the route table rather than the return value: the status
        # lives on the decorator, so only the app knows about it.
        route = next(r for r in _routes.router.routes
                     if r.path == "/inference-types" and "POST" in r.methods)
        assert route.status_code == status.HTTP_201_CREATED

    async def test_returns_the_created_item(self, service):
        resp = await _routes.create_inference_type(
            request=_request(), body=self._BODY, session=_SESSION
        )
        assert resp.success is True and resp.data.name == "vad"

    async def test_stamps_created_by_from_the_identity_header(self, service):
        await _routes.create_inference_type(
            request=_request("alice"), body=self._BODY, session=_SESSION
        )
        assert service.create_inference_type.await_args.kwargs["created_by"] == "alice"

    async def test_missing_identity_header_is_none_not_a_crash(self, service):
        # Downstream services trust gateway headers, but the route must not 500
        # if one is absent.
        await _routes.create_inference_type(
            request=_request(None), body=self._BODY, session=_SESSION
        )
        assert service.create_inference_type.await_args.kwargs["created_by"] is None

    async def test_409_propagates(self, service):
        service.create_inference_type = AsyncMock(
            side_effect=HTTPException(status_code=409, detail="already exists")
        )
        with pytest.raises(HTTPException) as exc:
            await _routes.create_inference_type(
                request=_request(), body=self._BODY, session=_SESSION
            )
        assert exc.value.status_code == 409


@pytest.mark.asyncio
class TestUpdate:
    async def test_forwards_name_and_body(self, service):
        body = InferenceTypeUpdate(unit="seconds")
        await _routes.update_inference_type(
            request=_request(), name="asr", body=body, session=_SESSION
        )
        args = service.update_inference_type.await_args.args
        assert args[0] == "asr" and args[1] is body

    async def test_stamps_updated_by_from_the_identity_header(self, service):
        await _routes.update_inference_type(
            request=_request("bob"), name="asr",
            body=InferenceTypeUpdate(unit="seconds"), session=_SESSION,
        )
        assert service.update_inference_type.await_args.kwargs["updated_by"] == "bob"

    async def test_rename_conflict_propagates_as_409(self, service):
        service.update_inference_type = AsyncMock(
            side_effect=HTTPException(status_code=409, detail="referenced by tier_quotas")
        )
        with pytest.raises(HTTPException) as exc:
            await _routes.update_inference_type(
                request=_request(), name="asr",
                body=InferenceTypeUpdate(name="asr2"), session=_SESSION,
            )
        assert exc.value.status_code == 409


@pytest.mark.asyncio
class TestDelete:
    async def test_returns_204_with_no_body(self, service):
        resp = await _routes.delete_inference_type(name="asr", session=_SESSION)
        assert resp.status_code == status.HTTP_204_NO_CONTENT
        assert resp.body == b"", "204 must not carry a body"

    async def test_calls_the_service(self, service):
        await _routes.delete_inference_type(name="asr", session=_SESSION)
        assert service.delete_inference_type.await_args.args[0] == "asr"

    async def test_409_propagates_and_returns_no_response(self, service):
        # A blocked delete must surface the conflict, not a bodyless 204 that
        # reads as success.
        service.delete_inference_type = AsyncMock(
            side_effect=HTTPException(status_code=409, detail="referenced by quota_usage")
        )
        with pytest.raises(HTTPException) as exc:
            await _routes.delete_inference_type(name="asr", session=_SESSION)
        assert exc.value.status_code == 409
        assert "quota_usage" in exc.value.detail

    async def test_declares_409_in_its_openapi_responses(self):
        # The 409 is a documented outcome of this endpoint, not an incident.
        route = next(r for r in _routes.router.routes
                     if r.path == "/inference-types/{name}" and "DELETE" in r.methods)
        assert 409 in route.responses


class TestRouterShape:
    """The mounted paths are part of the public contract."""

    def test_prefix(self):
        assert _routes.router.prefix == "/inference-types"

    def test_every_verb_is_mounted(self):
        # APIRouter records paths with the prefix already applied.
        mounted = {(r.path, verb) for r in _routes.router.routes for verb in r.methods}
        assert ("/inference-types", "GET") in mounted
        assert ("/inference-types", "POST") in mounted
        assert ("/inference-types/{name}", "GET") in mounted
        assert ("/inference-types/{name}", "PUT") in mounted
        assert ("/inference-types/{name}", "DELETE") in mounted
