"""Decrypt-only mirror of auth-service's app/core/pii_crypto.py.

users.email in ai4iplatform_auth is encrypted at rest (AES-SIV / RFC 5297,
deterministic) by a SQLAlchemy TypeDecorator that only auth-service's own
ORM applies — any other service reading it via a raw cross-database SELECT
gets back ciphertext, not plaintext. Every non-auth-service reader (
notifications_consumer/recipients.py, ai4i_core.kafka.recipients for
platform-core-service and payperuse_consumer) needs the SAME decrypt, so
it lives here once rather than as a per-service copy.

Keep this in sync with auth-service's own pii_crypto.py — same key, same
AES-SIV construction, same "enc:v1:" storage format, same email associated-
data context. Every service that configures this module needs the SAME
PII_ENCRYPTION_KEY value auth-service uses. Diverging (algorithm, prefix, or
context) silently breaks decryption instead of failing loudly, since
decrypt_email() below passes through anything not prefixed "enc:v1:" as
legacy plaintext.

No encrypt() here on purpose — only auth-service ever writes users.email.
"""
from __future__ import annotations

import base64
import os
from functools import lru_cache
from typing import Optional

from cryptography.hazmat.primitives.ciphers.aead import AESSIV

_PREFIX = "enc:v1:"
EMAIL_CONTEXT = b"email"
_KEY_ENV_VAR = "PII_ENCRYPTION_KEY"

#: Optionally configured by the service at startup (see configure_key()).
#: Takes precedence over the bare os.environ lookup — pydantic-settings
#: loads .env into a Settings *object*, not into os.environ, so a plain
#: os.getenv() here sees nothing unless something explicitly hands the
#: value over.
_configured_key: Optional[str] = None


class PIIEncryptionError(RuntimeError):
    pass


def configure_key(key: Optional[str]) -> None:
    """Register the raw (base64/hex) key string and reset the cached
    cipher. Call once, at service startup, with the SAME
    PII_ENCRYPTION_KEY value auth-service uses."""
    global _configured_key
    _configured_key = key.strip() if isinstance(key, str) and key.strip() else None
    _cipher.cache_clear()


def _decode_key(raw: str) -> bytes:
    raw = raw.strip()
    try:
        return base64.b64decode(raw, validate=True)
    except (ValueError, base64.binascii.Error):  # type: ignore[attr-defined]
        pass
    try:
        return bytes.fromhex(raw)
    except ValueError as exc:
        raise PIIEncryptionError(f"{_KEY_ENV_VAR} must be base64- or hex-encoded.") from exc


@lru_cache(maxsize=1)
def _cipher() -> AESSIV:
    raw = _configured_key or os.getenv(_KEY_ENV_VAR)
    if not raw:
        raise PIIEncryptionError(
            f"{_KEY_ENV_VAR} is not set — neither configure_key() nor the "
            f"{_KEY_ENV_VAR} environment variable provided one."
        )
    key = _decode_key(raw)
    if len(key) not in (32, 48, 64):
        raise PIIEncryptionError(
            f"{_KEY_ENV_VAR} decodes to {len(key)} bytes; AES-SIV requires 32, 48, or 64."
        )
    return AESSIV(key)


def is_encrypted(value: Optional[str]) -> bool:
    return isinstance(value, str) and value.startswith(_PREFIX)


def decrypt_email(token: Optional[str]) -> Optional[str]:
    """None-safe. Un-migrated legacy plaintext (no "enc:v1:" prefix) passes
    through unchanged, matching auth-service's own decrypt()."""
    if token is None:
        return None
    if not is_encrypted(token):
        return token
    raw = base64.urlsafe_b64decode(token[len(_PREFIX):].encode("ascii"))
    plaintext = _cipher().decrypt(raw, [EMAIL_CONTEXT])
    return plaintext.decode("utf-8")
