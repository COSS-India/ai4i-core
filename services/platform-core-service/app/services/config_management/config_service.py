from typing import List

from sqlalchemy import select
from sqlalchemy.exc import IntegrityError
from sqlalchemy.ext.asyncio import AsyncSession

from app.core.exceptions import DuplicateEntityError, EntityNotFoundError
from app.models.config_management.config import Config
from app.schemas.config_management.config_schema import (
    ConfigCreate,
    ConfigItem,
    ConfigUpdate,
)


async def list_configs(session: AsyncSession) -> List[ConfigItem]:
    result = await session.execute(select(Config).order_by(Config.id))
    return [ConfigItem.model_validate(row) for row in result.scalars().all()]


async def get_config(session: AsyncSession, config_id: int) -> ConfigItem:
    row = await session.get(Config, config_id)
    if row is None:
        raise EntityNotFoundError(f"Config {config_id}")
    return ConfigItem.model_validate(row)


async def create_config(
    session: AsyncSession,
    body: ConfigCreate,
    *,
    created_by: str | None = None,
) -> ConfigItem:
    row = Config(
        type=body.type,
        data=body.data,
        created_by=created_by,
        updated_by=created_by,
    )
    session.add(row)
    try:
        await session.commit()
    except IntegrityError as exc:
        await session.rollback()
        if "uq_configs_type" in str(exc.orig):
            raise DuplicateEntityError(f"Config with type '{body.type}' already exists")
        raise
    await session.refresh(row)
    return ConfigItem.model_validate(row)


async def update_config(
    session: AsyncSession,
    config_id: int,
    body: ConfigUpdate,
    *,
    updated_by: str | None = None,
) -> ConfigItem:
    row = await session.get(Config, config_id, with_for_update=True)
    if row is None:
        raise EntityNotFoundError(f"Config {config_id}")

    fields = body.model_dump(exclude_unset=True)
    for field, value in fields.items():
        setattr(row, field, value)
    row.updated_by = updated_by

    try:
        await session.commit()
    except IntegrityError as exc:
        await session.rollback()
        if "uq_configs_type" in str(exc.orig):
            raise DuplicateEntityError(f"Config with type '{body.type}' already exists")
        raise
    await session.refresh(row)
    return ConfigItem.model_validate(row)


async def delete_config(session: AsyncSession, config_id: int) -> int:
    row = await session.get(Config, config_id)
    if row is None:
        raise EntityNotFoundError(f"Config {config_id}")

    await session.delete(row)
    await session.commit()
    return config_id
