"""
Custom SQLAlchemy column types for transparent PII encryption at rest.

These ``TypeDecorator``s encrypt on the way to the database and decrypt on the
way back, so application code (``user.email``, ``user.phone_number``) always
sees plaintext while the column stores deterministic ciphertext. Because the
bind processor also runs for query parameters, equality lookups such as
``User.email == "a@b.com"`` are translated into a comparison against the
deterministic ciphertext automatically — that is what makes duplicate-email
detection work without decrypting the table.

The underlying storage type is ``Text`` since ciphertext is longer than the
original plaintext and not length-bounded in a meaningful way.
"""

from __future__ import annotations

from typing import Optional

from sqlalchemy.types import Text, TypeDecorator

from app.core import pii_crypto


class _EncryptedString(TypeDecorator):
    """Base transparent-encryption type. Subclasses set the field context."""

    impl = Text
    cache_ok = True

    #: AES-SIV associated data (domain separator) for this field.
    _context: bytes = b"generic"
    #: When True, normalise to ``strip().lower()`` before encrypting so that
    #: deterministic equality is case-insensitive (used for email).
    _normalize_lower: bool = False

    def process_bind_param(self, value: Optional[str], dialect) -> Optional[str]:
        if value is None:
            return None
        text = value if isinstance(value, str) else str(value)
        if self._normalize_lower:
            text = text.strip().lower()
        return pii_crypto.encrypt(text, self._context)

    def process_result_value(self, value: Optional[str], dialect) -> Optional[str]:
        if value is None:
            return None
        return pii_crypto.decrypt(value, self._context)


class EncryptedEmail(_EncryptedString):
    """Deterministic, case-insensitive encrypted email column."""

    cache_ok = True
    _context = pii_crypto.EMAIL_CONTEXT
    _normalize_lower = True


class EncryptedPhone(_EncryptedString):
    """Deterministic encrypted phone-number column."""

    cache_ok = True
    _context = pii_crypto.PHONE_CONTEXT
    _normalize_lower = False
