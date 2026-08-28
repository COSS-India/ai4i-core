"""Unit tests: field validation on UserUpdate (PUT /auth/me).

full_name here follows the same rules TenantUserUpdate applies to the same
users.full_name column (see test_tenant_field_validation.py) so a value
accepted/rejected on one path isn't treated differently on the other.
"""

import pytest
from pydantic import ValidationError

from app.schemas.user import UserUpdate


class TestUserUpdateFullName:
    def test_blank_full_name_rejected(self) -> None:
        with pytest.raises(ValidationError):
            UserUpdate(full_name="")

    def test_whitespace_only_full_name_rejected(self) -> None:
        with pytest.raises(ValidationError):
            UserUpdate(full_name="   ")

    def test_single_char_name_rejected(self) -> None:
        with pytest.raises(ValidationError):
            UserUpdate(full_name="A")

    def test_digits_in_name_raise(self) -> None:
        with pytest.raises(ValidationError):
            UserUpdate(full_name="Jane2")

    def test_valid_name_accepted(self) -> None:
        assert UserUpdate(full_name="Jane Doe").full_name == "Jane Doe"

    def test_accented_name_accepted(self) -> None:
        assert UserUpdate(full_name="José García").full_name == "José García"

    def test_indic_name_accepted(self) -> None:
        assert UserUpdate(full_name="कविता शर्मा").full_name == "कविता शर्मा"

    def test_surrounding_whitespace_trimmed(self) -> None:
        assert UserUpdate(full_name="  Jane Doe  ").full_name == "Jane Doe"

    def test_none_full_name_passes(self) -> None:
        # full_name omitted entirely -- partial update of other fields only.
        assert UserUpdate(phone_number="9876543210").full_name is None

    def test_max_length_255_accepted(self) -> None:
        UserUpdate(full_name="A" * 255)

    def test_over_max_length_rejected(self) -> None:
        with pytest.raises(ValidationError):
            UserUpdate(full_name="A" * 256)
