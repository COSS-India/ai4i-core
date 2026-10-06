"""Delivery failures -> notification_alert_failure_log, one row per event
that reached no recipient on any channel (one per member subject of a
grouped event, so each row names its service).

Written through ai4i_core.kafka's FailureLogger, the same writer the
producers use, so a consumer row has the same shape as theirs: producer
'notifications-consumer', stage DELIVERY. It writes on its own short
session and never raises. The row carries the envelope's identifying
fields as sent: nothing is looked up, so notification_id stays NULL.
"""
from __future__ import annotations

import os
import uuid
from functools import lru_cache
from typing import Any, List, Mapping, Optional

from ai4i_core.kafka import FailureCode, FailureStage, Operation, Producer
from ai4i_core.kafka.constants import DEFAULT_FAILURE_THROTTLE_S
from ai4i_core.kafka.failure_log import FailureLogger

from bootstrap.lifecycle import session_scope

#: notification_name is NOT NULL; an envelope without event_name gets this.
UNKNOWN_NOTIFICATION = "UNKNOWN"


@lru_cache(maxsize=1)
def _failure_logger() -> FailureLogger:
    return FailureLogger(
        session_scope,
        Producer.NOTIFICATIONS_CONSUMER,
        os.getenv("POD_NAME") or os.getenv("HOSTNAME"),
        DEFAULT_FAILURE_THROTTLE_S,
    )


def _mapping(value: Any) -> Optional[Mapping[str, Any]]:
    return value if isinstance(value, Mapping) else None


def _subjects(envelope: Mapping[str, Any]) -> List[Optional[Mapping[str, Any]]]:
    """One per row: a grouped event's member subjects (its own is empty), so
    each row names one of them; otherwise its own subject."""
    members = envelope.get("subjects")
    members = [m for m in members if isinstance(m, Mapping)] if isinstance(members, list) else []
    return members or [_mapping(envelope.get("subject"))]


def _event_id(value: Any) -> Optional[uuid.UUID]:
    """event_id is a UUID column; a value that isn't one is left out."""
    try:
        return uuid.UUID(str(value))
    except ValueError:
        return None


async def record(
    envelope: Mapping[str, Any],
    code: FailureCode,
    *,
    kafka_topic: Optional[str],
    operation: Operation = Operation.EMAIL_SEND,
    message: Optional[str] = None,
    error: Optional[BaseException] = None,
) -> None:
    for subject in _subjects(envelope):
        await _failure_logger().record(
            FailureStage.DELIVERY,
            code,
            notification_name=envelope.get("event_name") or UNKNOWN_NOTIFICATION,
            operation=operation,
            error=error,
            message=message,
            tenant_id=envelope.get("tenant_id"),
            subject=subject,
            event_id=_event_id(envelope.get("event_id")),
            kafka_topic=kafka_topic,
            observed=_mapping(envelope.get("observed")),
            band=_mapping(envelope.get("band")),
        )
