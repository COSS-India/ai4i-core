"""Standalone entry point for the one-off Usage Dashboard backfill.

    cd services/pyjob
    PROMETHEUS_URL=... python -m backfill          # read Prometheus → daily_usage
    python -m backfill undo                        # remove the backfilled rows

Reuses pyjob's database bootstrap (bootstrap.database) but is not a scheduled
job: it is run by hand, once per environment. Exit codes mirror the launcher:
0 success, 1 failure, 2 usage error.
"""
from __future__ import annotations

import asyncio
import sys

from ai4i_core.logging import configure_logging, get_logger

from bootstrap.database import close_databases, init_databases

from backfill import engine, undo

logger = get_logger(__name__)

_COMMANDS = ("run", "undo")


async def _execute(command: str) -> None:
    init_databases()
    try:
        await (undo.run() if command == "undo" else engine.run())
    finally:
        await close_databases()


def main(argv: list[str] | None = None) -> int:
    argv = sys.argv[1:] if argv is None else argv
    command = argv[0] if argv else "run"
    if command not in _COMMANDS:
        print(f"usage: python -m backfill [{'|'.join(_COMMANDS)}]", file=sys.stderr)
        return 2

    # configure_logging() clears root handlers, so nothing may log before it.
    configure_logging(service_name=f"usage-backfill-{command}")
    logger.info("Starting | command=%s", command)
    try:
        asyncio.run(_execute(command))
    except Exception:
        logger.exception("Failed | command=%s", command)
        return 1
    logger.info("Finished | command=%s", command)
    return 0


if __name__ == "__main__":
    raise SystemExit(main())
