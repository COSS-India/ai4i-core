"""Unit tests for inferenceServerType and sslVerify on service models."""
import os
import sys

import pytest
from pydantic import ValidationError

sys.path.insert(0, os.path.dirname(os.path.dirname(os.path.abspath(__file__))))

from models.service_create import ServiceCreateRequest
from models.service_update import ServiceUpdateRequest
from models.service_view import ServiceResponse


def _minimal_service_create_kwargs(**overrides):
    base = {
        "name": "test-svc",
        "serviceDescription": "d",
        "hardwareDescription": "h",
        "modelId": "mid",
        "modelVersion": "1.0.0",
        "endpoint": "http://localhost:1",
        "api_key": "k",
    }
    base.update(overrides)
    return base


@pytest.mark.unit
def test_service_create_defaults_inference_and_ssl():
    s = ServiceCreateRequest(**_minimal_service_create_kwargs())
    assert s.inferenceServerType == "triton"
    assert s.sslVerify is True


@pytest.mark.unit
def test_service_create_accepts_http_and_false_ssl():
    s = ServiceCreateRequest(
        **_minimal_service_create_kwargs(
            inferenceServerType="http",
            sslVerify=False,
        )
    )
    assert s.inferenceServerType == "http"
    assert s.sslVerify is False


@pytest.mark.unit
def test_service_create_rejects_invalid_inference_server_type():
    with pytest.raises(ValidationError):
        ServiceCreateRequest(
            **_minimal_service_create_kwargs(inferenceServerType="grpc")
        )


@pytest.mark.unit
def test_service_update_optional_inference_validators():
    u = ServiceUpdateRequest(serviceId="x", inferenceServerType="http", sslVerify=False)
    assert u.inferenceServerType == "http"
    assert u.sslVerify is False


@pytest.mark.unit
def test_service_update_rejects_invalid_inference_server_type():
    with pytest.raises(ValidationError):
        ServiceUpdateRequest(serviceId="x", inferenceServerType="vllm")


@pytest.mark.unit
def test_service_response_defaults():
    r = ServiceResponse(
        serviceId="a",
        uuid="b",
        name="n",
        serviceDescription="sd",
        hardwareDescription="hd",
        publishedOn=0,
        modelId="m",
    )
    assert r.inferenceServerType == "triton"
    assert r.sslVerify is True
