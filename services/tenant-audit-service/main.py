import os
from contextlib import asynccontextmanager
from typing import Any, Dict, List, Optional

from fastapi import Depends, FastAPI, HTTPException, Query
from pydantic import BaseModel
from sqlalchemy import text
from sqlalchemy.ext.asyncio import AsyncEngine, AsyncSession, async_sessionmaker, create_async_engine

import dotenv

from dotenv import load_dotenv
from auth_provider import AuthProvider

load_dotenv()


DB_USER = str(os.getenv("DB_USER"))
DB_PASSWORD = str(os.getenv("DB_PASSWORD"))
DB_HOST = str(os.getenv("DB_HOST"))
DB_PORT = int(os.getenv("DB_PORT"))
DB_NAME = str(os.getenv("DB_NAME"))


SERVICE_TABLES: Dict[str, Dict[str, str]] = {
    # Core text/speech services
    "nmt": {"requests": "nmt_requests", "results": "nmt_results"},
    "tts": {"requests": "tts_requests", "results": "tts_results"},
    "asr": {"requests": "asr_requests", "results": "asr_results"},
    "ocr": {"requests": "ocr_requests", "results": "ocr_results"},
    "ner": {"requests": "ner_requests", "results": "ner_results"},
    "llm": {"requests": "llm_requests", "results": "llm_results"},
    "transliteration": {
        "requests": "transliteration_requests",
        "results": "transliteration_results",
    },
    "language_detection": {
        "requests": "language_detection_requests",
        "results": "language_detection_results",
    },
    "audio_language_detection": {
        "requests": "audio_lang_detection_requests",
        "results": "audio_lang_detection_results",
    },
    "speaker_diarization": {
        "requests": "speaker_diarization_requests",
        "results": "speaker_diarization_results",
    },
    "language_diarization": {
        "requests": "language_diarization_requests",
        "results": "language_diarization_results",
    },
}


class ServiceTableData(BaseModel):
    tenant_id: str
    schema_name: str
    service: str
    request_table: str
    result_table: str
    requests: List[Dict[str, Any]]
    results: List[Dict[str, Any]]


multi_tenant_engine: Optional[AsyncEngine] = None
multi_tenant_session_factory: Optional[async_sessionmaker[AsyncSession]] = None


@asynccontextmanager
async def lifespan(app: FastAPI):
    """
    Initialize and clean up the multi-tenant database connection.
    """
    global multi_tenant_engine, multi_tenant_session_factory

    multi_tenant_db_url = f"postgresql+asyncpg://{DB_USER}:{DB_PASSWORD}@{DB_HOST}:{DB_PORT}/{DB_NAME}"
    if not multi_tenant_db_url:
        raise RuntimeError("MULTI_TENANT_DB_URL environment variable is not set")

    multi_tenant_engine = create_async_engine(
        multi_tenant_db_url,
        pool_size=10,
        max_overflow=5,
        pool_pre_ping=True,
        echo=False,
    )

    multi_tenant_session_factory = async_sessionmaker(
        multi_tenant_engine,
        class_=AsyncSession,
        expire_on_commit=False,
    )

    try:
        # Verify we can connect to the database
        async with multi_tenant_engine.begin() as conn:
            await conn.execute(text("SELECT 1"))
        yield
    finally:
        if multi_tenant_engine:
            await multi_tenant_engine.dispose()


app = FastAPI(
    title="Tenant Audit Service",
    version="1.0.0",
    description=(
        "Service to inspect per-tenant service tables (NMT/TTS/ASR) in tenant schemas. "
        "Given a tenant_id and service name, it resolves the tenant schema and returns "
        "rows from the corresponding request/result tables."
    ),
    lifespan=lifespan,
)


async def get_multi_tenant_session() -> AsyncSession:
    if multi_tenant_session_factory is None:
        raise RuntimeError("Database session factory is not initialized")

    async with multi_tenant_session_factory() as session:
        yield session


async def resolve_schema_name_for_tenant(
    tenant_id: str,
    db: AsyncSession,
) -> str:
    """
    Look up the schema_name for a given tenant_id from the tenants table.
    """
    stmt = text(
        "SELECT schema_name FROM tenants WHERE tenant_id = :tenant_id"
    ).bindparams(tenant_id=tenant_id)

    result = await db.execute(stmt)
    schema_name = result.scalar_one_or_none()

    if not schema_name:
        raise HTTPException(
            status_code=404,
            detail=f"Tenant with tenant_id '{tenant_id}' not found",
        )

    return schema_name


async def fetch_table_rows(
    db: AsyncSession,
    schema_name: str,
    table_name: str,
) -> List[Dict[str, Any]]:
    """
    Fetch rows from a specific table within a tenant schema.
    """
    # Switch search_path to the tenant schema so we can query plain table names.
    # NOTE: search_path cannot use bound params for identifiers in PostgreSQL,
    # so we safely interpolate the schema name (it comes from our tenants table).
    await db.execute(text(f'SET search_path TO "{schema_name}", public'))

    query = text(f"SELECT * FROM {table_name} ORDER BY created_at DESC")
    result = await db.execute(query)

    return [dict(row._mapping) for row in result]


