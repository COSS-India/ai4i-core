import pytest

from ai4icore_env import app_env
from ai4icore_model_management.triton_client import resolve_inference_ssl_verify


def test_resolve_inference_ssl_verify_prefers_per_service_override(monkeypatch):
    monkeypatch.setattr(app_env, "inference_ssl_verify", True, raising=False)
    assert resolve_inference_ssl_verify(False) is False
    assert resolve_inference_ssl_verify(True) is True


def test_resolve_inference_ssl_verify_falls_back_to_env(monkeypatch):
    monkeypatch.setattr(app_env, "inference_ssl_verify", False, raising=False)
    assert resolve_inference_ssl_verify(None) is False


def test_resolve_inference_ssl_verify_secure_default(monkeypatch):
    # If app_env ever lacks the field (older deployments), we still default secure.
    monkeypatch.delattr(app_env, "inference_ssl_verify", raising=False)
    assert resolve_inference_ssl_verify(None) is True

