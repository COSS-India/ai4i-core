"""Unit tests: full_name validation on RegisterRequest (POST /auth/register).

Mirrors TestUserUpdateFullName (test_user_update_schema.py) and
TestTenantUserUpdateValidation (test_tenant_field_validation.py) -- all three
share the same users.full_name column and now the same validation rules.
"""

import pytest
from pydantic import ValidationError

from app.schemas.auth import RegisterRequest

_BASE = {"email": "user@example.com", "password": "Passw0rd!", "confirm_password": "Passw0rd!"}


class TestRegisterRequestFullName:
    def test_blank_full_name_rejected(self) -> None:
        with pytest.raises(ValidationError):
            RegisterRequest(**_BASE, full_name="")

    def test_whitespace_only_full_name_rejected(self) -> None:
        with pytest.raises(ValidationError):
            RegisterRequest(**_BASE, full_name="   ")

    def test_single_char_name_rejected(self) -> None:
        with pytest.raises(ValidationError):
            RegisterRequest(**_BASE, full_name="A")

    def test_digits_in_name_raise(self) -> None:
        with pytest.raises(ValidationError):
            RegisterRequest(**_BASE, full_name="Jane2")

    def test_valid_name_accepted(self) -> None:
        assert RegisterRequest(**_BASE, full_name="Jane Doe").full_name == "Jane Doe"

    def test_none_full_name_passes(self) -> None:
        assert RegisterRequest(**_BASE).full_name is None

    def test_max_length_255_accepted(self) -> None:
        RegisterRequest(**_BASE, full_name="A" * 255)

    def test_over_max_length_rejected(self) -> None:
        with pytest.raises(ValidationError):
            RegisterRequest(**_BASE, full_name="A" * 256)
