"""ManagedConsumer — a confluent_kafka.Consumer that knows its own group, topic
and poll settings, and exposes async wrappers over librdkafka's blocking calls.

bootstrap/ owns CONSTRUCTION and POLLING.  It does not own the loop: retry,
error classification and drain behaviour stay with each consumer's run(), so
one consumer's policy never has to be negotiated with the others (§3.5).

Three implementation caveats, all verified against confluent-kafka 2.15.0:

  * Consumer is a C extension type (confluent_kafka.cimpl.Consumer) and
    subclassing it WORKS: pass the config dict as the sole positional argument
    to super().__init__() (plus the genuine `logger=` kwarg), then assign
    attributes and define methods normally.  Do not try to forward custom
    keyword arguments through to the base type.

  * Do NOT shadow inherited method names.  poll, consume, commit, store_offsets,
    subscribe, assign, seek, pause, resume, position, committed and close all
    come from the C type — hence consume_batch / store_processed / commit_stored
    / shutdown, each delegating to the inherited call of the obvious name.
    Overriding commit or store_offsets with an async method would break every
    internal caller expecting the synchronous one, including librdkafka's own
    use during close and rebalance, which runs on its thread, not the loop.

  * ONE executor worker, never more.  The underlying librdkafka handle is not
    safe to call concurrently from multiple threads, and the loop only ever has
    one call in flight.  The single worker also satisfies librdkafka's
    requirement that batch-API calls be issued in sequential order (§11).

Do not use confluent_kafka.aio.AIOConsumer.  It binds its background-thread →
event-loop bridge via the deprecated asyncio.get_event_loop()
(confluentinc/confluent-kafka-python#2211, open), which can silently attach to
the wrong loop — `await consumer.poll()` then hangs forever with no error, no
exception and no log line.  ManagedConsumer exists precisely so every blocking
call is pushed onto an executor explicitly.
"""
from __future__ import annotations

import asyncio
import functools
import logging
from concurrent.futures import ThreadPoolExecutor
from typing import Callable, Iterable

from ai4i_core.logging import get_logger
from confluent_kafka import Consumer, KafkaError, KafkaException, Message, TopicPartition

from bootstrap.config import KafkaSettings, build_consumer_config, get_kafka_settings

logger = get_logger(__name__)
_rdkafka_logger = logging.getLogger("librdkafka")

RevocationHook = Callable[[set[tuple[str, int]]], None]


