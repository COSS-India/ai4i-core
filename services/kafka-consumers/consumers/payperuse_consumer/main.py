"""payperuse_consumer — bills ai-inference spans against tenant wallets.

Reference implementation of the loop invariants in ARCHITECTURE.md §6 and §7.
A copy that violates them is a bug regardless of whether it appears to work.

The topic of otel trace has ONE partition (§0), so this loop is the only thing consuming it.
That is why it optimises for durability rather than throughput: chunked fetch to
catch up, per-message commit so a crash costs one message, and a deadline so a
slow chunk cannot get the partition taken away mid-work.

GROUP_ID is same as the old one to avoid double processing. Before chaning see point 10 of ARCHITECTURE.md
"""
from __future__ import annotations

import asyncio
import time

from ai4i_core.logging import get_logger
from confluent_kafka import KafkaError, KafkaException, Message

from bootstrap.config import get_db_settings
from bootstrap.consumers import CommitMode, ManagedConsumer
from bootstrap.lifecycle import infra, shutdown_event
from consumers.payperuse_consumer import config as cfg
from consumers.payperuse_consumer.handler import handle_ppu_usage

logger = get_logger(__name__)

# Hardcoded, never read from settings, never overridable by environment (§5).
#
# Still the legacy id: this group already has committed offsets for the topic,
# and KAFKA_AUTO_OFFSET_RESET is 'earliest', so renaming it would replay the
# whole topic from the beginning and re-bill every span in retention. Renaming
# it is an operational change (seed the new group's offsets first), not a code
# change.
GROUP_ID = "aio-python-consumers"
# ===============

async def run() -> None:
    db = get_db_settings()
    settings = cfg.get_settings()

    async with infra(db_name=db.PLATFORM_CORE_DB):
        consumer = ManagedConsumer.build_bulk_message_consumer(
            group_id=GROUP_ID,
            topic=settings.TOPIC_PAY_PER_USE,
            # Explicit, not defaulted: this is the single most consequential fact
            # about this consumer's durability (§6.1/§6.8).
            commit_mode=CommitMode.PER_MESSAGE,
        )
        # Before the first fetch: subscribe() already happened inside the factory,
        # so an assignment can arrive on the very first consume_batch().
        # consumer.add_assignment_hook(_on_assign)
        # consumer.add_revocation_hook(_on_revoke)

        shutdown = shutdown_event()
        logger.info(
            "Consumer started | group_id=%s topic=%s batch_size=%d commit_mode=%s",
            GROUP_ID, settings.TOPIC_PAY_PER_USE,
            consumer.batch_size, consumer.commit_mode.value,
        )
        try:
            while not shutdown.is_set():
                try:
                    chunk = await consumer.consume_batch()
                except KafkaException as exc:
                    # A fetch-level failure.  Only a fatal error may take the
                    # process down; anything else is logged and retried by the
                    # next iteration.
                    if exc.args[0].fatal():
                        raise
                    logger.error("Fetch failed | code=%s: %s", exc.args[0].name(), exc.args[0].str())
                    continue

                # ── the §6.4 chunk deadline ──
                # KAFKA_BATCH_SIZE x worst-case per-message time can exceed
                # max.poll.interval.ms.  Overrunning it means the partition is
                # taken away as on_lost WHILE we are still processing it —
                # self-inflicted double billing.  Stamped per chunk because only
                # consume() resets the poll clock; committing does not (§6.7).
                deadline = time.monotonic() + cfg.Constants.CHUNK_DEADLINE_S

                for index, msg in enumerate(chunk):
                    # ── the §6.4 fence, before anything else ──
                    # A rebalance can revoke a partition while its messages are
                    # still in this chunk; processing them would duplicate work the
                    # new owner is already doing.
                    #
                    # continue, NOT break.  A revocation takes away SOME partitions;
                    # the others in this chunk are independent and still ours, and
                    # abandoning them would re-fetch work that was never at risk.
                    if not consumer.owns(msg):
                        logger.warning(
                            "Skipping message from revoked partition | %s[%d]@%d",
                            msg.topic(), msg.partition(), msg.offset(),
                        )
                        continue

                    # ── classify before handling (§6.3) ──
                    if not _usable(msg):
                        continue

                    # break here, unlike the fence above: the deadline is a
                    # property of the whole CHUNK, not of one partition, so
                    # stopping outright is correct at any partition count.
                    #
                    # Abandoning is free: everything processed so far is already
                    # committed, and the remainder was never stored, so the next
                    # fetch returns it.  Checked BEFORE the handler so the deadline
                    # bounds when we stop starting work, not when we finish it.
                    if time.monotonic() > deadline:
                        logger.warning(
                            "Chunk deadline reached — yielding to the next fetch | "
                            "processed=%d remaining=%d",
                            index, len(chunk) - index,
                        )
                        break

                    # ── retry in hand, never seek (§7.1) ──
                    await _handle_with_retry(msg)

                    # ── store + commit after the handler returned.
                    #    record_processed resolves store-vs-commit from
                    #    commit_mode, so this line is correct under either policy.
                    #    Under PER_MESSAGE the flush arg is redundant and
                    #    harmless.
                    await consumer.record_processed(
                        msg, flush=(index == len(chunk) - 1),
                    )
        finally:
            consumer.shutdown()


