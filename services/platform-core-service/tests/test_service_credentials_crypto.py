"""Unit tests for app.core.service_credentials_crypto: round-trip
correctness, randomized ciphertext (unlike PII's deterministic AES-SIV),
legacy-plaintext passthrough, failure-safe decrypt, and fail-fast key
validation."""

from __future__ import annotations

import base64
import os

import pytest

from app.core import service_credentials_crypto as crypto

_VALID_KEY = base64.b64encode(os.urandom(32)).decode()


@pytest.fixture(autouse=True)
def _reset_key():
    crypto.configure_key(_VALID_KEY)
    yield
    crypto.configure_key(None)


class TestRoundTrip:
    def test_encrypt_then_decrypt_recovers_plaintext(self) -> None:
        token = "sk-vllm-test-token-value"
        ciphertext = crypto.encrypt(token)
        assert ciphertext != token
        assert crypto.decrypt(ciphertext) == token

    def test_none_is_none_safe(self) -> None:
        assert crypto.encrypt(None) is None
        assert crypto.decrypt(None) is None

    def test_encrypting_twice_yields_different_ciphertext(self) -> None:
        """Unlike pii_crypto's deterministic AES-SIV, this must be
        randomized — nothing ever looks up this column by equality."""
        token = "sk-vllm-test-token-value"
        first = crypto.encrypt(token)
        second = crypto.encrypt(token)
        assert first != second
        assert crypto.decrypt(first) == token
        assert crypto.decrypt(second) == token

    def test_plaintext_that_looks_like_ciphertext_still_round_trips(self) -> None:
        """A user token happening to start with the storage prefix must be
        encrypted like any other value, not stored verbatim."""
        token = "enc:v1:not-actually-encrypted"
        assert crypto.decrypt(crypto.encrypt(token)) == token

    def test_decrypt_passes_through_legacy_plaintext(self) -> None:
        """A row written before this feature's encryption shipped has no
        enc:v1: prefix — must read back unchanged, not error."""
        assert crypto.decrypt("plain-legacy-value") == "plain-legacy-value"

    def test_decrypt_returns_none_for_undecryptable_value(self) -> None:
        """A rotated key or corrupted row must not 500 every service read."""
        ciphertext = crypto.encrypt("token")
        crypto.configure_key(base64.b64encode(os.urandom(32)).decode())
        assert crypto.decrypt(ciphertext) is None
        assert crypto.decrypt("enc:v1:!!!not-base64") is None


class TestKeyValidation:
    def test_validate_key_raises_when_unset(self) -> None:
        crypto.configure_key(None)
        with pytest.raises(crypto.ServiceCredentialEncryptionError):
            crypto.validate_key()

    def test_validate_key_raises_when_not_base64(self) -> None:
        crypto.configure_key("not base64!")
        with pytest.raises(crypto.ServiceCredentialEncryptionError):
            crypto.validate_key()

    def test_validate_key_raises_on_wrong_length(self) -> None:
        crypto.configure_key(base64.b64encode(os.urandom(16)).decode())
        with pytest.raises(crypto.ServiceCredentialEncryptionError):
            crypto.validate_key()

    def test_validate_key_passes_with_valid_key(self) -> None:
        crypto.validate_key()  # must not raise (autouse fixture configured it)
