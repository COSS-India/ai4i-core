"""Shared text-cleaning and personal-name validators for Pydantic schemas.

Centralises the invisible-character stripping and name-charset checks so the
``users.full_name`` column is validated the same way regardless of which
endpoint wrote it (tenant-admin provisioning, self-service profile updates,
registration).
"""

import re
import unicodedata
from typing import Any

# Invisible Unicode characters that str.strip() does not remove:
# soft hyphen, zero-width space/non-joiner/joiner, LTR/RTL marks,
# line/paragraph separators, zero-width no-break space (BOM).
_INVISIBLE_CHARS = re.compile(
    "[­​‌‍‎‏﻿]+"
)

# Punctuation allowed in personal name fields
_NAME_PUNCT = frozenset(" -'")


def clean_text(v: Any) -> Any:
    """Strip invisible chars, trim whitespace, and NFC-normalise."""
    if isinstance(v, str):
        v = _INVISIBLE_CHARS.sub("", v).strip()
        v = unicodedata.normalize("NFC", v)
    return v


def check_name_chars(v: str) -> str:
    """Validate personal name character set.

    Allows Unicode letters and combining marks (covers Indic scripts,
    accented Latin, etc.) plus spaces, hyphens, and apostrophes.
    Requires at least one letter so punctuation-only values are rejected.
    """
    has_letter = False
    for c in v:
        cat = unicodedata.category(c)
        if cat.startswith(("L", "M")):
            has_letter = True
        elif c not in _NAME_PUNCT:
            raise ValueError(
                "may only contain letters, spaces, hyphens, and apostrophes"
            )
    if not has_letter:
        raise ValueError("must contain at least one letter")
    return v
