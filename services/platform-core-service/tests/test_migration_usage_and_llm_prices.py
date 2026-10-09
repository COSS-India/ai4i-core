"""Tests for the ai4iplatform_core migrations behind LLM token pricing and
the usage dashboard tables:

* 5d7f9b1c3e4a: cached input and output token prices on mm_services, with a
  backfill of existing LLM services
* 3b5d7f9a1c2e / 4c6e8a0b2d3f: the partitioned usage_events and daily_usage
  tables

Same approach as auth-service's test_migration_* tests: each test runs the
migration's own upgrade()/downgrade() against a real Postgres, inside a
transaction that is always rolled back. Partitioning, generated columns and
NULLS NOT DISTINCT are Postgres behaviour a mock can't stand in for.

Connection settings come from the environment, falling back to the alembic
.env: CORE_SERVICE_DB_*, then POSTGRES_*. The tests skip when no database is
reachable. The database must be migrated at least to f4a8c2d6e1b7.
"""

import importlib.util
import os
import sys
from datetime import datetime, timedelta, timezone
from decimal import Decimal
from pathlib import Path

import pytest
from sqlalchemy import create_engine, text
from sqlalchemy.exc import IntegrityError

try:
    from dotenv import dotenv_values
except ImportError:
    dotenv_values = None

_ALEMBIC_DIR = (
    Path(__file__).resolve().parents[3]
    / "infrastructure" / "databases" / "migrations" / "postgres" / "alembic"
)
_VERSIONS = _ALEMBIC_DIR / "versions" / "ai4iplatform_core"
_USAGE_EVENTS = "3b5d7f9a1c2e_create_usage_events_table.py"
_DAILY_USAGE = "4c6e8a0b2d3f_create_daily_usage_table.py"
_LLM_PRICES = "5d7f9b1c3e4a_add_llm_token_prices_to_mm_services.py"

_MODEL_ID = "test-migr-llm-prices-model"


# ── helpers ──────────────────────────────────────────────────────────────────


def _load(filename: str):
    path = _VERSIONS / filename
    assert path.exists(), f"migration file not found at {path}"
    spec = importlib.util.spec_from_file_location(f"_migration_under_test_{path.stem}", path)
    module = importlib.util.module_from_spec(spec)
    sys.modules[spec.name] = module
    spec.loader.exec_module(module)
    return module


def _setting(env: dict, name: str):
    for key in (f"CORE_SERVICE_DB_{name}", f"POSTGRES_{name}"):
        value = os.environ.get(key) or env.get(key)
        if value:
            return value
    return None


def _live_connection():
    env = {}
    if dotenv_values is not None and (_ALEMBIC_DIR / ".env").exists():
        env = dotenv_values(_ALEMBIC_DIR / ".env")
    parts = {name: _setting(env, name) for name in ("USER", "PASSWORD", "HOST", "PORT")}
    if not all(parts.values()):
        pytest.skip("no ai4iplatform_core DB settings (CORE_SERVICE_DB_* / POSTGRES_*)")
    database = os.environ.get("CORE_SERVICE_DB_NAME") or env.get("CORE_SERVICE_DB_NAME") or "ai4iplatform_core"
    url = (
        f"postgresql://{parts['USER']}:{parts['PASSWORD']}"
        f"@{parts['HOST']}:{parts['PORT']}/{database}"
    )
    try:
        return create_engine(url, connect_args={"connect_timeout": 5}).connect()
    except Exception as exc:
        pytest.skip(f"could not connect to ai4iplatform_core: {exc}")


def _run(conn, step) -> None:
    from alembic.operations import Operations
    from alembic.runtime.migration import MigrationContext

    with Operations.context(MigrationContext.configure(conn)):
        step()


def _exists(conn, table: str) -> bool:
    return conn.scalar(text("SELECT to_regclass(:t)"), {"t": table}) is not None


