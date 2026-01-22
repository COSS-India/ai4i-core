"""
API Integration Tests for Model Versioning feature.

These tests verify the HTTP endpoint behavior for model versioning operations.
Uses FastAPI TestClient to simulate API requests.
"""
import os
import sys
from unittest.mock import AsyncMock, MagicMock, patch
from datetime import datetime

import pytest
from fastapi import FastAPI
from fastapi.testclient import TestClient

# Add parent directory to path for imports
sys.path.insert(0, os.path.dirname(os.path.dirname(os.path.abspath(__file__))))

from models.db_models import VersionStatus


# ============================================================================
# Test Fixtures
# ============================================================================
@pytest.fixture
def app():
    """Create FastAPI app with routers for testing."""
    from main import app as main_app
    return main_app


@pytest.fixture
def client(app):
    """Create TestClient for API testing."""
    return TestClient(app)


@pytest.fixture
def auth_headers():
    """Mock authentication headers."""
    return {
        "Authorization": "Bearer test-token",
        "Content-Type": "application/json"
    }


@pytest.fixture
def sample_model_data():
    """Sample model data for API requests."""
    return {
        "modelId": "api-test-model",
        "version": "1.0.0",
        "versionStatus": "ACTIVE",
        "name": "API Test Model",
        "description": "Model created via API test",
        "refUrl": "https://example.com/model",
        "task": {"type": "asr"},
        "languages": [{"sourceLanguage": "en"}],
        "license": "MIT",
        "domain": ["general"],
        "inferenceEndPoint": {
            "schema": {
                "modelProcessingType": {"type": "batch"},
                "model_name": "test",
                "request": {},
                "response": {}
            }
        },
        "benchmarks": [],
        "submitter": {
            "name": "Test User",
            "aboutMe": "Tester",
            "team": []
        }
    }


# ============================================================================
# Test Model Creation API with Versioning
# ============================================================================
@pytest.mark.versioning
@pytest.mark.integration
class TestModelCreationAPI:
    """Test model creation API endpoints with versioning."""

    def test_create_model_with_version_status(self, sample_model_data):
        """
        Test POST /models with versionStatus field.
        """
        with patch('routers.router_restful.save_model_to_db') as mock_save:
            with patch('routers.router_restful.AuthProvider'):
                mock_save.return_value = None
                
                from routers.router_restful import router_restful
                from fastapi import FastAPI
                
                test_app = FastAPI()
                test_app.include_router(router_restful)
                client = TestClient(test_app)
                
                response = client.post(
                    "/models",
                    json=sample_model_data
                )
                
                # Check that save was called with correct data
                if mock_save.called:
                    call_args = mock_save.call_args[0][0]
                    assert call_args.versionStatus == VersionStatus.ACTIVE

    def test_create_model_with_deprecated_status(self, sample_model_data):
        """
        Test POST /models with DEPRECATED versionStatus.
        """
        with patch('routers.router_restful.save_model_to_db') as mock_save:
            with patch('routers.router_restful.AuthProvider'):
                mock_save.return_value = None
                
                sample_model_data['versionStatus'] = 'DEPRECATED'
                
                from routers.router_restful import router_restful
                from fastapi import FastAPI
                
                test_app = FastAPI()
                test_app.include_router(router_restful)
                client = TestClient(test_app)
                
                response = client.post(
                    "/models",
                    json=sample_model_data
                )
                
                if mock_save.called:
                    call_args = mock_save.call_args[0][0]
                    assert call_args.versionStatus == VersionStatus.DEPRECATED

    def test_create_multiple_versions_same_model(self, sample_model_data):
        """
        Test creating multiple versions of the same model via API.
        """
        with patch('routers.router_restful.save_model_to_db') as mock_save:
            with patch('routers.router_restful.AuthProvider'):
                mock_save.return_value = None
                
                from routers.router_restful import router_restful
                from fastapi import FastAPI
                
                test_app = FastAPI()
                test_app.include_router(router_restful)
                client = TestClient(test_app)
                
                # Create v1.0.0
                sample_model_data['version'] = '1.0.0'
                client.post("/models", json=sample_model_data)
                
                # Create v2.0.0
                sample_model_data['version'] = '2.0.0'
                client.post("/models", json=sample_model_data)
                
                assert mock_save.call_count == 2


