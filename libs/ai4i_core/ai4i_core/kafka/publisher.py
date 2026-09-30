"""Envelope v2 and the fire-and-forget hand-off to notification.events.

The producer does not wait for a Kafka acknowledgement. send() blocks for at
most max_block_ms when the broker is unreachable, so it runs on a worker
thread. If the send call itself fails, one PUBLISH failure row is written; a
delivery error reported later reaches only the service log. After the
hand-off, delivery is the consumer's job, keyed by event_id.
"""

import asyncio
import logging
import uuid
from dataclasses import dataclass, field
from datetime import datetime
from typing import Any, Dict, List, Mapping, Optional, Sequence

from . import constants as c
from . import metrics
from .constants import FailureCode, FailureStage, NotificationName, NotificationType, Operation, PublishResult, Severity
from .failure_log import FailureLogger
from .keys import kafka_message_key
from .models import Band, Measurement, Recipient
from .producer import get_kafka_producer_client

logger = logging.getLogger(__name__)


@dataclass(frozen=True)
class Envelope:
    event_id: uuid.UUID
    event_name: NotificationName
    notification_type: NotificationType
    tenant_id: str
    tenant_name: Optional[str]
    subject: Mapping[str, str]
    occurred_at: datetime
    channels: Sequence[str]
    severity: Severity
    details: Sequence[Any]
    recipients: Sequence[Recipient]
    band: Optional[Band] = None
    observed: Optional[Measurement] = None
    #: A grouped event's member subjects (its own subject is empty), so each
    #: failure row names one of them. Empty for a single-subject event.
    subjects: Sequence[Mapping[str, str]] = ()
    #: Carried into a PUBLISH failure row; not part of the message.
    state_hash: Optional[str] = field(default=None, compare=False)

    @property
    def key(self) -> str:
        return kafka_message_key(self.event_name, self.tenant_id, self.subject)

    @property
    def failure_subjects(self) -> List[Mapping[str, str]]:
        """The subject of each failure row this event writes: one per member
        of a grouped event, else its own."""
        return list(self.subjects) or [self.subject]

    def to_json(self) -> Dict[str, Any]:
        data = {
            "schema_version": c.ENVELOPE_SCHEMA_VERSION,
            "event_id": str(self.event_id),
            "event_name": self.event_name.value,
            "notification_type": self.notification_type.value,
            "tenant_id": self.tenant_id,
            "tenant_name": self.tenant_name,
            "subject": dict(self.subject),
            "occurred_at": self.occurred_at.isoformat(timespec="milliseconds"),
            "channels": list(self.channels),
            "severity": self.severity.value,
            "band": self.band.value_unit() if self.band is not None else None,
            "observed": self.observed.to_json() if self.observed is not None else None,
            "details": list(self.details),
            "recipients": [r.to_json() for r in self.recipients],
        }
        # Only a grouped event carries it, so a single-subject message is unchanged.
        if self.subjects:
            data["subjects"] = [dict(s) for s in self.subjects]
        return data


class Publisher:
    def __init__(self, topic: str, failure_log: FailureLogger):
        self._topic = topic
        self._failures = failure_log

    @property
    def topic(self) -> str:
        return self._topic

    async def send(self, envelope: Envelope, *, notification_id: Optional[int]) -> bool:
        """Hand one event to Kafka. True when the send call succeeded."""
        name = envelope.event_name.value
        value = envelope.to_json()
        key = envelope.key.encode("utf-8")
        try:
            producer = get_kafka_producer_client()
            loop = asyncio.get_running_loop()
            future = await loop.run_in_executor(
                None, lambda: producer.send(self._topic, value=value, key=key)
            )
        except Exception as exc:
            metrics.PUBLISHES.labels(name, PublishResult.FAILED.value).inc()
            for subject in envelope.failure_subjects:
                await self._failures.record(
                    FailureStage.PUBLISH, FailureCode.KAFKA_SEND_FAILED,
                    notification_name=name, notification_id=notification_id, tenant_id=envelope.tenant_id,
                    subject=subject, event_id=envelope.event_id, operation=Operation.KAFKA_SEND,
                    error=exc, kafka_topic=self._topic,
                    observed=envelope.observed.to_json() if envelope.observed else None,
                    band=envelope.band.value_unit() if envelope.band else None,
                    state_hash=envelope.state_hash,
                )
            return False
        try:
            future.add_errback(
                lambda exc: logger.warning(
                    "Kafka delivery failed for notification event %s (%s): %s", envelope.event_id, name, exc
                )
            )
        except Exception:
            pass
        metrics.PUBLISHES.labels(name, PublishResult.SENT.value).inc()
        return True
