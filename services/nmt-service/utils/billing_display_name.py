"""Import-light helpers for billing / PPU display (used by smr_service without pulling pay-per-use client deps)."""

from __future__ import annotations

from typing import Any


def billing_display_name_from_service_info(service_info: Any) -> str:
    """Registry service display name: Model Management `services.name` only (e.g. indictrans-gpu-t4)."""
    if service_info is None:
        return ""
    v = getattr(service_info, "name", None)
    if v is not None:
        s = str(v).strip()
        if s:
            return s
    return ""
