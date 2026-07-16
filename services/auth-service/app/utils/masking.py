"""
PII masking for API responses.

Email and phone are stored encrypted and decrypted transparently for internal
use (sending mail, token links, duplicate checks). For anything returned to a
client they must be masked. These helpers mask the *plaintext* value right
before it leaves the service, and a ``looks_masked`` guard lets update paths
ignore a masked value that a client echoed back unchanged.
"""

from __future__ import annotations

from typing import Any, Iterable, Optional

#: Character used for masked-out positions. Never appears in a real email/phone,
#: which is what ``looks_masked`` keys off of.
_MASK_CHAR = "*"

_DEFAULT_EMAIL_KEYS = ("email",)
_DEFAULT_PHONE_KEYS = ("phone_number", "phone")


def looks_masked(value: Optional[str]) -> bool:
    """True when ``value`` contains the mask character (so it isn't real data)."""
    return isinstance(value, str) and _MASK_CHAR in value


def mask_email(value: Optional[str]) -> Optional[str]:
    """Mask an email: keep the first char of the local part and of the domain
    name, plus the full TLD. e.g. ``john.doe@example.com`` -> ``j***@e***.com``.
    """
    if value is None:
        return None
    if not isinstance(value, str) or "@" not in value:
        return value
    local, _, domain = value.partition("@")
    masked_local = (local[0] + _MASK_CHAR * 3) if local else _MASK_CHAR * 3

    if "." in domain:
        name, _, rest = domain.partition(".")
        masked_name = (name[0] + _MASK_CHAR * 3) if name else _MASK_CHAR * 3
        masked_domain = f"{masked_name}.{rest}"
    else:
        masked_domain = (domain[0] + _MASK_CHAR * 3) if domain else _MASK_CHAR * 3

    return f"{masked_local}@{masked_domain}"


def mask_api_key(value: Optional[str]) -> Optional[str]:
    """Mask an API key, keeping only the first 4 and last 4 characters.
    e.g. ``ab12cd34ef56gh78`` -> ``ab12******gh78``.
    """
    if value is None:
        return None
    if not isinstance(value, str) or len(value) <= 8:
        return value
    return f"{value[:4]}{_MASK_CHAR * 6}{value[-4:]}"


def mask_phone(value: Optional[str]) -> Optional[str]:
    """Mask a phone number, leaving only the last 4 digits visible.
    e.g. ``+919876543210`` -> ``*********3210``.
    """
    if value is None:
        return None
    if not isinstance(value, str) or not value.strip():
        return value
    visible = value[-4:]
    return _MASK_CHAR * max(len(value) - 4, 0) + visible


def mask_pii_in_dict(
    data: dict[str, Any],
    *,
    email_keys: Iterable[str] = _DEFAULT_EMAIL_KEYS,
    phone_keys: Iterable[str] = _DEFAULT_PHONE_KEYS,
    mask_emails: bool = True,
    mask_phones: bool = True,
) -> dict[str, Any]:
    """Return ``data`` with known email/phone keys masked in place.

    Mutates and returns the same dict (callers pass a freshly built response
    dict, so in-place mutation is safe and avoids a copy).

    ``mask_emails`` / ``mask_phones`` let an authorised edit path selectively
    return a PII field in cleartext (e.g. an editable phone number) while still
    masking the rest. Both default to ``True`` so existing callers are
    unchanged and nothing leaks unless a caller opts in.
    """
    if mask_emails:
        for key in email_keys:
            if data.get(key) is not None:
                data[key] = mask_email(data[key])
    if mask_phones:
        for key in phone_keys:
            if data.get(key) is not None:
                data[key] = mask_phone(data[key])
    return data


def drop_masked_pii(
    data: dict[str, Any],
    *,
    email_keys: Iterable[str] = _DEFAULT_EMAIL_KEYS,
    phone_keys: Iterable[str] = _DEFAULT_PHONE_KEYS,
) -> dict[str, Any]:
    """Return a copy of ``data`` with masked email/phone values dropped.

    Update paths return masked PII, so a client may echo a masked value back on
    save. Only the known PII keys are inspected: a masked email/phone is dropped
    so it can't overwrite the stored plaintext, while a non-PII field that merely
    happens to contain the mask character (``*``) is left untouched.
    """
    pii_keys = set(email_keys) | set(phone_keys)
    return {
        key: value
        for key, value in data.items()
        if not (key in pii_keys and looks_masked(value))
    }
