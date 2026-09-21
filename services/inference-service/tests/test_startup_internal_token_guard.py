"""
Unit tests: inference-service fails fast at startup when
MODEL_MANAGEMENT_SERVICE_INTERNAL_TOKEN is unset (AI4IDS-3146 review follow-up).

Without this guard, an unset token sends an empty X-Internal-Service-Token
on every GET /internal/services/{id} call. platform-core-service's
_require_internal_caller always 403s that, which inference-service's HTTP
client turns into a ConnectionError — so every inference request (Triton
and LLM alike) fails, discovered only in production traffic rather than at
deploy time.
"""

import sys
from unittest.mock import patch

sys.path.insert(0, ".")

from app_factory import _validate_internal_service_token
from config import settings


def test_raises_when_url_configured_and_token_missing():
    """The exact bug scenario: MMS URL set (resolver will be used), token unset."""
    with patch.object(settings, "MODEL_MANAGEMENT_SERVICE_URL", "http://mms:8095"), \
         patch.object(settings, "MODEL_MANAGEMENT_SERVICE_INTERNAL_TOKEN", None):
        try:
            _validate_internal_service_token()
            assert False, "expected RuntimeError for missing internal token"
        except RuntimeError as exc:
            assert "MODEL_MANAGEMENT_SERVICE_INTERNAL_TOKEN" in str(exc)


def test_raises_when_token_is_empty_string():
    """An empty string is falsy, same as unset — must still fail fast."""
    with patch.object(settings, "MODEL_MANAGEMENT_SERVICE_URL", "http://mms:8095"), \
         patch.object(settings, "MODEL_MANAGEMENT_SERVICE_INTERNAL_TOKEN", ""):
        try:
            _validate_internal_service_token()
            assert False, "expected RuntimeError for empty internal token"
        except RuntimeError:
            pass


def test_raises_when_token_is_whitespace_only():
    """A whitespace-only token still produces an empty header after platform-
    core-service's own configure_key()-style strip — treat it as unset too."""
    with patch.object(settings, "MODEL_MANAGEMENT_SERVICE_URL", "http://mms:8095"), \
         patch.object(settings, "MODEL_MANAGEMENT_SERVICE_INTERNAL_TOKEN", "   "):
        try:
            _validate_internal_service_token()
            assert False, "expected RuntimeError for whitespace-only internal token"
        except RuntimeError:
            pass


def test_passes_when_both_configured():
    with patch.object(settings, "MODEL_MANAGEMENT_SERVICE_URL", "http://mms:8095"), \
         patch.object(settings, "MODEL_MANAGEMENT_SERVICE_INTERNAL_TOKEN", "shared-secret"):
        _validate_internal_service_token()  # must not raise


def test_passes_when_mms_url_not_configured():
    """No MMS URL means the resolver is never reached — nothing to guard yet."""
    with patch.object(settings, "MODEL_MANAGEMENT_SERVICE_URL", None), \
         patch.object(settings, "MODEL_MANAGEMENT_SERVICE_INTERNAL_TOKEN", None):
        _validate_internal_service_token()  # must not raise


if __name__ == "__main__":
    test_raises_when_url_configured_and_token_missing()
    test_raises_when_token_is_empty_string()
    test_raises_when_token_is_whitespace_only()
    test_passes_when_both_configured()
    test_passes_when_mms_url_not_configured()
    print("ALL 5 TESTS PASSED")
