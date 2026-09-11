"""One-off QA script — fires QUOTA_THRESHOLD/BUDGET_THRESHOLD/QUOTA_EXHAUSTED/
BUDGET_EXHAUSTED exactly the way payperuse_consumer's
_publish_usage_crossing_events does, without needing a real inference
request. Run from services/kafka-consumers with its .venv active:

    python _qa_publish_usage_events.py

Delete this file when you're done testing — it's not part of the service.
"""
import asyncio
import os
import sys

from sqlalchemy.ext.asyncio import create_async_engine, async_sessionmaker

sys.path.insert(0, os.path.dirname(__file__))  # so `bootstrap`/`consumers` resolve
from bootstrap.config import get_db_settings, get_kafka_settings
from ai4i_core.kafka import (
    init_kafka_producer,
    close_kafka_producer,
    check_and_record_threshold,
    check_and_record_exhaustion,
    publish_event,
)

TENANT_ID = "2"
SUBJECT = {"model_task_type": "nmt"}


async def main() -> None:
    db_settings = get_db_settings()
    kafka_settings = get_kafka_settings()

    init_kafka_producer(
        bootstrap_servers=kafka_settings.KAFKA_SERVER,
        topic="notification.events",
        enabled=True,
    )

    engine = create_async_engine(db_settings.get_database_url(db_settings.PLATFORM_CORE_DB))
    session_factory = async_sessionmaker(engine, expire_on_commit=False)

    async with session_factory() as db:
        # QUOTA_THRESHOLD — band 75
        if await check_and_record_threshold(db, "QUOTA_THRESHOLD", TENANT_ID, SUBJECT, 75):
            publish_event(
                event_name="QUOTA_THRESHOLD", tenant_id=TENANT_ID, subject=SUBJECT,
                details={"observed": 7500, "limit": 10000, "percent": 75, "inference_name": "nmt"},
            )
            print("Published QUOTA_THRESHOLD @ 75%")
        else:
            print("QUOTA_THRESHOLD @ 75% already recorded — skipped (expected on a re-run)")

        # BUDGET_THRESHOLD — band 80
        if await check_and_record_threshold(db, "BUDGET_THRESHOLD", TENANT_ID, {}, 80):
            publish_event(
                event_name="BUDGET_THRESHOLD", tenant_id=TENANT_ID, subject={},
                details={"observed": 80000, "limit": 100000, "percent": 80},
            )
            print("Published BUDGET_THRESHOLD @ 80%")
        else:
            print("BUDGET_THRESHOLD @ 80% already recorded — skipped (expected on a re-run)")

        # QUOTA_EXHAUSTED
        if await check_and_record_exhaustion(db, "QUOTA_EXHAUSTED", TENANT_ID, SUBJECT):
            publish_event(
                event_name="QUOTA_EXHAUSTED", tenant_id=TENANT_ID, subject=SUBJECT,
                details={"inference_name": "nmt"},
            )
            print("Published QUOTA_EXHAUSTED")
        else:
            print("QUOTA_EXHAUSTED already recorded — skipped (expected on a re-run)")

        # BUDGET_EXHAUSTED
        if await check_and_record_exhaustion(db, "BUDGET_EXHAUSTED", TENANT_ID, {}):
            publish_event(
                event_name="BUDGET_EXHAUSTED", tenant_id=TENANT_ID, subject={},
                details={},
            )
            print("Published BUDGET_EXHAUSTED")
        else:
            print("BUDGET_EXHAUSTED already recorded — skipped (expected on a re-run)")

    close_kafka_producer()
    await asyncio.sleep(1)  # let the producer's background sender thread flush
    await engine.dispose()


if __name__ == "__main__":
    asyncio.run(main())
