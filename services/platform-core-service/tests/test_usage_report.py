"""Usage Viewer report (AI4IDS-3278): period, metering queries, collector,
recipients, email/attachment, PDF and the send script."""
from __future__ import annotations

import email
from datetime import date, datetime, timezone
from decimal import Decimal
from types import SimpleNamespace
from unittest.mock import AsyncMock, MagicMock, Mock, create_autospec

import pytest
from ai4i_core.email import EmailDeliveryError, EmailSettings

from app.services.metering_service import MeteringService
from app.services.usage_report import formatting as fmt
from app.services.usage_report import mailer
from app.services.usage_report.collector import (
    BudgetSummary,
    InstitutionSpend,
    PeriodSpend,
    RankedInstitution,
    RankedModel,
    ReportData,
    UsageReportCollector,
)
from app.services.usage_report.pdf import render_report_html, render_report_pdf, report_context
from app.services.usage_report.period import ReportPeriod
from app.services.usage_report.recipients import usage_viewer_emails

UTC = timezone.utc
SEP = ReportPeriod.month(2026, 9)
AFTER_SEP = datetime(2026, 10, 13, 9, 0, tzinfo=UTC)
SEP_START = datetime(2026, 8, 31, 18, 30, tzinfo=UTC)  # 1 Sep 00:00 IST
SEP_END = datetime(2026, 9, 30, 18, 30, tzinfo=UTC)    # 1 Oct 00:00 IST


# ── period ───────────────────────────────────────────────────────────────────


class TestMonthlyPeriod:
    def test_parse(self):
        assert ReportPeriod.parse_month("2026-08") == ReportPeriod.month(2026, 8)

    @pytest.mark.parametrize("bad", ["2026-13", "2026-00", "2026-8", "Aug 2026", ""])
    def test_parse_rejects_bad_values(self, bad):
        with pytest.raises(ValueError):
            ReportPeriod.parse_month(bad)

    def test_resolves_to_the_dashboards_ist_day_period(self):
        p = SEP.usage_period(AFTER_SEP)
        assert (p.key, p.from_date, p.to_date) == ("custom", date(2026, 9, 1), date(2026, 9, 30))
        assert (p.start, p.end, p.days) == (SEP_START, SEP_END, 30)
        assert SEP.label == "September 2026" and SEP.key == "2026-09" and SEP.date_span == "1–30 Sep 2026"

    def test_unfinished_month_is_rejected(self):
        with pytest.raises(ValueError, match="October 2026"):
            ReportPeriod.month(2026, 10).usage_period(AFTER_SEP)

    def test_last_complete_wraps_year_in_ist(self):
        assert ReportPeriod.month(2026, 1).previous() == ReportPeriod.month(2025, 12)
        # 1 Jan 03:00 IST is still 31 Dec in UTC; the last complete IST month is December.
        assert ReportPeriod.latest_complete("monthly", datetime(2025, 12, 31, 21, 30, tzinfo=UTC)) == ReportPeriod.month(2025, 12)


# ── formatting ───────────────────────────────────────────────────────────────


class TestFormatting:
    @pytest.mark.parametrize("n,expected", [
        (None, "N/A"), (42, "42"), (973_100, "973.1K"), (18_400_000, "18.4M"), (10_000_000, "10M"),
    ])
    def test_count(self, n, expected):
        assert fmt.count(n) == expected

    @pytest.mark.parametrize("n,expected", [
        (590_000, "5.9 L"), (215_000_000, "21.5 Cr"), (500_000_000, "50 Cr"), (950, "950"),
    ])
    def test_indian(self, n, expected):
        assert fmt.indian(n) == expected

    def test_inr_and_signed(self):
        assert fmt.inr(Decimal("215000000")) == "₹21.5 Cr"
        assert fmt.signed_pct(18.0) == "+18%" and fmt.signed_pct(-4.25) == "-4.2%"
        assert fmt.signed_int(3) == "+3" and fmt.signed_int(-2) == "-2"


# ── MeteringService report queries ───────────────────────────────────────────


def _metering(query=None, scalar=0.0, auth_rows=None):
    client = MagicMock()
    client.query = AsyncMock(return_value=query or [])
    client.scalar = AsyncMock(return_value=scalar)
    auth_db = None
    if auth_rows is not None:
        auth_db = AsyncMock()
        auth_db.execute = AsyncMock(side_effect=auth_rows)
    return MeteringService(client=client, auth_db=auth_db), client


def _rows(*items):
    result = MagicMock()
    result.all.return_value = list(items)
    return result


def _prom(value, **labels):
    return {"metric": labels, "value": [0, str(value)]}


def _rng():
    from app.utils.metering_promql_builder import AbsoluteRange
    return AbsoluteRange(start=SEP_START, end=SEP_END)


class TestInferenceRequestTotal:
    @pytest.mark.asyncio
    async def test_matches_request_total_selector_and_raises_on_failure(self):
        svc, client = _metering(scalar=1234.4)
        assert await svc.inference_request_total(_rng()) == 1234
        promql = client.scalar.call_args.args[0]
        assert 'auth_type=~"api_key|"' in promql and "status_code" not in promql
        # request_total degrades a failed query to 0; this must raise instead.
        client.scalar.side_effect = RuntimeError("prometheus 502")
        with pytest.raises(RuntimeError):
            await svc.inference_request_total(_rng())


class TestActiveTenantIds:
    @pytest.mark.asyncio
    async def test_filters_to_active_tenants_and_drops_unlabelled_rows(self):
        rows = [_prom(5, tenant_id="1", tenant="A"), _prom(3, tenant_id="2", tenant="B"),
                _prom(9, tenant_id="", tenant="old")]
        svc, _ = _metering(query=rows, auth_rows=[_rows(("1",), ("3",))])
        assert await svc.active_tenant_ids(_rng()) == {"1"}

    @pytest.mark.asyncio
    async def test_auth_db_down_keeps_all_labelled_ids(self):
        svc, _ = _metering(query=[_prom(5, tenant_id="1", tenant="A")])
        assert await svc.active_tenant_ids(_rng()) == {"1"}


class TestActiveApplicationCount:
    @pytest.mark.asyncio
    async def test_counts_application_rows(self):
        svc, client = _metering(query=[_prom(4, application_id="7"), _prom(1, application_id="9")])
        assert await svc.active_application_count(_rng()) == 2
        promql = client.query.call_args.args[0]
        assert 'application_id!=""' in promql and "sum by(application_id)" in promql


