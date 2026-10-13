"""The Usage Viewer report PDF: ReportData → HTML template → PDF (AI4IDS-3278).

1. report_context() turns ReportData into the template's data contract:
   pre-formatted strings, plus *_width numbers (0–100) for bar widths.
   None means "not available for this period"; the template renders "—".
2. render_report_html() renders app/templates/reports/usage_report.html
   with Jinja (autoescaped, so an institution named "<b>…" stays text).
3. render_report_pdf() converts that HTML to one A4 page with WeasyPrint.

The template owns the design and can be restyled without touching this
file, as long as it keeps to the context keys below.

WeasyPrint needs Pango at runtime (see the service Dockerfile). Its URL
fetcher is limited to data: URIs, so rendering never reads local files or
calls out to the network, whatever the template contains.
"""
from __future__ import annotations

from pathlib import Path
from typing import Optional

from jinja2 import Environment, FileSystemLoader, StrictUndefined, select_autoescape

from app.services.usage_report import formatting as fmt
from app.services.usage_report.collector import ReportData
from app.utils.usage_period import IST

_TEMPLATE_DIR = Path(__file__).resolve().parent.parent.parent / "templates" / "reports"
_env = Environment(
    loader=FileSystemLoader(str(_TEMPLATE_DIR)),
    autoescape=select_autoescape(default=True, default_for_string=True),
    undefined=StrictUndefined,
    trim_blocks=True,
    lstrip_blocks=True,
)

TEMPLATE = "usage_report.html"
NOT_TRACKED = "Not tracked yet"
MAX_TASK_ROWS = 8


def _width(value: Optional[float], peak: Optional[float] = 100.0) -> float:
    """A bar's % of its track, clamped to 0–100."""
    if value is None or not peak:
        return 0.0
    return round(max(0.0, min(100.0, value / peak * 100)), 1)


def _segments(parts: list[tuple[int, str]]) -> list[dict]:
    total = sum(n for n, _ in parts)
    return [
        {"count": n, "css": css, "width": _width(n, total)}
        for n, css in parts if total and n > 0
    ]


def _card(label: str, value: Optional[str], note: Optional[str] = None) -> dict:
    return {"label": label, "value": value, "note": note}


def _health(d: ReportData) -> list[dict]:
    note = (f"{fmt.count(d.server_errors)} of {fmt.count(d.total_requests)} requests"
            if d.error_rate_pct is not None else None)
    # Availability, P95 latency and fallback rate are not tracked yet, so not shown.
    return [_card("Error rate (5xx)", fmt.pct(d.error_rate_pct), note)]


def _models(d: ReportData) -> dict:
    active, inactive = d.active_models, d.inactive_models
    known = active is not None and inactive is not None and (active + inactive) > 0
    peak = max((m.share_pct for m in d.top_models), default=0)
    return {
        "total": fmt.count(d.total_models),
        "active": fmt.count(active),
        "inactive": fmt.count(inactive),
        "active_width": _width(active, active + inactive) if known else None,
        "top": [
            {"name": m.name, "task": m.task, "share": fmt.pct(m.share_pct, 0), "width": _width(m.share_pct, peak)}
            for m in d.top_models
        ],
        "by_task": " · ".join(f"{k} {v}" for k, v in sorted(d.models_by_task.items(), key=lambda x: -x[1])),
    }