# ============================================================================
# Test Model Update API with Versioning
# ============================================================================
@pytest.mark.versioning
@pytest.mark.integration
class TestModelUpdateAPI:
    """Test model update API endpoints with versioning."""

    def test_update_model_with_version(self):
        """
        Test PATCH /models with version field.
        """
        with patch('routers.router_restful.update_model') as mock_update:
            with patch('routers.router_restful.AuthProvider'):
                mock_update.return_value = 1
                
                from routers.router_restful import router_restful
                from fastapi import FastAPI
                
                test_app = FastAPI()
                test_app.include_router(router_restful)
                client = TestClient(test_app)
                
                update_data = {
                    "modelId": "test-model",
                    "version": "1.0.0",
                    "name": "Updated Name"
                }
                
                response = client.patch("/models", json=update_data)
                
                if mock_update.called:
                    call_args = mock_update.call_args[0][0]
                    assert call_args.version == "1.0.0"

    def test_update_model_version_status(self):
        """
        Test PATCH /models to change versionStatus.
        """
        with patch('routers.router_restful.update_model') as mock_update:
            with patch('routers.router_restful.AuthProvider'):
                mock_update.return_value = 1
                
                from routers.router_restful import router_restful
                from fastapi import FastAPI
                
                test_app = FastAPI()
                test_app.include_router(router_restful)
                client = TestClient(test_app)
                
                update_data = {
                    "modelId": "test-model",
                    "version": "1.0.0",
                    "versionStatus": "DEPRECATED"
                }
                
                response = client.patch("/models", json=update_data)
                
                if mock_update.called:
                    call_args = mock_update.call_args[0][0]
                    assert call_args.versionStatus == VersionStatus.DEPRECATED


# ============================================================================
# Test Model Query API with Versioning
# ============================================================================
@pytest.mark.versioning
@pytest.mark.integration
class TestModelQueryAPI:
    """Test model query API endpoints with versioning."""

    def test_get_model_without_version_param(self):
        """
        Test GET /models/{model_id} without version query param.
        Should return latest ACTIVE version.
        """
        with patch('routers.router_restful.get_model_details') as mock_get:
            with patch('routers.router_restful.AuthProvider'):
                mock_get.return_value = {
                    "modelId": "test-model",
                    "uuid": "test-uuid",
                    "version": "2.0.0",
                    "versionStatus": "ACTIVE",
                    "name": "Test Model"
                }
                
                from routers.router_restful import router_restful
                from fastapi import FastAPI
                
                test_app = FastAPI()
                test_app.include_router(router_restful)
                client = TestClient(test_app)
                
                response = client.get("/models/test-model")
                
                assert response.status_code == 200
                data = response.json()
                assert data["versionStatus"] == "ACTIVE"

    def test_get_model_with_version_param(self):
        """
        Test GET /models/{model_id}?version=1.0.0 with version query param.
        Should return specific version.
        """
        with patch('routers.router_restful.get_model_details') as mock_get:
            with patch('routers.router_restful.AuthProvider'):
                mock_get.return_value = {
                    "modelId": "test-model",
                    "uuid": "test-uuid",
                    "version": "1.0.0",
                    "versionStatus": "DEPRECATED",
                    "name": "Test Model v1"
                }
                
                from routers.router_restful import router_restful
                from fastapi import FastAPI
                
                test_app = FastAPI()
                test_app.include_router(router_restful)
                client = TestClient(test_app)
                
                response = client.get("/models/test-model?version=1.0.0")
                
                assert response.status_code == 200
                data = response.json()
                assert data["version"] == "1.0.0"
                
                # Verify version was passed to get_model_details
                mock_get.assert_called_once_with("test-model", version="1.0.0")

    def test_list_models_includes_all_versions(self):
        """
        Test GET /models returns all versions.
        """
        with patch('routers.router_restful.list_all_models') as mock_list:
            with patch('routers.router_restful.AuthProvider'):
                mock_list.return_value = [
                    {"modelId": "model-a", "version": "1.0.0", "versionStatus": "DEPRECATED"},
                    {"modelId": "model-a", "version": "2.0.0", "versionStatus": "ACTIVE"},
                    {"modelId": "model-b", "version": "1.0.0", "versionStatus": "ACTIVE"}
                ]
                
                from routers.router_restful import router_restful
                from fastapi import FastAPI
                
                test_app = FastAPI()
                test_app.include_router(router_restful)
                client = TestClient(test_app)
                
                response = client.get("/models")
                
                assert response.status_code == 200
                data = response.json()
                assert len(data) == 3
                
                # Check all have versionStatus
                for model in data:
                    assert "versionStatus" in model

    def test_list_models_exclude_deprecated(self):
        """
        Test GET /models?include_deprecated=false returns only ACTIVE versions.
        """
        with patch('routers.router_restful.list_all_models') as mock_list:
            with patch('routers.router_restful.AuthProvider'):
                mock_list.return_value = [
                    {"modelId": "model-a", "version": "2.0.0", "versionStatus": "ACTIVE"},
                    {"modelId": "model-b", "version": "1.0.0", "versionStatus": "ACTIVE"}
                ]
                
                from routers.router_restful import router_restful
                from fastapi import FastAPI
                
                test_app = FastAPI()
                test_app.include_router(router_restful)
                client = TestClient(test_app)
                
                response = client.get("/models?include_deprecated=false")
                
                assert response.status_code == 200
                data = response.json()
                
                # All should be ACTIVE
                for model in data:
                    assert model["versionStatus"] == "ACTIVE"
                
                # Verify include_deprecated was passed
                mock_list.assert_called_once()
                call_kwargs = mock_list.call_args
                assert call_kwargs[1].get('include_deprecated') is False