class TestTenantTaskUsage:
    @pytest.mark.asyncio
    async def test_ranks_tenants_and_totals_tasks(self):
        from app.utils.metering_promql_builder import PROMETHEUS_API_PATH_LABEL as ep
        rows = [
            {"metric": {"tenant_id": "1", "tenant": "A", ep: "/api/v1/nmt/inference"}, "value": [0, "60"]},
            {"metric": {"tenant_id": "1", "tenant": "A", ep: "/api/v1/asr/inference"}, "value": [0, "20"]},
            {"metric": {"tenant_id": "2", "tenant": "B", ep: "/api/v1/chat/completions"}, "value": [0, "100"]},
        ]
        svc, _ = _metering(query=rows, auth_rows=[_rows(("1", "Ministry A"), ("2", "Ministry B"))])
        out = await svc.tenant_task_usage(_rng())
        assert [t["tenant"] for t in out["tenants"]] == ["Ministry B", "Ministry A"]
        assert out["tenants"][1]["tasks"] == {"nmt": 60, "asr": 20}
        assert out["task_totals"] == {"nmt": 60, "asr": 20, "llm": 100}
        assert out["grand_total"] == 180


# ── collector ────────────────────────────────────────────────────────────────


def _scalar_result(v):
    r = MagicMock()
    r.scalar.return_value = v
    return r


class _FakeAuthDB:
    """Answers the collector's auth-DB queries by SQL text."""

    def __init__(self, tenants=None, budget_tenants=None, fail_on=None):
        self.tenants = tenants or []  # (id, created_at)
        self.budget_tenants = budget_tenants or []  # (id, organisation)
        self.fail_on = fail_on
        self.rollback = AsyncMock()

    async def execute(self, stmt, params=None):
        sql = str(stmt)
        if self.fail_on and self.fail_on in sql:
            raise RuntimeError("db down")
        params = params or {}
        if sql.startswith("SELECT COUNT(*) FROM tenants WHERE created_at >= :start"):
            return _scalar_result(sum(1 for _, c in self.tenants if params["start"] <= c < params["end"]))
        if sql.startswith("SELECT COUNT(*) FROM tenants"):
            return _scalar_result(sum(1 for _, c in self.tenants if c < params["end"]))
        if sql.startswith("SELECT COUNT(*) FROM applications"):
            return _scalar_result(10)
        if "status = 'ACTIVE' AND created_at < :before" in sql:
            return _rows(*[(tid,) for tid, c in self.tenants if c < params["before"]])
        if "allocated_budget IS NOT NULL" in sql:
            return _rows(*[SimpleNamespace(id=i, organisation=o) for i, o in self.budget_tenants])
        raise AssertionError(f"unexpected SQL: {sql}")


def _fake_metering(**overrides):
    m = MagicMock(spec=MeteringService)
    m.refresh_retention = AsyncMock()
    m.inference_request_total = AsyncMock(side_effect=lambda rng: 1000 if rng.start == SEP_START else 800)
    m.registry_model_count = AsyncMock(return_value=10)
    m.registry_model_counts_by_task = AsyncMock(return_value={"nmt": 6, "asr": 3, "language_detection": 1})
    m.model_breakdown = AsyncMock(return_value={
        "services": [{"requests": 700, "success_pct": 99.0}],
        "model_totals": [
            {"model_id": "m1", "model_name": "IndicTrans2", "task_type": "nmt", "requests": 600},
            {"model_id": "m2", "model_name": "IndicConformer", "task_type": "asr", "requests": 100},
        ],
    })
    m.active_tenant_ids = AsyncMock(side_effect=lambda rng: {"1", "2"} if rng.start == SEP_START else {"2", "3"})
    m.active_application_count = AsyncMock(return_value=6)
    m.tenant_task_usage = AsyncMock(return_value={
        "tenants": [{"tenant_id": "1", "tenant": "Ministry A", "total": 750, "tasks": {"nmt": 600, "asr": 150}},
                    {"tenant_id": "2", "tenant": "Ministry B", "total": 250, "tasks": {"llm": 250}}],
        "task_totals": {"nmt": 600, "asr": 150, "llm": 250},
        "grand_total": 1000,
    })
    for k, v in overrides.items():
        setattr(m, k, v)
    return m


def _budget_ns(limit, spent):
    return SimpleNamespace(budget_limit=Decimal(str(limit)), spent=Decimal(str(spent)),
                           available_balance=Decimal(str(limit)) - Decimal(str(spent)))


@pytest.fixture
def retention_90d(monkeypatch):
    monkeypatch.setattr("app.utils.metering_promql_builder.retention_days", lambda: 90)


def _stub_repo(monkeypatch, name, side_effect):
    # autospec keeps the real signatures: a call that no longer matches the
    # repository (AI4IDS-3278 staging: 3 args to a 2-arg method) fails here too.
    from app.repositories.pay_per_use.usage_repository import UsageRepository

    monkeypatch.setattr(UsageRepository, name,
                        create_autospec(getattr(UsageRepository, name), side_effect=side_effect))


@pytest.fixture
def repo_state():
    """What the stubbed UsageRepository reads return; no patching."""
    return SimpleNamespace(
        budgets={"1": _budget_ns(100, 40)},
        data_from=SEP_START - (SEP_END - SEP_START),  # recording began long before September
        period_rows=[SimpleNamespace(cost=Decimal("12.5")), SimpleNamespace(cost=Decimal("17.5"))],
    )


@pytest.fixture
def repo(monkeypatch, repo_state):
    """UsageRepository's budget / period-spend reads, stubbed."""
    state = repo_state
    _stub_repo(monkeypatch, "get_tenant_budgets", lambda self, tenant_ids, auth_db=None: state.budgets)
    _stub_repo(monkeypatch, "get_usage_data_from", lambda self, p: state.data_from)
    _stub_repo(monkeypatch, "get_period_usage", lambda self, p, *a, **k: state.period_rows)
    return state


