"""
Per-block phase timing for the inference pipeline.

A lightweight companion to the OTel spans in request_span.py. Where traced_span
gives the coarse request / model / ai-inference timings, this module records the
fine-grained per-stage costs (resolve, validate, preprocess, build_payload,
triton, output_convert, ...) and merges them onto the existing root request span
as `<stage>_ms` attributes. The root span finalize also emits a single
human-readable "TIMING ..." line built from these values (see request_span.py).

Mechanism:
  - timed_phase("build_payload_ms") accumulates a perf_counter delta into a
    per-request contextvar dict. Accumulates (+=) so per-item loops (audio/TTS)
    sum across iterations under one key.
  - The root traced_span resets the dict on entry and merges it on finalize.

Everything is gated by settings.PHASE_TIMING_ENABLED. When off, timed_phase is a
no-op and nothing touches the contextvar, so the overhead is zero. The dict is
per-request (contextvar), so concurrent requests never share an accumulator.
"""

import time
from contextvars import ContextVar
from typing import Any, Dict, Optional

from config import settings

# Per-request accumulator: {"build_payload_ms": 1.2, "cache_hit": True, ...}.
# Default None so a missing reset (e.g. a direct unit call) is detectable.
_phases: ContextVar[Optional[Dict[str, Any]]] = ContextVar(
    "inference_phases", default=None
)


def _enabled() -> bool:
    return settings.PHASE_TIMING_ENABLED


def _round_ms(seconds: float) -> float:
    return round(seconds * 1000, 3)


def _phase_dict() -> Optional[Dict[str, Any]]:
    """The current request's accumulator, lazily created when enabled.

    Lazy creation covers direct calls that skip the root span (unit tests);
    real requests always get a fresh dict from start_root_phases() first.
    """
    if not _enabled():
        return None
    d = _phases.get()
    if d is None:
        d = {}
        _phases.set(d)
    return d


def add_ms(name: str, milliseconds: float) -> None:
    """Accumulate a duration (ms) under `name` for the current request."""
    d = _phase_dict()
    if d is not None:
        d[name] = round(d.get(name, 0.0) + milliseconds, 3)


def record_attr(name: str, value: Any) -> None:
    """Record a non-timing attribute (e.g. cache_hit) on the current request."""
    d = _phase_dict()
    if d is not None:
        d[name] = value


class _PhaseTimer:
    """Context manager (sync or async) that times its block into `name`."""

    __slots__ = ("_name", "_start")

    def __init__(self, name: str) -> None:
        self._name = name
        self._start: Optional[float] = None

    def __enter__(self) -> "_PhaseTimer":
        if _enabled():
            self._start = time.perf_counter()
        return self

    def __exit__(self, *exc: Any) -> bool:
        self._stop()
        return False

    async def __aenter__(self) -> "_PhaseTimer":
        return self.__enter__()

    async def __aexit__(self, *exc: Any) -> bool:
        return self.__exit__(*exc)

    def _stop(self) -> None:
        if self._start is not None:
            add_ms(self._name, _round_ms(time.perf_counter() - self._start))


def timed_phase(name: str) -> _PhaseTimer:
    """Time a block under `name`. Usable as `with` or `async with`.

    Accumulates across repeated entries within one request, so the same name
    used inside a per-item loop sums to the total for that stage.
    """
    return _PhaseTimer(name)


def start_root_phases() -> None:
    """Begin a fresh per-request accumulator (called on root span entry).

    Sets a new dict in this request's context, isolating concurrent requests.
    """
    if not _enabled():
        return
    _phases.set({})


def collect_phases() -> Dict[str, Any]:
    """Return a copy of the current request's accumulated phases (merged onto
    the root span on finalize). Empty when disabled or unstarted."""
    if not _enabled():
        return {}
    return dict(_phases.get() or {})
