"""
NMT database reader.

Provides a read-only async connection to the NMT service's database
(AUTH_DB / auth_service_v2_db) so the feedback service can pull
source + translated text for LLM evaluation without requiring the
NMT service to push anything.

Connection is lazily initialised on first use from the NMT_DB_URL
environment variable and reused for the lifetime of the process.
"""

import logging
import os
import re
from typing import List

from sqlalchemy import text
from sqlalchemy.ext.asyncio import AsyncSession, async_sessionmaker, create_async_engine

logger = logging.getLogger(__name__)

_nmt_engine = None
_nmt_session_factory = None

# Allowlist for schema names — prevents SQL injection in SET search_path.
_SAFE_SCHEMA_RE = re.compile(r'^[a-z0-9_]+$')


def _get_nmt_session_factory() -> async_sessionmaker:
    global _nmt_engine, _nmt_session_factory
    if _nmt_session_factory is None:
        nmt_db_url = os.getenv("NMT_DB_URL")
        if not nmt_db_url:
            raise RuntimeError(
                "NMT_DB_URL environment variable is not set. "
                "Set it to the postgresql+asyncpg:// URL of the NMT auth DB."
            )
        _nmt_engine = create_async_engine(
            nmt_db_url,
            pool_size=3,
            max_overflow=3,
            pool_pre_ping=True,
            echo=False,
        )
        _nmt_session_factory = async_sessionmaker(
            _nmt_engine,
            class_=AsyncSession,
            expire_on_commit=False,
        )
        logger.info("NMT DB connection pool initialised.")
    return _nmt_session_factory


async def fetch_nmt_records(
    limit: int, offset: int = 0, schema_name: str | None = None
) -> List[dict]:
    """
    Fetch recent completed NMT translations from the NMT database.

    Queries nmt_requests JOIN nmt_results, returning only rows where:
    - status is not 'processing' or 'error'
    - source_text and translated_text are both present

    schema_name: if the NMT tables live in a tenant-specific PostgreSQL schema,
    pass the schema name here so search_path is set before the query runs.

    Returns a list of dicts with keys:
        trace_id, source_text, translated_text,
        source_language, target_language, model_id, created_at
    """
    factory = _get_nmt_session_factory()
    async with factory() as db:
        if schema_name:
            if _SAFE_SCHEMA_RE.match(schema_name):
                await db.execute(text(f'SET search_path TO "{schema_name}", public'))
            else:
                logger.warning(
                    "Unsafe NMT schema_name rejected: %r — using default search_path",
                    schema_name,
                )
        result = await db.execute(
            text("""
                SELECT
                    nrq.id::text          AS trace_id,
                    nr.source_text        AS source_text,
                    nr.translated_text    AS translated_text,
                    nrq.source_language   AS source_language,
                    nrq.target_language   AS target_language,
                    nrq.model_id          AS model_id,
                    nrq.created_at        AS created_at
                FROM nmt_requests nrq
                JOIN nmt_results  nr ON nr.request_id = nrq.id
                WHERE nrq.status NOT IN ('processing', 'error')
                  AND nr.source_text    IS NOT NULL
                  AND nr.translated_text IS NOT NULL
                ORDER BY nrq.created_at DESC
                LIMIT  :limit
                OFFSET :offset
            """),
            {"limit": limit, "offset": offset},
        )
        rows = result.mappings().all()
        return [dict(row) for row in rows]
