"""
Shared pytest configuration for platform-core-service unit tests.

CoreSettings is instantiated at module import time (config.py:173), so env vars
must be set here at module level — before pytest imports any test module. An
autouse fixture would run too late (after imports) and cause a ValidationError
during collection.
"""

import os
import sys
import time
import types
from unittest.mock import MagicMock

# Ensure the local app/ package (platform-core-service/app/) is found before
# any installed 'app' package in site-packages (e.g. an old Flask app stub).
_SERVICE_ROOT = os.path.dirname(os.path.dirname(os.path.abspath(__file__)))
if _SERVICE_ROOT not in sys.path:
    sys.path.insert(0, _SERVICE_ROOT)

from pydantic import BaseModel as _PydanticBaseModel, ConfigDict as _ConfigDict

os.environ.setdefault("SERVICE_NAME", "platform-core-service")
os.environ.setdefault("SERVICE_VERSION", "0.0.0-test")
os.environ.setdefault("API_VERSION", "v1")
os.environ.setdefault("NER_SERVICE_URL", "http://localhost:9001")
os.environ.setdefault("PII_LLM_URL", "http://localhost:9002")
os.environ.setdefault("REDIS_HOST", "localhost")
os.environ.setdefault("REDIS_PORT", "6379")


def _conftest_stub(name: str, **attrs) -> types.ModuleType:
    mod = types.ModuleType(name)
    for k, v in attrs.items():
        setattr(mod, k, v)
    sys.modules.setdefault(name, mod)
    return mod


# Stub app.schemas.base with a real Pydantic BaseModel subclass.
# This prevents test modules from pulling in ai4i_core.bootstrap (which
# needs a live sqlalchemy engine) just to get BaseSchema.
class _BaseSchema(_PydanticBaseModel):
    model_config = _ConfigDict(from_attributes=True, populate_by_name=True)


_conftest_stub("app.schemas.base", BaseSchema=_BaseSchema)

# Stub ai4i_core so services that re-export shared exceptions can be imported
# without installing the full ai4i-core package.
class _AppError(Exception):
    def __init__(self, message: str = "", code: str = "APP_ERROR", status_code: int = 400, **_):
        super().__init__(message)
        self.message = message
        self.code = code
        self.status_code = status_code

class _EntityNotFoundError(_AppError): pass
class _DuplicateEntityError(_AppError): pass
class _ValidationError(_AppError): pass
class _InsufficientPermissionsError(_AppError): pass
class _ServiceError(_AppError): pass
class _ModelNotFoundError(_AppError): pass
class _ServiceUnavailableError(_AppError): pass
class _UnpublishedServiceError(_AppError): pass
class _RateLimitExceededError(_AppError): pass


# app.schemas.common builds its ErrorResponse envelope on top of this — mirrors
# the real ai4i_core.exceptions.ErrorDetail (code/timestamp optional & defaulted).
class _ErrorDetail(_PydanticBaseModel):
    message: str
    code: str | None = None
    timestamp: float = 0.0
    details: str | None = None

    def __init__(self, **data):
        if data.get("timestamp") is None:
            data["timestamp"] = time.time()
        super().__init__(**data)

def _success_response(data=None, meta=None):
    resp = {"success": True, "data": data}
    if meta:
        resp["meta"] = meta
    return resp


def _error_response(code, message, details=None):
    err = {"code": code, "message": message}
    if details:
        err["details"] = details
    return {"success": False, "error": err}


_ai4i_exc = _conftest_stub(
    "ai4i_core.exceptions",
    AppError=_AppError,
    EntityNotFoundError=_EntityNotFoundError,
    DuplicateEntityError=_DuplicateEntityError,
    ValidationError=_ValidationError,
    InsufficientPermissionsError=_InsufficientPermissionsError,
    ServiceError=_ServiceError,
    ModelNotFoundError=_ModelNotFoundError,
    ServiceUnavailableError=_ServiceUnavailableError,
    UnpublishedServiceError=_UnpublishedServiceError,
    RateLimitExceededError=_RateLimitExceededError,
    ErrorDetail=_ErrorDetail,
    register_exception_handlers=MagicMock(),
    # app.core.responses re-exports these — needed by any test that loads a
    # route module directly (e.g. app/routes/model.py, app/routes/service.py).
    success_response=_success_response,
    error_response=_error_response,
)
_conftest_stub("ai4i_core", exceptions=_ai4i_exc)

