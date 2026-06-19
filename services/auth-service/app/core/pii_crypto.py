"""
Deterministic, authenticated field-level encryption for PII (email / phone).

Why deterministic?
    Email duplicate detection relies on comparing stored values directly. With a
    deterministic scheme the same plaintext + same key + same context always
    produces the same ciphertext, so an equality lookup (``User.email == value``)
    matches encrypted rows without decrypting the whole table. We use AES-SIV
    (RFC 5297), which is deterministic *and* authenticated (tamper-evident) and
    needs no nonce.

Key management:
    The key is read from the ``PII_ENCRYPTION_KEY`` environment variable (base64
    or hex) so this module has no dependency on the service settings object and
    can be imported both by the running service and by Alembic data migrations.
    AES-SIV requires a 32, 48, or 64 byte key (it is split in half internally);
    use 64 bytes for AES-256-SIV.

Storage format:
    ``enc:v1:<urlsafe-base64(ciphertext)>``. The ``enc:v1:`` prefix lets us tell
    encrypted values from legacy plaintext, which keeps both ``encrypt`` and
    ``decrypt`` idempotent and the data migration safe to re-run.
"""

from __future__ import annotations

import base64
import os
from functools import lru_cache
from typing import Optional

from cryptography.hazmat.primitives.ciphers.aead import AESSIV

#: Version-tagged marker prepended to every ciphertext we store.
_PREFIX = "enc:v1:"

#: Per-field domain separators bound as AES-SIV associated data so the same
#: value stored as an email vs a phone yields different ciphertexts and cannot
#: be cross-correlated between columns.
EMAIL_CONTEXT = b"email"
PHONE_CONTEXT = b"phone"

_KEY_ENV_VAR = "PII_ENCRYPTION_KEY"

#: Optionally configured by the service at startup (see ``configure_key``).
#: Takes precedence over the environment variable so the running service can
#: source the key from its pydantic settings while Alembic migrations rely on
#: the env var loaded via python-dotenv.
_configured_key: Optional[str] = None


class PIIEncryptionError(RuntimeError):
    """Raised when the encryption key is missing or malformed."""


def configure_key(key: Optional[str]) -> None:
    """Register the raw (base64/hex) key string and reset the cached cipher."""
    global _configured_key
    _configured_key = key.strip() if isinstance(key, str) and key.strip() else None
    _cipher.cache_clear()


def _decode_key(raw: str) -> bytes:
    raw = raw.strip()
    # Prefer base64; fall back to hex so operators can supply either form.
    try:
        return base64.b64decode(raw, validate=True)
    except (ValueError, base64.binascii.Error):  # type: ignore[attr-defined]
        pass
    try:
        return bytes.fromhex(raw)
    except ValueError as exc:
        raise PIIEncryptionError(
            f"{_KEY_ENV_VAR} must be base64- or hex-encoded."
        ) from exc


@lru_cache(maxsize=1)
def _cipher() -> AESSIV:
    raw = _configured_key or os.getenv(_KEY_ENV_VAR)
    if not raw:
        raise PIIEncryptionError(
            f"{_KEY_ENV_VAR} is not set. Generate one with: "
            "python -c \"import base64,os;print(base64.b64encode(os.urandom(64)).decode())\""
        )
    key = _decode_key(raw)
    if len(key) not in (32, 48, 64):
        raise PIIEncryptionError(
            f"{_KEY_ENV_VAR} decodes to {len(key)} bytes; AES-SIV requires 32, 48, or 64."
        )
    return AESSIV(key)


def is_encrypted(value: Optional[str]) -> bool:
    """True when ``value`` is one of our stored ciphertext tokens."""
    return isinstance(value, str) and value.startswith(_PREFIX)


def encrypt(plaintext: Optional[str], context: bytes) -> Optional[str]:
    """Encrypt ``plaintext`` deterministically. Idempotent and ``None``-safe.

    Already-encrypted values are returned unchanged so re-encrypting a row is a
    no-op (the data migration depends on this).
    """
    if plaintext is None:
        return None
    text = plaintext if isinstance(plaintext, str) else str(plaintext)
    if is_encrypted(text):
        return text
    ciphertext = _cipher().encrypt(text.encode("utf-8"), [context])
    return _PREFIX + base64.urlsafe_b64encode(ciphertext).decode("ascii")


def decrypt(token: Optional[str], context: bytes) -> Optional[str]:
    """Decrypt a stored token. ``None``-safe; passes through legacy plaintext.

    Values without the ``enc:v1:`` prefix are assumed to be un-migrated
    plaintext and returned as-is, so the system keeps working during a partial
    rollout.
    """
    if token is None:
        return None
    if not is_encrypted(token):
        return token
    raw = base64.urlsafe_b64decode(token[len(_PREFIX):].encode("ascii"))
    return _cipher().decrypt(raw, [context]).decode("utf-8")
