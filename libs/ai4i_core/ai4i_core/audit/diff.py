"""Field-level difference between two audit snapshots."""

from typing import Any, Optional


def diff(prev: Optional[dict], new: Optional[dict]) -> list[dict[str, Any]]:
    """Fields whose value differs between ``prev`` and ``new``, sorted by name.

    Each item is ``{"field": name, "from": old, "to": new}``. A field missing
    on one side counts as ``None``, so for a CREATE (``prev`` is None) every
    populated field of ``new`` appears with ``"from": None``.
    """
    prev, new = prev or {}, new or {}
    return [
        {"field": key, "from": prev.get(key), "to": new.get(key)}
        for key in sorted(prev.keys() | new.keys())
        if prev.get(key) != new.get(key)
    ]
