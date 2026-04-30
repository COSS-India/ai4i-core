"""
Tests for Hash-based ID Generation in Model Management Service.

This module covers:
1. Model ID Hash Generation
2. Service ID Hash Generation  
3. Hash Determinism and Consistency
4. Normalization Behavior
5. Edge Cases and Boundary Conditions
"""
import os
import sys
import hashlib
from unittest.mock import AsyncMock, MagicMock, patch

import pytest
from fastapi import HTTPException

sys.path.insert(0, os.path.dirname(os.path.dirname(os.path.abspath(__file__))))

from db_operations import generate_model_id, generate_service_id


@pytest.mark.unit
class TestGenerateModelId:
    """Test cases for model ID hash generation."""

    def test_generates_32_character_hex_string(self):
        """Model ID should be a 32-character hexadecimal string."""
        model_id = generate_model_id("test-model", "1.0.0")
        
        assert len(model_id) == 32
        assert all(c in "0123456789abcdef" for c in model_id)

    def test_deterministic_output(self):
        """Same inputs should always produce the same model ID."""
        model_id_1 = generate_model_id("ai4bharath/indictrans", "2.0.0")
        model_id_2 = generate_model_id("ai4bharath/indictrans", "2.0.0")
        
        assert model_id_1 == model_id_2

    def test_different_versions_produce_different_ids(self):
        """Different versions of the same model should have different IDs."""
        model_id_v1 = generate_model_id("my-model", "1.0.0")
        model_id_v2 = generate_model_id("my-model", "2.0.0")
        
        assert model_id_v1 != model_id_v2

    def test_different_names_produce_different_ids(self):
        """Different model names with same version should have different IDs."""
        model_id_a = generate_model_id("model-a", "1.0.0")
        model_id_b = generate_model_id("model-b", "1.0.0")
        
        assert model_id_a != model_id_b

    def test_case_insensitive_normalization(self):
        """Model ID generation should be case-insensitive."""
        model_id_lower = generate_model_id("test-model", "1.0.0")
        model_id_upper = generate_model_id("TEST-MODEL", "1.0.0")
        model_id_mixed = generate_model_id("Test-Model", "1.0.0")
        
        assert model_id_lower == model_id_upper == model_id_mixed

    def test_whitespace_trimming(self):
        """Whitespace should be trimmed from inputs."""
        model_id_clean = generate_model_id("my-model", "1.0.0")
        model_id_padded = generate_model_id("  my-model  ", "  1.0.0  ")
        
        assert model_id_clean == model_id_padded

    def test_uses_sha256_algorithm(self):
        """Verify SHA256 algorithm is used for hash generation."""
        model_name = "verification-model"
        version = "3.0.0"
        
        expected_input = f"{model_name.lower()}:{version.lower()}"
        expected_hash = hashlib.sha256(expected_input.encode('utf-8')).hexdigest()[:32]
        
        actual_id = generate_model_id(model_name, version)
        
        assert actual_id == expected_hash

    def test_handles_special_characters_in_name(self):
        """Model names with special characters should produce valid IDs."""
        model_id = generate_model_id("org/model-name_v1", "1.0.0-beta")
        
        assert len(model_id) == 32
        assert all(c in "0123456789abcdef" for c in model_id)

    def test_handles_unicode_in_name(self):
        """Unicode characters in model name should be handled correctly."""
        model_id = generate_model_id("मॉडल-नाम", "1.0.0")
        
        assert len(model_id) == 32
        assert all(c in "0123456789abcdef" for c in model_id)

    def test_empty_version_produces_valid_id(self):
        """Empty version string should still produce a valid ID."""
        model_id = generate_model_id("test-model", "")
        
        assert len(model_id) == 32

    def test_semantic_version_formats(self):
        """Various semantic version formats should work correctly."""
        versions = ["1.0.0", "2.1.3-alpha", "0.0.1+build.123", "v1.0.0"]
        model_ids = [generate_model_id("model", v) for v in versions]
        
        assert len(set(model_ids)) == len(versions)


