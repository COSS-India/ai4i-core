"""bootstrap/consumers.py — ManagedConsumer.

The subclass caveats in ARCHITECTURE.md §3.4 are the point of this file: both
"the C extension type can be subclassed at all" and "no wrapper shadows an
inherited name" fail loudly here and silently in production.

No broker is required — librdkafka connects in the background, so construction
and subscribe() succeed against an unreachable bootstrap.servers.
"""
from __future__ import annotations

import confluent_kafka
import pytest
from confluent_kafka import Consumer

from bootstrap.config import KafkaSettings
from bootstrap.consumers import ManagedConsumer

# Unreachable on purpose: any test that accidentally needs a broker must fail,
# not quietly talk to a real one.
#
# _env_file=None because this is built at IMPORT time — during collection, before
# conftest's session fixture can move the CWD away from the deployment .env.
# Module-level settings in a test file must always opt out explicitly.
SETTINGS = KafkaSettings(KAFKA_SERVER="localhost:1", _env_file=None)


class _FakeMessage:
    def __init__(self, *, topic="t", partition=0, offset=0):
        self._topic, self._partition, self._offset = topic, partition, offset

    def topic(self):
        return self._topic

    def partition(self):
        return self._partition

    def offset(self):
        return self._offset


@pytest.fixture
def consumer():
    c = ManagedConsumer.build_bulk_message_consumer(
        group_id="test-group", topic="test-topic", settings=SETTINGS
    )
    try:
        yield c
    finally:
        c.shutdown()


class TestSubclassing:
    def test_can_be_constructed_on_top_of_the_c_extension_type(self):
        c = ManagedConsumer(
            {"bootstrap.servers": "localhost:1", "group.id": "g"},
            group_id="g",
            topic="t",
            poll_timeout=0.1,
            batch_size=1,
            auto_offset_reset="error",
            thread_name_prefix="kafka-test",
        )
        try:
            assert isinstance(c, Consumer)
            assert c.group_id == "g"
            assert c.topic == "t"
        finally:
            c.shutdown()

    def test_no_wrapper_name_shadows_an_inherited_one(self):
        # Overriding commit or store_offsets with an async method would break
        # librdkafka's own internal use during close and rebalance.
        ours = {"consume_batch", "store_processed", "commit_stored", "shutdown", "owns"}
        assert ours & set(dir(confluent_kafka.Consumer)) == set()

    def test_the_wrappers_delegate_to_inherited_names_that_do_exist(self):
        inherited = set(dir(confluent_kafka.Consumer))
        assert {"consume", "store_offsets", "commit", "close"} <= inherited


class TestBuildBulkMessageConsumer:
    def test_applies_settings_defaults(self, consumer):
        assert consumer.group_id == "test-group"
        assert consumer.topic == "test-topic"
        assert consumer.batch_size == 1  # do not raise without the guard
        assert consumer.poll_timeout == SETTINGS.KAFKA_POLL_TIMEOUT_S
        assert consumer.auto_offset_reset == "error"

    def test_explicit_arguments_win_over_settings(self):
        c = ManagedConsumer.build_bulk_message_consumer(
            group_id="g", topic="t", settings=SETTINGS, batch_size=25, poll_timeout=0.5
        )
        try:
            assert c.batch_size == 25
            assert c.poll_timeout == 0.5
        finally:
            c.shutdown()

    def test_subscribes_to_the_topic_with_all_three_rebalance_callbacks(self, monkeypatch):
        captured = {}

        def spy(self, topics, **kwargs):
            captured["topics"] = topics
            captured["kwargs"] = kwargs

        monkeypatch.setattr(ManagedConsumer, "subscribe", spy)
        c = ManagedConsumer.build_bulk_message_consumer(
            group_id="g", topic="the-topic", settings=SETTINGS
        )
        try:
            assert captured["topics"] == ["the-topic"]
            # Wiring them in the factory is what makes it impossible for a
            # consumer's run() to forget them.
            assert captured["kwargs"]["on_assign"] == c.on_assign
            assert captured["kwargs"]["on_revoke"] == c.on_revoke
            assert captured["kwargs"]["on_lost"] == c.on_lost
        finally:
            c.shutdown()

    def test_starts_with_no_assignment(self, consumer):
        assert consumer.owns(_FakeMessage()) is False
        assert consumer.generation == 0
