"""Argument parsing, logging, database / Redis lifecycle and asyncio.run.

    python main.py --job NAME      # run one job once, now, and exit
    python main.py --list          # print the job names, exit 0

Scheduling is done by the k8s CronJob, which runs ``--job NAME``.

Exit codes:

    0  the job succeeded
    1  the job failed
    2  usage: unknown or malformed job name, or a job module missing run()
"""
from __future__ import annotations

import argparse
import asyncio

from ai4i_core.logging import configure_logging, get_logger

from bootstrap.registry import InvalidJobError, JobSpec, available_jobs, load_job

logger = get_logger(__name__)

EXIT_OK = 0
EXIT_FAILED = 1
EXIT_USAGE = 2


def _validated(parser: argparse.ArgumentParser, name: str, names: list[str]) -> str:
    # The name reaches importlib, so it must be on the allow-list, not just well formed.
    if name not in names:
        parser.exit(EXIT_USAGE, f"unknown job {name!r}; available: {', '.join(names) or '(none)'}\n")
    return name


async def _execute(job: JobSpec) -> None:
    # Imported here so --list works without sqlalchemy settings in the environment.
    from bootstrap.database import close_databases, init_databases
    from bootstrap.redis_client import close_redis

    init_databases()
    try:
        await job.run()
    finally:
        await close_databases()
        await close_redis()


def _run_once(parser: argparse.ArgumentParser, name: str) -> int:
    # configure_logging() clears root handlers, so nothing may log before it.
    configure_logging(service_name=f"pyjob-{name}")
    try:
        job = load_job(name)
    except InvalidJobError as exc:
        parser.exit(EXIT_USAGE, f"{exc}\n")

    logger.info("Starting job | name=%s", name)
    try:
        asyncio.run(_execute(job))
    except Exception:
        logger.exception("Job failed | name=%s", name)
        return EXIT_FAILED
    logger.info("Job finished | name=%s", name)
    return EXIT_OK


def main(argv: list[str] | None = None) -> None:
    parser = argparse.ArgumentParser(prog="pyjob", description="Run one of the platform's scheduled jobs.")
    group = parser.add_mutually_exclusive_group(required=True)
    group.add_argument("--job", metavar="NAME", help="run one job once and exit")
    group.add_argument("--list", action="store_true", help="print the available jobs and exit")
    args = parser.parse_args(argv)

    names = available_jobs()

    if args.list:
        for name in names:
            print(name)
        return

    raise SystemExit(_run_once(parser, _validated(parser, args.job, names)))
