"""Telemetry API endpoints for querying traces."""
import re
import logging
from typing import Annotated, Optional

from fastapi import APIRouter, Depends, HTTPException, Query, Request, status

from app.schemas.telemetry import (
    SearchTracesResponse,
    SearchTraceSummary,
    TraceResponse,
)
from app.utils.opensearch_client import OpenSearchTraceClient
from app.utils.telemetry_params import (
    DEFAULT_COLUMN_KEYS,
    VALID_COLUMN_KEYS,
    parse_columns,
    parse_status_codes,
    validate_metadata_and_sort_params,
)
from app.services.telemetry_service import (
    get_trace_spans,
    search_traces,
    TraceFilterParams,
    PaginationParams,
)
from app.core.exceptions import InsufficientPermissionsError
from app.core.config import settings

logger = logging.getLogger(__name__)

router = APIRouter(prefix="/telemetry", tags=["Telemetry"])

# Role IDs (must match the seeded values in roles table)
_ROLE_ADMIN = 1
_ROLE_MODERATOR = 2
_ROLE_TENANT_ADMIN = 5

# All allowed roles for telemetry access (roles that can access telemetry endpoints)
ALLOWED_ROLES = {_ROLE_ADMIN, _ROLE_MODERATOR, _ROLE_TENANT_ADMIN}


def _check_permission_ids(request: Request, *allowed: int) -> None:
    """Raise if X-Permission-IDS header does not contain any of the allowed role IDs."""
    raw = request.headers.get("X-Permission-IDS", "")
    ids = {int(m) for m in re.findall(r"\d+", raw)}
    if not ids & set(allowed):
        raise InsufficientPermissionsError()


def _validate_telemetry_access(request: Request) -> None:
    """Validate that user has one of the allowed roles for telemetry access.

    Only roles 1 (admin), 2 (moderator), or 5 (tenant admin) are allowed.
    Raises InsufficientPermissionsError if user has role 3 (guest), 4 (user), or no role.
    """
    _check_permission_ids(request, *ALLOWED_ROLES)


def _is_admin(request: Request) -> bool:
    """Check if the user has admin/moderator role for trace access.
    Admin and Moderator can see all traces across all tenants.
    Returns True if user is admin or moderator, False otherwise.
    """
    try:
        _check_permission_ids(request, _ROLE_ADMIN, _ROLE_MODERATOR)
        return True
    except InsufficientPermissionsError:
        return False


def _get_tenant_id(request: Request) -> Optional[str]:
    """Caller's tenant from X-Tenant-Id (injected by the gateway from the validated JWT)."""
    return request.headers.get("X-Tenant-Id")


def _get_opensearch_client(request: Request) -> OpenSearchTraceClient:
    """Get OpenSearch client from app state."""
    client = getattr(request.app.state, "opensearch_client", None)
    if not client:
        raise HTTPException(
            status_code=status.HTTP_503_SERVICE_UNAVAILABLE,
            detail="OpenSearch service unavailable",
        )
    return client


def _resolve_tenant_filter(request: Request, is_admin: bool, tenant_id: Optional[str]) -> Optional[str]:
    if is_admin:
        tenant_filter = tenant_id
        if tenant_filter:
            logger.info(f"ADMIN trace read - filtering by tenant_id={tenant_filter}")
    else:
        tenant_filter = _get_tenant_id(request)
        if not tenant_filter:
            raise HTTPException(
                status_code=status.HTTP_403_FORBIDDEN,
                detail="No tenant_id in token for tenant-scoped trace access",
            )
        logger.info(f"Tenant-scoped trace read - tenant_id={tenant_filter}")
    return tenant_filter