# The seeded catalogue. Must mirror the seed migration
# (52eb3034332e_seed_inference_types.py) exactly — metering_service.py reads
# task-type unit labels from it (see _native_unit_suffix_for_metering_task), so
# a stub that drifts (a wrong unit, or a missing task type) silently masks a
# real bug behind a passing test. test_inference_type_catalogue_fixture.py
# asserts the two agree, which the old "must mirror the yaml" comment could
# only ask for.
_INFERENCE_TYPES = [
    {"id": 1, "name": "llm", "unit": "tokens", "pricing": "per_million_tokens",
     "endpoint_patterns": ["/api/v1/chat", "/api/v1/chat/completions"]},
    {"id": 2, "name": "asr", "unit": "audio_minutes", "pricing": "per_minute",
     "endpoint_patterns": ["/api/v1/asr/inference"]},
    {"id": 3, "name": "nmt", "unit": "characters", "pricing": "per_million_characters",
     "endpoint_patterns": ["/api/v1/nmt/inference"]},
    {"id": 4, "name": "tts", "unit": "characters", "pricing": "per_million_characters",
     "endpoint_patterns": ["/api/v1/tts/inference"]},
    {"id": 5, "name": "ner", "unit": "characters", "pricing": "per_million_characters",
     "endpoint_patterns": ["/api/v1/ner/inference"]},
    {"id": 6, "name": "ocr", "unit": "images", "pricing": "per_image",
     "endpoint_patterns": ["/api/v1/ocr/inference"]},
    {"id": 7, "name": "transliteration", "unit": "characters", "pricing": "per_million_characters",
     "endpoint_patterns": ["/api/v1/transliteration/inference"]},
    {"id": 8, "name": "language-detection", "unit": "characters", "pricing": "per_million_characters",
     "endpoint_patterns": ["/api/v1/language-detection/inference"]},
    {"id": 9, "name": "language-diarization", "unit": "audio_minutes", "pricing": "per_minute",
     "endpoint_patterns": ["/api/v1/language-diarization/inference"]},
    {"id": 10, "name": "speaker-diarization", "unit": "audio_minutes", "pricing": "per_minute",
     "endpoint_patterns": ["/api/v1/speaker-diarization/inference"]},
    {"id": 11, "name": "audio-lang-detection", "unit": "audio_minutes", "pricing": "per_minute",
     "endpoint_patterns": ["/api/v1/audio-lang-detection/inference"]},
    {"id": 12, "name": "pipeline", "unit": "requests", "pricing": "per_request",
     "endpoint_patterns": ["/api/v1/pipeline/inference"]},
]


async def _stub_get_all(*_args, **_kwargs):
    return _INFERENCE_TYPES


async def _stub_get_unit_map(*_args, **_kwargs):
    return {it["name"]: it["unit"] for it in _INFERENCE_TYPES}


_conftest_stub("ai4i_core.ppu",
    configure_catalogue=MagicMock(),
    get_catalogue=MagicMock(),
    to_legacy_entry=MagicMock(),
    load_inference_types=MagicMock(),
    quota_guard=MagicMock(),
)

# Stub app.core.database so background-task helpers (e.g. audit_service) can
# be loaded without requiring a live SQLAlchemy engine.  Tests mock the session
# factory at the service level and never call these functions directly.
_db_stub = _conftest_stub("app.core.database")
_db_stub.get_primary_session_factory = MagicMock()
_db_stub.get_auth_session_factory = MagicMock(return_value=None)
_db_stub.get_db = MagicMock()
_db_stub.get_engine = MagicMock()
# get_auth_db/get_auth_db_optional: imported by app/routes/usage.py and
# app/routes/application_usage.py — needed so those route modules can be
# loaded directly by file path (see test_application_usage_routes.py).
_db_stub.get_auth_db = MagicMock()
_db_stub.get_auth_db_optional = MagicMock()

# Stub app.dependencies.services so route modules (app/routes/model.py,
# app/routes/service.py, ...) can be loaded directly by file path without
# dragging in the full alert-management repository chain those DI factories
# pull in — tests that load a route module pass their own mock `svc` and
# never call get_model_service()/get_service_service() for real.
_deps_stub = _conftest_stub("app.dependencies.services")
_deps_stub.ModelService = MagicMock
_deps_stub.get_model_service = MagicMock()
_deps_stub.ServiceService = MagicMock
_deps_stub.get_service_service = MagicMock()
_deps_stub.get_metering_service = MagicMock()

# Stub app.core.redis (routes/metering.py's get_redis dependency) — the real
# module pulls in ai4i_core.bootstrap.redis, which isn't stubbed here.
_redis_stub = _conftest_stub("app.core.redis")
_redis_stub.get_redis = MagicMock()


# ── the inference-type catalogue, as tests see it ───────────────────────────
#
# metering_service reads unit labels through
# inference_type_cache.get_unit_map_standalone(), which opens its own session
# from the primary factory. That factory is stubbed above, so without this the
# call would fail, return {}, and every metering assertion would silently fall
# back to SERVICE_BREAKDOWN_CONFIG — the tests would still pass while covering
# none of the catalogue path they exist to cover.

import pytest  # noqa: E402


@pytest.fixture(autouse=True)
def _stub_inference_type_catalogue(monkeypatch):
    from app.services.pay_per_use import inference_type_cache

    monkeypatch.setattr(inference_type_cache, "get_all", _stub_get_all)
    monkeypatch.setattr(inference_type_cache, "get_unit_map", _stub_get_unit_map)
    monkeypatch.setattr(
        inference_type_cache, "get_unit_map_standalone", _stub_get_unit_map
    )


def test_catalogue_fixture_matches_the_seed_migration():
    """The stub above must agree with what the database is actually seeded with.

    Previously this was a comment asking whoever edited the list to keep it in
    sync with a YAML file. Now it is checkable: the seed migration is the single
    source of truth for the catalogue's initial contents.
    """
    import importlib.util
    from pathlib import Path

    seed = (
        Path(__file__).resolve().parents[3]
        / "infrastructure/databases/migrations/postgres/alembic/versions"
        / "ai4iplatform_core/52eb3034332e_seed_inference_types.py"
    )
    spec = importlib.util.spec_from_file_location("_seed", seed)
    module = importlib.util.module_from_spec(spec)
    spec.loader.exec_module(module)

    seeded = {row[0]: (list(row[1]), row[2], row[3]) for row in module._TYPES}
    stubbed = {
        it["name"]: (list(it["endpoint_patterns"]), it["unit"], it["pricing"])
        for it in _INFERENCE_TYPES
    }
    assert stubbed == seeded