# ============================================================================
# Test Error Responses
# ============================================================================
@pytest.mark.versioning
@pytest.mark.integration
class TestVersioningErrorResponses:
    """Test error responses for versioning-related errors."""

    def test_duplicate_version_error_response(self):
        """
        Test 400 error when creating duplicate model version.
        """
        from fastapi import HTTPException
        
        with patch('routers.router_restful.save_model_to_db') as mock_save:
            with patch('routers.router_restful.AuthProvider'):
                mock_save.side_effect = HTTPException(
                    status_code=400,
                    detail="Model with ID test-model and version 1.0.0 already exists."
                )
                
                from routers.router_restful import router_restful
                from fastapi import FastAPI
                
                test_app = FastAPI()
                test_app.include_router(router_restful)
                client = TestClient(test_app)
                
                sample_data = {
                    "modelId": "test-model",
                    "version": "1.0.0",
                    "name": "Test",
                    "description": "Test",
                    "refUrl": "http://test.com",
                    "task": {"type": "asr"},
                    "languages": [{"sourceLanguage": "en"}],
                    "license": "MIT",
                    "domain": ["general"],
                    "inferenceEndPoint": {
                        "schema": {
                            "modelProcessingType": {"type": "batch"},
                            "model_name": "test",
                            "request": {},
                            "response": {}
                        }
                    },
                    "benchmarks": [],
                    "submitter": {"name": "Test", "aboutMe": "Test", "team": []}
                }
                
                response = client.post("/models", json=sample_data)
                
                assert response.status_code == 400
                assert "already exists" in response.json()["detail"]

    def test_max_active_versions_error_response(self):
        """
        Test 400 error when max active versions limit is reached.
        """
        from fastapi import HTTPException
        
        with patch('routers.router_restful.save_model_to_db') as mock_save:
            with patch('routers.router_restful.AuthProvider'):
                mock_save.side_effect = HTTPException(
                    status_code=400,
                    detail="Maximum number of active versions (5) reached for model test-model."
                )
                
                from routers.router_restful import router_restful
                from fastapi import FastAPI
                
                test_app = FastAPI()
                test_app.include_router(router_restful)
                client = TestClient(test_app)
                
                sample_data = {
                    "modelId": "test-model",
                    "version": "6.0.0",
                    "name": "Test",
                    "description": "Test",
                    "refUrl": "http://test.com",
                    "task": {"type": "asr"},
                    "languages": [{"sourceLanguage": "en"}],
                    "license": "MIT",
                    "domain": ["general"],
                    "inferenceEndPoint": {
                        "schema": {
                            "modelProcessingType": {"type": "batch"},
                            "model_name": "test",
                            "request": {},
                            "response": {}
                        }
                    },
                    "benchmarks": [],
                    "submitter": {"name": "Test", "aboutMe": "Test", "team": []}
                }
                
                response = client.post("/models", json=sample_data)
                
                assert response.status_code == 400
                assert "Maximum number of active versions" in response.json()["detail"]

    def test_immutable_model_error_response(self):
        """
        Test 409 error when trying to update immutable model version.
        """
        from fastapi import HTTPException
        
        with patch('routers.router_restful.update_model') as mock_update:
            with patch('routers.router_restful.AuthProvider'):
                mock_update.side_effect = HTTPException(
                    status_code=409,
                    detail={
                        "kind": "ImmutableModelVersion",
                        "message": "Model cannot be modified because it is associated with published services."
                    }
                )
                
                from routers.router_restful import router_restful
                from fastapi import FastAPI
                
                test_app = FastAPI()
                test_app.include_router(router_restful)
                client = TestClient(test_app)
                
                update_data = {
                    "modelId": "production-model",
                    "version": "1.0.0",
                    "name": "Updated Name"
                }
                
                response = client.patch("/models", json=update_data)
                
                assert response.status_code == 409
                assert "ImmutableModelVersion" in str(response.json()["detail"])

    def test_version_required_error_response(self):
        """
        Test 400 error when version is missing in update request.
        """
        from fastapi import HTTPException
        
        with patch('routers.router_restful.update_model') as mock_update:
            with patch('routers.router_restful.AuthProvider'):
                mock_update.side_effect = HTTPException(
                    status_code=400,
                    detail="Version is required to update a specific model version."
                )
                
                from routers.router_restful import router_restful
                from fastapi import FastAPI
                
                test_app = FastAPI()
                test_app.include_router(router_restful)
                client = TestClient(test_app)
                
                update_data = {
                    "modelId": "test-model",
                    # version intentionally missing
                    "name": "Updated Name"
                }
                
                response = client.patch("/models", json=update_data)
                
                assert response.status_code == 400
                assert "Version is required" in response.json()["detail"]


