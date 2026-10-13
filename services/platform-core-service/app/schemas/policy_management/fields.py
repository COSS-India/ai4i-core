"""Input cleaning shared by the category and sub-category create schemas.

Both run as ``mode="before"`` validators so trimming happens before the
max_length check, and non-strings fall through to pydantic's str type check.
"""

import unicodedata

NAME_MAX_LEN = 100
DESCRIPTION_MAX_LEN = 1000
POLICY_DESCRIPTION_MAX_LEN = 200
# Largest value of a Postgres INTEGER id column; bigger ids 422 instead of
# overflowing in the driver.
ID_MAX = 2_147_483_647
# Policy-type size caps — must match the /simulate endpoint's own limits so
# platform-core never stores a type that /simulate would reject at run time.
# Both are configurable via MAX_CUSTOM_FIELDS / MAX_REGEX_LEN env vars.
MAX_CUSTOM_FIELDS = 100
MAX_REGEX_LEN = 1000


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
        raise ValueError(f"{label} Name must be a string")
    v = _strip_invisible(v)
    if not v:
        raise ValueError(f"{label} Name is required")
    return v


def clean_domain_key(v: str) -> str:
    """Strip invisible characters from a policy_fields domain key; reject blank."""
    v = _strip_invisible(v)
    if not v:
        raise ValueError("domain key must not be blank")
    return v


def clean_description(v):
    """Trim like a name; a blank description is stored as None."""
    if not isinstance(v, str):
        return v
    return _strip_invisible(v) or None