def _adoption(d: ReportData) -> dict:
    institution_segments: list[dict] = []
    if d.active_institutions is not None and d.total_institutions is not None:
        dormant = d.dormant_institutions or 0
        other = max(0, d.total_institutions - d.active_institutions - dormant)
        institution_segments = _segments(
            [(d.active_institutions, "seg-active"), (other, "seg-other"), (dormant, "seg-dormant")]
        )
    application_segments: list[dict] = []
    applications_active_pct = ""
    if d.active_applications is not None and d.total_applications:
        active = min(d.active_applications, d.total_applications)
        application_segments = _segments([(active, "seg-active"), (d.total_applications - active, "seg-other")])
        applications_active_pct = f"{fmt.pct(active / d.total_applications * 100, 0)} active"

    rows = list(d.requests_by_task)
    if len(rows) > MAX_TASK_ROWS:
        rows = rows[:MAX_TASK_ROWS - 1] + [("Others", sum(n for _, n in rows[MAX_TASK_ROWS - 1:]))]
    task_peak = max((n for _, n in rows), default=0)
    inst_peak = max((i.share_pct for i in d.top_institutions), default=0)
    change = d.requests_change_pct
    return {
        "institutions_total": fmt.count(d.total_institutions),
        "institutions_new": d.new_institutions,
        "institution_segments": institution_segments,
        "dormant_tracked": d.dormant_institutions is not None,
        "applications_total": fmt.count(d.total_applications),
        "applications_active_pct": applications_active_pct,
        "application_segments": application_segments,
        "requests": fmt.count(d.total_requests),
        "requests_change": fmt.signed_pct(change) if change is not None else None,
        "requests_change_up": change is not None and change >= 0,
        "avg_daily": fmt.indian(d.avg_daily_requests),
        "tasks": [{"name": name, "count": fmt.count(n), "width": _width(n, task_peak)} for name, n in rows],
        "top_institutions": [
            {"name": i.name, "tasks": ", ".join(i.main_tasks), "share": fmt.pct(i.share_pct, 0),
             "width": _width(i.share_pct, inst_peak)}
            for i in d.top_institutions
        ],
    }


def _budget(d: ReportData) -> dict:
    b, ps = d.budget, d.period_spend
    span = d.period.short_label
    if ps is None:
        spent_card = _card(f"Spent ({span})", None, "Usage not recorded for this period")
        burn_card = _card("Burn rate (per day)", None, "Usage not recorded for this period")
    else:
        note = (f"Recorded since {ps.since.astimezone(IST):%d %b}" if ps.since
                else (f"Lifetime to date: {fmt.inr(b.spent)}" if b else None))
        spent_card = _card(f"Spent ({span})", fmt.inr(ps.amount), note)
        burn_card = _card("Burn rate (per day)", fmt.inr(ps.burn_rate), f"Average over {ps.covered_days} day(s)")
    used = b.used_pct if b else None
    return {
        "cards": [
            _card("Allocated", fmt.inr(b.allocated) if b else fmt.NA, "Sum of institution allocations"),
            spent_card,
            _card("Remaining", fmt.inr(b.remaining) if b else fmt.NA, "Allocation minus spend to date"),
            burn_card,
        ],
        "used_width": _width(used) if used is not None else None,
        "used_pct": fmt.pct(used, 0),
        "remaining_pct": fmt.pct(100 - used, 0) if used is not None else fmt.NA,
        "exhausted": b.exhausted if b else None,
        "nearing": b.nearing_limit if b else None,
        "top_spend": [
            {"name": s.name, "spent": fmt.inr(s.spent), "used": fmt.pct(s.used_pct, 0), "width": _width(s.used_pct),
             "css": "red" if s.used_pct >= 100 else "amber" if s.used_pct >= 80 else ""}
            for s in (b.top_by_spend if b else [])
        ],
    }


def report_context(data: ReportData) -> dict:
    """The template's data contract (see the template's header comment)."""
    return {
        "period_label": data.period.label,
        "date_span": data.period.date_span,
        "generated_at": f"{data.generated_at.astimezone(IST):%d %b %Y %H:%M} IST",
        "not_tracked": NOT_TRACKED,
        "health_cards": _health(data),
        "models": _models(data),
        "adoption": _adoption(data),
        "budget": _budget(data),
    }


def render_report_html(data: ReportData) -> str:
    return _env.get_template(TEMPLATE).render(**report_context(data))


def render_report_pdf(data: ReportData) -> bytes:
    # Imported here: WeasyPrint loads Pango when imported, and only this step needs it.
    from weasyprint import HTML
    from weasyprint.urls import URLFetcher

    fetcher = URLFetcher(allowed_protocols=("data",))
    return HTML(string=render_report_html(data), url_fetcher=fetcher).write_pdf()