class ManagedConsumer(Consumer):

    def __init__(
        self,
        config: dict,
        *,
        group_id: str,
        topic: str,
        poll_timeout: float,
        batch_size: int,
        auto_offset_reset: str,
        thread_name_prefix: str,
    ) -> None:
        # config is the only thing the C type sees (plus logger=, a real base kwarg).
        # Routing librdkafka's own output through ai4i_core.logging is what keeps
        # its FAIL lines out of raw stderr in %3|…|FAIL| format (§3.1).
        super().__init__(config, logger=_rdkafka_logger)
        self.group_id = group_id
        self.topic = topic
        self.poll_timeout = poll_timeout
        self.batch_size = batch_size
        self.auto_offset_reset = auto_offset_reset

        # Assignment state for the §6.4 revocation fence.  Written by the
        # rebalance callbacks on the executor thread, read by the loop on the
        # event loop; plain assignment of a set and an int is adequate under the
        # GIL (§6.6).  No lock — a lock here risks the callback deadlock.
        self._assigned: set[tuple[str, int]] = set()
        self._generation: int = 0
        self._revocation_hooks: list[RevocationHook] = []

        self._executor = ThreadPoolExecutor(
            max_workers=1, thread_name_prefix=thread_name_prefix
        )

    # ── construction ───────────────────────────────────────────────────────
    @classmethod
    def build_bulk_message_consumer(
        cls,
        *,
        group_id: str,
        topic: str,
        settings: KafkaSettings | None = None,
        batch_size: int | None = None,
        poll_timeout: float | None = None,
        thread_name_prefix: str | None = None,
    ) -> "ManagedConsumer":
        """Construct, configure and subscribe a batch-fetch consumer.

        Built on consume(num_messages=…, timeout=…), which returns a LIST per
        call.  batch_size defaults to 1: the batch API is what the consumer is
        built on, and 1 is the safe setting for it today (§3.4/§6.4).  Raising
        it is a config change rather than a rewrite, once §8.2's write-time
        guard and §7.5's reconciliation are live.
        """
        s = settings or get_kafka_settings()
        consumer = cls(
            build_consumer_config(group_id, s),
            group_id=group_id,
            topic=topic,
            poll_timeout=poll_timeout if poll_timeout is not None else s.KAFKA_POLL_TIMEOUT_S,
            batch_size=batch_size if batch_size is not None else s.KAFKA_BATCH_SIZE,
            auto_offset_reset=s.KAFKA_AUTO_OFFSET_RESET,
            thread_name_prefix=thread_name_prefix or f"kafka-{group_id}",
        )
        # Subscribing here is what makes it impossible for a consumer's run()
        # to forget to wire the rebalance callbacks (§6.5).
        consumer.subscribe(
            [topic],
            on_assign=consumer.on_assign,
            on_revoke=consumer.on_revoke,
            on_lost=consumer.on_lost,
        )
        logger.info(
            "Consumer built | group_id=%s topic=%s batch_size=%d poll_timeout=%.1fs "
            "auto_offset_reset=%s assignor=cooperative-sticky",
            group_id,
            topic,
            consumer.batch_size,
            consumer.poll_timeout,
            consumer.auto_offset_reset,
        )
        return consumer

    # ── the fence ──────────────────────────────────────────────────────────
    def owns(self, msg: Message) -> bool:
        """True if this consumer still holds msg's partition.  Synchronous —
        the loop calls it before every message (§6.4)."""
        return (msg.topic(), msg.partition()) in self._assigned

    @property
    def generation(self) -> int:
        return self._generation

    def add_revocation_hook(self, hook: RevocationHook) -> None:
        """Register a callback invoked with the revoked (topic, partition) set.

        A consumer holding per-partition state (a retry counter, a buffer) must
        drop it here — stale state for a partition you no longer own would
        suppress processing if that partition came back (§6.5).  The reference
        implementation retries the in-hand Message and holds no such state, so
        it registers nothing.
        """
        self._revocation_hooks.append(hook)

    # ── rebalance callbacks ────────────────────────────────────────────────
    # librdkafka runs these on the executor thread from inside consume():
    # synchronous, short, no await, and NO COMMIT (§6.5).  A bare commit() here
    # raises _NO_OFFSET when nothing new is stored, and _ASSIGNMENT_LOST during
    # a revoke — either would propagate out of consume() and take the process
    # down on every rebalance and every clean shutdown.
    #
    # incremental_assign / incremental_unassign, never assign / unassign: the
    # protocol is COOPERATIVE.  Getting this wrong is not a clean error — the
    # binding auto-applies the assignment only when the callback made no assign
    # call at all, so a callback that ATTEMPTED assign() leaves the consumer
    # wedged with an unsynchronised assignment rather than crashed.
    def on_assign(self, consumer, partitions: list[TopicPartition]) -> None:
        added = {(tp.topic, tp.partition) for tp in partitions}
        # Under cooperative-sticky this list holds only the NEWLY added
        # partitions, not the full assignment — never reset state for partitions
        # still held.
        self._assigned |= added
        self._generation += 1
        self.incremental_assign(partitions)
        logger.info(
            "Partitions assigned | added=%s held=%d generation=%d",
            sorted(added),
            len(self._assigned),
            self._generation,
        )

    def on_revoke(self, consumer, partitions: list[TopicPartition]) -> None:
        self._drop(partitions)
        self.incremental_unassign(partitions)
        logger.info(
            "Partitions revoked | revoked=%s held=%d generation=%d",
            sorted((tp.topic, tp.partition) for tp in partitions),
            len(self._assigned),
            self._generation,
        )

    def on_lost(self, consumer, partitions: list[TopicPartition]) -> None:
        # Lost WITHOUT a clean revoke — session.timeout.ms or
        # max.poll.interval.ms exceeded.  Same state changes, logged at ERROR:
        # another consumer may already own these partitions and be ahead of us,
        # so work was very likely processed twice.  Emphatically no commit.
        self._drop(partitions)
        self.incremental_unassign(partitions)
        logger.error(
            "Partitions LOST (no clean revoke) | lost=%s held=%d generation=%d",
            sorted((tp.topic, tp.partition) for tp in partitions),
            len(self._assigned),
            self._generation,
        )

    def _drop(self, partitions: Iterable[TopicPartition]) -> None:
        removed = {(tp.topic, tp.partition) for tp in partitions}
        self._assigned -= removed
        self._generation += 1
        for hook in self._revocation_hooks:
            try:
                hook(removed)
            except Exception:  # never let a hook wedge a rebalance
                logger.exception("Revocation hook failed")

    # ── async wrappers over the blocking calls (§6.6) ───────────────────────
    async def consume_batch(self) -> list[Message]:
        """One batch fetch.  Returns [] on timeout — never None."""
        loop = asyncio.get_running_loop()
        return await loop.run_in_executor(
            self._executor,
            functools.partial(
                self.consume, num_messages=self.batch_size, timeout=self.poll_timeout
            ),
        )

    async def store_processed(self, msg: Message) -> None:
        """Mark this message's offset committable.  Local only, no broker
        round-trip.  store_offsets already records msg.offset() + 1 and already
        tracks the high-water mark per partition, so there is no pending_offsets
        dict to maintain and no manual +1 (§6.1)."""
        loop = asyncio.get_running_loop()
        await loop.run_in_executor(
            self._executor, functools.partial(self.store_offsets, message=msg)
        )

    async def commit_stored(self, offsets: list[TopicPartition] | None = None) -> None:
        """Commit the highest stored offset for every assigned partition,
        synchronously.

        asynchronous=False deliberately: fire-and-forget would let the loop move
        to the next message without knowing the previous one's offset is
        durable, reopening the window §6.1 exists to close.

        Swallows _NO_OFFSET: commit() raises KafkaException(_NO_OFFSET) when
        nothing new has been stored (verified, confluent-kafka 2.15.0), which
        happens routinely on a redelivered message that was already committed.
        Absorbing it here means no consumer can reintroduce that crash loop.
        """
        loop = asyncio.get_running_loop()

        def _commit() -> None:
            try:
                if offsets is None:
                    self.commit(asynchronous=False)
                else:
                    self.commit(offsets=offsets, asynchronous=False)
            except KafkaException as exc:
                code = exc.args[0].code()
                if code == KafkaError._NO_OFFSET:
                    return
                if code == KafkaError._ASSIGNMENT_LOST:
                    # The partition was taken while this message was in flight.
                    # The side effect already landed and the new owner will
                    # redo it; crashing changes nothing.  Log loudly and go on.
                    logger.error(
                        "Commit rejected — assignment lost mid-message; "
                        "this message will be redelivered to its new owner"
                    )
                    return
                raise

        await loop.run_in_executor(self._executor, _commit)

    def shutdown(self) -> None:
        """Leave the group and drain the executor.  close() blocks briefly; it
        is a one-off at shutdown and the loop has nothing else in flight.

        close() commits nothing here: its docs say it commits offsets "unless
        enable.auto.commit is set to False", and build_consumer_config fixes it
        to False.
        """
        try:
            self.close()
        finally:
            self._executor.shutdown(wait=True)