class TestCollector:
    TENANTS = [
        ("1", datetime(2026, 1, 1, tzinfo=UTC)),
        ("2", datetime(2026, 1, 1, tzinfo=UTC)),
        ("3", datetime(2026, 1, 1, tzinfo=UTC)),
        ("4", datetime(2026, 1, 1, tzinfo=UTC)),   # never active → dormant
        ("5", datetime(2026, 8, 10, tzinfo=UTC)),  # onboarded last month → not dormant yet
        ("6", datetime(2026, 9, 5, tzinfo=UTC)),   # new this month
    ]

    def _collector(self, metering=None, auth=None):
        auth = auth or _FakeAuthDB(tenants=self.TENANTS, budget_tenants=[("1", "Ministry A")])
        core = AsyncMock()
        return UsageReportCollector(metering or _fake_metering(), auth, core), auth, core

    @pytest.mark.asyncio
    async def test_collects_every_tracked_figure(self, retention_90d, repo):
        collector, _, _ = self._collector()
        d = await collector.collect(SEP, now=AFTER_SEP)
        assert d.failed == []
        assert (d.total_requests, d.prev_total_requests) == (1000, 800)
        assert d.requests_change_pct == pytest.approx(25.0)
        assert (d.total_models, d.active_models, d.inactive_models) == (10, 2, 8)
        assert d.models_by_task == {"NMT": 6, "ASR": 3, "Language Detection": 1}
        assert [m.name for m in d.top_models] == ["IndicTrans2", "IndicConformer"]
        assert d.top_models[0].task == "NMT"
        assert (d.total_institutions, d.new_institutions) == (6, 1)
        assert (d.active_institutions, d.prev_active_institutions, d.active_institutions_change) == (2, 2, 0)
        assert d.dormant_institutions == 1  # only tenant 4
        assert (d.total_applications, d.active_applications) == (10, 6)
        assert d.requests_by_task[0] == ("NMT", 600)
        assert d.top_institutions[0] == RankedInstitution("Ministry A", 75.0, ["NMT", "ASR"])
        assert d.avg_daily_requests == pytest.approx(1000 / 30)
        assert d.budget.used_pct == pytest.approx(40.0)
        assert d.period_spend == PeriodSpend(Decimal("30.0"), None, 30)
        assert d.period_spend.burn_rate == Decimal("1")

    @pytest.mark.asyncio
    async def test_refuses_a_month_that_has_not_ended(self, retention_90d, repo):
        collector, _, _ = self._collector()
        with pytest.raises(ValueError, match="yesterday or earlier"):
            await collector.collect(ReportPeriod.month(2026, 10), now=AFTER_SEP)

    @pytest.mark.asyncio
    async def test_refuses_a_month_older_than_prometheus_retention(self, monkeypatch, repo):
        monkeypatch.setattr("app.utils.metering_promql_builder.retention_days", lambda: 30)
        collector, _, _ = self._collector()
        # Sep starts 31 Aug 18:30 UTC; 30 days before 13 Oct is 13 Sep.
        with pytest.raises(ValueError, match="oldest retained"):
            await collector.collect(SEP, now=AFTER_SEP)

    @pytest.mark.asyncio
    async def test_previous_month_past_retention_leaves_comparisons_empty(self, monkeypatch, repo):
        # 60 days from 13 Oct reaches 14 Aug: September is retained, August is not.
        monkeypatch.setattr("app.utils.metering_promql_builder.retention_days", lambda: 60)
        metering = _fake_metering()
        collector, _, _ = self._collector(metering=metering)
        d = await collector.collect(SEP, now=AFTER_SEP)
        assert d.prev_total_requests is None and d.requests_change_pct is None
        assert d.prev_active_institutions is None and d.dormant_institutions is None
        assert d.failed == []
        # Never asked Prometheus for a month it no longer holds (it would read as zero).
        assert all(c.args[0].start == SEP_START for c in metering.active_tenant_ids.call_args_list)

    @pytest.mark.asyncio
    async def test_one_failing_figure_is_marked_and_the_rest_still_load(self, retention_90d, repo):
        metering = _fake_metering(active_application_count=AsyncMock(side_effect=RuntimeError("prom 502")))
        auth = _FakeAuthDB(tenants=self.TENANTS, fail_on="FROM applications")
        collector, auth, core = self._collector(metering=metering, auth=auth)
        d = await collector.collect(SEP, now=AFTER_SEP)
        assert set(d.failed) == {"active_applications", "total_applications"}
        assert d.active_applications is None and d.total_applications is None
        assert d.total_requests == 1000 and d.active_institutions == 2
        auth.rollback.assert_awaited()  # aborted transaction cleared before the next query
        core.rollback.assert_awaited()

    @pytest.mark.asyncio
    async def test_report_without_platform_health_is_sent_to_every_viewer(self, retention_90d, repo, portal):
        # Platform health was dropped from the report: the run completes with
        # nothing in data.failed (DONE, detail None), and neither the email nor
        # the PDF mentions the error rate.
        from app.services.usage_report.period import MONTHLY
        from app.services.usage_report.recipients import Recipient
        from app.services.usage_report.scheduler import DONE, run_scheduled

        collector, _, _ = self._collector(metering=_fake_metering())
        sent, attached = [], []

        async def send(mime, cfg):
            sent.append(mime)

        async def viewers():
            return [Recipient("u1", "a@x.gov.in"), Recipient("u2", "b@x.gov.in")]

        result = await run_scheduled(
            frequency=MONTHLY, collector=collector, viewers=viewers, email_cfg=_email_cfg(),
            anchor=date(2026, 1, 5), now=AFTER_SEP, send=send,
            render_pdf=lambda data: attached.append(render_report_html(data)) or b"%PDF-1.4",
        )
        assert (result.status, result.period, result.sent, result.detail) == (DONE, "2026-09", ["u1", "u2"], None)
        for mime in sent:
            for part in mime.walk():
                if part.get_content_type() in ("text/plain", "text/html"):
                    body = part.get_content()
                    assert "Platform health" not in body and "error rate" not in body
                    assert "Model portfolio:" in body
        assert "Platform Health" not in attached[0] and "Error rate" not in attached[0]

    @pytest.mark.asyncio
    async def test_registry_returning_none_is_a_failure_not_na(self, retention_90d, repo):
        # registry_model_count() swallows DB errors and returns None. Unflagged,
        # the script's partial guard would let "N/A models" reach the officials.
        collector, _, _ = self._collector(_fake_metering(registry_model_count=AsyncMock(return_value=None)))
        d = await collector.collect(SEP, now=AFTER_SEP)
        assert "total_models" in d.failed and d.total_models is None

    @pytest.mark.asyncio
    async def test_empty_model_breakdown_with_traffic_is_a_failure(self, retention_90d, repo):
        # model_breakdown() returns empty instead of raising when Prometheus fails.
        empty = AsyncMock(return_value={"services": [], "model_totals": []})
        collector, _, _ = self._collector(_fake_metering(model_breakdown=empty))
        d = await collector.collect(SEP, now=AFTER_SEP)
        assert "model_usage" in d.failed and d.active_models is None

    @pytest.mark.asyncio
    async def test_empty_model_breakdown_without_traffic_is_just_zero(self, retention_90d, repo):
        metering = _fake_metering(
            model_breakdown=AsyncMock(return_value={"services": [], "model_totals": []}),
            inference_request_total=AsyncMock(return_value=0),
        )
        collector, _, _ = self._collector(metering)
        d = await collector.collect(SEP, now=AFTER_SEP)
        assert "model_usage" not in d.failed and d.active_models == 0

    @pytest.mark.asyncio
    async def test_no_usage_recorded_for_the_month_is_unavailable_not_failed(self, retention_90d, repo):
        repo.data_from = None
        collector, _, _ = self._collector()
        d = await collector.collect(SEP, now=AFTER_SEP)
        assert d.period_spend is None and "period_spend" not in d.failed

    @pytest.mark.asyncio
    async def test_recording_that_began_mid_month_covers_only_those_days(self, retention_90d, repo):
        repo.data_from = datetime(2026, 9, 20, 18, 30, tzinfo=UTC)  # 21 Sep 00:00 IST
        collector, _, _ = self._collector()
        ps = (await collector.collect(SEP, now=AFTER_SEP)).period_spend
        assert ps.since == repo.data_from and ps.covered_days == 10
        assert ps.burn_rate == Decimal("3")  # 30 over 10 days, not over 30


