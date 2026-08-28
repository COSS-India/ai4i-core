"""Unit tests: field validation on UserUpdate (PUT /auth/me)."""

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

    def test_valid_name_accepted(self) -> None:
        assert UserUpdate(full_name="Jane Doe").full_name == "Jane Doe"

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
