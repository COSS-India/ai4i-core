"""Unit tests: field validation on tenant and tenant user schemas (AI4IDS-1806)."""

import pytest
from pydantic import ValidationError

from app.schemas.tenant import TenantCreate, TenantUpdate, TenantUserCreate, TenantUserUpdate


# ── TenantCreate — organisation ───────────────────────────────────────────────

class TestTenantCreateOrganisation:
    def _make(self, organisation: str) -> TenantCreate:
        return TenantCreate(contact_name="Jane Doe", organisation=organisation, email="a@b.com")

    def test_ascii_name_accepted(self) -> None:
        assert self._make("Acme Corp").organisation == "Acme Corp"

    def test_accented_latin_accepted(self) -> None:
        assert self._make("Société Générale").organisation == "Société Générale"

    def test_indic_script_accepted(self) -> None:
        # Devanagari — includes combining marks (Mc category)
        assert self._make("टाटा समूह").organisation == "टाटा समूह"

    def test_digits_accepted(self) -> None:
        assert self._make("Acme 123").organisation == "Acme 123"

    def test_hyphen_dot_apostrophe_accepted(self) -> None:
        assert self._make("O'Brien-Smith Ltd.").organisation == "O'Brien-Smith Ltd."

    def test_ampersand_accepted(self) -> None:
        assert self._make("AT&T").organisation == "AT&T"

    def test_parentheses_accepted(self) -> None:
        assert self._make("Acme (India) Pvt. Ltd.").organisation == "Acme (India) Pvt. Ltd."

    def test_slash_accepted(self) -> None:
        assert self._make("A/B Corp").organisation == "A/B Corp"

    def test_comma_accepted(self) -> None:
        assert self._make("Smith, Jones & Co.").organisation == "Smith, Jones & Co."

    def test_too_short_raises(self) -> None:
        with pytest.raises(ValidationError):
            self._make("A")

    def test_too_long_raises(self) -> None:
        with pytest.raises(ValidationError):
            self._make("A" * 101)

    def test_max_length_accepted(self) -> None:
        self._make("A" * 100)

    def test_invalid_chars_raises(self) -> None:
        with pytest.raises(ValidationError):
            self._make("Acme@Corp!")

    def test_punctuation_only_raises(self) -> None:
        with pytest.raises(ValidationError):
            self._make("--")

    def test_invisible_chars_stripped(self) -> None:
        obj = self._make("Acme​Corp")
        assert obj.organisation == "AcmeCorp"


# ── TenantCreate — contact_name ───────────────────────────────────────────────

class TestTenantCreateContactName:
    def _make(self, contact_name: str) -> TenantCreate:
        return TenantCreate(contact_name=contact_name, organisation="Acme Corp", email="a@b.com")

    def test_ascii_name_accepted(self) -> None:
        assert self._make("Jane Doe").contact_name == "Jane Doe"

    def test_accented_latin_accepted(self) -> None:
        assert self._make("José García").contact_name == "José García"

    def test_indic_name_accepted(self) -> None:
        assert self._make("कविता शर्मा").contact_name == "कविता शर्मा"

    def test_tamil_name_accepted(self) -> None:
        assert self._make("வள்ளுவர்").contact_name == "வள்ளுவர்"

    def test_hyphen_apostrophe_accepted(self) -> None:
        assert self._make("Anne-Marie O'Brien").contact_name == "Anne-Marie O'Brien"

    def test_too_short_raises(self) -> None:
        with pytest.raises(ValidationError):
            self._make("A")

    def test_too_long_raises(self) -> None:
        with pytest.raises(ValidationError):
            self._make("A" * 81)

    def test_digits_rejected(self) -> None:
        with pytest.raises(ValidationError):
            self._make("Jane123")

    def test_special_chars_rejected(self) -> None:
        with pytest.raises(ValidationError):
            self._make("Jane@Doe")

    def test_punctuation_only_raises(self) -> None:
        with pytest.raises(ValidationError):
            self._make("--")


# ── TenantCreate — phone_number ───────────────────────────────────────────────

