"""Email the monthly programme report to every Usage Viewer (AI4IDS-3278).

Run manually inside the platform-core container (it reuses the service's
.env: databases, PROMETHEUS_URL, SMTP, PII_ENCRYPTION_KEY, PORTAL_URL):

    python -m app.scripts.send_usage_report                      # last complete month
    python -m app.scripts.send_usage_report --period 2026-09
    python -m app.scripts.send_usage_report --to me@example.com  # test: only these address(es)
    python -m app.scripts.send_usage_report --dry-run --out-dir /tmp/report

--dry-run sends nothing: it writes the PDF and the email (HTML + text) to
--out-dir so they can be checked first.

There is no scheduler and no duplicate check (agreed for this release):
every run sends the report again to every recipient.

If any figure fails to load (e.g. Prometheus unreachable mid-run), nothing
is sent unless --allow-partial is given, so officials never get a report
with silently missing numbers.

Exit codes: 0 sent to everyone (or dry run written), 1 nothing or not
everything sent, 2 bad arguments.
"""
from __future__ import annotations

import argparse
import asyncio
import logging
import sys
from pathlib import Path
from typing import Optional

import httpx

logger = logging.getLogger("usage_report")

EXIT_OK, EXIT_FAILED, EXIT_USAGE = 0, 1, 2


def _parse_args(argv: Optional[list[str]]) -> argparse.Namespace:
    p = argparse.ArgumentParser(
        prog="python -m app.scripts.send_usage_report",
        description="Email the monthly programme report to every Usage Viewer.",
    )
    p.add_argument("--period", metavar="YYYY-MM",
                   help="month to report on (default: the last complete month, IST)")
    p.add_argument("--to", metavar="EMAIL", action="append",
                   help="send only to this address instead of the Usage Viewers (repeatable)")
    p.add_argument("--dry-run", action="store_true",
                   help="send nothing; write the PDF and email to --out-dir")
    p.add_argument("--out-dir", default=".", help="where --dry-run writes its files (default: .)")
    p.add_argument("--allow-partial", action="store_true",
                   help="send even if some figures failed to load (they show as N/A)")
    return p.parse_args(argv)


def _write_dry_run(out_dir: Path, data, pdf: bytes, recipients: list[str]) -> None:
    from app.services.usage_report.mailer import attachment_name, render_email

    out_dir.mkdir(parents=True, exist_ok=True)
    message = render_email(data, recipients[0] if recipients else "usage-viewer@example.com")
    (out_dir / attachment_name(data)).write_bytes(pdf)
    (out_dir / f"usage-report-{data.period.key}.html").write_text(message.html_body, encoding="utf-8")
    (out_dir / f"usage-report-{data.period.key}.txt").write_text(
        f"Subject: {message.subject}\nTo: {', '.join(recipients) or '(no Usage Viewers found)'}\n\n"
        f"{message.text_body}",
        encoding="utf-8",
    )
    logger.info("Dry run: wrote %s and the email to %s", attachment_name(data), out_dir.resolve())


async def run(args: argparse.Namespace) -> int:
    from ai4i_core import pii_crypto
    from sqlalchemy import text

    from app.core.config import settings
    from app.core.database import (
        close_auth_database,
        close_database,
        get_auth_session_factory,
        get_primary_session_factory,
        init_auth_database,
        init_database,
    )
    from app.repositories.model_management.model_repository import ModelRepository
    from app.repositories.model_management.service_repository import ServiceRepository
    from app.services.metering_service import MeteringService
    from app.services.usage_report.collector import UsageReportCollector
    from app.services.usage_report.mailer import deliver, email_settings
    from app.services.usage_report.pdf import render_report_pdf
    from app.services.usage_report.period import ReportMonth
    from app.services.usage_report.recipients import usage_viewer_emails
    from app.utils.prometheus_client import PrometheusClient

    try:
        month = ReportMonth.parse(args.period) if args.period else ReportMonth.last_complete()
    except ValueError as exc:
        logger.error("%s", exc)
        return EXIT_USAGE
    if not settings.prometheus_url:
        logger.error("PROMETHEUS_URL is not set; request figures cannot be collected")
        return EXIT_FAILED

    pii_crypto.configure_key(settings.pii_encryption_key)
    pii_crypto.validate_key()
    await init_database(db_url=settings.get_database_url(), pool_size=2, max_overflow=0)
    init_auth_database()
    http = httpx.AsyncClient()
    try:
        auth_factory = get_auth_session_factory()
        if auth_factory is None:
            logger.error("AUTH_DB_NAME is not set; institutions, budgets and recipients live in the auth DB")
            return EXIT_FAILED
        prometheus = PrometheusClient(settings.prometheus_url, http, timeout=settings.prometheus_timeout)
        async with get_primary_session_factory()() as core_db, auth_factory() as auth_db:
            # Fail once, clearly, rather than once per figure.
            for name, check in (
                ("core database", lambda: core_db.execute(text("SELECT 1"))),
                ("auth database", lambda: auth_db.execute(text("SELECT 1"))),
                ("Prometheus", lambda: prometheus.query("vector(1)")),
            ):
                try:
                    await check()
                except Exception as exc:
                    logger.error("Cannot reach the %s: %s", name, exc)
                    return EXIT_FAILED
            metering = MeteringService(prometheus, auth_db, ServiceRepository(core_db), ModelRepository(core_db))
            try:
                data = await UsageReportCollector(metering, auth_db, core_db).collect(month)
            except ValueError as exc:
                logger.error("%s", exc)
                return EXIT_USAGE
            try:
                recipients = args.to or await usage_viewer_emails(auth_db, pii_crypto.decrypt_email)
            except Exception:
                logger.exception("Could not look up the Usage Viewers")
                return EXIT_FAILED
    finally:
        await http.aclose()
        await close_auth_database()
        await close_database()

    if data.failed:
        logger.warning("Figures that failed to load (shown as N/A): %s", ", ".join(data.failed))
    pdf = render_report_pdf(data)

    if args.dry_run:
        _write_dry_run(Path(args.out_dir), data, pdf, recipients)
        return EXIT_OK
    if data.failed and not args.allow_partial:
        logger.error("Not sending: some figures failed to load. Fix the cause and re-run, "
                     "or pass --allow-partial to send with them as N/A.")
        return EXIT_FAILED
    if not recipients:
        logger.error("No active Usage Viewer has an email address; nothing sent")
        return EXIT_FAILED

    sent, failed = await deliver(data, pdf, recipients, email_settings())
    logger.info("Usage report %s: sent %d of %d (failed: %s)",
                month.key, len(sent), len(recipients), ", ".join(failed) or "none")
    return EXIT_OK if not failed else EXIT_FAILED


def main(argv: Optional[list[str]] = None) -> int:
    from ai4i_core.logging import configure_logging

    args = _parse_args(argv)
    # Passing third_party_log_levels replaces ai4i_core's defaults, so they're
    # repeated here; WeasyPrint and fontTools log every PDF layout step at INFO.
    configure_logging(
        service_name="usage-report",
        third_party_log_levels={
            "httpx": "WARNING",
            "httpcore": "WARNING",
            "urllib3": "WARNING",
            "sqlalchemy.engine": "WARNING",
            "weasyprint": "WARNING",
            "fontTools": "WARNING",
        },
    )
    return asyncio.run(run(args))


if __name__ == "__main__":
    sys.exit(main())
