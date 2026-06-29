"""
Shared pytest configuration for platform-core-service unit tests.

CoreSettings is instantiated at module import time (config.py:173), so env vars
must be set here at module level — before pytest imports any test module. An
autouse fixture would run too late (after imports) and cause a ValidationError
during collection.
"""

import os
import sys
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
class _AppError(Exception): pass
class _EntityNotFoundError(_AppError): pass
class _DuplicateEntityError(_AppError): pass
class _ValidationError(_AppError): pass
class _InsufficientPermissionsError(_AppError): pass
class _ServiceError(_AppError): pass
class _ModelNotFoundError(_AppError): pass
class _ServiceUnavailableError(_AppError): pass
class _UnpublishedServiceError(_AppError): pass
class _RateLimitExceededError(_AppError): pass

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
    register_exception_handlers=MagicMock(),
)
_conftest_stub("ai4i_core", exceptions=_ai4i_exc)

_INFERENCE_TYPES = [
    {"name": "llm",  "unit": "tokens"},
    {"name": "asr",  "unit": "minutes"},
    {"name": "nmt",  "unit": "characters"},
    {"name": "tts",  "unit": "characters"},
    {"name": "ocr",  "unit": "characters"},
]
_conftest_stub("ai4i_core.ppu",
    get_inference_types=lambda: _INFERENCE_TYPES,
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
