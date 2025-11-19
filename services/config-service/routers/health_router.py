import asyncio
from fastapi import APIRouter, HTTPException
from sqlalchemy import text


router = APIRouter()


@router.get("/health")
async def health():
    from main import redis_client, db_engine, kafka_producer, registry_client  # type: ignore
    try:
        if redis_client:
            await redis_client.ping()
            redis_status = "healthy"
        else:
            redis_status = "unhealthy"

        if db_engine:
            async with db_engine.begin() as conn:
                await conn.execute(text("SELECT 1"))
            postgres_status = "healthy"
        else:
            postgres_status = "unhealthy"

        kafka_status = "healthy" if kafka_producer else "unhealthy"
        zk_status = "healthy" if registry_client and await registry_client.health_check() else "unhealthy"

        overall = "healthy" if all(s == "healthy" for s in [redis_status, postgres_status, kafka_status, zk_status]) else "unhealthy"
        return {
            "status": overall,
            "redis": redis_status,
            "postgres": postgres_status,
            "kafka": kafka_status,
            "zookeeper": zk_status,
            "timestamp": asyncio.get_event_loop().time()
        }
    except Exception:
        raise HTTPException(status_code=503, detail="Service unhealthy")


@router.get("/ready")
async def ready():
    from main import redis_client, db_engine  # type: ignore
    if not redis_client or not db_engine:
        raise HTTPException(status_code=503, detail="Not ready")
    return {"status": "ready"}


@router.get("/live")
async def live():
    return {"status": "alive"}


