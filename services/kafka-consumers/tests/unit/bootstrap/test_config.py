"""bootstrap/config.py — settings, build_consumer_config, BrokerErrorReporter.

`build_consumer_config` here is now the ONLY one in the service —
`consumers/payperuse_consumer/main.py` builds on it too, and the superseded
service-root `config.py` (which deliberately disagreed with this module on
`auto.offset.reset`, the assignor, and `enable.auto.offset.store`) is deleted.

Half of the dict this builds is correctness, not tuning: an
`enable.auto.offset.store` left at its default commits past a message whose
handler raised (§6.1).  A test is the only thing standing between that and a
plausible-looking one-line "cleanup".

Nothing here needs a broker, a database or Redis.  Every settings object is
built with `_env_file=None` or through monkeypatched environment variables, so
whatever `.env` the developer has locally cannot change the verdict.
"""
from __future__ import annotations

import pytest
from pydantic import ValidationError

from bootstrap.config import (
    BrokerErrorReporter,
    DatabaseSettings,
    KafkaSettings,
    RedisSettings,
    build_consumer_config,
    get_db_settings,
    get_kafka_settings,
    get_redis_settings,
)

# Unreachable on purpose: a test that accidentally needs a broker must fail
# rather than quietly talk to a real one.
BROKER = "localhost:1"


def _kafka(**overrides) -> KafkaSettings:
    return KafkaSettings(KAFKA_SERVER=BROKER, _env_file=None, **overrides)


class TestKafkaSettings:
    def test_auto_offset_reset_defaults_to_error(self):
        # NOT 'earliest'.  'earliest' silently replays the whole topic when an
        # offset ages out of retention and re-bills every span still there
        # (§10.1); 'error' turns that into an _AUTO_OFFSET_RESET entry a human
        # has to answer for.  This default is the whole point of §10.
        assert _kafka().KAFKA_AUTO_OFFSET_RESET == "error"

    def test_batch_size_defaults_to_one(self):
        # Above 1 this opens an in-flight window across rebalances (§6.4) and
        # re-enables librdkafka's batch-API hazard (§11).  Raising it is gated on
        # the write-time guard and reconciliation job (§11).
        assert _kafka().KAFKA_BATCH_SIZE == 1

    def test_batch_size_below_one_is_rejected(self):
        with pytest.raises(ValidationError):
            _kafka(KAFKA_BATCH_SIZE=0)

    def test_remaining_defaults(self):
        s = _kafka()
        assert s.KAFKA_ENABLE_AUTO_COMMIT is False
        assert s.KAFKA_SESSION_TIMEOUT_MS == 30_000
        assert s.KAFKA_MAX_POLL_INTERVAL_MS == 300_000
        assert s.KAFKA_POLL_TIMEOUT_S == 1.0

    def test_asking_for_auto_commit_fails_loudly(self):
        # build_consumer_config hardcodes False, so honouring the setting is not
        # an option; the alternative to raising is ignoring the deployment's
        # request in silence.
        with pytest.raises(ValidationError, match="not supported"):
            _kafka(KAFKA_ENABLE_AUTO_COMMIT=True)

    def test_the_broker_address_is_required(self, monkeypatch):
        # conftest.py sets it for the suite; take it away to prove it has no
        # default.  A default broker address would let a misconfigured
        # deployment start up pointed at nothing.
        monkeypatch.delenv("KAFKA_SERVER", raising=False)
        with pytest.raises(ValidationError):
            KafkaSettings(_env_file=None)

    def test_the_group_id_is_not_a_setting(self):
        # It is a hardcoded constant per consumer (§5) and a parameter to
        # build_consumer_config — never environment-overridable, or a deployment
        # could point the billing consumer at another group's offsets.
        assert "KAFKA_GROUP_ID" not in KafkaSettings.model_fields
        assert not any("GROUP" in name for name in KafkaSettings.model_fields)

    def test_reads_from_the_environment(self, monkeypatch):
        monkeypatch.setenv("KAFKA_SERVER", "broker.invalid:9093")
        monkeypatch.setenv("KAFKA_AUTO_OFFSET_RESET", "latest")
        monkeypatch.setenv("KAFKA_POLL_TIMEOUT_S", "2.5")

        s = KafkaSettings(_env_file=None)

        assert s.KAFKA_SERVER == "broker.invalid:9093"
        assert s.KAFKA_AUTO_OFFSET_RESET == "latest"
        assert s.KAFKA_POLL_TIMEOUT_S == 2.5


class TestConnectionSettings:
    def test_database_url_is_asyncpg(self):
        db = DatabaseSettings(
            POSTGRES_USER="u",
            POSTGRES_PASSWORD="p",
            POSTGRES_HOST="h",
            POSTGRES_PORT=5433,
            PLATFORM_CORE_DB="ignored_by_the_call",
            _env_file=None,
        )
        # The database name is a PARAMETER: lifecycle.infra() picks it, so one
        # process can open more than one database from one set of credentials.
        assert db.get_database_url("some_db") == (
            "postgresql+asyncpg://u:p@h:5433/some_db"
        )

    def test_redis_url_carries_the_logical_db_index(self):
        rd = RedisSettings(REDIS_HOST="h", REDIS_DB=3, _env_file=None)
        # In the URL, not via init_redis(redis_db=...) — that kwarg does not
        # exist at the pinned ai4i-core 1.0.2 and would raise TypeError.
        assert rd.get_redis_url() == "redis://h:6379/3"

    def test_redis_url_includes_the_password_when_set(self):
        rd = RedisSettings(REDIS_HOST="h", REDIS_PASSWORD="s3cret", _env_file=None)
        assert rd.get_redis_url() == "redis://:s3cret@h:6379/0"


