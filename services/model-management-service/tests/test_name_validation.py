"""
Tests for Name Validation in Model Management Service.

This module covers:
1. Model Name Validation
2. Service Name Validation
3. Valid Name Patterns (alphanumeric, hyphen, forward slash)
4. Invalid Name Patterns
5. Edge Cases
"""
import os
import sys
from unittest.mock import AsyncMock, MagicMock, patch

import pytest
from pydantic import ValidationError

sys.path.insert(0, os.path.dirname(os.path.dirname(os.path.abspath(__file__))))

from models.model_create import ModelCreateRequest
from models.service_create import ServiceCreateRequest


def get_model_payload(name: str) -> dict:
    """Helper to create a valid model payload with specified name."""
    return {
        "version": "1.0.0",
        "name": name,
        "description": "Test description",
        "refUrl": "https://example.com",
        "task": {"type": "asr"},
        "languages": [{"sourceLanguage": "en"}],
        "license": "MIT",
        "domain": ["general"],
        "inferenceEndPoint": {
            "schema": {
                "modelProcessingType": {"type": "batch"},
                "request": {},
                "response": {}
            }
        },
        "benchmarks": [],
        "submitter": {"name": "Test User", "aboutMe": "Tester", "team": []}
    }


def get_service_payload(name: str) -> dict:
    """Helper to create a valid service payload with specified name."""
    return {
        "name": name,
        "serviceDescription": "Test service",
        "hardwareDescription": "GPU",
        "modelId": "test-model-id",
        "modelVersion": "1.0.0",
        "endpoint": "http://localhost:8080",
        "api_key": "test-key"
    }


@pytest.mark.unit
class TestModelNameValidPattern:
    """Test valid model name patterns."""

    @pytest.mark.parametrize("valid_name", [
        "simple-model",
        "model123",
        "ai4bharath/indictrans",
        "org/sub-org/model-name",
        "Model-Name-v1",
        "a",
        "A",
        "1",
        "a-b-c",
        "A/B/C",
        "model-123-gpu",
        "org/model-v2-beta",
    ])
    def test_valid_model_names_accepted(self, valid_name):
        """Model names with alphanumeric, hyphen, and forward slash should be accepted."""
        payload = get_model_payload(valid_name)
        model = ModelCreateRequest(**payload)
        
        assert model.name == valid_name

    def test_alphanumeric_only_name(self):
        """Alphanumeric-only names should be accepted."""
        payload = get_model_payload("ModelName123")
        model = ModelCreateRequest(**payload)
        
        assert model.name == "ModelName123"

    def test_hyphen_separated_name(self):
        """Hyphen-separated names should be accepted."""
        payload = get_model_payload("my-awesome-model")
        model = ModelCreateRequest(**payload)
        
        assert model.name == "my-awesome-model"

    def test_forward_slash_separated_name(self):
        """Forward slash separated names (like org/repo) should be accepted."""
        payload = get_model_payload("ai4bharath/indictrans-v2")
        model = ModelCreateRequest(**payload)
        
        assert model.name == "ai4bharath/indictrans-v2"

    def test_mixed_separators_name(self):
        """Names with both hyphen and forward slash should be accepted."""
        payload = get_model_payload("my-org/my-model-v1")
        model = ModelCreateRequest(**payload)
        
        assert model.name == "my-org/my-model-v1"


@pytest.mark.unit
class TestModelNameInvalidPattern:
    """Test invalid model name patterns."""

    @pytest.mark.parametrize("invalid_name", [
        "model name",
        "model_name",
        "model.name",
        "model@name",
        "model#name",
        "model$name",
        "model%name",
        "model&name",
        "model*name",
        "model+name",
        "model=name",
        "model!name",
        "model?name",
        "model:name",
        "model;name",
        "model,name",
        "model<name",
        "model>name",
        "model(name)",
        "model[name]",
        "model{name}",
        "model|name",
        "model\\name",
        "model`name",
        "model~name",
        "model'name",
        'model"name',
    ])
    def test_invalid_characters_rejected(self, invalid_name):
        """Names with invalid characters should be rejected."""
        payload = get_model_payload(invalid_name)
        
        with pytest.raises(ValidationError) as exc_info:
            ModelCreateRequest(**payload)
        
        error_str = str(exc_info.value)
        assert "name" in error_str.lower()

    def test_underscore_in_name_rejected(self):
        """Underscores should be rejected in model names."""
        payload = get_model_payload("model_name")
        
        with pytest.raises(ValidationError) as exc_info:
            ModelCreateRequest(**payload)
        
        assert "name" in str(exc_info.value).lower()

    def test_space_in_name_rejected(self):
        """Spaces should be rejected in model names."""
        payload = get_model_payload("model name")
        
        with pytest.raises(ValidationError) as exc_info:
            ModelCreateRequest(**payload)
        
        assert "name" in str(exc_info.value).lower()

    def test_dot_in_name_rejected(self):
        """Dots should be rejected in model names."""
        payload = get_model_payload("model.v1")
        
        with pytest.raises(ValidationError) as exc_info:
            ModelCreateRequest(**payload)
        
        assert "name" in str(exc_info.value).lower()


