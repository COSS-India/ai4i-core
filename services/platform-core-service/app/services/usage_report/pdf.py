"""The Usage Viewer report PDF: ReportData → HTML template → PDF (AI4IDS-3278).

1. report_context() turns ReportData into the template's data contract:
   pre-formatted strings, plus *_width numbers (0–100) for bar widths.
   Empty values arrive already worded (see formatting): "0", "—" or
   "Not available".
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

from app.core.config import settings
from app.services.usage_report import collector, formatting as fmt
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
MAX_TASK_ROWS = 8
NO_REQUESTS = "No requests in this period"
NO_SPEND = "No spend in this period"
# A stacked-bar segment narrower than this (% of the bar) has no room for its
# count; the legend still gives it.
MIN_LABELLED_SEGMENT = 8.0


def _width(value: Optional[float], peak: Optional[float] = 100.0) -> float:
    """A bar's % of its track, clamped to 0–100."""
    if value is None or not peak:
        return 0.0
    return round(max(0.0, min(100.0, value / peak * 100)), 1)


def _share_of(part: Optional[float], whole: Optional[float]) -> str:
    """part as a % of whole: "Not available" when either is unknown, "—" when
    whole is 0 (nothing to divide by)."""
    if part is None or whole is None:
        return fmt.NA
    return fmt.share(part / whole * 100 if whole else None)


def _active_share(active: Optional[int], total: Optional[int]) -> str:
    """"42% active", "Active: —" (none registered) or "Active: Not available"."""
    share = _share_of(active, total)
    return f"{share} active" if share.endswith("%") else f"Active: {share}"


def _segments(parts: list[tuple[int, str, str]]) -> tuple[list[dict], list[dict]]:
    """(bar segments, legend items) for a stacked bar of (count, css, label)
    parts. Every part is in the legend, zeros too; only non-zero parts get a
    segment, sized by its share of the total."""
    total = sum(n for n, _, _ in parts)
    segments = []
    for n, css, _ in parts:
        if total and n > 0:
            width = _width(n, total)
            segments.append({"count": fmt.count(n) if width >= MIN_LABELLED_SEGMENT else "",
                             "css": css, "width": width})
    legend = [{"css": css, "text": f"{fmt.count(n)} {label}"} for n, css, label in parts]
    return segments, legend


def _card(label: str, value: str, note: str = "") -> dict:
    return {"label": label, "value": value, "note": note, "muted": value in (fmt.NA, fmt.NO_RATE)}


def _empty(loaded: bool, message: str) -> str:
    """What an empty Top 5 card says: nothing happened, or the figure is missing."""
    return message if loaded else fmt.NA


def _models(d: ReportData) -> dict:
    active, inactive = d.active_models, d.inactive_models
    known = active is not None and inactive is not None
    return {
        "total": fmt.count(d.total_models),
        "active": f"{fmt.count(active)} active" if known else f"Active: {fmt.NA}",
        "inactive": f"{fmt.count(inactive)} inactive" if known else f"Inactive: {fmt.NA}",
        "active_width": _width(active, active + inactive) if known and (active + inactive) > 0 else None,
        "top": [
            # Bar length is the model's share of all requests: the % printed beside it.
            {"name": m.name, "task": m.task, "share": fmt.share(m.share_pct), "width": _width(m.share_pct)}
            for m in d.top_models
        ],
        "top_empty": _empty(active is not None, NO_REQUESTS),
        "by_task": " · ".join(
            f"{k} {fmt.count(v)}" for k, v in sorted(d.models_by_task.items(), key=lambda x: -x[1])
        ),
    }


