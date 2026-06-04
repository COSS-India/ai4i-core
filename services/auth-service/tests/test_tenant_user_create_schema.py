"""Unit tests: TenantUserCreate rejects missing/blank full_name (AI4IDS-1762)."""

import pytest
from pydantic import ValidationError

from app.schemas.tenant import TenantUserCreate


class TestTenantUserCreateFullName:
    def test_missing_full_name_raises_422(self) -> None:
        with pytest.raises(ValidationError) as exc_info:
            TenantUserCreate(email="user@tenant.com", role="USER")
        errors = exc_info.value.errors()
        assert any(e["loc"] == ("full_name",) for e in errors)

    def test_empty_string_raises_422(self) -> None:
        with pytest.raises(ValidationError):
            TenantUserCreate(email="user@tenant.com", full_name="", role="USER")

    def test_whitespace_only_raises_422(self) -> None:
        with pytest.raises(ValidationError):
            TenantUserCreate(email="user@tenant.com", full_name="   ", role="USER")

    def test_valid_full_name_accepted(self) -> None:
        obj = TenantUserCreate(email="user@tenant.com", full_name="Jane Doe", role="USER")
        assert obj.full_name == "Jane Doe"

    def test_full_name_is_stripped(self) -> None:
        obj = TenantUserCreate(email="user@tenant.com", full_name="  Jane Doe  ", role="USER")
        assert obj.full_name == "Jane Doe"

    def test_zero_width_space_only_raises_422(self) -> None:
        with pytest.raises(ValidationError):
            TenantUserCreate(email="user@tenant.com", full_name="\u200b", role="USER")

    def test_soft_hyphen_only_raises_422(self) -> None:
        with pytest.raises(ValidationError):
            TenantUserCreate(email="user@tenant.com", full_name="\u00ad", role="USER")

    def test_mixed_invisible_chars_only_raises_422(self) -> None:
        with pytest.raises(ValidationError):
            TenantUserCreate(email="user@tenant.com", full_name="\u200b\u200c\ufeff", role="USER")

    def test_invisible_chars_stripped_from_valid_name(self) -> None:
        obj = TenantUserCreate(email="user@tenant.com", full_name="John\u200b", role="USER")
        assert obj.full_name == "John"

    def test_unicode_name_accepted(self) -> None:
        obj = TenantUserCreate(email="user@tenant.com", full_name="José García", role="USER")
        assert obj.full_name == "José García"

    def test_max_length_accepted(self) -> None:
        TenantUserCreate(email="user@tenant.com", full_name="A" * 80, role="USER")

    def test_over_max_length_raises_422(self) -> None:
        with pytest.raises(ValidationError):
            TenantUserCreate(email="user@tenant.com", full_name="A" * 81, role="USER")

    def test_single_character_raises_422(self) -> None:
        with pytest.raises(ValidationError):
            TenantUserCreate(email="user@tenant.com", full_name="A", role="USER")

    def test_digits_in_full_name_raise_422(self) -> None:
        with pytest.raises(ValidationError):
            TenantUserCreate(email="user@tenant.com", full_name="Jane2", role="USER")


class TestTenantUserCreatePhone:
    def test_valid_e164_phone_accepted(self) -> None:
        obj = TenantUserCreate(email="user@tenant.com", full_name="Jane Doe", phone_number="+14155552671", role="USER")
        assert obj.phone_number == "+14155552671"

    def test_empty_phone_becomes_none(self) -> None:
        obj = TenantUserCreate(email="user@tenant.com", full_name="Jane Doe", phone_number="  ", role="USER")
        assert obj.phone_number is None

    def test_invalid_phone_raises_422(self) -> None:
        with pytest.raises(ValidationError):
            TenantUserCreate(email="user@tenant.com", full_name="Jane Doe", phone_number="919876543210", role="USER")
