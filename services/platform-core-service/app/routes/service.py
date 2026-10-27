"""
Service management API endpoints.
"""

import logging
from datetime import date, datetime
from typing import Annotated, Any, Dict, List, Optional, Union

from fastapi import APIRouter, Depends, Query, Request, Response
from pydantic import BeforeValidator
from sqlalchemy.ext.asyncio import AsyncSession

import importlib as _importlib

from app.core.database import get_db
from app.core.exceptions import AppError, ValidationError
from app.core.permissions import is_platform_admin
from app.dependencies.services import ServiceService, get_service_service
from app.repositories.model_management.service_repository import (
    ServiceListFilters,
    range_end_exclusive,
    range_start,
)
from app.schemas.model_management.service_columns import (
    ADMIN_ONLY_FILTER_PARAMS,
    ADMIN_ONLY_KEYS,
    SORTABLE_KEYS,
)
from app.schemas.common import MessageMeta, TotalMeta, error_responses
from app.schemas.enums.model_management import TaskTypeEnum
from app.services.pay_per_use import inference_type_cache
from app.schemas.model_management.service import (
    CreateServiceData,
    CreateServiceResponse,
    DeleteServiceData,
    DeleteServiceResponse,
    GetServiceResponse,
    ListServicesResponse,
    ListTryItServicesResponse,
    ServiceBulkEndpointUpdateRequest,
    ServiceCreateRequest,
    ServiceListMeta,
    ServicesData,
    ServiceUpdateRequest,
    UpdateServiceData,
    UpdateServiceEndpointsData,
    UpdateServiceEndpointsResponse,
    UpdateServiceResponse,
    validate_service_id,
)

# services/model-management/ is hyphenated; importlib is the only way to pull
# symbols out (mirrors app/main.py and app/dependencies/services.py).
mask_service_secrets = _importlib.import_module(
    "app.services.model-management.serializers"
).mask_service_secrets

logger = logging.getLogger(__name__)

router = APIRouter(
    prefix="/services",
    tags=["Service Management"],
)


# ── RBAC-aware response filtering (AI4IDS-1816) ──────────────────────────────
#
# service.read (permission id 51) is deliberately granted to every role,
# including Tenant Admin/User/Guest — every inference-submission flow in the
# frontend depends on GET /services to resolve a serviceId before calling
# NMT/ASR/TTS/etc, so this endpoint can't be locked down to Admin/Moderator
# without breaking inference for all non-admin users. What can and should be
# fixed: service_to_dict() returns internal fields (api_key, cost/
# billing, health, hardware, tier assignments) that no non-admin caller needs
# or should see. Non-admin callers (and the fully public try-it endpoint) get
# an allow-listed subset instead; Admin/Moderator keep the full response.

# Only fields actually consumed by the inference-submission flow and the
# public try-it picker (confirmed against every *Service.ts call site and
# shared picker component in frontend/simple-ui/src), plus "model" — required
# by inference-service's own internal GET /services/{id} call (no identity
# headers, so it always hits this filtered path), which reads
# model.adapterConfig and model.schema to build the actual Triton request.
# Dropping "model" here breaks inference for every service (AI4IDS-2562
# investigation) — the model card is Triton tensor-mapping/schema config, not
# a secret (no api_key/billing inside it), so it's safe to allow.
_NON_ADMIN_SERVICE_FIELDS = {
    "serviceId",
    "name",
    "modelId",
    "modelName",
    "modelVersion",
    "description",  # ULCA name for serviceDescription
    "serviceDescription",
    "endpoint",
    "taskType",
    "isPublished",
    "isTryItDefault",
    "task",
    "languages",
    "versionStatus",
    "model",
    "tierIds",  # required by inference-service tier enforcement
    # NOTE: the new nested `inferenceEndPoint` object is deliberately NOT
    # in this allow-list. It bundles `infraDescription`
    # (== the existing `hardwareDescription`, already admin-only) together
    # with the public-safe bits (callbackUrl, supported*Formats, ...) in one
    # object, and _filter_service_fields below only does a shallow top-level
    # filter — allow-listing the whole object would leak infraDescription to
    # non-admins. Exposing a redacted version of it is a separate follow-up
    # if a non-admin caller ever needs these fields.
}


