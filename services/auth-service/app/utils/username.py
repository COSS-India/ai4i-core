"""
Derive and allocate unique usernames from email for user provisioning.
"""

import re
from typing import Awaitable, Callable

from app.core.constants import USERNAME_MAX_LENGTH
from app.core.exceptions import DuplicateEntityError

ListCollisionFamily = Callable[[str], Awaitable[list[str]]]


def derive_username_from_email(email: str) -> str:
    """Return the email local part (e.g. ``rahul.sharma@mygov.in`` → ``rahul.sharma``)."""
    local = email.split("@", 1)[0].strip()
    if not local:
        local = "user"
    return local[:USERNAME_MAX_LENGTH]


def pick_unique_username(
    base: str,
    taken: set[str],
    *,
    max_suffix: int = 10_000,
) -> str:
    """Choose ``base`` or the lowest free ``base_<n>`` from an in-memory set."""
    base = base[:USERNAME_MAX_LENGTH]
    if base not in taken:
        return base

    suffixes: set[int] = set()
    prefix = f"{base}_"
    for name in taken:
        if not name.startswith(prefix):
            continue
        tail = name[len(prefix) :]
        if tail.isdigit():
            suffixes.add(int(tail))

    if 2 not in suffixes:
        n = 2
    elif suffixes and min(suffixes) == 2 and len(suffixes) == max(suffixes) - 1:
        # Dense block 2..N with no gaps — next free suffix in O(1).
        n = max(suffixes) + 1
    else:
        n = 2
        while n in suffixes:
            n += 1

    if n > max_suffix:
        raise DuplicateEntityError("User", "username")

    suffix = f"_{n}"
    return f"{base[: USERNAME_MAX_LENGTH - len(suffix)]}{suffix}"


async def allocate_unique_username(
    list_collision_family: ListCollisionFamily,
    base: str,
    *,
    max_suffix: int = 10_000,
) -> str:
    """Return ``base`` or ``base_2``, ``base_3``, … using a single DB round-trip."""
    base = base[:USERNAME_MAX_LENGTH]
    taken = set(await list_collision_family(base))
    return pick_unique_username(base, taken, max_suffix=max_suffix)