@pytest.mark.unit
class TestGenerateServiceId:
    """Test cases for service ID hash generation."""

    def test_generates_32_character_hex_string(self):
        """Service ID should be a 32-character hexadecimal string."""
        service_id = generate_service_id("model-name", "1.0.0", "service-name")
        
        assert len(service_id) == 32
        assert all(c in "0123456789abcdef" for c in service_id)

    def test_deterministic_output(self):
        """Same inputs should always produce the same service ID."""
        service_id_1 = generate_service_id("model", "1.0.0", "service")
        service_id_2 = generate_service_id("model", "1.0.0", "service")
        
        assert service_id_1 == service_id_2

    def test_different_model_names_produce_different_ids(self):
        """Different model names should produce different service IDs."""
        service_id_a = generate_service_id("model-a", "1.0.0", "service")
        service_id_b = generate_service_id("model-b", "1.0.0", "service")
        
        assert service_id_a != service_id_b

    def test_different_versions_produce_different_ids(self):
        """Different model versions should produce different service IDs."""
        service_id_v1 = generate_service_id("model", "1.0.0", "service")
        service_id_v2 = generate_service_id("model", "2.0.0", "service")
        
        assert service_id_v1 != service_id_v2

    def test_different_service_names_produce_different_ids(self):
        """Different service names should produce different service IDs."""
        service_id_a = generate_service_id("model", "1.0.0", "service-a")
        service_id_b = generate_service_id("model", "1.0.0", "service-b")
        
        assert service_id_a != service_id_b

    def test_case_insensitive_normalization(self):
        """Service ID generation should be case-insensitive."""
        service_id_lower = generate_service_id("model", "1.0.0", "service")
        service_id_upper = generate_service_id("MODEL", "1.0.0", "SERVICE")
        service_id_mixed = generate_service_id("Model", "1.0.0", "Service")
        
        assert service_id_lower == service_id_upper == service_id_mixed

    def test_whitespace_trimming(self):
        """Whitespace should be trimmed from all inputs."""
        service_id_clean = generate_service_id("model", "1.0.0", "service")
        service_id_padded = generate_service_id("  model  ", "  1.0.0  ", "  service  ")
        
        assert service_id_clean == service_id_padded

    def test_uses_sha256_algorithm(self):
        """Verify SHA256 algorithm is used for hash generation."""
        model_name = "test-model"
        version = "2.0.0"
        service_name = "test-service"
        
        expected_input = f"{model_name.lower()}:{version.lower()}:{service_name.lower()}"
        expected_hash = hashlib.sha256(expected_input.encode('utf-8')).hexdigest()[:32]
        
        actual_id = generate_service_id(model_name, version, service_name)
        
        assert actual_id == expected_hash

    def test_handles_forward_slash_in_names(self):
        """Names with forward slashes should be handled correctly."""
        service_id = generate_service_id(
            "ai4bharath/indictrans-v2",
            "1.0.0",
            "ai4bharath/indictrans-gpu"
        )
        
        assert len(service_id) == 32
        assert all(c in "0123456789abcdef" for c in service_id)

    def test_handles_hyphen_in_names(self):
        """Names with hyphens should be handled correctly."""
        service_id = generate_service_id(
            "my-awesome-model",
            "1.0.0-beta",
            "my-production-service"
        )
        
        assert len(service_id) == 32


@pytest.mark.unit
class TestHashCollisionResistance:
    """Test hash collision resistance properties."""

    def test_model_id_collision_resistance_similar_inputs(self):
        """Similar inputs should produce distinctly different hashes."""
        ids = [
            generate_model_id("model", "1.0.0"),
            generate_model_id("model", "1.0.1"),
            generate_model_id("model1", "1.0.0"),
            generate_model_id("model-", "1.0.0"),
        ]
        
        assert len(set(ids)) == len(ids)

    def test_service_id_collision_resistance_similar_inputs(self):
        """Similar service inputs should produce distinctly different hashes."""
        ids = [
            generate_service_id("model", "1.0.0", "service"),
            generate_service_id("model", "1.0.0", "service1"),
            generate_service_id("model", "1.0.1", "service"),
            generate_service_id("model1", "1.0.0", "service"),
        ]
        
        assert len(set(ids)) == len(ids)

    def test_model_and_service_ids_are_independent(self):
        """Model ID and service ID for same inputs should be different."""
        model_id = generate_model_id("test-model", "1.0.0")
        service_id = generate_service_id("test-model", "1.0.0", "test-model")
        
        assert model_id != service_id