def _adoption(d: ReportData) -> dict:
    institution_segments: list[dict] = []
    institution_legend: list[dict] = []
    if d.active_institutions is not None and d.total_institutions is not None:
        active = min(d.active_institutions, d.total_institutions)
        dormant = d.dormant_institutions
        parts = [(active, "seg-active", "active"),
                 (max(0, d.total_institutions - active - (dormant or 0)), "seg-other", "not active this period")]
        if dormant is not None:
            parts.append((dormant, "seg-dormant", "dormant"))
        institution_segments, institution_legend = _segments(parts)
    application_segments: list[dict] = []
    application_legend: list[dict] = []
    if d.active_applications is not None and d.total_applications is not None:
        active = min(d.active_applications, d.total_applications)
        application_segments, application_legend = _segments(
            [(active, "seg-active", "active"), (d.total_applications - active, "seg-other", "inactive")]
        )

    rows = list(d.requests_by_task)
    if len(rows) > MAX_TASK_ROWS:
        rows = rows[:MAX_TASK_ROWS - 1] + [("Others", sum(n for _, n in rows[MAX_TASK_ROWS - 1:]))]
    task_total = sum(n for _, n in rows)
    change = d.requests_change_pct
    avg = d.avg_daily_requests
    return {
        "institutions_total": fmt.count(d.total_institutions),
        "institutions_new": d.new_institutions,
        "institutions_active_pct": _active_share(d.active_institutions, d.total_institutions),
        "institution_segments": institution_segments,
        "institution_legend": institution_legend,
        "dormant_tracked": d.dormant_institutions is not None,
        "applications_total": fmt.count(d.total_applications),
        "applications_active_pct": _active_share(d.active_applications, d.total_applications),
        "application_segments": application_segments,
        "application_legend": application_legend,
        "requests": fmt.count(d.total_requests),
        "requests_change": fmt.signed_pct(change) if change is not None else None,
        "requests_change_up": change is not None and change >= 0,
        # A period under a day has no per-day average.
        "avg_daily": fmt.NA if d.total_requests is None else (fmt.NO_RATE if avg is None else fmt.count(avg)),
        # Bar length is the task's share of all requests.
        "tasks": [{"name": name, "count": fmt.count(n), "width": _width(n, task_total)} for name, n in rows],
        "top_institutions": [
            {"name": i.name, "tasks": ", ".join(i.main_tasks), "share": fmt.share(i.share_pct),
             "width": _width(i.share_pct)}
            for i in d.top_institutions
        ],
        "top_empty": _empty("institution_usage" not in d.failed, NO_REQUESTS),
    }


def _budget(d: ReportData) -> dict:
    b, ps = d.budget, d.period_spend
    span = d.period.short_label
    if ps is None:
        note = "" if "period_spend" in d.failed else "Usage not recorded for this period"
        spent_card = _card(f"Spent ({span})", fmt.NA, note)
        burn_card = _card("Burn rate (per day)", fmt.NA, note)
    else:
        note = (f"Recorded since {ps.since.astimezone(IST):%d %b}" if ps.since
                else (f"Lifetime to date: {fmt.inr(b.spent)}" if b else ""))
        spent_card = _card(f"Spent ({span})", fmt.inr(ps.amount), note)
        burn_card = (
            _card("Burn rate (per day)", fmt.NO_RATE, "Not calculated for periods under a day")
            if ps.burn_rate is None
            else _card("Burn rate (per day)", fmt.inr(ps.burn_rate), f"Average over {ps.covered_days} day(s)")
        )
    used = b.used_pct if b else None
    if b is None:
        used_pct = remaining_pct = fmt.NA
    else:  # used is None: nothing allocated to measure against
        used_pct = fmt.share(used)
        remaining_pct = fmt.share(max(0.0, 100 - used) if used is not None else None)
    return {
        "cards": [
            _card("Allocated", fmt.inr(b.allocated) if b else fmt.NA, "Sum of institution allocations"),
            spent_card,
            _card("Remaining", fmt.inr(b.remaining) if b else fmt.NA, "Allocation minus spend to date"),
            burn_card,
        ],
        "fy_allocation": fmt.NA,
        "used_width": _width(used) if used is not None else None,
        "used_pct": used_pct,
        "remaining_pct": remaining_pct,
        "exhausted": fmt.count(b.exhausted) if b else fmt.NA,
        "nearing": fmt.count(b.nearing_limit) if b else fmt.NA,
        "nearing_pct": fmt.share(collector.NEARING_LIMIT_PCT),
        "top_spend": [
            {"name": s.name, "spent": fmt.inr(s.spent), "used": fmt.share(s.used_pct),
             "width": _width(s.used_pct),
             "css": "" if s.used_pct is None
                    else "red" if s.used_pct >= collector.EXHAUSTED_PCT
                    else "amber" if s.used_pct >= collector.NEARING_LIMIT_PCT else ""}
            for s in d.top_by_spend
        ],
        "top_spend_empty": _empty(ps is not None and "top_by_spend" not in d.failed, NO_SPEND),
    }


def report_context(data: ReportData) -> dict:
    """The template's data contract (see the template's header comment)."""
    return {
        "report_title": settings.get_usage_report_title(),
        "period_label": data.period.label,
        "frequency": data.period.title,
        "date_span": data.period.date_span,
        "generated_at": f"{data.generated_at.astimezone(IST):%d %b %Y %H:%M} IST",
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
