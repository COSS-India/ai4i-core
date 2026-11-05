"""Model List column helpers — backend-only mappings for sort validation and
response field projection. Column definitions (labels, required, display order)
live in the config table (type ``model-column``) and are served to the frontend
from there; this file holds only what the GET /models/list endpoint needs.
"""

from typing import Dict, FrozenSet, Tuple

# Maps each column key (as stored in the config table) to the response fields
# that column renders from. Used to project the response when ?columns= is set.
COLUMN_FIELDS_MAP: Dict[str, Tuple[str, ...]] = {
    "name":          ("name",),
    "version":       ("version",),
    "taskType":      ("task",),
    "providerName":  ("providerName",),
    "status":        ("versionStatus",),
    "createdAt":     ("createdAt",),
    "noOfServices":  ("noOfServices",),
    "actions":       ("modelId", "name", "versionStatus"),
}

# Column keys that have a backend sort expression in _sort_model_expressions().
SORTABLE_KEYS: FrozenSet[str] = frozenset({
    "name", "version", "taskType", "providerName", "status", "createdAt", "noOfServices"
})


def response_fields_for(selected: FrozenSet[str]) -> FrozenSet[str]:
    """Response fields to keep for the selected column ids."""
    fields: set = set()
    for col_id in selected:
        fields.update(COLUMN_FIELDS_MAP.get(col_id, ()))
    return frozenset(fields)