class TestRegistryCountsAreOneQuery:
    @pytest.mark.asyncio
    async def test_models_per_task_type_is_one_grouped_call_not_one_per_task(self, retention_90d, repo):
        # Before: registry_model_count was awaited once per task type (12) plus once
        # for the total — 13 sequential DB round-trips.
        metering = _fake_metering()
        collector, _, _ = TestCollector()._collector(metering)
        await collector.collect(SEP, now=AFTER_SEP)
        metering.registry_model_count.assert_awaited_once_with()
        metering.registry_model_counts_by_task.assert_awaited_once_with()

    @pytest.mark.asyncio
    async def test_grouped_counts_map_registry_task_types_to_metering_keys(self):
        repo = MagicMock()
        repo.count_models_by_task_type = AsyncMock(return_value={"nmt": 6, "language-detection": 2, "unknown": 9})
        svc = MeteringService(client=MagicMock(), model_repo=repo)
        assert await svc.registry_model_counts_by_task() == {"nmt": 6, "language_detection": 2}

    @pytest.mark.asyncio
    async def test_grouped_counts_raise_without_a_registry(self):
        with pytest.raises(RuntimeError):
            await MeteringService(client=MagicMock()).registry_model_counts_by_task()


class TestBudgetSummary:
    @pytest.mark.asyncio
    async def test_exactly_100_percent_counts_as_exhausted(self, retention_90d, repo):
        # The dashboard's budgetExceededTenants uses `spent > limit` ("exceeded"), so a
        # tenant at exactly 100% is not counted there; the report asks "used 100%".
        repo.budgets = {
            "1": _budget_ns(100, 100),   # exactly 100% → exhausted
            "2": _budget_ns(100, 130),   # over → exhausted
            "3": _budget_ns(100, 80),    # 80% → nearing
            "4": _budget_ns(100, "79.9"),  # below threshold
            "5": _budget_ns(0, 0),       # zero budget, nothing spent → neither
            "6": _budget_ns(100, 0),     # no spend → not in top-by-spend
        }
        auth = _FakeAuthDB(tenants=TestCollector.TENANTS, budget_tenants=[(i, f"Inst {i}") for i in repo.budgets])
        collector = UsageReportCollector(_fake_metering(), auth, AsyncMock())
        b = (await collector.collect(SEP, now=AFTER_SEP)).budget
        assert (b.exhausted, b.nearing_limit) == (2, 1)
        assert b.allocated == Decimal(500) and b.spent == Decimal("389.9")
        assert b.remaining == b.allocated - b.spent
        assert [s.name for s in b.top_by_spend] == ["Inst 2", "Inst 1", "Inst 3", "Inst 4"]
        assert b.top_by_spend[0].used_pct == pytest.approx(130.0)

    def test_used_pct_none_without_allocation(self):
        assert BudgetSummary(Decimal(0), Decimal(5), Decimal(-5), 0, 0, []).used_pct is None


class _BudgetAuthDB(_FakeAuthDB):
    """Also answers the real UsageRepository.get_tenant_budgets' auth-DB reads."""

    def __init__(self, allocated, apps, keys, **kw):
        super().__init__(**kw)
        self.allocated = allocated  # tenant id -> allocated_budget
        self.apps = apps            # application id -> tenant id
        self.keys = keys            # api_key id -> application id

    async def execute(self, stmt, params=None):
        sql = str(stmt)
        if "FROM tenants WHERE id = ANY(:ids)" in sql:
            return _rows(*[SimpleNamespace(id=i, allocated_budget=self.allocated[i], tier_id=None,
                                           budget_effective_from=None, budget_effective_to=None)
                           for i in params["ids"] if i in self.allocated])
        if sql.startswith("SELECT id, tenant_id FROM applications"):
            return _rows(*[SimpleNamespace(id=a, tenant_id=t) for a, t in self.apps.items() if t in params["ids"]])
        if sql.startswith("SELECT id, application_id FROM api_key"):
            return _rows(*[SimpleNamespace(id=k, application_id=a) for k, a in self.keys.items()
                           if a in params["app_ids"]])
        return await super().execute(stmt, params)


class TestBudgetAgainstTheRealRepository:
    @pytest.mark.asyncio
    async def test_budget_figure_loads_through_the_real_get_tenant_budgets(self, retention_90d, repo_state,
                                                                           monkeypatch):
        # Staging (AI4IDS-3278): the collector passed a leftover billing_month
        # (None) that get_tenant_budgets no longer takes → TypeError → "figures
        # failed to load: budget" → status=not_ready and no email to anyone.
        from app.repositories.pay_per_use.usage_repository import UsageRepository

        # Only the period-spend reads are stubbed; get_tenant_budgets stays real.
        _stub_repo(monkeypatch, "get_usage_data_from", lambda self, p: repo_state.data_from)
        _stub_repo(monkeypatch, "get_period_usage", lambda self, p, *a, **k: repo_state.period_rows)
        assert not isinstance(UsageRepository.get_tenant_budgets, Mock)
        # conftest's autouse catalogue stub must still be active (a monkeypatch.undo() would drop it).
        from app.services.pay_per_use import inference_type_cache
        assert inference_type_cache.get_all.__module__.endswith("conftest")

        auth = _BudgetAuthDB(
            allocated={1: Decimal(100), 2: Decimal(50)},
            apps={10: 1, 20: 2},
            keys={100: 10, 101: 10, 200: 20},
            tenants=TestCollector.TENANTS, budget_tenants=[("1", "Ministry A"), ("2", "Ministry B")],
        )
        core = AsyncMock()
        core.execute = AsyncMock(return_value=_rows(
            SimpleNamespace(api_key_id=100, api_key_budget_used=Decimal(30)),
            SimpleNamespace(api_key_id=101, api_key_budget_used=Decimal(55)),  # tenant 1: 85 of 100
            SimpleNamespace(api_key_id=200, api_key_budget_used=Decimal(50)),  # tenant 2: 50 of 50
        ))
        d = await UsageReportCollector(_fake_metering(), auth, core).collect(SEP, now=AFTER_SEP)

        assert "budget" not in d.failed
        b = d.budget
        assert (b.allocated, b.spent, b.remaining) == (Decimal(150), Decimal(135), Decimal(15))
        assert (b.exhausted, b.nearing_limit) == (1, 1)
        assert [(s.name, s.spent) for s in b.top_by_spend] == [("Ministry A", Decimal(85)), ("Ministry B", Decimal(50))]


