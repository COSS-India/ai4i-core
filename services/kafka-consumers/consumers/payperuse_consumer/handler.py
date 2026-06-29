import json

from consumers.registry import kafka_listener


@kafka_listener("my_topic")
async def handle_my_topic(msg) -> None:
    payload = json.loads(msg.value)
    # TODO: process payload
