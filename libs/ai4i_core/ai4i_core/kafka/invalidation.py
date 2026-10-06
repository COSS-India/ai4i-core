"""Pub/Sub invalidation on ntf:v1:invalidate.

Writers change the DB, SET the new value in Redis, then PUBLISH one message.
Every process runs one listener that drops the matching L1 entries, so its
next read is one Redis GET. A process ignores its own messages, drops all L1
on a message it cannot parse, and drops all L1 after every (re)subscribe,
because messages sent while it was disconnected are lost.
"""

import asyncio
import json
import logging
import os
from dataclasses import dataclass
from typing import Callable, Optional, Sequence, Tuple

from . import constants as c
from .constants import InvalidationKind
from .keys import iso_z, utc_now

logger = logging.getLogger(__name__)


@dataclass(frozen=True)
class InvalidationMessage:
    kind: InvalidationKind
    names: Tuple[str, ...]
    tenant_id: Optional[str]
    keys: Tuple[str, ...]
    origin: str
    ts: str


def origin_of(service: str, pod_name: Optional[str]) -> str:
    """{service}/{pod}/pid-{pid} — identifies the sending process."""
    return f"{service}/{pod_name or 'local'}/pid-{os.getpid()}"


def build_message(
    kind: InvalidationKind,
    origin: str,
    *,
    names: Sequence[str] = (),
    tenant_id: Optional[str] = None,
    keys: Sequence[str] = (),
) -> str:
    return json.dumps(
        {
            "v": c.INVALIDATION_MESSAGE_VERSION,
            "kind": kind.value,
            "names": [n.value if hasattr(n, "value") else str(n) for n in names],
            "tenant_id": tenant_id,
            "keys": list(keys),
            "origin": origin,
            "ts": iso_z(utc_now()),
        }
    )


def parse_message(raw) -> Optional[InvalidationMessage]:
    """None when the message cannot be parsed."""
    try:
        if isinstance(raw, bytes):
            raw = raw.decode("utf-8")
        data = json.loads(raw)
        if data.get("v") != c.INVALIDATION_MESSAGE_VERSION:
            return None
        return InvalidationMessage(
            kind=InvalidationKind(data["kind"]),
            names=tuple(str(n) for n in data.get("names") or ()),
            tenant_id=str(data["tenant_id"]) if data.get("tenant_id") is not None else None,
            keys=tuple(str(k) for k in data.get("keys") or ()),
            origin=str(data["origin"]),
            ts=str(data.get("ts") or ""),
        )
    except Exception:
        return None


class InvalidationListener:
    """One subscriber connection per process, reconnecting with backoff."""

    def __init__(
        self,
        redis,
        origin: str,
        on_message: Callable[[InvalidationMessage], None],
        on_drop_all: Callable[[], None],
    ):
        self._redis = redis
        self._origin = origin
        self._on_message = on_message
        self._on_drop_all = on_drop_all
        self._task: Optional[asyncio.Task] = None

    def start(self) -> None:
        if self._task is None or self._task.done():
            self._task = asyncio.create_task(self._run(), name="notification_invalidation_listener")

    async def stop(self) -> None:
        if self._task is not None and not self._task.done():
            self._task.cancel()
            await asyncio.gather(self._task, return_exceptions=True)
        self._task = None

    def handle(self, raw) -> None:
        message = parse_message(raw)
        if message is None:
            logger.warning("Unparseable notification invalidation message; dropping all L1 entries")
            self._on_drop_all()
            return
        if message.origin == self._origin:
            return
        self._on_message(message)

    async def _run(self) -> None:
        backoff = c.LISTENER_RECONNECT_MIN_S
        while True:
            pubsub = self._redis.pubsub()
            try:
                await pubsub.subscribe(c.INVALIDATION_CHANNEL)
                # Anything sent while disconnected is lost.
                self._on_drop_all()
                backoff = c.LISTENER_RECONNECT_MIN_S
                logger.info("Notification invalidation listener subscribed to %s", c.INVALIDATION_CHANNEL)
                # Short polls, not listen(): a shared client's socket_timeout
                # would end a blocking read on a quiet channel and force a
                # reconnect (and an L1 drop) every few seconds.
                while True:
                    item = await pubsub.get_message(
                        ignore_subscribe_messages=True, timeout=c.LISTENER_POLL_TIMEOUT_S
                    )
                    if item is not None and item.get("type") == "message":
                        self.handle(item.get("data"))
            except asyncio.CancelledError:
                raise
            except Exception as exc:
                logger.warning("Notification invalidation listener error, reconnecting in %ss: %s", backoff, exc)
                await asyncio.sleep(backoff)
                backoff = min(backoff * 2, c.LISTENER_RECONNECT_MAX_S)
            finally:
                try:
                    await pubsub.aclose()
                except Exception:
                    pass
