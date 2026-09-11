"""Decrypt-only mirror of auth-service's app/core/pii_crypto.py.

users.email in ai4iplatform_auth is encrypted at rest (AES-SIV / RFC 5297,
deterministic) by a SQLAlchemy TypeDecorator that only auth-service's own
ORM applies — a raw cross-database SELECT (recipients.py) gets back
ciphertext, not plaintext. This consumer never WRITES to auth's database, so
only decrypt() is reproduced here, not encrypt().

Keep this in sync with auth-service's copy — same key, same AES-SIV
construction, same "enc:v1:" storage format, same email associated-data
context. Both this module and its sibling read PII_ENCRYPTION_KEY, so
deploying this consumer requires the SAME value auth-service uses.
Diverging (algorithm, prefix, or context) silently breaks decryption instead
of failing loudly, since decrypt() below passes through anything not
prefixed "enc:v1:" as legacy plaintext.

If a third consumer of this key ever shows up, this belongs in ai4i_core
instead of a second copy here.
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

#: Set by main.py at startup from cfg.get_settings().PII_ENCRYPTION_KEY.
#: Takes precedence over the bare os.environ lookup below — matching
#: auth-service's own pii_crypto.py exactly, for the same reason: pydantic-
#: settings loads .env into a Settings *object*, not into os.environ, so a
#: plain os.getenv() here sees nothing unless something explicitly hands the
#: value over. configure_key() is that handoff.
_configured_key: Optional[str] = None


class PIIEncryptionError(RuntimeError):
    pass


def configure_key(key: Optional[str]) -> None:
    """Register the raw (base64/hex) key string and reset the cached cipher.
    Call once, at startup — see main.py."""
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
