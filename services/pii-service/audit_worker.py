import asyncio
import os
import json
import asyncpg
from aiokafka import AIOKafkaConsumer
from pathlib import Path

from dotenv import load_dotenv

_SERVICE_DIR = Path(__file__).resolve().parent
load_dotenv(_SERVICE_DIR / ".env")

DB_HOST = os.getenv("DB_HOST", "postgres")
DB_NAME = os.getenv("DB_NAME", "pii_guardrail")
DB_USER = os.getenv("DB_USER", "admin")
DB_PASS = os.getenv("DB_PASS", "secret")

KAFKA_BOOTSTRAP_SERVERS = os.getenv("KAFKA_BOOTSTRAP_SERVERS", "localhost:9092")
KAFKA_AUDIT_TOPIC = os.getenv("KAFKA_AUDIT_TOPIC", "pii_audit_logs")


async def consume_and_insert():
    pool = await asyncpg.create_pool(user=DB_USER, password=DB_PASS, database=DB_NAME, host=DB_HOST)
    consumer = AIOKafkaConsumer(
        KAFKA_AUDIT_TOPIC,
        bootstrap_servers=KAFKA_BOOTSTRAP_SERVERS,
        group_id="pii_audit_group",
        auto_offset_reset="earliest",
    )

    await consumer.start()
    try:
        async for msg in consumer:
            data = json.loads(msg.value.decode("utf-8"))
            try:
                async with pool.acquire() as conn:
                    await conn.execute(
                        "INSERT INTO audit_logs (trace_id, tenant_id, domain_id, target_context, pii_count, processing_ms, trace_json) VALUES ($1, $2, $3, $4, $5, $6, $7)",
                        data.get("trace_id"),
                        data.get("tenant_id"),
                        data.get("domain_id"),
                        data.get("target_context"),
                        data.get("pii_count"),
                        data.get("processing_ms"),
                        json.dumps(data.get("trace_json", [])),
                    )
            except Exception as db_err:
                print(f"DB insert error: {db_err}")
    finally:
        await consumer.stop()
        await pool.close()


if __name__ == "__main__":
    asyncio.run(consume_and_insert())
