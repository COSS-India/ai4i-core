"""Per-user column preferences, keyed by view.

``VIEW_CATALOGUES`` is the registry of views that support a column picker; to
add one (e.g. the logs dashboard) register a ``ViewCatalogue`` for it.
"""

from dataclasses import dataclass
from typing import Callable, Dict, FrozenSet, List, Optional, Sequence

from sqlalchemy.ext.asyncio import AsyncSession

from app.core.exceptions import EntityNotFoundError, ValidationError
from app.repositories.user_preferences import table_preference_repository as repo
from app.schemas.model_management import service_columns
from app.services.user_preferences import preference_cache


@dataclass(frozen=True)
class ViewCatalogue:
    # is_admin -> columns in display order (objects with an ``id``)
    columns_for_caller: Callable[[bool], Sequence]
    mandatory: FrozenSet[str]
    defaults: FrozenSet[str]


VIEW_CATALOGUES: Dict[str, ViewCatalogue] = {
    "service-list": ViewCatalogue(
        columns_for_caller=service_columns.columns_for_caller,
        mandatory=service_columns.MANDATORY_KEYS,
        defaults=service_columns.DEFAULT_VISIBLE_KEYS,
    ),
}


def _catalogue(view_key: str) -> ViewCatalogue:
    cat = VIEW_CATALOGUES.get(view_key)
    if cat is None:
        raise EntityNotFoundError(f"Preference view '{view_key}'")
    return cat


def _order(cat: ViewCatalogue, is_admin: bool) -> List[str]:
    return [c.id for c in cat.columns_for_caller(is_admin)]


def _shape(view_key: str, visible: List[str], is_default: bool) -> dict:
    return {"viewKey": view_key, "visibleColumns": visible, "isDefault": is_default}


def _defaults(cat: ViewCatalogue, is_admin: bool) -> List[str]:
    return [i for i in _order(cat, is_admin) if i in cat.defaults or i in cat.mandatory]


async def _stored(session: AsyncSession, user_id: str, view_key: str) -> Optional[List[str]]:
    """Stored column ids (None if nothing saved): cache first, DB on a miss."""
    stored = await preference_cache.get_columns(user_id, view_key)
    if stored is preference_cache.MISS:
        stored = await repo.get(session, user_id, view_key)
        await preference_cache.set_columns(user_id, view_key, stored)
    return stored


async def get_preference(
    session: AsyncSession, user_id: str, view_key: str, is_admin: bool
) -> dict:
    cat = _catalogue(view_key)
    stored = await _stored(session, user_id, view_key)
    if stored:
        allowed = set(_order(cat, is_admin))
        kept = {i for i in stored if i in allowed}
        if kept - cat.mandatory:
            kept |= cat.mandatory
            return _shape(view_key, [i for i in _order(cat, is_admin) if i in kept], False)
    return _shape(view_key, _defaults(cat, is_admin), True)


async def save_preference(
    session: AsyncSession, user_id: str, view_key: str, columns: List[str], is_admin: bool
) -> dict:
    cat = _catalogue(view_key)
    order = _order(cat, is_admin)
    unknown = sorted({c for c in columns if c not in order})
    if unknown:
        raise ValidationError(f"Unknown column ids for view '{view_key}': {', '.join(unknown)}")
    chosen = set(columns)
    if not chosen - cat.mandatory:
        raise ValidationError("Select at least one column besides the mandatory ones.")
    chosen |= cat.mandatory
    ordered = [i for i in order if i in chosen]
    await repo.upsert(session, user_id, view_key, ordered)
    await preference_cache.set_columns(user_id, view_key, ordered)
    return _shape(view_key, ordered, False)


async def reset_preference(
    session: AsyncSession, user_id: str, view_key: str, is_admin: bool
) -> dict:
    cat = _catalogue(view_key)
    await repo.delete_preference(session, user_id, view_key)
    await preference_cache.set_columns(user_id, view_key, None)
    return _shape(view_key, _defaults(cat, is_admin), True)