# ── recipients ───────────────────────────────────────────────────────────────


class TestUsageViewerEmails:
    @pytest.mark.asyncio
    async def test_dedupes_and_skips_undecryptable(self):
        db = AsyncMock()
        db.execute = AsyncMock(return_value=_rows(
            ("u1", "enc:b@x.gov.in"), ("u2", "enc:A@x.gov.in"), ("u3", "enc:a@X.gov.in"),
            ("u4", "bad"), ("u5", None),
        ))

        def decrypt(token):
            if token == "bad":
                raise ValueError("wrong key")
            return token.split(":", 1)[1] if token else None

        assert await usage_viewer_emails(db, decrypt) == ["A@x.gov.in", "b@x.gov.in"]
        assert db.execute.call_args.args[1] == {"role": "USAGE VIEWER"}


# ── email / attachment ───────────────────────────────────────────────────────


def _full_data() -> ReportData:
    d = ReportData(period=SEP, generated_at=AFTER_SEP)
    d.total_requests, d.prev_total_requests = 18_400_000, 15_600_000
    d.total_models, d.active_models = 42, 31
    d.models_by_task = {"NMT": 12, "ASR": 9}
    d.top_models = [RankedModel("IndicTrans2", "NMT", 22.0)]
    d.total_institutions, d.new_institutions, d.active_institutions = 36, 2, 26
    d.prev_active_institutions, d.dormant_institutions = 23, 6
    d.total_applications, d.active_applications = 84, 61
    d.requests_by_task = [("NMT", 6_100_000), ("ASR", 4_400_000)]
    d.top_institutions = [RankedInstitution("Ministry A", 24.0, ["ASR", "TTS"])]
    d.budget = BudgetSummary(Decimal(500), Decimal(215), Decimal(285), 2, 3,
                             [InstitutionSpend("Ministry A", Decimal(62), 100.0)])
    d.period_spend = PeriodSpend(Decimal(63_000_000), None, 30)
    return d


TICKET_BRANDING = {  # the values env.template ships with (the ticket's email format)
    "usage_report_subject_prefix": "AI Switch",
    "usage_report_title": "AI4I Orchestrate Adoption report",
    "usage_report_team_name": "AI4I Orchestrate Support Team",
    "usage_report_filename_prefix": "AI4I-Orchestrate_Programme-Report_India-AI-Mission",
}


def set_branding(monkeypatch, **values):
    for name, value in {**TICKET_BRANDING, **values}.items():
        monkeypatch.setattr(f"app.core.config.settings.{name}", value)


@pytest.fixture
def portal(monkeypatch):
    monkeypatch.setattr("app.services.usage_report.mailer.settings.portal_url", "https://portal.gov.in/")
    monkeypatch.setattr("app.services.usage_report.mailer.settings.usage_report_sender_name", None)
    set_branding(monkeypatch)


class TestBrandingFromSettings:
    """No product name in code: subject, title, team and file name come from
    USAGE_REPORT_* settings, falling back to PLATFORM_NAME."""

    def test_configured_values_are_used_everywhere(self, portal, monkeypatch):
        from app.services.usage_report.pdf import report_context

        set_branding(monkeypatch, usage_report_subject_prefix="Programme X", usage_report_title="X Usage report",
                     usage_report_team_name="X Team", usage_report_filename_prefix="X_Report")
        msg = mailer.render_email(_full_data(), "v@x.gov.in")
        assert msg.subject == "Programme X – Monthly programme report – September 2026"
        assert "Please find attached the X Usage report for September 2026." in msg.text_body
        assert "X Team" in msg.text_body and "X_Report_2026-09.pdf" in msg.text_body
        assert mailer.attachment_name(_full_data()) == "X_Report_2026-09.pdf"
        assert report_context(_full_data())["report_title"] == "X Usage report"

    def test_blank_values_fall_back_to_platform_name(self, portal, monkeypatch):
        # The original mismatch: header said PLATFORM_NAME ("AI4Inclusion"), body a
        # baked-in "AI4I Orchestrate". Unset, everything now follows PLATFORM_NAME.
        monkeypatch.setattr("app.core.config.settings.platform_name", "AI4Inclusion")
        set_branding(monkeypatch, usage_report_subject_prefix=None, usage_report_title="  ",
                     usage_report_team_name=None, usage_report_filename_prefix=None)
        msg = mailer.render_email(_full_data(), "v@x.gov.in")
        assert msg.subject == "AI4Inclusion – Monthly programme report – September 2026"
        assert "the AI4Inclusion Adoption report for" in msg.text_body
        assert "AI4Inclusion Support Team" in msg.text_body
        assert mailer.attachment_name(_full_data()) == "AI4Inclusion_Programme-Report_2026-09.pdf"
        for body in (msg.text_body, msg.html_body):
            assert "AI4I Orchestrate" not in body and "AI Switch" not in body

    @pytest.mark.parametrize("prefix,expected", [
        ("Min. of Agri/Health: 2026 ", "Min.-of-AgriHealth-2026"),
        ("../../etc/passwd", "etcpasswd"),       # no path separators survive
        ("  ///  ", "Usage-Report"),             # nothing usable left
    ])
    def test_filename_prefix_is_made_safe(self, monkeypatch, prefix, expected):
        monkeypatch.setattr("app.core.config.settings.usage_report_filename_prefix", prefix)
        from app.core.config import settings
        assert settings.get_usage_report_filename_prefix() == expected

    @pytest.mark.parametrize("field", ["usage_report_subject_prefix", "usage_report_title",
                                       "usage_report_team_name", "usage_report_sender_name"])
    def test_line_breaks_are_rejected_at_startup(self, field):
        # A line break in the subject would inject email headers (and make every send fail).
        from pydantic import ValidationError

        from app.core.config import CoreSettings
        with pytest.raises(ValidationError, match="line breaks"):
            CoreSettings(**{field: "AI Switch\r\nBcc: attacker@example.com"})


