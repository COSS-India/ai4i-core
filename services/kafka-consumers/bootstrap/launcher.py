"""Argument parsing, name validation, logging, module loading, asyncio.run.

``main.py`` is the only entry point, in BOTH directions, so a single image runs
the service and verifies it:

    python main.py --consumer      payperuse_consumer   # run it, forever
    python main.py --test-consumer payperuse_consumer   # run the unit suite, exit with the verdict
    python main.py --list                               # print the names, exit 0

This module MUST NOT import any config — neither bootstrap.config nor a
consumer's.  Settings read the environment, so a launcher that imported shared
or foreign config would let consumer A's missing variable break consumer B's
process, which is precisely the coupling one-process-per-consumer removes
(§3.2).  Config is imported by the consumer module, after its name is known.
``pytest`` obeys the same rule for the same reason: it is imported lazily inside
the --test-consumer branch, so an image built without it still starts normally
instead of failing every production launch on a ModuleNotFoundError.

Exit codes:

    0  clean shutdown after SIGTERM/SIGINT, or every test passed
    1  a test failed, errored, was skipped in gate mode, or nothing was collected
    2  usage — unknown/malformed name, or a module with no callable run()
    3  this build cannot test: pytest or tests/unit is absent

    Any other non-zero code is a startup failure (database, Redis, broker),
    which the orchestrator restarts.
"""
from __future__ import annotations

import argparse
import asyncio
import importlib
import os
import re
import sys
from pathlib import Path

SERVICE_ROOT = Path(__file__).resolve().parent.parent
CONSUMERS_DIR = SERVICE_ROOT / "consumers"
_NAME_RE = re.compile(r"^[a-z][a-z0-9_]*$")

# The suite is tests/unit — the whole of the testing scope today.
SUITE_DIR = SERVICE_ROOT / "tests" / "unit"
PYTEST_INI = SERVICE_ROOT / "tests" / "pytest.ini"

# Exit codes, named so the translation table below reads as prose.
EXIT_OK = 0
EXIT_FAILED = 1
EXIT_USAGE = 2
EXIT_CANNOT_TEST = 3


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


def _validated(parser: argparse.ArgumentParser, name: str, names: list[str]) -> str:
    """Regex AND allow-list, before the value can reach importlib or pytest.

    Security control, not ergonomics: this value is fed to
    importlib.import_module() and to pytest's argument list.  An unvalidated
    value ("../../something", or any dotted path) is arbitrary module import
    inside the container.  Do not relax either check to accept dotted paths
    (§9), and do not give --test-consumer a second, weaker validator: it reaches
    exactly the same places.
    """
    if not _NAME_RE.match(name) or name not in names:
        parser.exit(
            EXIT_USAGE,
            f"unknown consumer {name!r}; available: {', '.join(names) or '(none)'}\n",
        )
    return name


def _run_test_suite(name: str) -> int:
    """Run the unit suite in-process and return the verdict as an exit code.

    The whole of ``tests/unit`` runs, not some subset selected by ``name``.  The
    name is still validated — identically to ``--consumer``, since it reaches the
    same places — and it labels the log stream, but the suite is shared: every
    consumer stands on ``bootstrap/``, so a consumer whose shared code is broken
    is not a consumer that passes.  When a consumer grows tests of its own they
    land under ``tests/unit/`` too and run here with everything else.

    Two rows are the ones that stop this from lying:

      * "no tests collected" is pytest's 5 — a bad path, a collection error, an
        empty suite.  Mapped to 0 it would report success on zero coverage.
      * a SKIP is a failure in gate mode.  ITEST_GATE=1 below is what
        tests/conftest.py reads to turn "did not run" into "failed".
    """
    # Checked before pytest is imported and before logging is configured, so a
    # build without the suite answers "cannot test" rather than dying on an
    # import.  The flag is accepted by every build on purpose: pointing it at an
    # image that cannot test must say so, not print "unrecognized arguments".
    if not SUITE_DIR.is_dir() or not PYTEST_INI.is_file():
        print(
            f"this build cannot test: {SUITE_DIR} or {PYTEST_INI} is missing",
            file=sys.stderr,
        )
        return EXIT_CANNOT_TEST
    try:
        import pytest
    except ImportError:
        # ImportError, not just ModuleNotFoundError: a pytest that is present but
        # unimportable (a broken plugin, a partial install) leaves this build
        # equally unable to test, and "cannot test" is the honest answer to both.
        print("this build cannot test: pytest is not installed", file=sys.stderr)
        return EXIT_CANNOT_TEST

    # Distinguishable from a consumer run in the same log stream.
    from ai4i_core.logging import configure_logging

    configure_logging(service_name=f"kafka-consumer-test-{name}")

    os.environ["ITEST_GATE"] = "1"
    code = pytest.main(
        [
            # tests/ is the rootdir and pytest only finds its config by walking up
            # from a path argument; passing -c is what guarantees THIS file is the
            # one in effect, wherever the container's cwd happens to be.
            "-c", str(PYTEST_INI),
            str(SUITE_DIR),
            # The image runs read-only as appuser.
            "-p", "no:cacheprovider",
            "-q",
        ]
    )
    # Every non-zero pytest code collapses to 1: the caller needs one bit, and
    # the reason belongs in the report, not in the exit status.  Collapsing also
    # keeps pytest's own 2/3/4/5 from colliding with this launcher's 2 and 3.
    return EXIT_OK if code == 0 else EXIT_FAILED


def _run_consumer(parser: argparse.ArgumentParser, name: str) -> None:
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
        parser.exit(EXIT_USAGE, f"consumers.{name}.main has no callable run()\n")

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


def main(argv: list[str] | None = None) -> None:
    parser = argparse.ArgumentParser(
        prog="kafka-consumers",
        description="Run one Kafka consumer, or one consumer's integration suite.",
    )
    # Mutually exclusive and required: there is NO environment fallback and NO
    # default for any of them.  A deployment that forgets the argument must fail
    # loudly rather than silently running the wrong consumer, and there must be
    # exactly one mechanism so there is never a question of precedence (§3.2).
    group = parser.add_mutually_exclusive_group(required=True)
    group.add_argument("--consumer", metavar="NAME", help="consumer package under consumers/")
    group.add_argument(
        "--test-consumer",
        metavar="NAME",
        dest="test_consumer",
        help="run the unit suite for NAME and exit with the verdict",
    )
    group.add_argument("--list", action="store_true", help="print the available consumers and exit")
    args = parser.parse_args(argv)

    names = available_consumers()

    if args.list:
        for name in names:
            print(name)
        return

    # `is not None`, NOT truthiness: `--test-consumer ""` is a supplied argument
    # that happens to be empty, and it must be rejected as a malformed name
    # rather than falling through to the --consumer branch, where the name is
    # None and validation dies on a TypeError instead of exiting 2.
    if args.test_consumer is not None:
        name = _validated(parser, args.test_consumer, names)
        raise SystemExit(_run_test_suite(name))

    _run_consumer(parser, _validated(parser, args.consumer, names))