def _filter_service_fields(item: Dict[str, Any]) -> Dict[str, Any]:
    """Strip internal/sensitive fields (api_key, billing, health,
    hardware, tiers, audit) down to what non-admin/public callers need."""
    return {k: v for k, v in item.items() if k in _NON_ADMIN_SERVICE_FIELDS}


_TRY_IT_SUPPORTED_TASK_TYPES = {TaskTypeEnum.nmt.value, TaskTypeEnum.llm.value}


@router.get(
    "/try-it-service-list",
    summary="List Try-It Services",
    # _filter_service_fields strips sensitive keys (api_key, billing, health,
    # ...) from the dict entirely for non-admin/public callers — they must
    # stay absent from the JSON, not reappear as an explicit `null` just
    # because ServiceListItem declares them. exclude_unset achieves that: it
    # drops only fields that were never in the source dict, while a field
    # that legitimately IS None in the data (e.g. licenseUrl for an admin)
    # still comes through as explicit null, unchanged.
    response_model_exclude_unset=True,
)
async def list_try_it_services(
    task_types: str = Query(
        ...,
        description="Comma-separated task types",
    ),
    svc: ServiceService = Depends(get_service_service),
) -> ListTryItServicesResponse:
    """List published services available for public trial."""
    _task_types = [t.strip().lower() for t in task_types.split(",") if t.strip().lower() in _TRY_IT_SUPPORTED_TASK_TYPES]
    if not _task_types:
        raise ValidationError(
            message="Try-it is not available for this task type.",
            code="TRY_IT_UNSUPPORTED",
        )
    items, total = await svc.list_services(
        task_types=_task_types, is_published=True
    )
    # This endpoint has no auth at all (see api_permissions.json: try-it is
    # public) — always filtered, never the admin/full view.
    items = [_filter_service_fields(i) for i in items]
    return ListTryItServicesResponse(
        success=True, data=ServicesData(services=items), meta=TotalMeta(total=total)
    )


def _parse_date_or_datetime(value: Any) -> Any:
    """A bare YYYY-MM-DD stays a calendar date (a whole UTC day); anything with
    a time is a datetime that keeps its UTC offset. Pydantic's own union would
    read 2026-01-05T00:00:00+05:30 as the date 2026-01-05 and drop the offset."""
    if not isinstance(value, str):
        return value
    value = value.strip()
    if len(value) == 10:
        return date.fromisoformat(value)
    return datetime.fromisoformat(value)


DateOrDatetime = Annotated[date | datetime, BeforeValidator(_parse_date_or_datetime)]

_DATE_PARAM_HELP = (
    "Either an ISO date (YYYY-MM-DD, a whole UTC day) or an ISO datetime with offset "
    "(e.g. 2026-01-05T00:00:00+05:30, an exact instant; no offset means UTC). "
    "URL-encode '+' as %2B."
)


