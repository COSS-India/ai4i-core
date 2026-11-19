"""Application name lookups in auth_db for the Logs Dashboard.

Spans carry only the application id (attributes.app_id, a string), so the
dashboard resolves names here at read time.
"""
from typing import Iterable, Optional

from sqlalchemy import text
from sqlalchemy.ext.asyncio import AsyncSession


def _escape_like(value: str) -> str:
    return value.replace("\\", "\\\\").replace("%", "\\%").replace("_", "\\_")


async def find_application_ids_by_name(
    auth_db: AsyncSession, name: str, tenant_id: Optional[str]
) -> list[str]:
    """Ids of applications whose name contains ``name`` (case-insensitive),
    limited to ``tenant_id`` when given."""
    sql = "SELECT id FROM applications WHERE name ILIKE :pattern"
    params: dict = {"pattern": f"%{_escape_like(name)}%"}
    if tenant_id is not None:
        if not tenant_id.isdecimal():
            return []
        sql += " AND tenant_id = :tenant_id"
        params["tenant_id"] = int(tenant_id)
    result = await auth_db.execute(text(sql), params)
    return [str(row.id) for row in result]


async def application_names_by_id(auth_db: AsyncSession, ids: Iterable[str]) -> dict[str, str]:
    """Map of application id to name for the given ids; unknown ids are absent."""
    numeric_ids = sorted({int(i) for i in ids if i.isdecimal()})
    if not numeric_ids:
        return {}
    result = await auth_db.execute(
        text("SELECT id, name FROM applications WHERE id = ANY(:ids)"), {"ids": numeric_ids}
    )
    return {str(row.id): row.name for row in result}
