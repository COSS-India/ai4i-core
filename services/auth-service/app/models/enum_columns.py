"""Helpers for SQLAlchemy Enum columns stored as VARCHAR (native_enum=False)."""

import enum
from typing import Type

from sqlalchemy import Enum

from app.core.constants import VARCHAR_ENUM_MAX_LENGTH


def assert_enum_values_fit_varchar(
    enum_cls: Type[enum.Enum],
    *,
    max_length: int = VARCHAR_ENUM_MAX_LENGTH,
) -> None:
    """Fail fast at import if any enum label exceeds the VARCHAR column width."""
    for member in enum_cls:
        value = member.value
        if len(value) > max_length:
            raise ValueError(
                f"{enum_cls.__name__}.{member.name} value {value!r} exceeds "
                f"VARCHAR_ENUM_MAX_LENGTH={max_length}"
            )


def varchar_enum_type(enum_cls: Type[enum.Enum]) -> Enum:
    """SQLAlchemy Enum type stored as VARCHAR (not a PostgreSQL ENUM type)."""
    assert_enum_values_fit_varchar(enum_cls)
    return Enum(
        enum_cls,
        values_callable=lambda x: [e.value for e in x],
        native_enum=False,
        length=VARCHAR_ENUM_MAX_LENGTH,
    )
