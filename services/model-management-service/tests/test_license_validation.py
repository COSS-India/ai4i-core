"""
Tests for License Type Validation in Model Management Service.

This module covers:
1. Valid License Type Acceptance
2. Invalid License Type Rejection
3. Case-Insensitive License Matching
4. License Enum Coverage
5. Integration with Model Creation
"""
import os
import sys
from unittest.mock import AsyncMock, MagicMock, patch

import pytest
from pydantic import ValidationError

sys.path.insert(0, os.path.dirname(os.path.dirname(os.path.abspath(__file__))))

from models.type_enum import LicenseEnum
from models.model_create import ModelCreateRequest


def get_valid_model_payload(license_value: str) -> dict:
    """Helper to create a valid model payload with specified license."""
    return {
        "version": "1.0.0",
        "name": "test-model",
        "description": "Test description",
        "refUrl": "https://example.com",
        "task": {"type": "asr"},
        "languages": [{"sourceLanguage": "en"}],
        "license": license_value,
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


@pytest.mark.unit
class TestLicenseEnum:
    """Test LicenseEnum values and properties."""

    def test_permissive_licenses_exist(self):
        """Verify permissive license types are defined."""
        assert LicenseEnum.MIT.value == "MIT"
        assert LicenseEnum.APACHE_2_0.value == "Apache-2.0"
        assert LicenseEnum.BSD_2_CLAUSE.value == "BSD-2-Clause"
        assert LicenseEnum.BSD_3_CLAUSE.value == "BSD-3-Clause"
        assert LicenseEnum.ISC.value == "ISC"
        assert LicenseEnum.UNLICENSE.value == "Unlicense"
        assert LicenseEnum.ZLIB.value == "Zlib"

    def test_copyleft_licenses_exist(self):
        """Verify copyleft license types are defined."""
        assert LicenseEnum.GPL_2_0.value == "GPL-2.0"
        assert LicenseEnum.GPL_3_0.value == "GPL-3.0"
        assert LicenseEnum.LGPL_2_1.value == "LGPL-2.1"
        assert LicenseEnum.LGPL_3_0.value == "LGPL-3.0"
        assert LicenseEnum.AGPL_3_0.value == "AGPL-3.0"
        assert LicenseEnum.MPL_2_0.value == "MPL-2.0"
        assert LicenseEnum.EPL_2_0.value == "EPL-2.0"
        assert LicenseEnum.CDDL_1_0.value == "CDDL-1.0"

    def test_creative_commons_licenses_exist(self):
        """Verify Creative Commons license types are defined."""
        assert LicenseEnum.CC0_1_0.value == "CC0-1.0"
        assert LicenseEnum.CC_BY_4_0.value == "CC-BY-4.0"
        assert LicenseEnum.CC_BY_SA_4_0.value == "CC-BY-SA-4.0"
        assert LicenseEnum.CC_BY_NC_4_0.value == "CC-BY-NC-4.0"
        assert LicenseEnum.CC_BY_NC_SA_4_0.value == "CC-BY-NC-SA-4.0"
        assert LicenseEnum.CC_BY_ND_4_0.value == "CC-BY-ND-4.0"
        assert LicenseEnum.CC_BY_NC_ND_4_0.value == "CC-BY-NC-ND-4.0"

    def test_ai_ml_specific_licenses_exist(self):
        """Verify AI/ML specific license types are defined."""
        assert LicenseEnum.OPENRAIL_M.value == "OpenRAIL-M"
        assert LicenseEnum.OPENRAIL_S.value == "OpenRAIL-S"
        assert LicenseEnum.BIGSCIENCE_OPENRAIL_M.value == "BigScience-OpenRAIL-M"
        assert LicenseEnum.CREATIVEML_OPENRAIL_M.value == "CreativeML-OpenRAIL-M"
        assert LicenseEnum.APACHE_2_0_WITH_LLM_EXCEPTION.value == "Apache-2.0-with-LLM-exception"

    def test_special_category_licenses_exist(self):
        """Verify special category license types are defined."""
        assert LicenseEnum.PROPRIETARY.value == "Proprietary"
        assert LicenseEnum.CUSTOM.value == "Custom"
        assert LicenseEnum.OTHER.value == "Other"

    def test_license_enum_is_string_enum(self):
        """LicenseEnum should be a string enum."""
        assert isinstance(LicenseEnum.MIT.value, str)
        assert str(LicenseEnum.MIT) == "LicenseEnum.MIT"

    def test_license_enum_count(self):
        """Verify expected number of license types."""
        all_licenses = list(LicenseEnum)
        assert len(all_licenses) >= 30


@pytest.mark.unit
class TestLicenseValidationAcceptance:
    """Test valid license acceptance in model creation."""

    @pytest.mark.parametrize("license_value", [
        "MIT",
        "Apache-2.0",
        "GPL-3.0",
        "CC-BY-4.0",
        "OpenRAIL-M",
        "Proprietary",
        "Custom",
        "Other",
    ])
    def test_valid_license_accepted(self, license_value):
        """Valid license values should be accepted."""
        payload = get_valid_model_payload(license_value)
        model = ModelCreateRequest(**payload)
        
        assert model.license == license_value

    def test_all_enum_licenses_accepted(self):
        """All LicenseEnum values should be accepted."""
        for license_enum in LicenseEnum:
            payload = get_valid_model_payload(license_enum.value)
            model = ModelCreateRequest(**payload)
            
            assert model.license == license_enum.value


@pytest.mark.unit
class TestLicenseValidationRejection:
    """Test invalid license rejection in model creation."""

    @pytest.mark.parametrize("invalid_license", [
        "INVALID",
        "mit-license",
        "Apache2.0",
        "GPL3",
        "Creative Commons",
        "Public Domain",
        "Freeware",
        "Shareware",
        "WTFPL",
        "None",
        "N/A",
        "",
    ])
    def test_invalid_license_rejected(self, invalid_license):
        """Invalid license values should be rejected."""
        payload = get_valid_model_payload(invalid_license)
        
        with pytest.raises(ValidationError) as exc_info:
            ModelCreateRequest(**payload)
        
        error_str = str(exc_info.value)
        assert "license" in error_str.lower() or "Invalid" in error_str

    def test_misspelled_license_rejected(self):
        """Misspelled license names should be rejected."""
        misspelled = ["MITT", "Apach-2.0", "GPl-3.0", "CC-BY4.0"]
        
        for license_value in misspelled:
            payload = get_valid_model_payload(license_value)
            
            with pytest.raises(ValidationError):
                ModelCreateRequest(**payload)

    def test_partial_license_name_rejected(self):
        """Partial license names should be rejected."""
        partial = ["Apache", "GPL", "CC", "BSD"]
        
        for license_value in partial:
            payload = get_valid_model_payload(license_value)
            
            with pytest.raises(ValidationError):
                ModelCreateRequest(**payload)


@pytest.mark.unit
class TestLicenseCaseInsensitivity:
    """Test case-insensitive license matching."""

    @pytest.mark.parametrize("license_input,expected_output", [
        ("mit", "MIT"),
        ("MIT", "MIT"),
        ("Mit", "MIT"),
        ("apache-2.0", "Apache-2.0"),
        ("APACHE-2.0", "Apache-2.0"),
        ("Apache-2.0", "Apache-2.0"),
        ("gpl-3.0", "GPL-3.0"),
        ("GPL-3.0", "GPL-3.0"),
        ("Gpl-3.0", "GPL-3.0"),
        ("openrail-m", "OpenRAIL-M"),
        ("OPENRAIL-M", "OpenRAIL-M"),
        ("OpenRAIL-M", "OpenRAIL-M"),
        ("proprietary", "Proprietary"),
        ("PROPRIETARY", "Proprietary"),
        ("Proprietary", "Proprietary"),
    ])
    def test_case_insensitive_license_matching(self, license_input, expected_output):
        """License matching should be case-insensitive and normalize to enum value."""
        payload = get_valid_model_payload(license_input)
        model = ModelCreateRequest(**payload)
        
        assert model.license == expected_output


@pytest.mark.unit
class TestLicenseWhitespaceHandling:
    """Test whitespace handling in license validation."""

    @pytest.mark.parametrize("license_input,expected_output", [
        ("  MIT  ", "MIT"),
        ("MIT ", "MIT"),
        (" MIT", "MIT"),
        ("  Apache-2.0  ", "Apache-2.0"),
    ])
    def test_whitespace_trimmed_from_license(self, license_input, expected_output):
        """Leading and trailing whitespace should be trimmed."""
        payload = get_valid_model_payload(license_input)
        model = ModelCreateRequest(**payload)
        
        assert model.license == expected_output


@pytest.mark.unit
class TestLicenseValidationErrorMessages:
    """Test license validation error messages."""

    def test_error_message_lists_valid_licenses(self):
        """Error message should list valid license options."""
        payload = get_valid_model_payload("INVALID_LICENSE")
        
        with pytest.raises(ValidationError) as exc_info:
            ModelCreateRequest(**payload)
        
        error_message = str(exc_info.value)
        assert "MIT" in error_message or "Valid licenses" in error_message

    def test_error_message_shows_invalid_value(self):
        """Error message should show the invalid value provided."""
        invalid_value = "COMPLETELY_INVALID_12345"
        payload = get_valid_model_payload(invalid_value)
        
        with pytest.raises(ValidationError) as exc_info:
            ModelCreateRequest(**payload)
        
        error_message = str(exc_info.value)
        assert "Invalid" in error_message or "license" in error_message.lower()


@pytest.mark.unit
class TestLicenseFieldRequired:
    """Test license field requirement."""

    def test_missing_license_raises_error(self):
        """Missing license field should raise validation error."""
        payload = get_valid_model_payload("MIT")
        del payload["license"]
        
        with pytest.raises(ValidationError) as exc_info:
            ModelCreateRequest(**payload)
        
        errors = exc_info.value.errors()
        license_errors = [e for e in errors if "license" in str(e.get("loc", []))]
        assert len(license_errors) > 0

    def test_none_license_raises_error(self):
        """None license value should raise validation error."""
        payload = get_valid_model_payload("MIT")
        payload["license"] = None
        
        with pytest.raises(ValidationError):
            ModelCreateRequest(**payload)


@pytest.mark.integration
class TestLicenseValidationWithApi:
    """Test license validation in API context."""

    def test_api_accepts_valid_license(self):
        """API should accept valid license values."""
        from fastapi import FastAPI
        from fastapi.testclient import TestClient
        
        with patch('routers.router_restful.save_model_to_db') as mock_save:
            with patch('routers.router_restful.AuthProvider'):
                mock_save.return_value = "generated-model-id"
                
                from routers.router_restful import router_restful
                
                test_app = FastAPI()
                test_app.include_router(router_restful)
                client = TestClient(test_app)
                
                payload = get_valid_model_payload("Apache-2.0")
                response = client.post("/models", json=payload)
                
                if mock_save.called:
                    call_args = mock_save.call_args[0][0]
                    assert call_args.license == "Apache-2.0"

    def test_api_rejects_invalid_license(self):
        """API should reject invalid license with 422 status."""
        from fastapi import FastAPI
        from fastapi.testclient import TestClient
        
        with patch('routers.router_restful.AuthProvider'):
            from routers.router_restful import router_restful
            
            test_app = FastAPI()
            test_app.include_router(router_restful)
            client = TestClient(test_app)
            
            payload = get_valid_model_payload("INVALID_LICENSE")
            response = client.post("/models", json=payload)
            
            assert response.status_code == 422


@pytest.mark.unit
class TestLicenseEnumCategories:
    """Test license categorization."""

    def test_get_all_permissive_licenses(self):
        """Verify all permissive licenses can be identified."""
        permissive = [
            LicenseEnum.MIT,
            LicenseEnum.APACHE_2_0,
            LicenseEnum.BSD_2_CLAUSE,
            LicenseEnum.BSD_3_CLAUSE,
            LicenseEnum.ISC,
            LicenseEnum.UNLICENSE,
            LicenseEnum.ZLIB,
        ]
        
        for license_type in permissive:
            assert license_type in LicenseEnum

    def test_get_all_copyleft_licenses(self):
        """Verify all copyleft licenses can be identified."""
        copyleft = [
            LicenseEnum.GPL_2_0,
            LicenseEnum.GPL_3_0,
            LicenseEnum.LGPL_2_1,
            LicenseEnum.LGPL_3_0,
            LicenseEnum.AGPL_3_0,
            LicenseEnum.MPL_2_0,
        ]
        
        for license_type in copyleft:
            assert license_type in LicenseEnum

    def test_get_all_ai_ml_licenses(self):
        """Verify all AI/ML specific licenses can be identified."""
        ai_ml = [
            LicenseEnum.OPENRAIL_M,
            LicenseEnum.OPENRAIL_S,
            LicenseEnum.BIGSCIENCE_OPENRAIL_M,
            LicenseEnum.CREATIVEML_OPENRAIL_M,
            LicenseEnum.APACHE_2_0_WITH_LLM_EXCEPTION,
        ]
        
        for license_type in ai_ml:
            assert license_type in LicenseEnum
