"""Input cleaning shared by the category and sub-category create schemas.

Both run as ``mode="before"`` validators so trimming happens before the
max_length check, and non-strings fall through to pydantic's str type check.
"""

import unicodedata

NAME_MAX_LEN = 100
DESCRIPTION_MAX_LEN = 1000
# Largest value of a Postgres INTEGER id column; bigger ids 422 instead of
# overflowing in the driver.
ID_MAX = 2_147_483_647


def _is_invisible(c: str) -> bool:
    # Whitespace plus control/format characters such as U+200B zero-width space.
    return c.isspace() or unicodedata.category(c) in ("Cc", "Cf")


def _strip_invisible(v: str) -> str:
    start, end = 0, len(v)
    while start < end and _is_invisible(v[start]):
        start += 1
    while end > start and _is_invisible(v[end - 1]):
        end -= 1
    return v[start:end]


def clean_name(v, label: str):
    """Trim invisible characters from both ends; a name with nothing visible
    left is blank. Zero-width joiners inside a name are kept — some scripts
    need them."""
    if not isinstance(v, str):
        return v
    v = _strip_invisible(v)
    if not v:
        raise ValueError(f"{label} Name is required")
    return v


def clean_description(v):
    """Trim like a name; a blank description is stored as None."""
    if not isinstance(v, str):
        return v
    return _strip_invisible(v) or None
