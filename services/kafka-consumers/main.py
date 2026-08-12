"""Entrypoint for every consumer in this service — one process per consumer.

The deployment picks which one with ``--consumer <name>``, so a single image
serves them all:

    python main.py --consumer payperuse_consumer
    python main.py --list

Responsibilities, in order: parse arguments, validate the name, configure
logging, import ``consumers.<name>.main`` and run its ``run()``.

This module MUST NOT import any config — neither the shared ``config.py`` nor a
consumer's. Pydantic settings read the environment as they are constructed, so a
launcher that imported one consumer's config would let that consumer's missing
environment variable break every other consumer's process — precisely the
coupling one-process-per-consumer removes. Config is imported by the consumer
module, after its name is known.

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

CONSUMERS_DIR = Path(__file__).resolve().parent / "consumers"
_NAME_RE = re.compile(r"^[a-z][a-z0-9_]*$")


def available_consumers() -> list[str]:
    """Directories under consumers/ that hold a main.py and have a legal name.

    This one enumeration backs --list, the error message AND the validation
    below — kept as a single function so the three cannot drift apart.
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
        description="Run one Kafka consumer. One process per consumer.",
    )
    # --consumer is required and has NO environment fallback and NO default: a
    # deployment that forgets it must fail loudly at startup rather than
    # silently running the wrong consumer, and having exactly one mechanism
    # means there is never a question of precedence.
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
    # importlib.import_module(). An unvalidated value ("../../something", or any
    # dotted path) is arbitrary module import inside the container. Regex AND
    # allow-list — do not relax either to accept dotted paths.
    if not _NAME_RE.match(name) or name not in names:
        parser.exit(2, f"unknown consumer {name!r}; available: {', '.join(names) or '(none)'}\n")

    # Before importing the consumer, so its import-time log records are
    # formatted; and per-consumer, so the processes are distinguishable in
    # OpenSearch. configure_logging() clears root handlers — nothing may
    # configure logging before this line.
    from ai4i_core.logging import configure_logging, get_logger

    configure_logging(service_name=f"kafka-consumer:{name}")
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
    logger.info("Consumer exited | name=%s", name)


if __name__ == "__main__":
    main()