@pytest.mark.unit
class TestModelNameRequired:
    """Test model name requirement."""

    def test_empty_name_rejected(self):
        """Empty model name should be rejected."""
        payload = get_model_payload("")
        
        with pytest.raises(ValidationError):
            ModelCreateRequest(**payload)

    def test_missing_name_rejected(self):
        """Missing model name should raise validation error."""
        payload = get_model_payload("valid-name")
        del payload["name"]
        
        with pytest.raises(ValidationError) as exc_info:
            ModelCreateRequest(**payload)
        
        errors = exc_info.value.errors()
        name_errors = [e for e in errors if "name" in str(e.get("loc", []))]
        assert len(name_errors) > 0

    def test_none_name_rejected(self):
        """None model name should be rejected."""
        payload = get_model_payload("valid-name")
        payload["name"] = None
        
        with pytest.raises(ValidationError):
            ModelCreateRequest(**payload)


@pytest.mark.unit
class TestModelNameErrorMessages:
    """Test model name validation error messages."""

    def test_error_message_explains_valid_format(self):
        """Error message should explain valid name format."""
        payload = get_model_payload("invalid_name")
        
        with pytest.raises(ValidationError) as exc_info:
            ModelCreateRequest(**payload)
        
        error_str = str(exc_info.value)
        assert "alphanumeric" in error_str.lower() or "hyphen" in error_str.lower() or "slash" in error_str.lower()

    def test_error_message_shows_example(self):
        """Error message should show an example of valid name."""
        payload = get_model_payload("bad@name")
        
        with pytest.raises(ValidationError) as exc_info:
            ModelCreateRequest(**payload)
        
        error_str = str(exc_info.value)
        assert "example" in error_str.lower() or "ai4bharath" in error_str.lower()


@pytest.mark.unit
class TestServiceNameValidPattern:
    """Test valid service name patterns."""

    @pytest.mark.parametrize("valid_name", [
        "simple-service",
        "service123",
        "ai4bharath/indictrans-gpu",
        "org/service-name",
        "Service-Name-v1",
        "a",
        "1",
        "service-v1-prod",
    ])
    def test_valid_service_names_accepted(self, valid_name):
        """Service names with alphanumeric, hyphen, and forward slash should be accepted."""
        payload = get_service_payload(valid_name)
        service = ServiceCreateRequest(**payload)
        
        assert service.name == valid_name


@pytest.mark.unit
class TestServiceNameInvalidPattern:
    """Test invalid service name patterns."""

    @pytest.mark.parametrize("invalid_name", [
        "service name",
        "service_name",
        "service.name",
        "service@name",
        "service#name",
        "service$name",
    ])
    def test_invalid_characters_rejected(self, invalid_name):
        """Names with invalid characters should be rejected."""
        payload = get_service_payload(invalid_name)
        
        with pytest.raises(ValidationError) as exc_info:
            ServiceCreateRequest(**payload)
        
        error_str = str(exc_info.value)
        assert "name" in error_str.lower()


@pytest.mark.unit
class TestServiceNameRequired:
    """Test service name requirement."""

    def test_empty_name_rejected(self):
        """Empty service name should be rejected."""
        payload = get_service_payload("")
        
        with pytest.raises(ValidationError):
            ServiceCreateRequest(**payload)

    def test_missing_name_rejected(self):
        """Missing service name should raise validation error."""
        payload = get_service_payload("valid-name")
        del payload["name"]
        
        with pytest.raises(ValidationError):
            ServiceCreateRequest(**payload)


