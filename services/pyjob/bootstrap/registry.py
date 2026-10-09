"""Job discovery.

A job is a module ``jobs/<name>.py`` that defines:

    async def run() -> None    # one run of the job

Schedules live in the k8s CronJob manifests, not here.

The module name is the job name. Discovery is a directory scan, so adding a
job is adding a file; nothing else is registered by hand.
"""
from __future__ import annotations

import importlib
import re
from dataclasses import dataclass
from pathlib import Path
from typing import Awaitable, Callable

SERVICE_ROOT = Path(__file__).resolve().parent.parent
JOBS_DIR = SERVICE_ROOT / "jobs"
_NAME_RE = re.compile(r"^[a-z][a-z0-9_]*$")


@dataclass(frozen=True)
class JobSpec:
    name: str
    run: Callable[[], Awaitable[None]]


class InvalidJobError(Exception):
    pass


def available_jobs() -> list[str]:
    """Modules under jobs/ with a legal name. Backs --list, the error message
    and the allow-list check on --job, so the three can't drift apart."""
    if not JOBS_DIR.is_dir():
        return []
    return sorted(
        path.stem
        for path in JOBS_DIR.glob("*.py")
        if path.stem != "__init__" and _NAME_RE.match(path.stem)
    )


def load_job(name: str) -> JobSpec:
    """Import ``jobs.<name>`` and check it defines run().

    ``name`` must already be validated against available_jobs(): it is fed to
    importlib.
    """
    module = importlib.import_module(f"jobs.{name}")
    run: Callable[[], Awaitable[None]] = getattr(module, "run", None)
    if not callable(run):
        raise InvalidJobError(f"jobs.{name} has no callable run()")
    return JobSpec(name=name, run=run)
