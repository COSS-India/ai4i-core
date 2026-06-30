from confluent_kafka.cimpl import Message
from sqlalchemy import text

from ai4i_core.logging import get_logger
from config import settings
from consumers.registry import kafka_listener
from db_registry import db_registry

logger = get_logger(__name__)


async def _check_db(db_name: str) -> None:
    """Run SELECT 1 against the named database and log the result."""
    try:
        async with db_registry.get_session(db_name) as session:
            await session.execute(text("SELECT 1"))
        logger.info("DB connectivity check passed | db=%s status=ok", db_name)
    except Exception as exc:
        logger.error("DB connectivity check failed | db=%s error=%s", db_name, exc)


@kafka_listener(settings.topics.TOPIC_PAY_PER_USE)
async def handle_ppu_usage(msg: Message) -> None:
    payload = msg.value()
    logger.info(
        "Message received | topic=%s partition=%d offset=%d size=%d bytes",
        msg.topic(),
        msg.partition(),
        msg.offset(),
        len(payload) if payload else 0,
    )
    