class TestTenantCreatePhone:
    def _make(self, phone: str) -> TenantCreate:
        return TenantCreate(contact_name="Jane Doe", organisation="Acme Corp", email="a@b.com", phone_number=phone)

    def test_valid_e164_accepted(self) -> None:
        assert self._make("+919876543210").phone_number == "+919876543210"

    def test_none_accepted(self) -> None:
        obj = TenantCreate(contact_name="Jane Doe", organisation="Acme Corp", email="a@b.com")
        assert obj.phone_number is None

    def test_empty_string_coerced_to_none(self) -> None:
        assert self._make("").phone_number is None

    def test_formatted_number_normalised(self) -> None:
        # Common user input — spaces and dashes stripped before E.164 check
        assert self._make("+91 98765 43210").phone_number == "+919876543210"

    def test_dashes_stripped(self) -> None:
        assert self._make("+1-202-555-0123").phone_number == "+12025550123"

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
        assert TenantUpdate(organisation="AT&T").organisation == "AT&T"

    def test_indic_org_accepted(self) -> None:
        assert TenantUpdate(organisation="टाटा समूह").organisation == "टाटा समूह"

    def test_invalid_organisation_raises(self) -> None:
        with pytest.raises(ValidationError):
            TenantUpdate(organisation="Bad@Org!")

    def test_valid_contact_name_accepted(self) -> None:
        assert TenantUpdate(contact_name="José García").contact_name == "José García"

    def test_indic_contact_name_accepted(self) -> None:
        assert TenantUpdate(contact_name="कविता शर्मा").contact_name == "कविता शर्मा"

    def test_invalid_contact_name_raises(self) -> None:
        with pytest.raises(ValidationError):
            TenantUpdate(contact_name="Jane123")

    def test_max_length_is_255(self) -> None:
        # Existing stored names up to DB column length must round-trip
        TenantUpdate(organisation="A" * 255)

    def test_phone_empty_string_coerced_to_none(self) -> None:
        # Frontend sends "" when phone field is cleared — must become None
        assert TenantUpdate(organisation="Acme Corp", phone_number="").phone_number is None

    def test_phone_formatted_normalised(self) -> None:
        assert TenantUpdate(organisation="Acme", phone_number="+91 98765 43210").phone_number == "+919876543210"

    def test_phone_non_e164_accepted(self) -> None:
        # Pre-existing stored numbers without E.164 format must not break edits
        assert TenantUpdate(organisation="Acme", phone_number="044-12345678").phone_number == "04412345678"


# ── TenantUserCreate ──────────────────────────────────────────────────────────

class TestTenantUserCreateValidation:
    def test_ascii_name_accepted(self) -> None:
        obj = TenantUserCreate(email="u@t.com", full_name="Jane Doe", role="USER")
        assert obj.full_name == "Jane Doe"

    def test_accented_name_accepted(self) -> None:
        obj = TenantUserCreate(email="u@t.com", full_name="José García", role="USER")
        assert obj.full_name == "José García"

    def test_indic_name_accepted(self) -> None:
        obj = TenantUserCreate(email="u@t.com", full_name="कविता शर्मा", role="USER")
        assert obj.full_name == "कविता शर्मा"

    def test_hyphen_apostrophe_accepted(self) -> None:
        obj = TenantUserCreate(email="u@t.com", full_name="Anne-Marie O'Brien", role="USER")
        assert obj.full_name == "Anne-Marie O'Brien"

    def test_digits_in_name_raise(self) -> None:
        with pytest.raises(ValidationError):
            TenantUserCreate(email="u@t.com", full_name="Jane2", role="USER")

    def test_too_short_raises(self) -> None:
        with pytest.raises(ValidationError):
            TenantUserCreate(email="u@t.com", full_name="A", role="USER")

    def test_punctuation_only_raises(self) -> None:
        with pytest.raises(ValidationError):
            TenantUserCreate(email="u@t.com", full_name="--", role="USER")

    def test_phone_valid_e164_accepted(self) -> None:
        obj = TenantUserCreate(email="u@t.com", full_name="Jane Doe", role="USER", phone_number="+919876543210")
        assert obj.phone_number == "+919876543210"

    def test_phone_empty_string_coerced_to_none(self) -> None:
        obj = TenantUserCreate(email="u@t.com", full_name="Jane Doe", role="USER", phone_number="")
        assert obj.phone_number is None

    def test_phone_formatted_normalised(self) -> None:
        obj = TenantUserCreate(email="u@t.com", full_name="Jane Doe", role="USER", phone_number="+91 98765 43210")
        assert obj.phone_number == "+919876543210"

    def test_phone_invalid_raises(self) -> None:
        with pytest.raises(ValidationError):
            TenantUserCreate(email="u@t.com", full_name="Jane Doe", role="USER", phone_number="919876543210")


# ── TenantUserUpdate ──────────────────────────────────────────────────────────

class TestTenantUserUpdateValidation:
    def test_valid_name_accepted(self) -> None:
        assert TenantUserUpdate(full_name="José García").full_name == "José García"

    def test_indic_name_accepted(self) -> None:
        assert TenantUserUpdate(full_name="कविता शर्मा").full_name == "कविता शर्मा"

    def test_digits_in_name_raise(self) -> None:
        with pytest.raises(ValidationError):
            TenantUserUpdate(full_name="Jane2")

    def test_none_name_passes(self) -> None:
        assert TenantUserUpdate(email="u@t.com").full_name is None

    def test_max_length_is_255(self) -> None:
        TenantUserUpdate(full_name="A" * 255)

    def test_phone_empty_string_coerced_to_none(self) -> None:
        assert TenantUserUpdate(full_name="Jane Doe", phone_number="").phone_number is None

    def test_phone_formatted_normalised(self) -> None:
        assert TenantUserUpdate(full_name="Jane Doe", phone_number="+91 98765 43210").phone_number == "+919876543210"

    def test_phone_non_e164_accepted(self) -> None:
        # Pre-existing stored numbers must not break edits
        assert TenantUserUpdate(full_name="Jane Doe", phone_number="044-12345678").phone_number == "04412345678"
