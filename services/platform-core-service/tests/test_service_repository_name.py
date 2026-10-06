"""app/repositories/model_management/service_repository.py — get_name_by_service_id.

Built from the Service model, so a renamed table or column fails here
rather than only when a monitoring alert fires. No deleted_at filter: a
soft-deleted service keeps its name in monitoring emails.
"""

from __future__ import annotations

from types import SimpleNamespace

import pytest
from sqlalchemy.dialects import postgresql

from app.repositories.model_management.service_repository import ServiceRepository


class _Session:
    def __init__(self, name):
        self.name = name
        self.statements = []

    async def execute(self, statement):
        self.statements.append(statement)
        return SimpleNamespace(scalar_one_or_none=lambda: self.name)


@pytest.mark.asyncio
async def test_reads_only_the_name_by_service_id_including_soft_deleted():
    session = _Session("indictrans-gpu-t4")

    assert await ServiceRepository(session).get_name_by_service_id("de9a4570") == "indictrans-gpu-t4"

    (statement,) = session.statements
    sql = str(statement.compile(dialect=postgresql.dialect(), compile_kwargs={"literal_binds": True}))
    assert sql.split() == "SELECT mm_services.name FROM mm_services WHERE mm_services.service_id = 'de9a4570'".split()


@pytest.mark.asyncio
async def test_no_row_gives_none():
    assert await ServiceRepository(_Session(None)).get_name_by_service_id("missing") is None