class ServiceListFilterParams:
    """Query-param dependency: the filter half of GET /services."""

    def __init__(
        self,
        task_types: Annotated[
            Optional[str],
            Query(
                description="Comma-separated task types to include. A single value is a one-element list.",
            ),
        ] = None,
        is_published: Annotated[
            Optional[bool],
            Query(
                description="Filter by publication status: true for published only, false for unpublished only.",
            ),
        ] = None,
        created_by: Annotated[
            Optional[str], Query(description="Filter by user ID who created the service.")
        ] = None,
        name: Annotated[
            Optional[str],
            Query(
                description="Case-insensitive 'contains' match on the service name.",
            ),
        ] = None,
        service_id: Annotated[
            Optional[str],
            Query(
                description="Case-insensitive 'contains' match on the service ID.",
            ),
        ] = None,
        model_name: Annotated[
            Optional[str],
            Query(
                description="Case-insensitive 'contains' match on the name of the model the service runs.",
            ),
        ] = None,
        tier_ids: Annotated[
            Optional[str],
            Query(
                description=(
                    "Comma-separated tier IDs (UUIDs). Returns services assigned to ANY of them. "
                    "Open to every caller: the Application fallback picker lists the services "
                    "mapped to the Institution's Tier with it; non-admins get published services only."
                ),
            ),
        ] = None,
        created_from: Annotated[
            Optional[DateOrDatetime],
            Query(
                description=(
                    "Services created at or after this point: the start of the day for a date, "
                    "the instant itself for a datetime. " + _DATE_PARAM_HELP + " Admin/moderator only."
                ),
            ),
        ] = None,
        created_to: Annotated[
            Optional[DateOrDatetime],
            Query(
                description=(
                    "Services created before this point: up to and including the day for a date, "
                    "strictly before the instant for a datetime (send the next day's local midnight). "
                    + _DATE_PARAM_HELP + " Must not be before created_from. Admin/moderator only."
                ),
            ),
        ] = None,
        published_from: Annotated[
            Optional[DateOrDatetime],
            Query(
                description=(
                    "Services published at or after this point: the start of the day for a date, "
                    "the instant itself for a datetime. " + _DATE_PARAM_HELP + " Admin/moderator only."
                ),
            ),
        ] = None,
        published_to: Annotated[
            Optional[DateOrDatetime],
            Query(
                description=(
                    "Services published before this point: up to and including the day for a date, "
                    "strictly before the instant for a datetime (send the next day's local midnight). "
                    + _DATE_PARAM_HELP + " Must not be before published_from. Admin/moderator only."
                ),
            ),
        ] = None,
    ) -> None:
        self.task_types = task_types
        self.is_published = is_published
        self.created_by = created_by
        self.name = name
        self.service_id = service_id
        self.model_name = model_name
        self.tier_ids = tier_ids
        self.created_from = created_from
        self.created_to = created_to
        self.published_from = published_from
        self.published_to = published_to


class ServiceListSortParams:
    """Query-param dependency: the sort and pagination half of GET /services."""

    def __init__(
        self,
        sort_by: Annotated[
            Optional[str],
            Query(
                description=(
                    "Column id to sort by: " + ", ".join(sorted(SORTABLE_KEYS)) + ". Sorting is applied "
                    "across the full result set before pagination; empty values come last. Price, tier, "
                    "created_at and published_at are admin/moderator only. Default: published first, newest first."
                ),
            ),
        ] = None,
        sort_order: Annotated[
            str,
            Query(
                description="Sort direction when sort_by is given: asc (default) or desc.",
            ),
        ] = "asc",
        offset: Annotated[
            int,
            Query(
                ge=0,
                description="Number of items to skip (for pagination).",
            ),
        ] = 0,
        limit: Annotated[
            Optional[int],
            Query(
                ge=1,
                le=1000,
                description="Maximum number of items to return. Omit to return all services.",
            ),
        ] = None,
    ) -> None:
        self.sort_by = sort_by
        self.sort_order = sort_order
        self.offset = offset
        self.limit = limit


def _validate_sort(sort_by: Optional[str], sort_order: str, is_admin: bool) -> None:
    """Reject unknown sort columns/directions and admin-only sorts for non-admins."""
    if sort_by is not None and sort_by not in SORTABLE_KEYS:
        raise ValidationError(
            message=f"sort_by must be one of: {', '.join(sorted(SORTABLE_KEYS))}",
            code="INVALID_SORT_BY",
        )
    if sort_order not in {"asc", "desc"}:
        raise ValidationError(message="sort_order must be 'asc' or 'desc'", code="INVALID_SORT_ORDER")
    if not is_admin and sort_by in ADMIN_ONLY_KEYS:
        raise ValidationError(
            message=f"sort_by '{sort_by}' is not available to this caller.",
            code="SORT_NOT_PERMITTED",
        )