def _usable(msg: Message) -> bool:
    """Error classification (§6.3).  Only a FATAL error may take the process down.

    Do NOT use err.retriable() as the discriminator: KafkaError(_MAX_POLL_EXCEEDED)
    reports retriable() == False and fatal() == False (verified, confluent-kafka
    2.15.0), so a retriable()-based rule would let it through to the raise branch
    — and _MAX_POLL_EXCEEDED is precisely the error you receive BECAUSE you were
    slow, which restarting makes worse.
    """
    err = msg.error()
    if err is None:
        return True

    if err.code() == KafkaError._PARTITION_EOF:
        # Informational end-of-partition, not a failure.  Only delivered when
        # enable.partition.eof is on; handle it anyway.
        return False

    if err.code() == KafkaError._AUTO_OFFSET_RESET:
        # KAFKA_AUTO_OFFSET_RESET=error turned a silent full-topic replay into
        # this entry (§10.1).  It will not resolve on its own and consuming
        # cannot proceed, so make it a loud, restarting failure rather than a
        # process that spins forever logging ERROR and billing nothing.
        logger.critical(
            "No valid committed offset for %s[%d] — the group is unseeded or its "
            "offset aged out of retention.  Seed the group's offsets deliberately "
            "(ARCHITECTURE.md §10.2); do NOT switch auto.offset.reset to earliest, "
            "which would replay the topic and re-bill every span older than the "
            "1h dedup TTL. | %s",
            msg.topic(), msg.partition(), err.str(),
        )
        raise KafkaException(err)

    if err.fatal():
        logger.critical("Fatal Kafka error — exiting for restart | code=%s: %s", err.name(), err.str())
        raise KafkaException(err)

    # Everything else: log and continue.  Raising here crash-loops the process
    # on transient conditions.
    logger.error("Kafka error entry | code=%s: %s", err.name(), err.str())
    return False


async def _handle_with_retry(msg: Message) -> None:
    """Retry the IN-HAND Message object, in place.  There is no rewind.

    The handler's contract: returning means success-or-permanent-skip (commit
    and move on); raising means transient failure (retry).  Permanent skips are
    signalled by returning, never by raising.

    Why no seek(): the crash case is already covered because an unstored offset
    is never committed, so a restart resumes at exactly this message.  Removing
    seek() also removes librdkafka's "avoid storing offsets after seek()"
    ordering rule.

    The tradeoff, stated plainly: this blocks the partition for up to a few
    seconds, and giving up after MAX_ATTEMPTS DROPS a message.  Bounded-retry-
    then-skip is chosen because a permanently stalled billing partition loses
    the data anyway once topic retention expires — and does so with no CRITICAL
    line for anyone to act on.  Recovery from that line is manual replay.
    """
    for attempt in range(1, cfg.Constants.MAX_ATTEMPTS + 1):
        try:
            await handle_ppu_usage(msg)
            return
        except Exception as exc:
            if attempt == cfg.Constants.MAX_ATTEMPTS:
                logger.critical(
                    "Giving up after %d attempts — MESSAGE DROPPED | %s[%d]@%d payload=%r: %s",
                    attempt, msg.topic(), msg.partition(), msg.offset(), msg.value(), exc,
                )
                return
            delay = cfg.Constants.BACKOFF_BASE_S * (2 ** (attempt - 1))  # 1s, 2s
            logger.warning(
                "Handler failed — retrying in %.1fs | attempt=%d/%d %s[%d]@%d: %s",
                delay, attempt, cfg.Constants.MAX_ATTEMPTS,
                msg.topic(), msg.partition(), msg.offset(), exc,
            )
            await asyncio.sleep(delay)