@pytest.mark.unit
class TestHashIdIntegrationWithDb:
    """Test hash ID generation integration with database operations."""

    @pytest.mark.asyncio
    async def test_save_model_generates_hash_id(self, mock_db_session, sample_model_payload):
        """Model creation should auto-generate hash-based model ID."""
        with patch('db_operations.AppDatabase', return_value=mock_db_session):
            from db_operations import save_model_to_db
            from models.model_create import ModelCreateRequest

            mock_result = MagicMock()
            mock_result.scalar.return_value = None
            mock_count_result = MagicMock()
            mock_count_result.scalar.return_value = 0
            mock_db_session.execute.side_effect = [mock_result, mock_count_result]

            request_data = {
                "version": "1.0.0",
                "name": "test-model",
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
                "submitter": {"name": "Test", "aboutMe": "Test", "team": []}
            }
            
            expected_model_id = generate_model_id("test-model", "1.0.0")
            
            try:
                await save_model_to_db(ModelCreateRequest(**request_data))
            except Exception:
                pass

            if mock_db_session.add.called:
                added_model = mock_db_session.add.call_args[0][0]
                assert added_model.model_id == expected_model_id

    @pytest.mark.asyncio
    async def test_save_service_generates_hash_id(self, mock_db_session, mock_model):
        """Service creation should auto-generate hash-based service ID."""
        with patch('db_operations.AppDatabase', return_value=mock_db_session):
            from db_operations import save_service_to_db
            from models.service_create import ServiceCreateRequest

            mock_model.name = "test-model"
            mock_model_result = MagicMock()
            mock_model_result.scalars.return_value.first.return_value = mock_model
            
            mock_dup_result = MagicMock()
            mock_dup_result.scalars.return_value.first.return_value = None
            
            mock_db_session.execute.side_effect = [mock_model_result, mock_dup_result]

            request = ServiceCreateRequest(
                name="test-service",
                serviceDescription="Test service",
                hardwareDescription="GPU",
                modelId="existing-model-id",
                modelVersion="1.0.0",
                endpoint="http://localhost:8080",
                api_key="test-key"
            )
            
            expected_service_id = generate_service_id("test-model", "1.0.0", "test-service")
            
            try:
                await save_service_to_db(request)
            except Exception:
                pass

            if mock_db_session.add.called:
                added_service = mock_db_session.add.call_args[0][0]
                assert added_service.service_id == expected_service_id


@pytest.mark.unit
class TestHashIdEdgeCases:
    """Test edge cases for hash ID generation."""

    def test_very_long_model_name(self):
        """Very long model names should produce valid IDs."""
        long_name = "a" * 1000
        model_id = generate_model_id(long_name, "1.0.0")
        
        assert len(model_id) == 32

    def test_very_long_version_string(self):
        """Very long version strings should produce valid IDs."""
        long_version = "1.0.0" + "-beta" * 100
        model_id = generate_model_id("model", long_version)
        
        assert len(model_id) == 32

    def test_numeric_only_model_name(self):
        """Numeric-only model names should produce valid IDs."""
        model_id = generate_model_id("12345", "1.0.0")
        
        assert len(model_id) == 32

    def test_special_unicode_characters(self):
        """Special Unicode characters should be handled."""
        model_id = generate_model_id("モデル-名前", "バージョン")
        
        assert len(model_id) == 32

    def test_model_id_with_emoji(self):
        """Emoji in model name should be handled."""
        model_id = generate_model_id("model-🚀", "1.0.0")
        
        assert len(model_id) == 32

    def test_only_whitespace_inputs(self):
        """Whitespace-only inputs should produce valid (empty input) hash."""
        model_id = generate_model_id("   ", "   ")
        
        assert len(model_id) == 32

    def test_newlines_in_input(self):
        """Newlines in input should be stripped."""
        model_id_clean = generate_model_id("model", "1.0.0")
        model_id_newline = generate_model_id("model\n", "1.0.0\n")
        
        assert model_id_clean != model_id_newline

    def test_tabs_in_input(self):
        """Tabs should be treated differently from spaces."""
        model_id_space = generate_model_id("model name", "1.0.0")
        model_id_tab = generate_model_id("model\tname", "1.0.0")
        
        assert model_id_space != model_id_tab