async def fetch_latest_table_rows(
    db: AsyncSession,
    schema_name: str,
    table_name: str,
) -> List[Dict[str, Any]]:
    """
    Fetch the latest row (by created_at DESC) from a specific table
    within a tenant schema.
    """
    await db.execute(text(f'SET search_path TO "{schema_name}", public'))

    query = text(f"SELECT * FROM {table_name} ORDER BY created_at DESC LIMIT 1")
    result = await db.execute(query)

    return [dict(row._mapping) for row in result]


@app.get("/api/v1/tenant-audit/health",
         dependencies=[Depends(AuthProvider)],)
async def health() -> Dict[str, str]:
    return {"status": "healthy", "service": "tenant-audit-service"}


@app.get(
    "/api/v1/tenant-audit/tenant/service/data/latest",
    response_model=ServiceTableData,
    summary="Get latest tenant service table entry",
    dependencies=[Depends(AuthProvider)],
)
async def get_tenant_service_data(
    tenant_id: str = Query(..., description="Tenant identifier"),
    service: str = Query(
        ...,
        description=(
            "Service name: one of "
            "[nmt, tts, asr, ocr, ner, llm, transliteration, "
            "language-detection, audio-lang-detection, "
            "speaker-diarization, language-diarization]"
        ),
        pattern=(
            "^(nmt|tts|asr|ocr|ner|llm|transliteration|"
            "language-detection|audio-lang-detection|"
            "speaker-diarization|language-diarization)$"
        ),
    ),
    db: AsyncSession = Depends(get_multi_tenant_session),
) -> ServiceTableData:
    """
    Given a tenant_id and service name, resolve the tenant schema and
    return only the latest entry (by created_at) from the corresponding
    request and result tables in that schema.
    """
    service = service.lower()
    if service not in SERVICE_TABLES:
        raise HTTPException(
            status_code=400,
            detail=(
                f"Unsupported service '{service}'. "
                f"Supported values are: {', '.join(SERVICE_TABLES.keys())}"
            ),
        )

    tables = SERVICE_TABLES[service]
    schema_name = await resolve_schema_name_for_tenant(tenant_id=tenant_id, db=db)

    requests = await fetch_latest_table_rows(
        db=db,
        schema_name=schema_name,
        table_name=tables["requests"],
    )

    results = await fetch_latest_table_rows(
        db=db,
        schema_name=schema_name,
        table_name=tables["results"],
    )

    return ServiceTableData(
        tenant_id=tenant_id,
        schema_name=schema_name,
        service=service,
        request_table=tables["requests"],
        result_table=tables["results"],
        requests=requests,
        results=results,
    )


@app.get(
    "/api/v1/tenant-audit/tenant/service/data/all",
    response_model=ServiceTableData,
    summary="Get all tenant service table data",
    dependencies=[Depends(AuthProvider)],
)
async def list_tenant_service_data(
    tenant_id: str = Query(..., description="Tenant identifier"),
    service: str = Query(
        ...,
        description=(
            "Service name: one of "
            "[nmt, tts, asr, ocr, ner, llm, transliteration, "
            "language-detection, audio-lang-detection, "
            "speaker-diarization, language-diarization]"
        ),
        pattern=(
            "^(nmt|tts|asr|ocr|ner|llm|transliteration|"
            "language-detection|audio-lang-detection|"
            "speaker-diarization|language-diarization)$"
        ),
    ),
    db: AsyncSession = Depends(get_multi_tenant_session),
) -> ServiceTableData:
    """
    Given a tenant_id and service name, resolve the tenant schema and
    return all entries from the corresponding request and result tables
    in that schema (ordered by created_at DESC).
    """
    service = service.lower()
    if service not in SERVICE_TABLES:
        raise HTTPException(
            status_code=400,
            detail=(
                f"Unsupported service '{service}'. "
                f"Supported values are: {', '.join(SERVICE_TABLES.keys())}"
            ),
        )

    tables = SERVICE_TABLES[service]
    schema_name = await resolve_schema_name_for_tenant(tenant_id=tenant_id, db=db)

    requests = await fetch_table_rows(
        db=db,
        schema_name=schema_name,
        table_name=tables["requests"],
    )

    results = await fetch_table_rows(
        db=db,
        schema_name=schema_name,
        table_name=tables["results"],
    )

    return ServiceTableData(
        tenant_id=tenant_id,
        schema_name=schema_name,
        service=service,
        request_table=tables["requests"],
        result_table=tables["results"],
        requests=requests,
        results=results,
    )


if __name__ == "__main__":
    import uvicorn

    uvicorn.run("main:app", host="0.0.0.0", port=9003, reload=True)

