"""Argument parsing, name validation, logging, module loading, asyncio.run.

The deployment picks which consumer runs with ``--consumer <name>``, so a single
image serves them all:

    python main.py --consumer payperuse_consumer
    python main.py --list

This module MUST NOT import any config — neither bootstrap.config nor a
consumer's.  Settings read the environment, so a launcher that imported shared
or foreign config would let consumer A's missing variable break consumer B's
process, which is precisely the coupling one-process-per-consumer removes
(§3.2).  Config is imported by the consumer module, after its name is known.

Exit codes: 0 on a clean shutdown after SIGTERM/SIGINT; 2 for an unknown or
malformed ``--consumer`` or a module with no callable ``run``; non-zero for a
startup failure (database, Redis, broker), which the orchestrator restarts.
"""
from __future__ import annotations

import argparse
import asyncio
import importlib
import re
from pathlib import Path

CONSUMERS_DIR = Path(__file__).resolve().parent.parent / "consumers"
_NAME_RE = re.compile(r"^[a-z][a-z0-9_]*$")


def available_consumers() -> list[str]:
    """Directories under consumers/ that hold a main.py and have a legal name.

    This enumeration backs --list, the error message, AND the security control
    in main() — keep them one function so the three cannot drift apart.
    """
    if not CONSUMERS_DIR.is_dir():
        return []
    return sorted(
        path.name
        for path in CONSUMERS_DIR.iterdir()
        if path.is_dir() and _NAME_RE.match(path.name) and (path / "main.py").is_file()
    )


def main(argv: list[str] | None = None) -> None:
    parser = argparse.ArgumentParser(
        prog="kafka-consumers",
        description="Run one Kafka consumer.  One process per consumer.",
    )
    # --consumer is required and has NO environment fallback and NO default: a
    # deployment that forgets it must fail loudly rather than silently running
    # the wrong consumer, and there must be exactly one mechanism so there is
    # never a question of precedence (§3.2).
    group = parser.add_mutually_exclusive_group(required=True)
    group.add_argument("--consumer", metavar="NAME", help="consumer package under consumers/")
    group.add_argument("--list", action="store_true", help="print the available consumers and exit")
    args = parser.parse_args(argv)

    names = available_consumers()

    if args.list:
        for name in names:
            print(name)
        return

    name = args.consumer
    # Security control, not ergonomics: this value is fed to
    # importlib.import_module().  An unvalidated value ("../../something", or
    # any dotted path) is arbitrary module import inside the container.
    # Regex AND allow-list — do not relax either to accept dotted paths (§9).
    if not _NAME_RE.match(name) or name not in names:
        parser.exit(2, f"unknown consumer {name!r}; available: {', '.join(names) or '(none)'}\n")

    # Before importing the consumer, so import-time records are formatted; and
    # per-consumer, so processes are distinguishable in OpenSearch.  Note
    # configure_logging() clears root handlers — nothing may configure logging
    # before this line.
    from ai4i_core.logging import configure_logging, get_logger

    configure_logging(service_name=f"kafka-consumer-{name}")
    logger = get_logger(__name__)

    module = importlib.import_module(f"consumers.{name}.main")
    run = getattr(module, "run", None)
    if not callable(run):
        parser.exit(2, f"consumers.{name}.main has no callable run()\n")

    logger.info(
        "Starting consumer | name=%s group_id=%s",
        name,
        getattr(module, "GROUP_ID", "<unset>"),
    )
    try:
        asyncio.run(run())
    except KeyboardInterrupt:  # SIGINT already set the consumer's shutdown event
        pass
    logger.info("Consumer exited cleanly | name=%s", name)
