"""consumers/notification_consumer/pii_crypto.py — decrypt-only mirror of
auth-service's app/core/pii_crypto.py.

This module never encrypts (recipients.py only ever reads what auth-service
already wrote), so these tests build ciphertext directly with AESSIV rather
than round-tripping through this module's own encrypt() — there isn't one.
Same key, same "enc:v1:" + urlsafe-b64 framing, and the same EMAIL_CONTEXT
associated data auth-service's pii_crypto.py uses, so a real
ai4iplatform_auth.users.email value decrypts here exactly as it does there.
"""
from __future__ import annotations

import base64

import pytest
from cryptography.hazmat.primitives.ciphers.aead import AESSIV

from consumers.notification_consumer import pii_crypto

# 64 bytes -> AES-256-SIV, mirroring auth-service's own test key
# (services/auth-service/tests/test_pii_crypto_masking.py).
_TEST_KEY = base64.b64encode(b"\x01" * 64).decode("ascii")


def _encrypt(plaintext: str, key: str = _TEST_KEY) -> str:
    """Builds a token the same way auth-service's EncryptedEmail column
    does: AES-SIV over the plaintext with EMAIL_CONTEXT as associated data,
    urlsafe-b64 encoded, "enc:v1:" prefixed."""
    raw_key = base64.b64decode(key)
    ciphertext = AESSIV(raw_key).encrypt(plaintext.encode("utf-8"), [pii_crypto.EMAIL_CONTEXT])
    return pii_crypto._PREFIX + base64.urlsafe_b64encode(ciphertext).decode("ascii")


@pytest.fixture(autouse=True)
def _configured_key():
    pii_crypto.configure_key(_TEST_KEY)
    yield
    pii_crypto.configure_key(None)


class TestDecryptEmail:
    def test_round_trip(self):
        token = _encrypt("john.doe@example.com")
        assert pii_crypto.decrypt_email(token) == "john.doe@example.com"

    def test_none_is_passed_through(self):
        assert pii_crypto.decrypt_email(None) is None

    def test_legacy_unmigrated_plaintext_passes_through_unchanged(self):
        # A users.email row written before the AES-SIV migration has no
        # "enc:v1:" prefix — recipients.py must still resolve a real
        # address for it, not fail or mangle it.
        assert pii_crypto.decrypt_email("plain@x.com") == "plain@x.com"

    def test_wrong_key_fails_to_decrypt(self):
        token = _encrypt("john.doe@example.com")
        pii_crypto.configure_key(base64.b64encode(b"\x02" * 64).decode("ascii"))
        with pytest.raises(Exception):
            pii_crypto.decrypt_email(token)

    def test_is_encrypted_detects_prefix(self):
        assert pii_crypto.is_encrypted(_encrypt("a@b.com"))
        assert not pii_crypto.is_encrypted("plain@x.com")
        assert not pii_crypto.is_encrypted(None)


class TestCipherKeyHandling:
    def test_missing_key_raises(self):
        pii_crypto.configure_key(None)
        with pytest.raises(pii_crypto.PIIEncryptionError):
            pii_crypto.decrypt_email(_encrypt("a@b.com"))

    def test_malformed_key_raises(self):
        pii_crypto.configure_key("not-a-valid-key!!!")
        with pytest.raises(pii_crypto.PIIEncryptionError):
            pii_crypto.decrypt_email(_encrypt("a@b.com"))

    def test_wrong_length_key_raises(self):
        short_key = base64.b64encode(b"\x01" * 10).decode("ascii")
        pii_crypto.configure_key(short_key)
        with pytest.raises(pii_crypto.PIIEncryptionError):
            pii_crypto.decrypt_email(_encrypt("a@b.com"))
