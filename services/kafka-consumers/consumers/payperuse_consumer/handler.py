from confluent_kafka.cimpl import Message

from config import settings
from consumers.registry import kafka_listener


@kafka_listener(settings.topics.TOPIC_PAY_PER_USE)
async def handle_ppu_usage(msg: Message) -> None:
    payload = msg.value()
    # TODO: process payload
    print(payload)

    # raise UltimatelyDLQException("Example DLQ push")