@router.get("/traces/search", response_model=SearchTracesResponse)
async def search_traces_opensearch(
    request: Request,
    task_types: Optional[str] = Query(None, description="Comma-separated task type filter (e.g. nmt,llm,asr)"),
    status_filter: Optional[str] = Query(None, description="Filter by status (success, failed) — legacy alias for `status`"),
    tenant_id: Optional[str] = Query(None, description="Filter by tenant_id (ADMIN only for other tenants)"),
    start_date: Optional[str] = Query(None, description="Start date in ISO format"),
    end_date: Optional[str] = Query(None, description="End date in ISO format"),
    page: int = Query(1, ge=1, description="Page number for pagination"),
    page_size: int = Query(20, ge=1, le=100, description="Number of traces per page"),
    opensearch_client: OpenSearchTraceClient = Depends(_get_opensearch_client),
    # Annotated (not `= Query(None)`) so a direct call that omits these gets
    # None, not a truthy FieldInfo.
    user: Annotated[Optional[str], Query(
        max_length=256, description="Exact end-user ID the caller sent as OpenAI `user`",
    )] = None,
    metadata_key: Annotated[Optional[str], Query(
        min_length=1, max_length=64, pattern=r"^[^=]+$",
        description="Caller metadata key (no '='); requires metadata_value",
    )] = None,
    metadata_value: Annotated[Optional[str], Query(
        max_length=512, description="Exact value for metadata_key",
    )] = None,
    q: Annotated[Optional[str], Query(
        min_length=1, max_length=256,
        description="Keyword search across all span fields",
    )] = None,
    log_status: Annotated[Optional[str], Query(
        alias="status",
        description="Filter by status: success or failed",
    )] = None,
    status_code: Annotated[Optional[str], Query(
        description="Comma-separated HTTP status codes 100-599, max 10 values",
    )] = None,
    service_id: Optional[str] = Query(None, description="Exact match on service ID"),
    sort_by: Optional[str] = Query(None, description="Sort field: timestamp, url, latency, status_code"),
    sort_order: Optional[str] = Query(None, description="Sort direction: desc (default) or asc"),
    method: Annotated[Optional[str], Query(
        max_length=16, description="Contains match on HTTP method (e.g. GET, POST)",
    )] = None,
    model: Annotated[Optional[str], Query(
        max_length=256, description="Contains match on model name",
    )] = None,
    error: Annotated[Optional[str], Query(
        max_length=512, description="Phrase match on error/status description",
    )] = None,
    service: Annotated[Optional[str], Query(
        max_length=256, description="Phrase match on service name",
    )] = None,
    url: Annotated[Optional[str], Query(
        max_length=512, description="Contains match on request URL",
    )] = None,
    application: Annotated[Optional[str], Query(
        max_length=256, description="Contains match on application ID",
    )] = None,
    columns: Annotated[Optional[str], Query(
        description=(
            "Comma-separated column keys to include in each response row. "
            f"Defaults to: {','.join(sorted(DEFAULT_COLUMN_KEYS))}. "
            f"Valid keys: {','.join(sorted(VALID_COLUMN_KEYS))}"
        ),
    )] = None,
):
    """
    Search traces from OpenSearch for the Logs Dashboard.

    Returns one page of matching logs (`data`) plus the true pagination
    `total`, a `summary` of success/failure counts across all matched traces,
    and `aggregations` (by_level, by_task) covering every log that matches
    the filters — not just the page being returned.

    When `q` is given a keyword pre-query resolves matching trace IDs across
    all span types first; the main query then gates on that set. If the
    keyword matches more than 20,000 distinct traces a 400 is returned
    immediately so the caller can narrow the search.
    """
    _validate_telemetry_access(request)
    validate_metadata_and_sort_params(metadata_key, metadata_value, sort_by, sort_order)
    selected_columns = parse_columns(columns)
    status_code_list = parse_status_codes(status_code)
    # `status` (log_status) takes precedence over the legacy `status_filter` alias
    effective_status = log_status or status_filter

    try:
        is_admin_user = _is_admin(request)
        tenant_filter = _resolve_tenant_filter(request, is_admin_user, tenant_id)

        logger.info(
            f"Searching traces - task_types={task_types}, status={effective_status}, "
            f"tenant={tenant_filter}, service_id={service_id}, status_code={status_code}, "
            f"method={method}, model={model}, url={url}, application={application}, "
            f"error={'set' if error else None}, service={service}, "
            f"q={'set' if q else None}, sort_by={sort_by}, sort_order={sort_order}, "
            f"user_filter={user is not None}, metadata_filter={metadata_key is not None}"
        )

        result = await search_traces(
            opensearch_client,
            selected_columns=selected_columns,
            tenant_filter=tenant_filter,
            is_admin=is_admin_user,
            filters=TraceFilterParams(
                effective_status=effective_status,
                task_types=task_types,
                user=user,
                metadata_key=metadata_key,
                metadata_value=metadata_value,
                service_id=service_id,
                status_code_list=status_code_list,
                start_date=start_date,
                end_date=end_date,
                q=q,
                method=method,
                model=model,
                error=error,
                service=service,
                url=url,
                application=application,
            ),
            pagination=PaginationParams(
                page=page,
                page_size=page_size,
                sort_by=sort_by,
                sort_order=sort_order,
            ),
        )

        summary = SearchTraceSummary(
            success=result["by_level"].get("success", 0),
            failure=result["by_level"].get("failed", 0) + result["by_level"].get("failure", 0),
        )

        return SearchTracesResponse(
            data=result["data"],
            total=result["total"],
            page=page,
            pageSize=page_size,
            aggregations={
                "total": result["agg_total"] if effective_status else result["total"],
                "by_level": result["by_level"],
                "by_task": result["by_task"],
                "partial": result["is_partial"],
            },
            summary=summary,
        )

    except HTTPException:
        raise
    except Exception as e:
        logger.error(f"Error searching OpenSearch: {e}", exc_info=True)
        raise HTTPException(
            status_code=status.HTTP_500_INTERNAL_SERVER_ERROR,
            detail=f"Error searching OpenSearch: {str(e)}",
        )


@router.get("/traces/{trace_id}", response_model=TraceResponse)
async def get_trace_by_id(
    trace_id: str,
    request: Request,
    opensearch_client: OpenSearchTraceClient = Depends(_get_opensearch_client),
):
    """
    Get a specific trace by ID from OpenSearch.

    Args:
        trace_id: The trace ID to retrieve (hex format)

    Returns:
        Complete trace with all spans
    """
    try:
        _validate_telemetry_access(request)
        is_admin_user = _is_admin(request)
        tenant_scope = None if is_admin_user else _get_tenant_id(request)
        if not is_admin_user and not tenant_scope:
            raise HTTPException(
                status_code=status.HTTP_403_FORBIDDEN,
                detail="No tenant_id in token for tenant-scoped trace access",
            )

        logger.info(f"Getting trace {trace_id} from OpenSearch")

        spans, service = get_trace_spans(
            opensearch_client,
            trace_id,
            is_admin=is_admin_user,
            tenant_scope=tenant_scope,
        )

        trace_response = TraceResponse(
            trace_id=trace_id,
            service=service,
            tenant_id=tenant_scope or "system",
            environment=settings.environment,
            hostname="unknown",
            spans=spans,
        )

        logger.info(f"Successfully retrieved trace {trace_id} with {len(spans)} spans")
        return trace_response

    except HTTPException:
        raise
    except Exception as e:
        logger.error(f"Error getting trace: {e}", exc_info=True)
        raise HTTPException(
            status_code=status.HTTP_500_INTERNAL_SERVER_ERROR,
            detail=f"Error getting trace: {str(e)}",
        )
