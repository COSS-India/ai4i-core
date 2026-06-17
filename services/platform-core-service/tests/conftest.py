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
# This prevents test modules from pulling in ai4icore_core.bootstrap (which
# needs a live sqlalchemy engine) just to get BaseSchema.
class _BaseSchema(_PydanticBaseModel):
    model_config = _ConfigDict(from_attributes=True, populate_by_name=True)


_conftest_stub("app.schemas.base", BaseSchema=_BaseSchema)

# Stub app.core.database so background-task helpers (e.g. audit_service) can
# be loaded without requiring a live SQLAlchemy engine.  Tests mock the session
# factory at the service level and never call these functions directly.
_db_stub = _conftest_stub("app.core.database")
_db_stub.get_primary_session_factory = MagicMock()
_db_stub.get_auth_session_factory = MagicMock(return_value=None)
_db_stub.get_db = MagicMock()
_db_stub.get_engine = MagicMock()
