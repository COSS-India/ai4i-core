"""Email the programme report to every Usage Viewer (AI4IDS-3278).

Run manually inside the platform-core container (it reuses the service's
.env: databases, PROMETHEUS_URL, SMTP, PII_ENCRYPTION_KEY, PORTAL_URL):

    python -m app.scripts.send_usage_report                      # last complete month
    python -m app.scripts.send_usage_report --period 2026-09
    python -m app.scripts.send_usage_report --to me@example.com  # test: only these address(es)
    python -m app.scripts.send_usage_report --dry-run --out-dir /tmp/report
    python -m app.scripts.send_usage_report --scheduled [--frequency weekly]

--dry-run sends nothing: it writes the PDF and the email (HTML + text) to
--out-dir so they can be checked first.

A manual run (--period / default) has no duplicate check and isn't logged:
every run sends the report again to every recipient.

--scheduled runs what the pyjob `usage_report` CronJob triggers
(POST /internal/usage-report/run): the latest complete period of the
frequency, to every Usage Viewer. No send log or retry in this release, so it
too sends again on every run.

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
        description="Email the programme report to every Usage Viewer.",
    )
    p.add_argument("--period", metavar="YYYY-MM",
                   help="month to report on (default: the last complete month, IST)")
    p.add_argument("--to", metavar="EMAIL", action="append",
                   help="send only to this address instead of the Usage Viewers (repeatable)")
    p.add_argument("--dry-run", action="store_true",
                   help="send nothing; write the PDF and email to --out-dir")
    p.add_argument("--out-dir", default=".", help="where --dry-run writes its files (default: .)")
    p.add_argument("--allow-partial", action="store_true",
                   help="send even if some figures failed to load (they show as 'Not available')")
    p.add_argument("--scheduled", action="store_true",
                   help="run the scheduled send (latest complete period, to every Usage Viewer)")
    p.add_argument("--frequency", metavar="FREQ",
                   help="with --scheduled: monthly (default), or a duration: 1d, 7d, 2h …")
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
    from app.core.database import close_auth_database, close_database, init_auth_database, init_database
    from app.services.usage_report.mailer import deliver, email_settings
    from app.services.usage_report.pdf import render_report_pdf
    from app.services.usage_report.period import MONTHLY, ReportPeriod
    from app.services.usage_report.recipients import usage_viewer_emails
    from app.services.usage_report.scheduler import BUSY, DONE, NOTHING_DUE, run_scheduled_report
    from app.services.usage_report.sources import report_sources

    if args.scheduled and (args.period or args.to or args.dry_run or args.allow_partial):
        logger.error("--scheduled takes only --frequency; it always sends the latest period to the Usage Viewers")
        return EXIT_USAGE
    month = None
    if not args.scheduled:  # the scheduled run picks its own period
        try:
            month = ReportPeriod.parse_month(args.period) if args.period else ReportPeriod.latest_complete(MONTHLY)
        except ValueError as exc:
            logger.error("%s", exc)
            return EXIT_USAGE

    pii_crypto.configure_key(settings.pii_encryption_key)
    pii_crypto.validate_key()
    await init_database(db_url=settings.get_database_url(), pool_size=2, max_overflow=0)
    init_auth_database()
    http = httpx.AsyncClient()
    try:
        if args.scheduled:
            try:
                result = await run_scheduled_report(args.frequency, http)
            except (ValueError, RuntimeError) as exc:
                logger.error("%s", exc)
                return EXIT_FAILED
            logger.info("Scheduled usage report: %s", result.as_dict())
            ok = result.status in (NOTHING_DUE, BUSY) or (result.status == DONE and not result.failed)
            return EXIT_OK if ok else EXIT_FAILED
        try:
            async with report_sources(http) as src:
                # Fail once, clearly, rather than once per figure.
                for name, check in (
                    ("core database", lambda: src.core_db.execute(text("SELECT 1"))),
                    ("auth database", lambda: src.auth_db.execute(text("SELECT 1"))),
                    ("Prometheus", lambda: src.prometheus.query("vector(1)")),
                ):
                    try:
                        await check()
                    except Exception as exc:
                        logger.error("Cannot reach the %s: %s", name, exc)
                        return EXIT_FAILED
                try:
                    data = await src.collector.collect(month)
                except ValueError as exc:
                    logger.error("%s", exc)
                    return EXIT_USAGE
                try:
                    recipients = args.to or await usage_viewer_emails(src.auth_db, pii_crypto.decrypt_email)
                except Exception:
                    logger.exception("Could not look up the Usage Viewers")
                    return EXIT_FAILED
        except RuntimeError as exc:  # Prometheus or the auth DB not configured (report_sources)
            logger.error("%s", exc)
            return EXIT_FAILED
    finally:
        await http.aclose()
        await close_auth_database()
        await close_database()

    if data.failed:
        logger.warning("Figures that failed to load (shown as 'Not available'): %s", ", ".join(data.failed))
    pdf = render_report_pdf(data)

    if args.dry_run:
        _write_dry_run(Path(args.out_dir), data, pdf, recipients)
        return EXIT_OK
    if data.failed and not args.allow_partial:
        logger.error("Not sending: some figures failed to load. Fix the cause and re-run, "
                     "or pass --allow-partial to send with them as 'Not available'.")
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