def _reject_admin_only_filters(filters: ServiceListFilterParams, is_admin: bool) -> None:
    """Raise FILTER_NOT_PERMITTED if a non-admin supplied an admin-only filter."""
    if is_admin:
        return
    # tier_ids stays open although the Tier column is admin-only: the
    # Application fallback picker filters by the Institution's own Tier.
    supplied = {p: getattr(filters, p) for p in ADMIN_ONLY_FILTER_PARAMS - {"tier_ids"}}
    denied = sorted(p for p, v in supplied.items() if v is not None)
    if denied:
        raise ValidationError(
            message=f"Filter parameter(s) not available to this caller: {', '.join(denied)}",
            code="FILTER_NOT_PERMITTED",
        )


def _validate_date_ranges(filters: ServiceListFilterParams) -> None:
    """Raise INVALID_DATE_RANGE when a *_from/*_to pair selects nothing. Bounds
    are compared as instants so a date and a datetime can be mixed."""
    for lo_name, lo, hi_name, hi in (
        ("created_from", filters.created_from, "created_to", filters.created_to),
        ("published_from", filters.published_from, "published_to", filters.published_to),
    ):
        if lo is not None and hi is not None and range_start(lo) >= range_end_exclusive(hi):
            raise ValidationError(
                message=f"{lo_name} must not be after {hi_name}",
                code="INVALID_DATE_RANGE",
            )


def _split_csv(value: Optional[str]) -> List[str]:
    """Split a comma-separated query value into stripped, lowercased, non-empty items."""
    if not value:
        return []
    return [part for part in (p.strip().lower() for p in value.split(",")) if part]


async def _resolve_task_types(task_types: Optional[str], db: AsyncSession) -> List[str]:
    # ONE task-type filter param: a drill-down is just a one-element list, so a
    # separate single param would only recreate union/precedence ambiguity.
    # Parsed leniently: names outside the catalogue (e.g. entries with no
    # registered models) are skipped rather than failing the whole request —
    # they can't match any row anyway.
    #
    # The allowlist is the live catalogue, not TaskTypeEnum. Only the validation
    # source changed: mm_models/mm_services are still filtered by name, since
    # their task type is a JSONB string, not a foreign key.
    requested = _split_csv(task_types)
    if not requested:
        return []
    valid = {entry["name"] for entry in await inference_type_cache.get_all(db)}
    return [t for t in requested if t in valid]


@router.get("", response_model_exclude_unset=True)
async def list_services(
    request: Request,
    response: Response,
    svc: Annotated[ServiceService, Depends(get_service_service)],
    db: Annotated[AsyncSession, Depends(get_db)],
    filters: Annotated[ServiceListFilterParams, Depends()],
    paging: Annotated[ServiceListSortParams, Depends()],
) -> ListServicesResponse:
    """List services with optional filters, sorting and offset/limit pagination.

    Filters combine with AND; filtering, sorting and pagination all run over
    the full dataset server-side, and `meta.total` / `X-Total-Count` is the
    number of services matching the filters (not just the page).
    """
    is_admin = is_platform_admin(request)
    sort_by = paging.sort_by or None  # a blank sort_by from the UI means default order
    _validate_sort(sort_by, paging.sort_order, is_admin)
    _reject_admin_only_filters(filters, is_admin)
    _validate_date_ranges(filters)
    task_types = await _resolve_task_types(filters.task_types, db)
    tier_ids = _split_csv(filters.tier_ids) or None
    # A non-admin filters by tier to pick from what their Tier can call (the
    # Application fallback picker): published services only, whatever was sent.
    is_published = True if (tier_ids and not is_admin) else filters.is_published
    items, total = await svc.list_services(
        task_types=task_types or None,
        is_published=is_published,
        created_by=filters.created_by,
        offset=paging.offset,
        limit=paging.limit,
        filters=ServiceListFilters(
            name=filters.name or None,
            service_id=filters.service_id or None,
            model_name=filters.model_name or None,
            tier_ids=tier_ids,
            created_from=filters.created_from,
            created_to=filters.created_to,
            published_from=filters.published_from,
            published_to=filters.published_to,
        ),
        sort_by=sort_by,
        sort_order=paging.sort_order,
    )
    # Non-admin already loses api_key/inferenceEndPoint entirely below, so
    # masking them first would be wasted work — only admins need it.
    if is_admin:
        items = [mask_service_secrets(i) for i in items]
    else:
        items = [_filter_service_fields(i) for i in items]
    response.headers["X-Total-Count"] = str(total)
    return ListServicesResponse(
        success=True,
        data=ServicesData(services=items),
        meta=ServiceListMeta(total=total, offset=paging.offset, limit=paging.limit),
    )


