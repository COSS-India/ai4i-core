"""Errors shared by the category and sub-category services."""

from typing import Optional

from app.core.exceptions import AppError


def in_use_error(entity: str, count: Optional[int], child: str, children: str) -> AppError:
    """409 for a delete blocked by rows still under ``entity``. ``count`` is
    None when the RESTRICT foreign key, not the pre-delete count, caught a
    child added in the meantime."""
    if count is None:
        what = children
    else:
        what = f"{count} {child if count == 1 else children}"
    return AppError(
        f"{entity} has {what} and cannot be deleted; delete or move them first.",
        code="ENTITY_IN_USE",
        status_code=409,
    )
