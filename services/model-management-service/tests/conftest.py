"""
Pytest configuration and shared fixtures for Model Management Service tests.
"""
import asyncio
import os
import sys
from typing import AsyncGenerator, Generator, Dict, Any
from unittest.mock import AsyncMock, MagicMock, patch
from datetime import datetime

import pytest
import pytest_asyncio

# Add parent directory to path for imports
sys.path.insert(0, os.path.dirname(os.path.dirname(os.path.abspath(__file__))))

from models.db_models import Model, Service, VersionStatus
from models.model_create import ModelCreateRequest, Task, InferenceEndPoint, Schema, ModelProcessingType, Submitter, Benchmark
from models.model_update import ModelUpdateRequest
from models.service_create import ServiceCreateRequest
from models.service_update import ServiceUpdateRequest


@pytest.fixture(scope="session")
def event_loop() -> Generator:
    """Create an instance of the default event loop for the test session."""
    loop = asyncio.get_event_loop_policy().new_event_loop()
    yield loop
    loop.close()


@pytest.fixture
def sample_task() -> Dict[str, Any]:
    """Sample task object for model creation."""
    return {"type": "asr"}


@pytest.fixture
def sample_inference_endpoint() -> Dict[str, Any]:
    """Sample inference endpoint for model creation."""
    return {
        "schema": {
            "modelProcessingType": {"type": "batch"},
            "model_name": "test-model",
            "request": {},
            "response": {}
        }
    }


@pytest.fixture
def sample_submitter() -> Dict[str, Any]:
    """Sample submitter for model creation."""
    return {
        "name": "Test User",
        "aboutMe": "Test submitter",
        "team": [
            {"name": "Team Member", "aboutMe": "Developer", "oauthId": None}
        ]
    }


@pytest.fixture
def sample_languages() -> list:
    """Sample languages list for model creation."""
    return [{"sourceLanguage": "en"}, {"sourceLanguage": "hi"}]


@pytest.fixture
def sample_benchmarks() -> list:
    """Sample benchmarks for model creation."""
    return []


@pytest.fixture
def sample_model_payload(
    sample_task,
    sample_inference_endpoint,
    sample_submitter,
    sample_languages,
    sample_benchmarks
) -> Dict[str, Any]:
    """Complete sample model payload for creating a model."""
    return {
        "modelId": "test-asr-model",
        "version": "1.0.0",
        "versionStatus": "ACTIVE",
        "name": "Test ASR Model",
        "description": "A test model for ASR",
        "refUrl": "https://example.com/model",
        "task": sample_task,
        "languages": sample_languages,
        "license": "MIT",
        "domain": ["general"],
        "inferenceEndPoint": sample_inference_endpoint,
        "benchmarks": sample_benchmarks,
        "submitter": sample_submitter
    }


@pytest.fixture
def sample_service_payload() -> Dict[str, Any]:
    """Complete sample service payload for creating a service."""
    return {
        "serviceId": "test-asr-service",
        "name": "Test ASR Service",
        "serviceDescription": "A test service for ASR",
        "hardwareDescription": "GPU instance",
        "modelId": "test-asr-model",
        "modelVersion": "1.0.0",
        "endpoint": "http://localhost:8087",
        "api_key": "test-api-key",
        "healthStatus": {"status": "healthy", "lastUpdated": datetime.now().isoformat()},
        "benchmarks": {},
        "isPublished": False
    }


def create_model_request(
    model_id: str = "test-model",
    version: str = "1.0.0",
    version_status: str = "ACTIVE",
    name: str = "Test Model",
    task_type: str = "asr"
) -> ModelCreateRequest:
    """Helper to create ModelCreateRequest objects for testing."""
    return ModelCreateRequest(
        modelId=model_id,
        version=version,
        versionStatus=VersionStatus(version_status),
        name=name,
        description="Test model description",
        refUrl="https://example.com/model",
        task=Task(type=task_type),
        languages=[{"sourceLanguage": "en"}],
        license="MIT",
        domain=["general"],
        inferenceEndPoint=InferenceEndPoint(
            schema=Schema(
                modelProcessingType=ModelProcessingType(type="batch"),
                model_name="test-model",
                request={},
                response={}
            )
        ),
        benchmarks=[],
        submitter=Submitter(
            name="Test User",
            aboutMe="Test",
            team=[]
        )
    )


def create_model_update_request(
    model_id: str,
    version: str,
    version_status: str = None,
    name: str = None
) -> ModelUpdateRequest:
    """Helper to create ModelUpdateRequest objects for testing."""
    return ModelUpdateRequest(
        modelId=model_id,
        version=version,
        versionStatus=VersionStatus(version_status) if version_status else None,
        name=name
    )


def create_service_request(
    service_id: str = "test-service",
    model_id: str = "test-model",
    model_version: str = "1.0.0",
    is_published: bool = False
) -> ServiceCreateRequest:
    """Helper to create ServiceCreateRequest objects for testing."""
    return ServiceCreateRequest(
        serviceId=service_id,
        name="Test Service",
        serviceDescription="Test service description",
        hardwareDescription="GPU",
        modelId=model_id,
        modelVersion=model_version,
        endpoint="http://localhost:8087",
        api_key="test-key",
        isPublished=is_published
    )


@pytest.fixture
def mock_db_session():
    """Mock async database session."""
    session = AsyncMock()
    session.execute = AsyncMock()
    session.commit = AsyncMock()
    session.rollback = AsyncMock()
    session.refresh = AsyncMock()
    session.close = AsyncMock()
    session.add = MagicMock()
    return session


@pytest.fixture
def mock_model():
    """Create a mock Model object."""
    model = MagicMock(spec=Model)
    model.id = "test-uuid"
    model.model_id = "test-model"
    model.version = "1.0.0"
    model.version_status = VersionStatus.ACTIVE
    model.version_status_updated_at = datetime.now()
    model.name = "Test Model"
    model.description = "Test description"
    model.submitted_on = 1234567890
    model.updated_on = None
    model.task = {"type": "asr"}
    model.languages = [{"sourceLanguage": "en"}]
    model.domain = ["general"]
    model.license = "MIT"
    model.ref_url = "https://example.com"
    model.inference_endpoint = {}
    model.benchmarks = []
    model.submitter = {"name": "Test"}
    return model


@pytest.fixture
def mock_service():
    """Create a mock Service object."""
    service = MagicMock(spec=Service)
    service.id = "service-uuid"
    service.service_id = "test-service"
    service.name = "Test Service"
    service.model_id = "test-model"
    service.model_version = "1.0.0"
    service.is_published = False
    service.published_at = None
    service.unpublished_at = None
    return service


# Custom markers
def pytest_configure(config):
    config.addinivalue_line("markers", "unit: Unit tests for isolated components")
    config.addinivalue_line("markers", "integration: Integration tests requiring database")
    config.addinivalue_line("markers", "versioning: Model versioning specific tests")


# Pytest plugins
pytest_plugins = ["pytest_asyncio"]

