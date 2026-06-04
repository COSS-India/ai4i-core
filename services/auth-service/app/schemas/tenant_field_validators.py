"""
Shared field validators for Create Tenant and Add Tenant User request schemas.
"""

import re
from typing import Optional

from app.core.constants import (
    E164_PHONE_MAX_DIGITS,
    TENANT_CONTACT_NAME_MAX_LENGTH,
    TENANT_CONTACT_NAME_MIN_LENGTH,
    TENANT_ORGANISATION_MAX_LENGTH,
    TENANT_ORGANISATION_MIN_LENGTH,
    TENANT_USER_FULL_NAME_MAX_LENGTH,
    TENANT_USER_FULL_NAME_MIN_LENGTH,
)

# Invisible Unicode characters that str.strip() does not remove.
_INVISIBLE_CHARS = re.compile(
    "[\u00ad\u200b\u200c\u200d\u200e\u200f\u2028\u2029\ufeff]+"
)

_ORGANISATION_ALLOWED_EXTRA = frozenset(" -.'")
_E164_PHONE_RE = re.compile(r"^\+[1-9]\d{1,14}$")


def strip_invisible_chars(value: str) -> str:
    return _INVISIBLE_CHARS.sub("", value)


def validate_organisation(value: str) -> str:
    cleaned = strip_invisible_chars(value).strip()
    if not cleaned:
        raise ValueError("Organisation is required.")
    if len(cleaned) < TENANT_ORGANISATION_MIN_LENGTH:
        raise ValueError(
            f"Organisation must be between {TENANT_ORGANISATION_MIN_LENGTH} "
            f"and {TENANT_ORGANISATION_MAX_LENGTH} characters."
        )
    if len(cleaned) > TENANT_ORGANISATION_MAX_LENGTH:
        raise ValueError(
            f"Organisation must be between {TENANT_ORGANISATION_MIN_LENGTH} "
            f"and {TENANT_ORGANISATION_MAX_LENGTH} characters."
        )
    for ch in cleaned:
        if ch.isascii() and ch.isalnum():
            continue
        if ch in _ORGANISATION_ALLOWED_EXTRA:
            continue
        raise ValueError(
            "Organisation may only contain letters, numbers, spaces, hyphens, dots, and apostrophes."
        )
    return cleaned


def validate_person_name(value: str, *, field_label: str) -> str:
    cleaned = strip_invisible_chars(value).strip()
    if not cleaned:
        raise ValueError(f"{field_label} is required.")
    min_len = (
        TENANT_CONTACT_NAME_MIN_LENGTH
        if field_label == "Contact name"
        else TENANT_USER_FULL_NAME_MIN_LENGTH
    )
    max_len = (
        TENANT_CONTACT_NAME_MAX_LENGTH
        if field_label == "Contact name"
        else TENANT_USER_FULL_NAME_MAX_LENGTH
    )
    if len(cleaned) < min_len or len(cleaned) > max_len:
        raise ValueError(f"{field_label} must be between {min_len} and {max_len} characters.")
    for ch in cleaned:
        if ch in (" ", "-", "'", "\u2019"):
            continue
        if not ch.isalpha():
            raise ValueError(
                f"{field_label} may only contain letters, spaces, hyphens, and apostrophes."
            )
    return cleaned


def validate_optional_e164_phone(value: Optional[str]) -> Optional[str]:
    if value is None:
        return None
    cleaned = strip_invisible_chars(value).strip()
    if not cleaned:
        return None
    if not _E164_PHONE_RE.fullmatch(cleaned):
        raise ValueError(
            "Phone number must be in E.164 format (e.g. +919876543210): "
            f"a leading + followed by up to {E164_PHONE_MAX_DIGITS} digits, no spaces or symbols."
        )
    return cleaned
