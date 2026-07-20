"""
Unit tests for PII encryption, response masking, and the masked-value guard.

Covers:
  * ``pii_crypto`` round trip, ``None`` safety, idempotency, and context binding.
  * Deterministic equality — the property duplicate-email detection relies on:
    same plaintext + same context -> identical ciphertext, and the email column
    type normalises case/whitespace so an equality lookup matches stored rows.
  * ``mask_email`` / ``mask_phone`` / ``looks_masked`` behaviour.
  * ``drop_masked_pii`` only drops masked email/phone, never other fields.
"""

import base64
import os

import pytest

# A fixed test key (64 bytes -> AES-256-SIV) configured before importing modules
# that build the cipher lazily. Real keys come from PII_ENCRYPTION_KEY.
_TEST_KEY = base64.b64encode(b"\x01" * 64).decode("ascii")
os.environ.setdefault("PII_ENCRYPTION_KEY", _TEST_KEY)

from app.core import pii_crypto  # noqa: E402
from app.models.types import EncryptedEmail, EncryptedPhone  # noqa: E402
from app.utils.masking import (  # noqa: E402
    drop_masked_pii,
    looks_masked,
    mask_api_key,
    mask_email,
    mask_phone,
    mask_pii_in_dict,
)

pii_crypto.configure_key(_TEST_KEY)


class TestValidateKey:
    def test_passes_with_valid_key(self):
        pii_crypto.configure_key(_TEST_KEY)
        # Should not raise.
        pii_crypto.validate_key()

    def test_raises_when_key_missing(self, monkeypatch):
        monkeypatch.delenv("PII_ENCRYPTION_KEY", raising=False)
        pii_crypto.configure_key(None)
        try:
            with pytest.raises(pii_crypto.PIIEncryptionError):
                pii_crypto.validate_key()
        finally:
            pii_crypto.configure_key(_TEST_KEY)

    def test_raises_when_key_malformed(self):
        pii_crypto.configure_key("not-a-valid-key!!!")
        try:
            with pytest.raises(pii_crypto.PIIEncryptionError):
                pii_crypto.validate_key()
        finally:
            pii_crypto.configure_key(_TEST_KEY)


class TestPiiCryptoRoundTrip:
    def test_round_trip_email(self):
        token = pii_crypto.encrypt("john.doe@example.com", pii_crypto.EMAIL_CONTEXT)
        assert token != "john.doe@example.com"
        assert pii_crypto.is_encrypted(token)
        assert pii_crypto.decrypt(token, pii_crypto.EMAIL_CONTEXT) == "john.doe@example.com"

    def test_round_trip_phone(self):
        token = pii_crypto.encrypt("+919876543210", pii_crypto.PHONE_CONTEXT)
        assert pii_crypto.decrypt(token, pii_crypto.PHONE_CONTEXT) == "+919876543210"

    def test_none_is_passed_through(self):
        assert pii_crypto.encrypt(None, pii_crypto.EMAIL_CONTEXT) is None
        assert pii_crypto.decrypt(None, pii_crypto.EMAIL_CONTEXT) is None

    def test_decrypt_passes_through_legacy_plaintext(self):
        # Un-migrated rows have no enc:v1: prefix and must survive untouched.
        assert pii_crypto.decrypt("plain@x.com", pii_crypto.EMAIL_CONTEXT) == "plain@x.com"


class TestPiiCryptoIdempotency:
    def test_encrypt_is_idempotent(self):
        once = pii_crypto.encrypt("a@b.com", pii_crypto.EMAIL_CONTEXT)
        twice = pii_crypto.encrypt(once, pii_crypto.EMAIL_CONTEXT)
        assert once == twice
        assert pii_crypto.decrypt(twice, pii_crypto.EMAIL_CONTEXT) == "a@b.com"