def _has_column(conn, table: str, column: str) -> bool:
    return bool(conn.scalar(text(
        "SELECT 1 FROM information_schema.columns WHERE table_name = :t AND column_name = :c"
    ), {"t": table, "c": column}))


def _insert(conn, table: str, **row) -> None:
    conn.execute(
        text(f"INSERT INTO {table} ({', '.join(row)}) VALUES ({', '.join(':' + k for k in row)})"),
        row,
    )


def _month_start(moment: datetime, months_ahead: int = 0) -> datetime:
    month_index = moment.year * 12 + moment.month - 1 + months_ahead
    return datetime(month_index // 12, month_index % 12 + 1, 1, tzinfo=timezone.utc)


@pytest.fixture()
def conn():
    connection = _live_connection()
    trans = connection.begin()
    try:
        yield connection
    finally:
        trans.rollback()
        connection.close()


# ── 5d7f9b1c3e4a: LLM token prices on mm_services ───────────────────────────


@pytest.fixture()
def llm_prices(conn):
    """The migration, with the DB put back to just before it."""
    migration = _load(_LLM_PRICES)
    if _has_column(conn, "mm_services", "output_cost_per_unit"):
        _run(conn, migration.downgrade)
    _insert(
        conn, "mm_models",
        id=_uuid(conn), model_id=_MODEL_ID, version="v1", version_status="ACTIVE",
        name="test-migr-llm-prices-model", task="{}", languages="[]", domain="[]",
        inference_endpoint="{}", submitter="{}", is_lang_detection_enabled=False,
        is_multilingual=False, training_dataset="{}",
    )
    return migration


def _uuid(conn) -> str:
    return str(conn.scalar(text("SELECT gen_random_uuid()")))


def _add_service(conn, service_id: str, task_type, cost_per_unit) -> None:
    _insert(
        conn, "mm_services",
        id=_uuid(conn), service_id=service_id, name=service_id, model_id=_MODEL_ID,
        model_version="v1", endpoint="http://localhost:8000/v1/chat/completions",
        is_multilingual_enabled=False, task_type=task_type, cost_per_unit=cost_per_unit,
    )


def _prices(conn, service_id: str):
    return conn.execute(text(
        "SELECT cached_input_cost_per_unit, output_cost_per_unit FROM mm_services WHERE service_id = :s"
    ), {"s": service_id}).one()


class TestLlmTokenPricesBackfill:
    def test_llm_services_get_their_price_in_both_new_columns(self, conn, llm_prices) -> None:
        _add_service(conn, "test-migr/llm-lower", "llm", Decimal("0.10"))
        _add_service(conn, "test-migr/llm-upper", "LLM", Decimal("0.2"))

        _run(conn, llm_prices.upgrade)

        assert _prices(conn, "test-migr/llm-lower") == (Decimal("0.10"), Decimal("0.10"))
        assert _prices(conn, "test-migr/llm-upper") == (Decimal("0.2"), Decimal("0.2"))

    def test_llm_service_without_a_price_stays_null(self, conn, llm_prices) -> None:
        _add_service(conn, "test-migr/llm-unpriced", "llm", None)

        _run(conn, llm_prices.upgrade)

        assert _prices(conn, "test-migr/llm-unpriced") == (None, None)

    def test_other_task_types_are_not_backfilled(self, conn, llm_prices) -> None:
        _add_service(conn, "test-migr/asr", "asr", Decimal("0.5"))
        _add_service(conn, "test-migr/untyped", None, Decimal("0.5"))

        _run(conn, llm_prices.upgrade)

        assert _prices(conn, "test-migr/asr") == (None, None)
        assert _prices(conn, "test-migr/untyped") == (None, None)

    def test_downgrade_then_upgrade_round_trips(self, conn, llm_prices) -> None:
        _add_service(conn, "test-migr/llm-round-trip", "llm", Decimal("0.10"))
        _run(conn, llm_prices.upgrade)

        _run(conn, llm_prices.downgrade)
        assert not _has_column(conn, "mm_services", "cached_input_cost_per_unit")
        assert not _has_column(conn, "mm_services", "output_cost_per_unit")

        _run(conn, llm_prices.upgrade)
        assert _prices(conn, "test-migr/llm-round-trip") == (Decimal("0.10"), Decimal("0.10"))

    @pytest.mark.parametrize("column", ["cached_input_cost_per_unit", "output_cost_per_unit"])
    def test_negative_price_is_rejected(self, conn, llm_prices, column) -> None:
        _add_service(conn, "test-migr/llm-negative", "llm", Decimal("0.10"))
        _run(conn, llm_prices.upgrade)

        with pytest.raises(IntegrityError, match=f"ck_mm_services_{column}_range"):
            with conn.begin_nested():
                conn.execute(text(
                    f"UPDATE mm_services SET {column} = -1 WHERE service_id = 'test-migr/llm-negative'"
                ))


# ── 3b5d7f9a1c2e / 4c6e8a0b2d3f: usage_events and daily_usage ──────────────


@pytest.fixture()
def usage_tables(conn):
    """Both tables freshly created by their migrations, as of now."""
    usage_events, daily_usage = _load(_USAGE_EVENTS), _load(_DAILY_USAGE)
    if _exists(conn, "daily_usage"):
        _run(conn, daily_usage.downgrade)
    if _exists(conn, "usage_events"):
        _run(conn, usage_events.downgrade)
    _run(conn, usage_events.upgrade)
    _run(conn, daily_usage.upgrade)
    return conn


def _event(conn, **cols) -> None:
    row = {
        "correlation_id": "test-migr-corr-1",
        "span_id": "a1b2c3d4e5f60718",
        "occurred_at": datetime.now(timezone.utc),
        **cols,
    }
    _insert(conn, "usage_events", **row)


def _event_partition(conn, span_id: str) -> str:
    return conn.scalar(text(
        "SELECT tableoid::regclass::text FROM usage_events WHERE span_id = :s"
    ), {"s": span_id})


class TestUsageEventsKey:
    def test_spans_of_one_request_are_separate_rows(self, usage_tables) -> None:
        """TTS per_item: one span per chunk, same correlation id, same transaction."""
        now = datetime.now(timezone.utc)
        _event(usage_tables, span_id="chunk-span-0001", occurred_at=now)
        _event(usage_tables, span_id="chunk-span-0002", occurred_at=now)

        assert usage_tables.scalar(text(
            "SELECT count(*) FROM usage_events WHERE correlation_id = 'test-migr-corr-1'"
        )) == 2

    def test_redelivered_span_hits_the_primary_key(self, usage_tables) -> None:
        occurred_at = datetime.now(timezone.utc)
        _event(usage_tables, occurred_at=occurred_at)

        with pytest.raises(IntegrityError, match="duplicate key"):
            with usage_tables.begin_nested():
                _event(usage_tables, occurred_at=occurred_at)


class TestUsageEventsCost:
    def test_total_cost_is_the_sum_of_the_stored_costs(self, usage_tables) -> None:
        _event(
            usage_tables, input_units_cost=Decimal("0.0176"),
            cached_input_units_cost=Decimal("0.04096"), output_units_cost=Decimal("0.0375"),
        )

        assert usage_tables.scalar(text("SELECT total_cost FROM usage_events")) == Decimal("0.096060")

    def test_sub_scale_costs_are_accepted(self, usage_tables) -> None:
        """Each cost rounds to 0.000000 when stored; a CHECK on the total failed here."""
        _event(
            usage_tables, input_units_cost=Decimal("0.0000004"),
            cached_input_units_cost=Decimal("0.0000004"), output_units_cost=Decimal("0.0000004"),
        )

        assert usage_tables.scalar(text("SELECT total_cost FROM usage_events")) == 0

    def test_total_cost_cannot_be_written(self, usage_tables) -> None:
        with pytest.raises(Exception, match="generated column"):
            with usage_tables.begin_nested():
                _event(usage_tables, total_cost=Decimal("1"))


class TestUsageEventsPartitions:
    def test_current_and_next_utc_month_have_partitions(self, usage_tables) -> None:
        now = datetime.now(timezone.utc)
        next_month = _month_start(now, 1)
        _event(usage_tables, span_id="span-now", occurred_at=now)
        _event(usage_tables, span_id="span-next", occurred_at=next_month)

        assert _event_partition(usage_tables, "span-now") == now.strftime("usage_events_%Y_%m")
        assert _event_partition(usage_tables, "span-next") == next_month.strftime("usage_events_%Y_%m")

    def test_month_boundary_is_utc_midnight(self, usage_tables) -> None:
        """00:30 IST on the 1st is still the previous UTC month, like billing_month."""
        next_month = _month_start(datetime.now(timezone.utc), 1)
        ist = timezone(timedelta(hours=5, minutes=30))
        just_before = (next_month - timedelta(minutes=1)).astimezone(ist)   # 05:29 IST on the 1st
        _event(usage_tables, span_id="span-before", occurred_at=just_before)

        assert _event_partition(usage_tables, "span-before") == (
            (next_month - timedelta(days=1)).strftime("usage_events_%Y_%m")
        )

    def test_month_without_a_partition_goes_to_default(self, usage_tables) -> None:
        later = _month_start(datetime.now(timezone.utc), 2)
        _event(usage_tables, span_id="span-later", occurred_at=later)

        assert _event_partition(usage_tables, "span-later") == "usage_events_default"


def _daily(conn, **cols) -> None:
    today = datetime.now(timezone.utc).date()
    row = {"usage_date": today, "billing_month": today.strftime("%Y-%m"), "tenant_id": -9001, **cols}
    _insert(conn, "daily_usage", **row)


class TestDailyUsage:
    def test_cost_is_generated_and_accepts_sub_scale_costs(self, usage_tables) -> None:
        _daily(
            usage_tables, input_units_cost=Decimal("0.0000004"),
            cached_input_units_cost=Decimal("0.0000004"), output_units_cost=Decimal("0.5"),
        )

        assert usage_tables.scalar(text("SELECT cost FROM daily_usage")) == Decimal("0.500000")

    def test_upsert_matches_rows_with_null_dimensions(self, usage_tables) -> None:
        today = datetime.now(timezone.utc).date()
        upsert = text(
            "INSERT INTO daily_usage (usage_date, billing_month, tenant_id, request_count, success_count)"
            " VALUES (:d, :m, -9001, 1, 1)"
            " ON CONFLICT (usage_date, tenant_id, application_id, api_key_id, tier_id, service_id,"
            "              inference_type_id, billing_month)"
            " DO UPDATE SET request_count = daily_usage.request_count + 1,"
            "               success_count = daily_usage.success_count + 1"
        )
        params = {"d": today, "m": today.strftime("%Y-%m")}
        usage_tables.execute(upsert, params)
        usage_tables.execute(upsert, params)

        assert usage_tables.execute(text("SELECT count(*), max(request_count) FROM daily_usage")).one() == (1, 2)

    def test_partitions_by_utc_day_with_a_default(self, usage_tables) -> None:
        now = datetime.now(timezone.utc)
        later = _month_start(now, 2).date()
        _daily(usage_tables, usage_date=now.date())
        _daily(usage_tables, usage_date=later, billing_month=later.strftime("%Y-%m"))

        partitions = usage_tables.execute(text(
            "SELECT usage_date, tableoid::regclass::text FROM daily_usage ORDER BY usage_date"
        )).all()
        assert partitions == [
            (now.date(), now.strftime("daily_usage_%Y_%m")),
            (later, "daily_usage_default"),
        ]