class TestRenderEmail:
    def test_subject_and_summary_use_real_figures(self, portal):
        msg = mailer.render_email(_full_data(), "viewer@x.gov.in")
        assert msg.subject == "AI Switch – Monthly programme report – September 2026"
        lines = mailer.summary_lines(_full_data())
        assert lines == [
            "Model portfolio: 42 Models; 31 were used in September.",
            "Adoption: 26 of 36 Institutions were live (+3 vs August). 18.4M requests were served (+17.9%).",
        ]
        for body in (msg.html_body, msg.text_body):
            assert "AI4I-Orchestrate_Programme-Report_India-AI-Mission_2026-09.pdf" in body
            assert "https://portal.gov.in/usage-dashboard" in body

    def test_no_untracked_or_dummy_figures_in_the_email(self, portal):
        # Availability, P95, providers, financial-year totals and the budget line
        # are not tracked, so they must not appear with made-up values.
        msg = mailer.render_email(_full_data(), "viewer@x.gov.in")
        for body in (msg.html_body, msg.text_body):
            for dummy in ("availability", "P95", "providers", "financial year", "Budget:",
                          "99.6%", "640 ms", "62.4M", "43%", "₹21.5 Cr", "₹50 Cr"):
                assert dummy not in body, dummy

    def test_failed_figures_show_na_and_drop_the_comparison(self, portal):
        lines = mailer.summary_lines(ReportData(period=SEP, generated_at=AFTER_SEP))
        assert "N/A Models" in lines[0]
        assert "N/A of N/A Institutions were live." in lines[1]
        assert " vs " not in lines[1]

    def test_sender_name_is_escaped_in_html(self, portal, monkeypatch):
        monkeypatch.setattr("app.services.usage_report.mailer.settings.usage_report_sender_name",
                            "<script>x</script>")
        msg = mailer.render_email(_full_data(), "viewer@x.gov.in")
        assert "<script>" not in msg.html_body and "&lt;script&gt;" in msg.html_body


def _email_cfg(**kw) -> EmailSettings:
    base = dict(email_provider="smtp", email_from="noreply@x.gov.in", email_from_name="AI4I",
                smtp_host="smtp.x.gov.in", environment="production")
    base.update(kw)
    return EmailSettings(_env_file=None, **base)


class TestRenderedOnce:
    @pytest.mark.asyncio
    async def test_the_template_is_rendered_once_for_any_number_of_recipients(self, portal, monkeypatch):
        # Before: rendered once per recipient although the template never uses the
        # address — 50 Usage Viewers meant 50 identical renderings.
        calls = []
        real = mailer._renderer.render
        monkeypatch.setattr(mailer._renderer, "render", lambda *a, **k: calls.append(1) or real(*a, **k))
        sent_to = []

        async def send(mime, cfg):
            sent_to.append(mime["To"])

        recipients = ["a@x.gov.in", "b@x.gov.in", "c@x.gov.in"]
        sent, failed = await mailer.deliver(_full_data(), b"%PDF", recipients, _email_cfg(), send=send)
        assert len(calls) == 1
        assert sent == recipients and sent_to == recipients and failed == {}


class TestReportMime:
    def test_pdf_is_attached_alongside_html_and_text(self, portal):
        msg = mailer.render_email(_full_data(), "viewer@x.gov.in")
        mime = mailer.build_report_mime(msg, b"%PDF-1.4 test", "report.pdf", _email_cfg())
        parsed = email.message_from_bytes(mime.as_bytes())
        assert parsed.get_content_type() == "multipart/mixed"
        assert parsed["To"] == "viewer@x.gov.in"
        types = [p.get_content_type() for p in parsed.walk()]
        assert "text/plain" in types and "text/html" in types and "application/pdf" in types
        pdf_part = next(p for p in parsed.walk() if p.get_content_type() == "application/pdf")
        assert pdf_part.get_filename() == "report.pdf"
        assert pdf_part.get_payload(decode=True) == b"%PDF-1.4 test"

    @pytest.mark.asyncio
    async def test_unconfigured_smtp_raises_instead_of_pretending_to_send(self):
        with pytest.raises(EmailDeliveryError, match="SMTP is not configured"):
            await mailer.send_report_mime(MagicMock(), _email_cfg(smtp_host=None, environment="development"))
        with pytest.raises(EmailDeliveryError):
            await mailer.send_report_mime(MagicMock(), _email_cfg(email_provider="console"))


class TestDeliver:
    @pytest.mark.asyncio
    async def test_one_email_per_recipient_and_a_failure_does_not_stop_the_rest(self, portal):
        seen = []

        async def send(mime, cfg):
            seen.append(mime["To"])
            if mime["To"] == "b@x.gov.in":
                raise EmailDeliveryError("relay refused")

        sent, failed = await mailer.deliver(
            _full_data(), b"%PDF", ["a@x.gov.in", "b@x.gov.in", "c@x.gov.in"], _email_cfg(), send=send
        )
        assert seen == ["a@x.gov.in", "b@x.gov.in", "c@x.gov.in"]  # never more than one To
        assert sent == ["a@x.gov.in", "c@x.gov.in"] and list(failed) == ["b@x.gov.in"]
        assert "relay refused" in failed["b@x.gov.in"]

    @pytest.mark.asyncio
    async def test_header_injection_in_to_fails_that_recipient_only(self, portal):
        send = AsyncMock()
        sent, failed = await mailer.deliver(
            _full_data(), b"%PDF", ["a@x.gov.in\r\nBcc: evil@x.com", "c@x.gov.in"], _email_cfg(), send=send
        )
        assert sent == ["c@x.gov.in"] and len(failed) == 1
        assert send.await_count == 1


# ── PDF (HTML template → WeasyPrint) ─────────────────────────────────────────


def _weasyprint():
    """WeasyPrint needs Pango at runtime (installed in the service image)."""
    try:
        import weasyprint
    except (ImportError, OSError) as exc:  # OSError: Pango missing
        pytest.skip(f"WeasyPrint unavailable: {exc}")
    return weasyprint


def _pages(html: str) -> int:
    return len(_weasyprint().HTML(string=html).render().pages)