class TestDeterministicEquality:
    def test_same_plaintext_same_ciphertext(self):
        a = pii_crypto.encrypt("a@b.com", pii_crypto.EMAIL_CONTEXT)
        b = pii_crypto.encrypt("a@b.com", pii_crypto.EMAIL_CONTEXT)
        assert a == b

    def test_context_separates_ciphertext(self):
        # Same value under email vs phone context must not be cross-correlatable.
        as_email = pii_crypto.encrypt("12345", pii_crypto.EMAIL_CONTEXT)
        as_phone = pii_crypto.encrypt("12345", pii_crypto.PHONE_CONTEXT)
        assert as_email != as_phone

    def test_email_bind_param_normalises_for_lookup(self):
        # The email column type lower/strips before encrypting, so an equality
        # lookup (User.email == "A@B.com ") resolves to the stored ciphertext.
        col = EncryptedEmail()
        stored = col.process_bind_param("a@b.com", dialect=None)
        looked_up = col.process_bind_param("  A@B.com ", dialect=None)
        assert stored == looked_up
        assert col.process_result_value(stored, dialect=None) == "a@b.com"

    def test_phone_bind_param_is_case_sensitive_no_normalise(self):
        col = EncryptedPhone()
        a = col.process_bind_param("+91987", dialect=None)
        b = col.process_bind_param(" +91987 ", dialect=None)
        # Phone is not normalised, so surrounding whitespace yields a different
        # ciphertext (and decrypts back to the exact original).
        assert a != b
        assert col.process_result_value(a, dialect=None) == "+91987"


class TestMaskEmail:
    def test_basic(self):
        assert mask_email("john.doe@example.com") == "j***@e***.com"

    def test_none(self):
        assert mask_email(None) is None

    def test_non_email_returned_unchanged(self):
        assert mask_email("not-an-email") == "not-an-email"

    def test_output_is_detected_as_masked(self):
        assert looks_masked(mask_email("john@example.com"))


class TestMaskPhone:
    def test_keeps_last_four(self):
        assert mask_phone("+919876543210") == "*********3210"

    def test_none(self):
        assert mask_phone(None) is None

    def test_output_is_detected_as_masked(self):
        assert looks_masked(mask_phone("+919876543210"))


class TestMaskApiKey:
    def test_keeps_first_and_last_four(self):
        assert mask_api_key("ab12cd34ef56gh78") == "ab12******gh78"

    def test_none(self):
        assert mask_api_key(None) is None

    def test_short_value_returned_unchanged(self):
        assert mask_api_key("abcd1234") == "abcd1234"

    def test_output_is_detected_as_masked(self):
        assert looks_masked(mask_api_key("ab12cd34ef56gh78"))


class TestLooksMasked:
    def test_true_when_contains_mask_char(self):
        assert looks_masked("j***@e***.com")

    def test_false_for_clean_value(self):
        assert not looks_masked("john@example.com")

    def test_false_for_none_and_non_str(self):
        assert not looks_masked(None)
        assert not looks_masked(12345)  # type: ignore[arg-type]


class TestMaskPiiInDict:
    def test_masks_both_by_default(self):
        out = mask_pii_in_dict(
            {"email": "john@example.com", "phone_number": "+919876543210"}
        )
        assert out == {"email": "j***@e***.com", "phone_number": "*********3210"}

    def test_can_reveal_phone_only(self):
        # Edit Tenant User: phone is editable, email stays masked.
        out = mask_pii_in_dict(
            {"email": "john@example.com", "phone_number": "+919876543210"},
            mask_phones=False,
        )
        assert out == {"email": "j***@e***.com", "phone_number": "+919876543210"}

    def test_can_reveal_email_and_phone(self):
        # Edit Tenant while PENDING: both correctable, so both revealed.
        out = mask_pii_in_dict(
            {"email": "john@example.com", "phone_number": "+919876543210"},
            mask_emails=False,
            mask_phones=False,
        )
        assert out == {"email": "john@example.com", "phone_number": "+919876543210"}


class TestDropMaskedPii:
    def test_drops_masked_email_and_phone(self):
        out = drop_masked_pii({"email": "j***@e***.com", "phone_number": "***3210"})
        assert out == {}

    def test_keeps_real_pii_values(self):
        data = {"email": "john@example.com", "phone_number": "+919876543210"}
        assert drop_masked_pii(dict(data)) == data

    def test_does_not_drop_non_pii_field_with_mask_char(self):
        # A non-PII field that legitimately contains '*' must survive.
        out = drop_masked_pii({"password": "p*ss*word", "email": "j***@x***.com"})
        assert out == {"password": "p*ss*word"}

    def test_leaves_unrelated_fields_untouched(self):
        data = {"full_name": "John Doe", "timezone": "UTC"}
        assert drop_masked_pii(dict(data)) == data