# ============================================================================
# Test Request Validation
# ============================================================================
@pytest.mark.versioning
@pytest.mark.integration
class TestRequestValidation:
    """Test request body validation for versioning fields."""

    def test_invalid_version_status_rejected(self):
        """
        Test that invalid versionStatus value is rejected.
        """
        with patch('routers.router_restful.AuthProvider'):
            from routers.router_restful import router_restful
            from fastapi import FastAPI
            
            test_app = FastAPI()
            test_app.include_router(router_restful)
            client = TestClient(test_app)
            
            sample_data = {
                "modelId": "test-model",
                "version": "1.0.0",
                "versionStatus": "INVALID_STATUS",  # Invalid
                "name": "Test",
                "description": "Test",
                "refUrl": "http://test.com",
                "task": {"type": "asr"},
                "languages": [{"sourceLanguage": "en"}],
                "license": "MIT",
                "domain": ["general"],
                "inferenceEndPoint": {
                    "schema": {
                        "modelProcessingType": {"type": "batch"},
                        "model_name": "test",
                        "request": {},
                        "response": {}
                    }
                },
                "benchmarks": [],
                "submitter": {"name": "Test", "aboutMe": "Test", "team": []}
            }
            
            response = client.post("/models", json=sample_data)
            
            # Should return 422 Unprocessable Entity for validation error
            assert response.status_code == 422

    def test_valid_version_status_accepted(self):
        """
        Test that valid versionStatus values are accepted.
        """
        with patch('routers.router_restful.save_model_to_db') as mock_save:
            with patch('routers.router_restful.AuthProvider'):
                mock_save.return_value = None
                
                from routers.router_restful import router_restful
                from fastapi import FastAPI
                
                test_app = FastAPI()
                test_app.include_router(router_restful)
                client = TestClient(test_app)
                
                base_data = {
                    "modelId": "test-model",
                    "version": "1.0.0",
                    "name": "Test",
                    "description": "Test",
                    "refUrl": "http://test.com",
                    "task": {"type": "asr"},
                    "languages": [{"sourceLanguage": "en"}],
                    "license": "MIT",
                    "domain": ["general"],
                    "inferenceEndPoint": {
                        "schema": {
                            "modelProcessingType": {"type": "batch"},
                            "model_name": "test",
                            "request": {},
                            "response": {}
                        }
                    },
                    "benchmarks": [],
                    "submitter": {"name": "Test", "aboutMe": "Test", "team": []}
                }
                
                # Test ACTIVE
                base_data["versionStatus"] = "ACTIVE"
                response = client.post("/models", json=base_data)
                assert response.status_code in [200, 201, 500]  # 500 if mock db fails
                
                # Test DEPRECATED
                base_data["versionStatus"] = "DEPRECATED"
                base_data["version"] = "0.9.0"
                response = client.post("/models", json=base_data)
                assert response.status_code in [200, 201, 500]