class TestReportHtml:
    def test_real_values_and_placeholders(self):
        html = render_report_html(_full_data())
        for real in ("September 2026", "42", "31 active", "11 inactive", "36 total",
                     "+2 new this period", "84 total", "18.4M", "+17.9%", "6.1 L",
                     "₹500", "₹285", "₹6.3 Cr", "Ministry A", "IndicTrans2"):
            assert real in html, real
        # Availability, P95, fallback rate and providers are not tracked, so not shown.
        for untracked in ("Availability", "Latency P95", "Fallback rate", "Providers"):
            assert untracked not in html, untracked

    def test_sections_are_unnumbered_and_platform_health_is_gone(self):
        import re

        html = render_report_html(_full_data())
        assert re.findall(r"<h2>(.*?)</h2>", html) == ["Model Portfolio", "Adoption Ratio", "Budget Utilisation"]
        for removed in ("Platform Health", "Error rate", "5xx"):
            assert removed not in html, removed
        assert "health_cards" not in report_context(_full_data())

    def test_dormant_legend_is_just_dormant(self):
        html = render_report_html(_full_data())
        assert '<span class="seg-dormant">dormant</span>' in html
        assert "2+ periods" not in html

    def test_untrusted_names_are_escaped(self):
        # An institution can be named by an admin; the name must stay text, not markup.
        d = _full_data()
        d.top_institutions = [RankedInstitution('<img src="file:///etc/passwd">', 50.0, ["NMT"])]
        html = render_report_html(d)
        assert '<img src="file:///etc/passwd">' not in html
        assert "&lt;img src=&#34;file:///etc/passwd&#34;&gt;" in html

    def test_empty_report_renders_no_traffic_messages(self):
        html = render_report_html(ReportData(period=SEP, generated_at=AFTER_SEP))
        assert "No model traffic in this period" in html
        assert "No institution traffic in this period" in html
        assert "Usage not recorded for this period" in html

    @pytest.mark.parametrize("active,total,width", [(10, 10, 100.0), (0, 10, 0.0), (1, 1000, 0.1)])
    def test_donut_width_edges(self, active, total, width):
        d = _full_data()
        d.active_models, d.total_models = active, total
        assert report_context(d)["models"]["active_width"] == width

    def test_bar_widths_are_clamped(self):
        d = _full_data()
        d.budget = BudgetSummary(Decimal(1), Decimal(5), Decimal(-4), 1, 0,
                                 [InstitutionSpend("X", Decimal(5), 500.0)])
        ctx = report_context(d)
        assert ctx["budget"]["used_width"] == 100.0
        assert ctx["budget"]["top_spend"][0]["width"] == 100.0


class TestThresholdsHaveOneSource:
    @pytest.mark.asyncio
    async def test_changing_the_nearing_limit_changes_counts_and_pdf_together(self, retention_90d, repo, monkeypatch):
        # Before: collector used NEARING_LIMIT_PCT, the PDF hard-coded 80 — at 70 a
        # 75%-used institution was counted "nearing" but drawn navy under "80%+".
        from app.services.usage_report import collector as collector_module

        monkeypatch.setattr(collector_module, "NEARING_LIMIT_PCT", 70.0)
        repo.budgets = {"1": _budget_ns(100, 75)}
        auth = _FakeAuthDB(tenants=TestCollector.TENANTS, budget_tenants=[("1", "Inst 1")])
        d = await UsageReportCollector(_fake_metering(), auth, AsyncMock()).collect(SEP, now=AFTER_SEP)
        assert d.budget.nearing_limit == 1
        budget = report_context(d)["budget"]
        assert budget["nearing_pct"] == "70%"
        assert budget["top_spend"][0]["css"] == "amber"
        assert "nearing limit (70%+ used)" in render_report_html(d)


class TestReportPdf:
    def test_full_report_is_one_a4_page(self):
        _weasyprint()
        pdf = render_report_pdf(_full_data())
        assert pdf.startswith(b"%PDF")
        assert _pages(render_report_html(_full_data())) == 1

    @staticmethod
    def _worst_case() -> ReportData:
        d = _full_data()
        d.top_models = [RankedModel("M" * 200, "Transliteration", 20.0)] * 5
        d.top_institutions = [RankedInstitution("I" * 300, 20.0, ["Speaker Diarization", "NMT"])] * 5
        d.requests_by_task = [(f"Task {i}", 10**9 - i) for i in range(20)]
        d.budget = BudgetSummary(Decimal(10**15), Decimal(10**15), Decimal(0), 99, 99,
                                 [InstitutionSpend("S" * 300, Decimal(10**15), 100.0)] * 5)
        return d

    def test_worst_case_content_still_fits_one_page(self):
        assert _pages(render_report_html(self._worst_case())) == 1

    def test_long_names_do_not_push_percentages_off_the_page(self):
        # Without min-width: 0 on flex items, a 300-character institution name
        # widens its panel and the % column lands past the page edge (~1600px).
        from weasyprint.formatting_structure import boxes

        page = _weasyprint().HTML(string=render_report_html(self._worst_case())).render().pages[0]
        content_right = page.width - 12 * 96 / 25.4 + 1  # 12mm right margin, in CSS px
        pct_right = max(
            b.position_x + b.width for b in page._page_box.descendants()
            if isinstance(b, boxes.TextBox) and b.text.strip().endswith("%")
        )
        assert pct_right <= content_right

    def test_local_files_are_not_fetched(self, monkeypatch, tmp_path):
        # A template (or a future edit to it) referencing a local file must not
        # embed it: the renderer only allows data: URIs.
        from app.services.usage_report import pdf as pdf_module

        weasyprint = _weasyprint()
        png = tmp_path / "secret.png"
        png.write_bytes(bytes.fromhex(
            "89504e470d0a1a0a0000000d4948445200000001000000010806000000"
            "1f15c4890000000d49444154789c6360000002000154a24f5d0000000049454e44ae426082"
        ))
        html = f'<p>x</p><img src="file://{png}">'
        unrestricted = weasyprint.HTML(string=html).write_pdf()
        assert b"/Image" in unrestricted  # control: the image does load without the restriction
        monkeypatch.setattr(pdf_module, "render_report_html", lambda data: html)
        assert b"/Image" not in pdf_module.render_report_pdf(_full_data())


# ── script ───────────────────────────────────────────────────────────────────


