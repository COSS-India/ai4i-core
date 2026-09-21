"""
Randomized authenticated encryption for the vLLM Authentication Token at
rest (mm_services.llm_auth_token).

Unlike app.core.pii_crypto's deterministic AES-SIV (needed for email/phone
equality lookups), this credential is never looked up by value, so it uses
AES-256-GCM with a fresh random nonce per call. Key: the base64-encoded
32-byte SERVICE_CREDENTIALS_ENCRYPTION_KEY setting, registered at startup
via configure_key(). Ciphertext is stored as
``enc:v1:<urlsafe-base64(nonce || ciphertext)>`` — the prefix distinguishes
it from legacy plaintext.
"""

from __future__ import annotations

import base64
import logging
import os
from functools import lru_cache
from typing import Optional

from cryptography.exceptions import InvalidTag
from cryptography.hazmat.primitives.ciphers.aead import AESGCM

logger = logging.getLogger(__name__)

_PREFIX = "enc:v1:"
_NONCE_LEN = 12
_CONTEXT = b"llm_auth_token"
_KEY_SETTING = "SERVICE_CREDENTIALS_ENCRYPTION_KEY"

_configured_key: Optional[str] = None


class ServiceCredentialEncryptionError(RuntimeError):
    """Raised when the encryption key is missing or malformed."""


def configure_key(key: Optional[str]) -> None:
    """Register the raw base64 key string and reset the cached cipher."""
    global _configured_key
    _configured_key = key.strip() if isinstance(key, str) and key.strip() else None
    _cipher.cache_clear()


@lru_cache(maxsize=1)
def _cipher() -> AESGCM:
    if not _configured_key:
        raise ServiceCredentialEncryptionError(
            f"{_KEY_SETTING} is not set. Generate one with: "
            "python -c \"import base64,os;print(base64.b64encode(os.urandom(32)).decode())\""
        )
    try:
        key = base64.b64decode(_configured_key, validate=True)
    except ValueError as exc:
        raise ServiceCredentialEncryptionError(f"{_KEY_SETTING} must be base64-encoded.") from exc
    if len(key) != 32:
        raise ServiceCredentialEncryptionError(
            f"{_KEY_SETTING} decodes to {len(key)} bytes; AES-256-GCM requires 32."
        )
    return AESGCM(key)


def validate_key() -> None:
    """Eagerly build the cipher so a missing/malformed key fails at startup
    (see app/main.py's lifespan), not on the first encrypted read/write."""
    _cipher()


def encrypt(plaintext: Optional[str]) -> Optional[str]:
    """Encrypt a request-supplied value with a fresh random nonce. ``None``-safe."""
    if plaintext is None:
        return None
    nonce = os.urandom(_NONCE_LEN)
    ciphertext = _cipher().encrypt(nonce, plaintext.encode("utf-8"), _CONTEXT)
    return _PREFIX + base64.urlsafe_b64encode(nonce + ciphertext).decode("ascii")


def decrypt(token: Optional[str]) -> Optional[str]:
    """Decrypt a stored token. ``None``-safe; passes through legacy
    (un-migrated) plaintext. An undecryptable value (rotated key, corrupted
    row) yields ``None`` rather than failing every read of every service."""
    if token is None or not token.startswith(_PREFIX):
        return token
    try:
        raw = base64.urlsafe_b64decode(token[len(_PREFIX):].encode("ascii"))
        return _cipher().decrypt(raw[:_NONCE_LEN], raw[_NONCE_LEN:], _CONTEXT).decode("utf-8")
    except (InvalidTag, ValueError):
        logger.warning("llm_auth_token could not be decrypted — key rotated or value corrupted")
        return None
