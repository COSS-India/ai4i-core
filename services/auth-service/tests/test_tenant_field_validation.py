"""Unit tests: field validation on tenant and tenant user schemas (AI4IDS-1806)."""

import pytest
from pydantic import ValidationError

from app.schemas.tenant import TenantCreate, TenantUpdate, TenantUserCreate, TenantUserUpdate


# ── TenantCreate ──────────────────────────────────────────────────────────────

class TestTenantCreateOrganisation:
    def _valid(self, organisation: str) -> TenantCreate:
        return TenantCreate(contact_name="Jane Doe", organisation=organisation, email="a@b.com")

    def test_standard_name_accepted(self) -> None:
        assert self._valid("Acme Corp").organisation == "Acme Corp"

    def test_unicode_letters_accepted(self) -> None:
        assert self._valid("Société Générale").organisation == "Société Générale"

    def test_digits_accepted(self) -> None:
        assert self._valid("Acme 123").organisation == "Acme 123"

    def test_hyphen_dot_apostrophe_accepted(self) -> None:
        assert self._valid("O'Brien-Smith Ltd.").organisation == "O'Brien-Smith Ltd."

    def test_too_short_raises(self) -> None:
        with pytest.raises(ValidationError):
            self._valid("A")

    def test_too_long_raises(self) -> None:
        with pytest.raises(ValidationError):
            self._valid("A" * 101)

    def test_max_length_accepted(self) -> None:
        self._valid("A" * 100)

    def test_invalid_chars_raises(self) -> None:
        with pytest.raises(ValidationError):
            self._valid("Acme@Corp!")

    def test_invisible_chars_stripped(self) -> None:
        obj = self._valid("Acme​Corp")
        assert obj.organisation == "AcmeCorp"


class TestTenantCreateContactName:
    def _valid(self, contact_name: str) -> TenantCreate:
        return TenantCreate(contact_name=contact_name, organisation="Acme Corp", email="a@b.com")

    def test_standard_name_accepted(self) -> None:
        assert self._valid("Jane Doe").contact_name == "Jane Doe"

    def test_unicode_name_accepted(self) -> None:
        assert self._valid("José García").contact_name == "José García"

    def test_hyphen_apostrophe_accepted(self) -> None:
        assert self._valid("Anne-Marie O'Brien").contact_name == "Anne-Marie O'Brien"

    def test_too_short_raises(self) -> None:
        with pytest.raises(ValidationError):
            self._valid("A")

    def test_too_long_raises(self) -> None:
        with pytest.raises(ValidationError):
            self._valid("A" * 81)

    def test_digits_rejected(self) -> None:
        with pytest.raises(ValidationError):
            self._valid("Jane123")

    def test_special_chars_rejected(self) -> None:
        with pytest.raises(ValidationError):
            self._valid("Jane@Doe")


class TestTenantCreatePhone:
    def _make(self, phone: str) -> TenantCreate:
        return TenantCreate(contact_name="Jane Doe", organisation="Acme Corp", email="a@b.com", phone_number=phone)

    def test_valid_e164_accepted(self) -> None:
        assert self._make("+919876543210").phone_number == "+919876543210"

    def test_none_accepted(self) -> None:
        obj = TenantCreate(contact_name="Jane Doe", organisation="Acme Corp", email="a@b.com")
        assert obj.phone_number is None

    def test_missing_plus_raises(self) -> None:
        with pytest.raises(ValidationError):
            self._make("919876543210")

    def test_letters_raise(self) -> None:
        with pytest.raises(ValidationError):
            self._make("+91abc")

    def test_too_many_digits_raises(self) -> None:
        with pytest.raises(ValidationError):
            self._make("+1" + "2" * 15)


# ── TenantUpdate ──────────────────────────────────────────────────────────────

class TestTenantUpdateValidation:
    def test_none_fields_pass(self) -> None:
        obj = TenantUpdate()
        assert obj.organisation is None
        assert obj.contact_name is None
        assert obj.phone_number is None

    def test_valid_organisation_accepted(self) -> None:
        obj = TenantUpdate(organisation="New Org Ltd.")
        assert obj.organisation == "New Org Ltd."

    def test_invalid_organisation_raises(self) -> None:
        with pytest.raises(ValidationError):
            TenantUpdate(organisation="Bad@Org!")

    def test_valid_contact_name_accepted(self) -> None:
        obj = TenantUpdate(contact_name="José García")
        assert obj.contact_name == "José García"

    def test_invalid_contact_name_raises(self) -> None:
        with pytest.raises(ValidationError):
            TenantUpdate(contact_name="Jane123")

    def test_valid_phone_accepted(self) -> None:
        obj = TenantUpdate(phone_number="+12025550123")
        assert obj.phone_number == "+12025550123"

    def test_invalid_phone_raises(self) -> None:
        with pytest.raises(ValidationError):
            TenantUpdate(phone_number="0044123456789")


# ── TenantUserCreate ──────────────────────────────────────────────────────────

class TestTenantUserCreateValidation:
    def test_unicode_name_accepted(self) -> None:
        obj = TenantUserCreate(email="u@t.com", full_name="José García", role="USER")
        assert obj.full_name == "José García"

    def test_hyphen_apostrophe_accepted(self) -> None:
        obj = TenantUserCreate(email="u@t.com", full_name="Anne-Marie O'Brien", role="USER")
        assert obj.full_name == "Anne-Marie O'Brien"

    def test_digits_in_name_raise(self) -> None:
        with pytest.raises(ValidationError):
            TenantUserCreate(email="u@t.com", full_name="Jane2", role="USER")

    def test_too_short_raises(self) -> None:
        with pytest.raises(ValidationError):
            TenantUserCreate(email="u@t.com", full_name="A", role="USER")

    def test_valid_phone_accepted(self) -> None:
        obj = TenantUserCreate(email="u@t.com", full_name="Jane Doe", role="USER", phone_number="+919876543210")
        assert obj.phone_number == "+919876543210"

    def test_invalid_phone_raises(self) -> None:
        with pytest.raises(ValidationError):
            TenantUserCreate(email="u@t.com", full_name="Jane Doe", role="USER", phone_number="919876543210")


# ── TenantUserUpdate ──────────────────────────────────────────────────────────

class TestTenantUserUpdateValidation:
    def test_valid_name_accepted(self) -> None:
        obj = TenantUserUpdate(full_name="José García")
        assert obj.full_name == "José García"

    def test_digits_in_name_raise(self) -> None:
        with pytest.raises(ValidationError):
            TenantUserUpdate(full_name="Jane2")

    def test_none_name_passes(self) -> None:
        obj = TenantUserUpdate(email="u@t.com")
        assert obj.full_name is None

    def test_valid_phone_accepted(self) -> None:
        obj = TenantUserUpdate(full_name="Jane Doe", phone_number="+12025550123")
        assert obj.phone_number == "+12025550123"

    def test_invalid_phone_raises(self) -> None:
        with pytest.raises(ValidationError):
            TenantUserUpdate(full_name="Jane Doe", phone_number="bad-phone")