class TestSettingsAccessors:
    """The accessors are @lru_cache'd, which is what makes them cheap enough to
    call from anywhere — and what makes conftest's cache_clear fixture
    load-bearing."""

    def test_each_accessor_reads_once(self):
        assert get_kafka_settings() is get_kafka_settings()
        assert get_db_settings() is get_db_settings()
        assert get_redis_settings() is get_redis_settings()

    def test_importing_config_does_not_read_settings(self):
        # §3.2: merely importing must not explode.  Settings are read at run()
        # time, when logging is configured and the consumer name is known.
        # cache_info() is proof no import-time call happened — the autouse
        # fixture cleared the caches, and nothing has touched them since.
        assert get_kafka_settings.cache_info().currsize == 0


class TestBuildConsumerConfig:
    def test_group_id_is_a_parameter(self):
        cfg = build_consumer_config("some-group", _kafka())
        assert cfg["group.id"] == "some-group"

    def test_maps_settings_onto_librdkafka_keys(self):
        s = _kafka(
            KAFKA_AUTO_OFFSET_RESET="latest",
            KAFKA_SESSION_TIMEOUT_MS=11_000,
            KAFKA_MAX_POLL_INTERVAL_MS=222_000,
        )
        cfg = build_consumer_config("g", s)

        assert cfg["bootstrap.servers"] == BROKER
        assert cfg["auto.offset.reset"] == "latest"
        assert cfg["session.timeout.ms"] == 11_000
        assert cfg["max.poll.interval.ms"] == 222_000

    def test_poll_timeout_and_batch_size_are_not_librdkafka_keys(self):
        # They are consume() call arguments, held on ManagedConsumer.  A config
        # key of a name librdkafka does not know raises at construction.
        cfg = build_consumer_config("g", _kafka())
        assert not {k for k in cfg if "poll.timeout" in k or "batch.size" in k}

    @pytest.mark.parametrize(
        "key, value",
        [
            # Nothing is committed on a timer behind the loop's back.
            ("enable.auto.commit", False),
            # THE important one.  Left at its default (true) a fetch marks a
            # message committable the instant it is returned — including one
            # whose handler later raised — so any commit advances past a failed
            # message and the span is never re-billed (§6.1).
            ("enable.auto.offset.store", False),
            # Incremental rebalancing: only partitions that must move are
            # revoked, instead of stop-the-world for the whole group (§6.5).
            ("partition.assignment.strategy", "cooperative-sticky"),
        ],
    )
    def test_correctness_keys_are_fixed_not_configurable(self, key, value):
        """These three are not tuning knobs — do not promote them to settings.

        Each is pinned here because each is a plausible-looking one-line change
        whose failure mode is silent and financial.
        """
        assert build_consumer_config("g", _kafka())[key] == value

    def test_an_error_callback_is_always_installed(self):
        # Without one, _TRANSPORT / _ALL_BROKERS_DOWN never reach the
        # application: the binding registers a default that discards them, and
        # the consumer sits disconnected while consume() returns [] and the
        # healthcheck sees a live process (§3.1).
        assert isinstance(build_consumer_config("g", _kafka())["error_cb"],
                          BrokerErrorReporter)

    def test_falls_back_to_the_cached_settings(self, monkeypatch):
        monkeypatch.setenv("KAFKA_SERVER", "from-the-environment:9093")
        cfg = build_consumer_config("g")  # no settings argument
        assert cfg["bootstrap.servers"] == "from-the-environment:9093"


class _FakeKafkaError:
    """Stands in for confluent_kafka.KafkaError, which cannot be instantiated
    from Python with a chosen code."""

    def __init__(self, code: int, *, fatal: bool = False, name: str = "_TRANSPORT"):
        self._code, self._fatal, self._name = code, fatal, name

    def code(self):
        return self._code

    def fatal(self):
        return self._fatal

    def name(self):
        return self._name

    def str(self):
        return "broker unreachable"


class TestBrokerErrorReporter:
    def test_logs_the_first_error_for_a_code(self, caplog):
        reporter = BrokerErrorReporter()
        with caplog.at_level("ERROR"):
            reporter(_FakeKafkaError(-195))
        assert "Broker error" in caplog.text

    def test_rate_limits_per_code_not_globally(self, caplog):
        """Measured against an unreachable broker, librdkafka fires 32 callbacks
        in ~1.5s ALTERNATING _TRANSPORT and _ALL_BROKERS_DOWN.  Deduping on
        "the last code seen" would therefore suppress nothing at all."""
        reporter = BrokerErrorReporter(min_interval_s=3600)
        with caplog.at_level("ERROR"):
            for _ in range(16):
                reporter(_FakeKafkaError(-195, name="_TRANSPORT"))
                reporter(_FakeKafkaError(-187, name="_ALL_BROKERS_DOWN"))

        # 32 callbacks, one line each for the two distinct codes.
        assert caplog.text.count("Broker error") == 2

    def test_a_fatal_error_is_critical(self, caplog):
        reporter = BrokerErrorReporter()
        with caplog.at_level("CRITICAL"):
            reporter(_FakeKafkaError(-150, fatal=True, name="_FATAL"))
        assert [r.levelname for r in caplog.records] == ["CRITICAL"]