@router.get(
    "/{service_id:path}",
    summary="Retrieve Service",
    responses=error_responses(404),
    response_model_exclude_unset=True,
)
async def view_service(
    request: Request,
    service_id: str,
    svc: ServiceService = Depends(get_service_service),
) -> GetServiceResponse:
    """Retrieve full service details."""
    try:
        validate_service_id(service_id)
    except ValueError as exc:
        raise ValidationError(message=str(exc), code="INVALID_SERVICE_ID")
    data = await svc.get_service_detail(service_id)
    if is_platform_admin(request):
        data = mask_service_secrets(data)
    else:
        data = _filter_service_fields(data)
    return GetServiceResponse(success=True, data=data)


@router.post("", responses=error_responses(400, 409))
async def create_service(
    request: Request,
    payload: ServiceCreateRequest,
    svc: ServiceService = Depends(get_service_service),
) -> CreateServiceResponse:
    """Create a new service."""
    user_id = request.headers.get("X-User-Id")
    service_id = await svc.create_service(payload, created_by=user_id)
    return CreateServiceResponse(
        success=True,
        data=CreateServiceData(serviceId=service_id, name=payload.name),
        meta=MessageMeta(message=f"Service '{payload.name}' created successfully."),
    )


@router.patch("", responses=error_responses(400, 404, 409))
async def update_service(
    request: Request,
    payload: ServiceUpdateRequest | ServiceBulkEndpointUpdateRequest,
    svc: ServiceService = Depends(get_service_service),
) -> Union[UpdateServiceResponse, UpdateServiceEndpointsResponse]:
    """Update an existing service, or update multiple services' endpoints in
    one call by sending {"services": [{"serviceId", "endpoint"}, ...]}."""
    user_id = request.headers.get("X-User-Id")
    if isinstance(payload, ServiceBulkEndpointUpdateRequest):
        updated_ids = await svc.update_service_endpoints(
            payload.services, updated_by=user_id
        )
        return UpdateServiceEndpointsResponse(
            success=True,
            data=UpdateServiceEndpointsData(serviceIds=updated_ids),
            meta=MessageMeta(message=f"{len(updated_ids)} service endpoint(s) updated successfully."),
        )
    await svc.update_service(payload, updated_by=user_id)
    return UpdateServiceResponse(
        success=True,
        data=UpdateServiceData(serviceId=payload.serviceId),
        meta=MessageMeta(message=f"Service '{payload.serviceId}' updated successfully."),
    )


@router.delete("/{service_id:path}", responses=error_responses(404, 409))
async def delete_service(
    service_id: str,
    svc: ServiceService = Depends(get_service_service),
) -> DeleteServiceResponse:
    """Delete a service by its service ID."""
    await svc.delete_service(service_id)
    return DeleteServiceResponse(
        success=True,
        data=DeleteServiceData(serviceId=service_id),
        meta=MessageMeta(message=f"Service '{service_id}' deleted successfully."),
    )