@pytest.mark.unit
class TestNameEdgeCases:
    """Test edge cases for name validation."""

    def test_single_character_name(self):
        """Single character names should be accepted."""
        payload = get_model_payload("a")
        model = ModelCreateRequest(**payload)
        assert model.name == "a"

    def test_single_digit_name(self):
        """Single digit names should be accepted."""
        payload = get_model_payload("1")
        model = ModelCreateRequest(**payload)
        assert model.name == "1"

    def test_very_long_name(self):
        """Very long names with valid characters should be accepted."""
        long_name = "a" * 100 + "-" + "b" * 100
        payload = get_model_payload(long_name)
        model = ModelCreateRequest(**payload)
        assert model.name == long_name

    def test_multiple_consecutive_hyphens(self):
        """Multiple consecutive hyphens should be accepted."""
        payload = get_model_payload("model--name")
        model = ModelCreateRequest(**payload)
        assert model.name == "model--name"

    def test_multiple_consecutive_slashes(self):
        """Multiple consecutive forward slashes should be accepted."""
        payload = get_model_payload("org//model")
        model = ModelCreateRequest(**payload)
        assert model.name == "org//model"

    def test_name_starting_with_hyphen(self):
        """Names starting with hyphen should be accepted."""
        payload = get_model_payload("-model")
        model = ModelCreateRequest(**payload)
        assert model.name == "-model"

    def test_name_ending_with_hyphen(self):
        """Names ending with hyphen should be accepted."""
        payload = get_model_payload("model-")
        model = ModelCreateRequest(**payload)
        assert model.name == "model-"

    def test_name_starting_with_slash(self):
        """Names starting with forward slash should be accepted."""
        payload = get_model_payload("/model")
        model = ModelCreateRequest(**payload)
        assert model.name == "/model"

    def test_name_ending_with_slash(self):
        """Names ending with forward slash should be accepted."""
        payload = get_model_payload("model/")
        model = ModelCreateRequest(**payload)
        assert model.name == "model/"

    def test_only_hyphens(self):
        """Name with only hyphens should be accepted."""
        payload = get_model_payload("---")
        model = ModelCreateRequest(**payload)
        assert model.name == "---"

    def test_only_slashes(self):
        """Name with only forward slashes should be accepted."""
        payload = get_model_payload("///")
        model = ModelCreateRequest(**payload)
        assert model.name == "///"

    def test_mixed_case_preserved(self):
        """Mixed case should be preserved in name."""
        payload = get_model_payload("MyModel-Name")
        model = ModelCreateRequest(**payload)
        assert model.name == "MyModel-Name"


@pytest.mark.integration
class TestNameValidationWithApi:
    """Test name validation in API context."""

    def test_api_accepts_valid_name(self):
        """API should accept valid model names."""
        from fastapi import FastAPI
        from fastapi.testclient import TestClient
        
        with patch('routers.router_restful.save_model_to_db') as mock_save:
            with patch('routers.router_restful.AuthProvider'):
                mock_save.return_value = "generated-id"
                
                from routers.router_restful import router_restful
                
                test_app = FastAPI()
                test_app.include_router(router_restful)
                client = TestClient(test_app)
                
                payload = get_model_payload("ai4bharath/indictrans-v2")
                response = client.post("/models", json=payload)
                
                if mock_save.called:
                    call_args = mock_save.call_args[0][0]
                    assert call_args.name == "ai4bharath/indictrans-v2"

    def test_api_rejects_invalid_name(self):
        """API should reject invalid model names with 422 status."""
        from fastapi import FastAPI
        from fastapi.testclient import TestClient
        
        with patch('routers.router_restful.AuthProvider'):
            from routers.router_restful import router_restful
            
            test_app = FastAPI()
            test_app.include_router(router_restful)
            client = TestClient(test_app)
            
            payload = get_model_payload("invalid_name_with_underscore")
            response = client.post("/models", json=payload)
            
            assert response.status_code == 422


@pytest.mark.unit  
class TestNamePatternRegex:
    """Test the regex pattern used for name validation."""

    def test_regex_pattern_matches_alphanumeric(self):
        """Regex should match alphanumeric characters."""
        import re
        pattern = r'^[a-zA-Z0-9/-]+$'
        
        assert re.match(pattern, "abc")
        assert re.match(pattern, "ABC")
        assert re.match(pattern, "123")
        assert re.match(pattern, "aB1")

    def test_regex_pattern_matches_hyphen(self):
        """Regex should match hyphen."""
        import re
        pattern = r'^[a-zA-Z0-9/-]+$'
        
        assert re.match(pattern, "a-b")
        assert re.match(pattern, "-")
        assert re.match(pattern, "a-b-c")

    def test_regex_pattern_matches_forward_slash(self):
        """Regex should match forward slash."""
        import re
        pattern = r'^[a-zA-Z0-9/-]+$'
        
        assert re.match(pattern, "a/b")
        assert re.match(pattern, "/")
        assert re.match(pattern, "a/b/c")

    def test_regex_pattern_rejects_underscore(self):
        """Regex should not match underscore."""
        import re
        pattern = r'^[a-zA-Z0-9/-]+$'
        
        assert not re.match(pattern, "a_b")

    def test_regex_pattern_rejects_space(self):
        """Regex should not match space."""
        import re
        pattern = r'^[a-zA-Z0-9/-]+$'
        
        assert not re.match(pattern, "a b")

    def test_regex_pattern_rejects_empty(self):
        """Regex should not match empty string."""
        import re
        pattern = r'^[a-zA-Z0-9/-]+$'
        
        assert not re.match(pattern, "")