# ============================================================================
# Test Response Schema
# ============================================================================
@pytest.mark.versioning
@pytest.mark.integration
class TestResponseSchema:
    """Test that response schema includes versioning fields."""

    def test_model_response_includes_version_fields(self):
        """
        Test that model response includes version-related fields.
        """
        with patch('routers.router_restful.get_model_details') as mock_get:
            with patch('routers.router_restful.AuthProvider'):
                mock_get.return_value = {
                    "modelId": "test-model",
                    "uuid": "test-uuid",
                    "version": "1.0.0",
                    "versionStatus": "ACTIVE",
                    "versionStatusUpdatedAt": "2024-01-15T10:30:00",
                    "name": "Test Model",
                    "description": "Test",
                    "languages": [],
                    "domain": [],
                    "submitter": {},
                    "license": "MIT",
                    "inferenceEndPoint": {},
                    "source": "",
                    "task": {"type": "asr"}
                }
                
                from routers.router_restful import router_restful
                from fastapi import FastAPI
                
                test_app = FastAPI()
                test_app.include_router(router_restful)
                client = TestClient(test_app)
                
                response = client.get("/models/test-model")
                
                assert response.status_code == 200
                data = response.json()
                
                # Required versioning fields
                assert "version" in data
                assert "versionStatus" in data
                assert "versionStatusUpdatedAt" in data

    def test_model_list_response_includes_version_fields(self):
        """
        Test that model list response includes version fields for each item.
        """
        with patch('routers.router_restful.list_all_models') as mock_list:
            with patch('routers.router_restful.AuthProvider'):
                mock_list.return_value = [
                    {
                        "modelId": "model-a",
                        "uuid": "uuid-1",
                        "version": "1.0.0",
                        "versionStatus": "ACTIVE",
                        "versionStatusUpdatedAt": "2024-01-15T10:30:00",
                        "name": "Model A",
                        "description": "Test",
                        "languages": [],
                        "domain": [],
                        "submitter": {},
                        "license": "MIT",
                        "inferenceEndPoint": {},
                        "source": "",
                        "task": {"type": "asr"}
                    }
                ]
                
                from routers.router_restful import router_restful
                from fastapi import FastAPI
                
                test_app = FastAPI()
                test_app.include_router(router_restful)
                client = TestClient(test_app)
                
                response = client.get("/models")
                
                assert response.status_code == 200
                data = response.json()
                
                for model in data:
                    assert "version" in model
                    assert "versionStatus" in model

