from typing import List

from sqlalchemy import select
from sqlalchemy.exc import IntegrityError
from sqlalchemy.ext.asyncio import AsyncSession

from app.core.exceptions import AppError, DuplicateEntityError, EntityNotFoundError
from app.models.config_management.config import Config
from app.schemas.config_management.config_schema import (
    ConfigCreate,
    ConfigItem,
    ConfigUpdate,
)


def _sorted_by_label(data: object, *, reverse: bool) -> object:
    """Sort data's items by their 'label' when it's a list of {label: ...} dicts.

    Only a single row's data is reordered — this is applied when a specific
    type is requested, not across the row listing itself. Any other shape
    (dict, string, list without a label on every item, etc.) is returned
    unchanged since there is no defined sort key for it.
    """
    if isinstance(data, list) and data and all(isinstance(item, dict) and "label" in item for item in data):
        return sorted(data, key=lambda item: str(item["label"]).lower(), reverse=reverse)
    return data


async def list_configs(
    session: AsyncSession, *, type_filter: str | None = None, sort_order: str | None = None
) -> List[ConfigItem]:
    query = select(Config)
    if type_filter is not None:
        query = query.where(Config.type == type_filter.strip())
        query = query.order_by(Config.id)
    else:
        order_column = Config.id.desc() if sort_order == "desc" else Config.id.asc()
        query = query.order_by(order_column)

    result = await session.execute(query)
    items = [ConfigItem.model_validate(row) for row in result.scalars().all()]

    if type_filter is not None and sort_order is not None:
        reverse = sort_order == "desc"
        for item in items:
            item.data = _sorted_by_label(item.data, reverse=reverse)

    return items


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
            raise DuplicateEntityError(f"Config type '{body.type}'")
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
            raise DuplicateEntityError(f"Config type '{body.type}'")
        raise
    await session.refresh(row)
    return ConfigItem.model_validate(row)


async def delete_config(session: AsyncSession, config_id: int) -> int:
    row = await session.get(Config, config_id)
    if row is None:
        raise EntityNotFoundError(f"Config {config_id}")

    if row.is_default:
        raise AppError(
            message="Config marked as default cannot be deleted.",
            code="DEFAULT_CONFIG_PROTECTED",
            status_code=409,
        )

    await session.delete(row)
    await session.commit()
    return config_id