class TestSendScript:
    @pytest.fixture
    def wired(self, monkeypatch):
        """The script's run() with every external dependency stubbed."""
        from ai4i_core import pii_crypto

        import app.core.database as database
        from app.scripts import send_usage_report as script

        monkeypatch.setattr("app.core.config.settings.prometheus_url", "http://prom:9090")
        prom_query = AsyncMock(return_value=[{"value": [0, "1"]}])
        monkeypatch.setattr("app.utils.prometheus_client.PrometheusClient.query", prom_query)
        monkeypatch.setattr(pii_crypto, "configure_key", lambda key: None)
        monkeypatch.setattr(pii_crypto, "validate_key", lambda: None)
        # conftest stubs app.core.database without these, so add them (raising=False).
        monkeypatch.setattr(database, "init_database", AsyncMock(), raising=False)
        monkeypatch.setattr(database, "close_database", AsyncMock(), raising=False)
        monkeypatch.setattr(database, "init_auth_database", lambda: None, raising=False)
        monkeypatch.setattr(database, "close_auth_database", AsyncMock(), raising=False)

        class _Session:
            async def __aenter__(self):
                return AsyncMock()

            async def __aexit__(self, *exc):
                return False

        monkeypatch.setattr(database, "get_auth_session_factory", lambda: _Session, raising=False)
        monkeypatch.setattr(database, "get_primary_session_factory", lambda: _Session, raising=False)
        state = SimpleNamespace(data=_full_data(), deliver=AsyncMock(return_value=(["v@x.gov.in"], {})),
                                prom_query=prom_query)
        monkeypatch.setattr(
            "app.services.usage_report.collector.UsageReportCollector.collect",
            AsyncMock(side_effect=lambda period: state.data),
        )
        monkeypatch.setattr("app.services.usage_report.recipients.usage_viewer_emails",
                            AsyncMock(return_value=["v@x.gov.in"]))
        monkeypatch.setattr("app.services.usage_report.mailer.deliver", state.deliver)
        monkeypatch.setattr("app.services.usage_report.mailer.email_settings", lambda: _email_cfg())
        set_branding(monkeypatch)
        return script, state

    @pytest.mark.asyncio
    async def test_sends_to_usage_viewers(self, wired):
        script, state = wired
        assert await script.run(script._parse_args(["--period", "2026-09"])) == script.EXIT_OK
        args = state.deliver.call_args.args
        assert args[2] == ["v@x.gov.in"] and args[1].startswith(b"%PDF")

    @pytest.mark.asyncio
    async def test_partial_figures_send_nothing_unless_allowed(self, wired):
        script, state = wired
        state.data.failed = ["total_requests"]
        assert await script.run(script._parse_args(["--period", "2026-09"])) == script.EXIT_FAILED
        state.deliver.assert_not_awaited()
        assert await script.run(script._parse_args(["--period", "2026-09", "--allow-partial"])) == script.EXIT_OK
        state.deliver.assert_awaited_once()

    @pytest.mark.asyncio
    async def test_to_overrides_recipients(self, wired):
        script, state = wired
        await script.run(script._parse_args(["--period", "2026-09", "--to", "me@x.gov.in"]))
        assert state.deliver.call_args.args[2] == ["me@x.gov.in"]

    @pytest.mark.asyncio
    async def test_dry_run_writes_files_and_sends_nothing(self, wired, tmp_path):
        script, state = wired
        code = await script.run(script._parse_args(["--period", "2026-09", "--dry-run", "--out-dir", str(tmp_path)]))
        assert code == script.EXIT_OK
        state.deliver.assert_not_awaited()
        assert sorted(p.name for p in tmp_path.iterdir()) == [
            "AI4I-Orchestrate_Programme-Report_India-AI-Mission_2026-09.pdf",
            "usage-report-2026-09.html", "usage-report-2026-09.txt",
        ]

    @pytest.mark.asyncio
    async def test_partial_send_exits_non_zero(self, wired):
        script, state = wired
        state.deliver.return_value = (["a@x.gov.in"], {"b@x.gov.in": "relay refused"})
        assert await script.run(script._parse_args(["--period", "2026-09"])) == script.EXIT_FAILED

    @pytest.mark.asyncio
    async def test_unreachable_prometheus_fails_once_and_sends_nothing(self, wired):
        script, state = wired
        state.prom_query.side_effect = RuntimeError("connection refused")
        assert await script.run(script._parse_args(["--period", "2026-09"])) == script.EXIT_FAILED
        state.deliver.assert_not_awaited()

    @pytest.mark.asyncio
    @pytest.mark.parametrize("status,failed,code", [
        ("done", [], 0), ("nothing_due", [], 0), ("busy", [], 0),
        ("done", ["u2"], 1), ("not_ready", [], 1), ("no_recipients", [], 1),
    ])
    async def test_scheduled_runs_the_scheduler_and_maps_its_outcome(self, wired, monkeypatch, status, failed, code):
        from app.services.usage_report import scheduler

        script, state = wired
        run = AsyncMock(return_value=scheduler.RunResult(status, "weekly", "p", [], failed))
        monkeypatch.setattr(scheduler, "run_scheduled_report", run)
        assert await script.run(script._parse_args(["--scheduled", "--frequency", "weekly"])) == code
        assert run.await_args.args[0] == "weekly"
        state.deliver.assert_not_awaited()  # the manual path is not used

    @pytest.mark.asyncio
    async def test_scheduled_rejects_manual_options(self, wired):
        script, state = wired
        assert await script.run(script._parse_args(["--scheduled", "--to", "me@x.gov.in"])) == script.EXIT_USAGE

    @pytest.mark.asyncio
    @pytest.mark.parametrize("missing", ["prometheus", "auth_db"])
    async def test_missing_configuration_fails_the_same_way_in_both_paths(self, wired, monkeypatch, missing):
        # One check (report_sources) now serves the manual and the scheduled path.
        import app.core.database as database
        from app.services.usage_report import scheduler

        script, state = wired
        if missing == "prometheus":
            monkeypatch.setattr("app.core.config.settings.prometheus_url", None)
        else:
            monkeypatch.setattr(database, "get_auth_session_factory", lambda: None, raising=False)
        assert await script.run(script._parse_args(["--period", "2026-09"])) == script.EXIT_FAILED
        state.deliver.assert_not_awaited()

        from contextlib import asynccontextmanager

        @asynccontextmanager
        async def lock(engine):
            yield True
        monkeypatch.setattr("app.services.usage_report.send_log.report_lock", lock)
        monkeypatch.setattr(database, "get_engine", lambda: None, raising=False)
        with pytest.raises(RuntimeError, match="PROMETHEUS_URL" if missing == "prometheus" else "AUTH_DB_NAME"):
            await scheduler.run_scheduled_report("monthly", http_client=None)

    @pytest.mark.asyncio
    async def test_bad_period_is_a_usage_error(self, wired):
        script, state = wired
        assert await script.run(script._parse_args(["--period", "Sept"])) == script.EXIT_USAGE
        state.deliver.assert_not_awaited()
