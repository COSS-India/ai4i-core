"""One-off manual test: publishes a single hand-built envelope straight onto
notification.events, bypassing every producer entirely. Matches the current
array-based `details` contract — design doc §9.5.

Run from services/kafka-consumers with its .venv active:

    python _mock_produce.py

Edit EVENT_NAME/TENANT_ID/DETAILS below to test a different one of the 9
events — swap DETAILS for the exact ordered list §9.5 specifies for that
event_name. Delete this file when you're done testing; it's not part of the
service.
"""
import json
import time

from kafka import KafkaProducer

BROKER = "localhost:9093"
TOPIC = "notification.events"

EVENT_NAME = "TIER_CHANGED"
TENANT_ID = "2"

envelope = {
    "event_name": EVENT_NAME,
    "tenant_id": TENANT_ID,
    "occurred_at": "2026-09-15T10:00:00+00:00",
    "subject": {},
    "details": [
        "Silver",                                          # current_tier_name
        "Gold",                                             # new_tier_name
        "High-volume tier",                                 # new_tier_description
        ["ASR: 10,000 req/mo", "NMT: 5,000 req/mo"],         # quota_lines
        "1000",                                             # new_rate_limit_value
        "2026-09-10",                                        # effective_from
        "2027-09-09",                                        # effective_to
    ],
    "actor_id": None,
}

producer = KafkaProducer(
    bootstrap_servers=BROKER,
    value_serializer=lambda v: json.dumps(v).encode("utf-8"),
)
producer.send(TOPIC, envelope)
producer.flush()
time.sleep(1)
print(f"Published {EVENT_NAME} for tenant {TENANT_ID}: {json.dumps(envelope)}")
