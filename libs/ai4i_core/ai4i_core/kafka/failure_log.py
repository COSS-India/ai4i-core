"""Write-once failure log (notification_alert_failure_log).

Q-F1 runs on its own short session, so a rolled-back caller transaction never
drops it, and it never raises. Failures without an event_id are throttled to
one row per (producer, stage, error_code, notification_name, tenant_id) per
window per process; the count skipped in between goes into
error_detail.suppressed of the next row. Failures with an event_id are never
throttled: each one is a lost event.
"""

import contextlib
import contextvars
import logging
import time
import uuid
from typing import Any, Callable, Dict, Mapping, Optional, Tuple

from sqlalchemy import text

from . import constants as c
from . import metrics
from .constants import FailureCode, FailureStage, Operation, Producer
from .keys import canonical_json

logger = logging.getLogger(__name__)


def _qualified_name(error: BaseException) -> str:
    """e.g. asyncpg.exceptions.ConnectionDoesNotExistError; builtins stay bare."""
    kind = type(error)
    return kind.__qualname__ if kind.__module__ == "builtins" else f"{kind.__module__}.{kind.__qualname__}"


#: A component running inside another producer's process (the monitoring
#: evaluator inside platform-core) records its failures under its own name.
_producer_override: contextvars.ContextVar[Optional[Producer]] = contextvars.ContextVar(
    "notification_failure_producer", default=None
)


@contextlib.contextmanager
def producer_scope(producer: Producer):
    token = _producer_override.set(Producer(producer))
    try:
        yield
    finally:
        _producer_override.reset(token)

WRITE_FAILED_EVENT = "notification.failure_log.write_failed"

# Q-F1
_INSERT_SQL = text(
    """
    INSERT INTO notification_alert_failure_log
           (event_id, notification_name, notification_id, tenant_id, subject,
            producer, pod_name, stage, error_code, error_message, error_detail)
    VALUES (:event_id, :notification_name, :notification_id, :tenant_id, CAST(:subject AS JSONB),
            :producer, :pod_name, :stage, :error_code, :error_message, CAST(:error_detail AS JSONB))
    """
)

# Q-F5
_PURGE_SQL = text(
    """
    DELETE FROM notification_alert_failure_log
     WHERE created_at < now() - make_interval(days => :retention_days)
    """
)


def _truncate(value: Optional[str]) -> str:
    return (value or "")[: c.ERROR_MESSAGE_MAX_CHARS]


def _trace_id() -> Optional[str]:
    try:
        from opentelemetry import trace

        context = trace.get_current_span().get_span_context()
        return format(context.trace_id, "032x") if context.is_valid else None
    except Exception:
        return None


def _name(value) -> str:
    return value.value if hasattr(value, "value") else str(value)


class FailureLogger:
    def __init__(
        self,
        session_factory,
        producer: Producer,
        pod_name: Optional[str],
        throttle_s: int,
        clock: Callable[[], float] = time.monotonic,
    ):
        self._session_factory = session_factory
        self._producer = producer
        self._pod_name = pod_name
        self._throttle_s = throttle_s
        self._clock = clock
        # throttle key -> (last written at, suppressed since)
        self._throttle: Dict[Tuple[str, ...], Tuple[float, int]] = {}

    def _admit(self, key: Tuple[str, ...], window_s: int) -> Optional[int]:
        """None when this failure is suppressed; else the suppressed count to
        report on the row being written."""
        now = self._clock()
        last = self._throttle.get(key)
        if last is not None and now - last[0] < window_s:
            self._throttle[key] = (last[0], last[1] + 1)
            return None
        suppressed = last[1] if last is not None else 0
        self._throttle[key] = (now, 0)
        return suppressed

    async def record(
        self,
        stage: FailureStage,
        code: FailureCode,
        *,
        notification_name,
        operation: Operation,
        error: Optional[BaseException] = None,
        message: Optional[str] = None,
        notification_id: Optional[int] = None,
        tenant_id: Optional[str] = None,
        subject: Optional[Mapping[str, Any]] = None,
        event_id: Optional[uuid.UUID] = None,
        redis_key: Optional[str] = None,
        kafka_topic: Optional[str] = None,
        observed: Optional[Mapping[str, Any]] = None,
        band: Optional[Mapping[str, Any]] = None,
        state_hash: Optional[str] = None,
        throttle_s: Optional[int] = None,
    ) -> None:
        """Write one failure row. Never raises."""
        try:
            name = _name(notification_name)
            producer = _producer_override.get() or self._producer
            suppressed = 0
            if event_id is None:
                key = (producer.value, stage.value, code.value, name, str(tenant_id or ""))
                admitted = self._admit(key, self._throttle_s if throttle_s is None else throttle_s)
                if admitted is None:
                    return
                suppressed = admitted

            text_message = _truncate(message if message is not None else (str(error) if error else code.value))
            detail = {
                "exception": _qualified_name(error) if error is not None else code.value,
                "message": text_message,
                "operation": operation.value,
                "redis_key": redis_key,
                "kafka_topic": kafka_topic,
                "observed": dict(observed) if observed is not None else None,
                "band": dict(band) if band is not None else None,
                "state_hash": state_hash,
                "suppressed": suppressed,
                "trace_id": _trace_id(),
            }
            params = {
                "event_id": event_id,
                "notification_name": name,
                "notification_id": notification_id,
                "tenant_id": str(tenant_id) if tenant_id is not None else None,
                "subject": canonical_json(dict(subject)) if subject is not None else None,
                "producer": producer.value,
                "pod_name": self._pod_name,
                "stage": stage.value,
                "error_code": code.value,
                "error_message": text_message,
                "error_detail": canonical_json(detail),
            }
        except Exception:
            logger.exception("Could not build a notification failure row (%s %s)", stage, code)
            return

        metrics.FAILURES.labels(stage.value, code.value).inc()
        try:
            async with self._session_factory() as session:
                await session.execute(_INSERT_SQL, params)
                await session.commit()
        except Exception:
            logger.error(WRITE_FAILED_EVENT, extra={"failure_row": params}, exc_info=True)


async def purge_failures(session, retention_days: int) -> int:
    """Q-F5: delete failure rows older than the retention window."""
    result = await session.execute(_PURGE_SQL, {"retention_days": retention_days})
    return result.rowcount or 0
