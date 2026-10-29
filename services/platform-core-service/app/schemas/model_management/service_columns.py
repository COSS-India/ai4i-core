"""Service List column catalogue — single source of truth for the column
picker (GET /services/columns), the list endpoint's sort/filter whitelist and
``columns`` projection (GET /services) and per-user column preference
validation.

Column ids are stable API identifiers; labels are display-only. List order
is the display order.
"""

from dataclasses import dataclass, field
from typing import FrozenSet, List, Optional, Tuple

FILTER_TEXT = "text"
FILTER_SINGLE_SELECT = "single_select"
FILTER_MULTI_SELECT = "multi_select"
FILTER_DATE_RANGE = "date_range"


@dataclass(frozen=True)
class ServiceListColumn:
    id: str
    label: str
    mandatory: bool = False
    default_visible: bool = False
    sortable: bool = True
    # None → not filterable. Otherwise one of the FILTER_* constants.
    filter_type: Optional[str] = None
    # Query params on GET /services that carry this column's filter value(s).
    filter_params: Tuple[str, ...] = field(default_factory=tuple)
    # Mirrors _NON_ADMIN_SERVICE_FIELDS in app/routes/service.py: a column
    # whose data non-admins never receive is hidden from them entirely.
    admin_only: bool = False
    # Response fields (ServiceListItem keys) this column renders from; GET
    # /services?columns=... returns only the fields of the selected columns.
    fields: Tuple[str, ...] = field(default_factory=tuple)

    @property
    def filterable(self) -> bool:
        return self.filter_type is not None


SERVICE_LIST_COLUMNS: List[ServiceListColumn] = [
    ServiceListColumn("name", "Name", mandatory=True, default_visible=True,
                      filter_type=FILTER_TEXT, filter_params=("name",), fields=("name",)),
    ServiceListColumn("actions", "Actions", mandatory=True, default_visible=True, sortable=False,
                      fields=("serviceId", "name", "isPublished", "versionStatus")),
    ServiceListColumn("task_type", "Model Task Type", default_visible=True,
                      filter_type=FILTER_MULTI_SELECT, filter_params=("task_types",),
                      fields=("taskType", "task")),
    ServiceListColumn("tier", "Tier", default_visible=True,
                      filter_type=FILTER_MULTI_SELECT, filter_params=("tier_ids",), admin_only=True,
                      fields=("tierNames",)),
    ServiceListColumn("status", "Status", default_visible=True,
                      filter_type=FILTER_SINGLE_SELECT, filter_params=("is_published",),
                      fields=("isPublished",)),
    ServiceListColumn("created_at", "Created At", default_visible=True,
                      filter_type=FILTER_DATE_RANGE, filter_params=("created_from", "created_to"),
                      admin_only=True, fields=("createdAt",)),
    ServiceListColumn("model_name", "Model Name",
                      filter_type=FILTER_TEXT, filter_params=("model_name",), fields=("modelName",)),
    ServiceListColumn("service_id", "Service ID",
                      filter_type=FILTER_TEXT, filter_params=("service_id",), fields=("serviceId",)),
    ServiceListColumn("input_price", "Input Price", admin_only=True, fields=("costPerUnit",)),
    ServiceListColumn("output_price", "Output Price", admin_only=True, fields=("outputCostPerUnit",)),
    ServiceListColumn("cached_input_price", "Cached Input Price", admin_only=True,
                      fields=("cachedInputCostPerUnit",)),
    ServiceListColumn("published_at", "Published On",
                      filter_type=FILTER_DATE_RANGE, filter_params=("published_from", "published_to"),
                      admin_only=True, fields=("publishedAt",)),
]

COLUMNS_BY_ID = {col.id: col for col in SERVICE_LIST_COLUMNS}
VALID_COLUMN_KEYS: FrozenSet[str] = frozenset(COLUMNS_BY_ID)
MANDATORY_KEYS: FrozenSet[str] = frozenset(c.id for c in SERVICE_LIST_COLUMNS if c.mandatory)
DEFAULT_VISIBLE_KEYS: FrozenSet[str] = frozenset(c.id for c in SERVICE_LIST_COLUMNS if c.default_visible)
SORTABLE_KEYS: FrozenSet[str] = frozenset(c.id for c in SERVICE_LIST_COLUMNS if c.sortable)
ADMIN_ONLY_KEYS: FrozenSet[str] = frozenset(c.id for c in SERVICE_LIST_COLUMNS if c.admin_only)
# Filters of admin-only columns that every caller may still use: tier_ids backs
# the Application fallback picker (an Institution Admin lists the services of
# their own Tier; routes/service.py returns published ones only to non-admins).
FILTER_PARAMS_OPEN_TO_ALL: FrozenSet[str] = frozenset({"tier_ids"})
ADMIN_ONLY_FILTER_PARAMS: FrozenSet[str] = frozenset(
    p for c in SERVICE_LIST_COLUMNS if c.admin_only for p in c.filter_params
) - FILTER_PARAMS_OPEN_TO_ALL

# Sent on every projected row whatever was selected: the row id, what the
# Actions column needs, and tierIds.
ALWAYS_FIELDS: Tuple[str, ...] = ("serviceId", "name", "isPublished", "versionStatus", "tierIds")
# Also sent on every projected row to admins/moderators; null when empty.
ADMIN_ALWAYS_FIELDS: Tuple[str, ...] = ("createdAt", "updatedAt", "publishedAt")


def response_fields_for(selected: FrozenSet[str], is_admin: bool) -> FrozenSet[str]:
    """Response fields to keep for the selected column ids."""
    fields = set(ALWAYS_FIELDS)
    if is_admin:
        fields.update(ADMIN_ALWAYS_FIELDS)
    for col_id in selected:
        fields.update(COLUMNS_BY_ID[col_id].fields)
    return frozenset(fields)


def columns_for_caller(is_admin: bool) -> List[ServiceListColumn]:
    """Columns the caller may see, in display order."""
    if is_admin:
        return list(SERVICE_LIST_COLUMNS)
    return [c for c in SERVICE_LIST_COLUMNS if not c.admin_only]
