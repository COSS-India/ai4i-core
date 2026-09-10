"""Pure decision logic for status.value — design doc §6, "three patterns".

No I/O here on purpose: given the row's current status and the incoming
message, decide (a) what the new status should be, if anything, and (b)
whether that change means an email should go out. ledger.py is what
actually tries to persist the decision, atomically, against a possibly-
stale read — see its module docstring for why `guard` matters.
"""
from __future__ import annotations

from dataclasses import dataclass
from typing import Any, Dict, Optional

from ai4i_core.logging import get_logger

logger = get_logger(__name__)

# design doc §6, Pattern 1 — a percentage that only moves up, or resets.
PERCENTAGE_EVENTS = {"QUOTA_THRESHOLD", "BUDGET_THRESHOLD"}
# design doc §6, Pattern 2 — an on/off flag.
FLAG_EVENTS = {"QUOTA_EXHAUSTED", "BUDGET_EXHAUSTED"}
# design doc §6, Pattern 3 — this exact admin action, right now.
ONE_SHOT_EVENTS = {
    "TIER_ASSIGNED",
    "TIER_CHANGED",
    "BUDGET_ASSIGNED",
    "BUDGET_UPDATED",
    "QUOTA_LIMIT_UPDATED",
}


@dataclass(frozen=True)
class StatusDecision:
    """What patterns.decide() worked out.

    new_status is None when nothing should change at all (no DB write is
    even attempted). When it's not None, `guard` tells ledger.py which
    atomic condition makes the write safe against a concurrent, possibly
    stale, writer computing a different candidate from the same read:

      - "monotonic": only replace the existing value if it's genuinely
        empty or numerically lower than the new one. Required for anything
        that must never let a late/stale write drag a HIGHER already-
        recorded value back down (a value in the doc's generic "just
        IS DISTINCT FROM" example doesn't protect against this — a delayed
        message computing a lower band could otherwise silently undo a
        newer, higher one that already sent).
      - "reset": only clear back to {} if it isn't already {} — a plain
        distinctness check is fine here, there's no "which one is newer"
        ambiguity for a reset.
      - "marker": only replace if the stored marker (occurred_at) differs
        from the incoming one — exactly the doc's "is this the same message
        redelivered" check for the 5 one-shot admin events.
    """

    new_status: Optional[Dict[str, Any]]
    should_send: bool
    guard: str = "monotonic"  # "monotonic" | "reset" | "marker"


def decide(
    *,
    event_name: str,
    current_status: Optional[Dict[str, Any]],
    occurred_at: str,
    details: Dict[str, Any],
    thresholds: Dict[str, bool],
) -> StatusDecision:
    current_status = current_status or {}
    if event_name in PERCENTAGE_EVENTS:
        return _decide_percentage(current_status, details, thresholds)
    if event_name in FLAG_EVENTS:
        return _decide_flag(current_status, details)
    if event_name in ONE_SHOT_EVENTS:
        return _decide_one_shot(current_status, occurred_at)
    raise ValueError(f"No status pattern known for event_name={event_name!r}")


def _decide_percentage(
    current_status: Dict[str, Any], details: Dict[str, Any], thresholds: Dict[str, bool]
) -> StatusDecision:
    percent = details.get("percent")
    if percent is None:
        logger.error("Percentage event missing details.percent — nothing to compare against")
        return StatusDecision(new_status=None, should_send=False)

    configured_bands = sorted(int(key) for key, enabled in thresholds.items() if enabled)
    eligible = [band for band in configured_bands if band <= percent]
    highest_eligible = max(eligible) if eligible else None
    current_value = current_status.get("value")

    if highest_eligible is None:
        # Below every configured band — a reset, if there was something to reset.
        if current_value is not None:
            return StatusDecision(new_status={}, should_send=False, guard="reset")
        return StatusDecision(new_status=None, should_send=False)

    if current_value is None or highest_eligible > current_value:
        return StatusDecision(
            new_status={"value": highest_eligible, "delivery": "in_progress"},
            should_send=True,
            guard="monotonic",
        )
    return StatusDecision(new_status=None, should_send=False)


def _decide_flag(current_status: Dict[str, Any], details: Dict[str, Any]) -> StatusDecision:
    current_value = current_status.get("value")
    # The producer contract for these two isn't finalised yet (see the
    # design doc's open questions) — this assumes an optional details.percent
    # is how a fall-back-under-100% reset would be signalled, since the event
    # itself only fires forward today. Confirm with whoever builds the
    # producer side before relying on the reset path in production.
    percent = details.get("percent")
    if percent is not None and percent < 100:
        if current_value:
            return StatusDecision(new_status={}, should_send=False, guard="reset")
        return StatusDecision(new_status=None, should_send=False)

    if current_value == 1:
        return StatusDecision(new_status=None, should_send=False)
    return StatusDecision(
        new_status={"value": 1, "delivery": "in_progress"}, should_send=True, guard="monotonic"
    )


def _decide_one_shot(current_status: Dict[str, Any], occurred_at: str) -> StatusDecision:
    current_value = current_status.get("value")
    if current_value == occurred_at:
        return StatusDecision(new_status=None, should_send=False)
    return StatusDecision(
        new_status={"value": occurred_at, "delivery": "in_progress"},
        should_send=True,
        guard="marker",
    )
