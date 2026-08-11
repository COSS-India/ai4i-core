"""Telemetry API endpoints for querying traces."""
import re
import logging
from typing import Optional

from fastapi import APIRouter, Depends, HTTPException, Query, Request, status

from app.schemas.telemetry import SearchTracesResponse, TraceResponse
from app.utils.opensearch_client import OpenSearchTraceClient
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

# Fixed display order for the trace-detail waterfall: every task type
# (LLM, NMT, ASR, ...) resolves a model before calling it, so this sequence
# is always correct regardless of task type or nesting shape.
_SPAN_ORDER = {"request": 0, "model": 1, "ai-inference": 2}


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


@router.get("/traces/search", response_model=SearchTracesResponse)
async def search_traces_opensearch(
    request: Request,
    task_types: Optional[str] = Query(None, description="Comma-separated task type filter (e.g. nmt,llm,asr)"),
    status_filter: Optional[str] = Query(None, description="Filter by status (success, failure, etc.)"),
    tenant_id: Optional[str] = Query(None, description="Filter by tenant_id (ADMIN only for other tenants)"),
    start_date: Optional[str] = Query(None, description="Start date in ISO format"),
    end_date: Optional[str] = Query(None, description="End date in ISO format"),
    page: int = Query(1, ge=1, description="Page number for pagination"),
    page_size: int = Query(20, ge=1, le=100, description="Number of traces per page"),
    opensearch_client: OpenSearchTraceClient = Depends(_get_opensearch_client),
):
    """
    Search traces from OpenSearch using direct queries on nested fields.
    """

    # Validate user has one of the allowed roles (1, 2, or 5)
    _validate_telemetry_access(request)

    try:
        is_admin = _is_admin(request)

        # Access is already gated at the gateway (traces.read). Here we only decide
        # breadth: admin sees all tenants (optionally narrowed by ?tenant_id); everyone
        # else is scoped to their own tenant and the client tenant_id is ignored.
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

        # Build OpenSearch query to find matching traces, then return ALL spans for those traces
        filter_clauses = []

        if tenant_filter:
            filter_clauses.append({"match_phrase": {"attributes.tenantId": tenant_filter}})

        if task_types:
            types_list = [t.strip() for t in task_types.split(",") if t.strip()]
            if len(types_list) == 1:
                filter_clauses.append({"match_phrase": {"attributes.task_type": types_list[0]}})
            elif types_list:
                filter_clauses.append({
                    "bool": {
                        "should": [{"match_phrase": {"attributes.task_type": t}} for t in types_list],
                        "minimum_should_match": 1,
                    }
                })

        if status_filter:
            filter_clauses.append({"match_phrase": {"attributes.status": status_filter}})

        if start_date or end_date:
            range_query = {}
            if start_date:
                range_query["gte"] = start_date
            if end_date:
                range_query["lte"] = end_date
            filter_clauses.append({"range": {"@timestamp": range_query}})

        # Step 1: Find trace_ids that match the filters
        if filter_clauses:
            filter_query = {"bool": {"must": filter_clauses}}
        else:
            filter_query = {"match_all": {}}

        logger.info(f"Searching traces - task_types={task_types}, status={status_filter}, tenant={tenant_filter}")

        # Step 2: page the matching traces at the TRACE level, newest-first.
        # Collapsing on trace_id makes each result row one trace (not one span), so
        # from/size paginate over traces; sorting by @timestamp desc (the client
        # default) orders them by recency; the cardinality agg yields the distinct
        # trace count so page math reflects traces, not spans.
        offset = (page - 1) * page_size
        ids_response = opensearch_client.search_traces(
            query=filter_query,
            size=page_size,
            from_=offset,
            source_fields=["context.trace_id"],
            collapse={"field": "context.trace_id.keyword"},
            aggs={"trace_count": {"cardinality": {"field": "context.trace_id.keyword"}}},
        )

        # Total count is the number of matching traces (not spans)
        total = ids_response.get("aggregations", {}).get("trace_count", {}).get("value", 0)

        _NULL_TRACE_ID = "0x" + "0" * 32

        # Preserve the newest-first order from the collapse result
        paginated_trace_ids = []
        for hit in ids_response.get("hits", {}).get("hits", []):
            trace_id = hit.get("_source", {}).get("context", {}).get("trace_id")
            if trace_id and trace_id != _NULL_TRACE_ID and trace_id not in paginated_trace_ids:
                paginated_trace_ids.append(trace_id)

        # Step 3: fetch ALL spans for the paged traces. Filters target single span
        # types (task_type on the 'model' span, url on 'request'), so we re-fetch the
        # full set per trace — unfiltered — to assemble complete metadata.
        traces_map = {}
        if paginated_trace_ids:
            trace_id_clauses = [{"match_phrase": {"context.trace_id": tid}} for tid in paginated_trace_ids]
            spans_response = opensearch_client.search_traces(
                query={"bool": {"should": trace_id_clauses, "minimum_should_match": 1}},
                size=len(paginated_trace_ids) * 50,  # generous per-trace span ceiling
                source_fields=["@timestamp", "name", "context.trace_id", "attributes", "service_name"],
            )

            for hit in spans_response.get("hits", {}).get("hits", []):
                source = hit.get("_source", {})
                trace_id = source.get("context", {}).get("trace_id")
                if not trace_id:
                    continue

                span_name = source.get("name")
                attrs = source.get("attributes", {})

                if trace_id not in traces_map:
                    traces_map[trace_id] = {
                        "trace_id": trace_id,
                        "service": source.get("service_name") or "ai4x-inference",
                        "task_type": None,
                        "status": "unknown",
                        "url": None,
                        "tenant_id": tenant_filter or attrs.get("tenantId") or "system",
                        "timestamp": source.get("@timestamp") or source.get("timestamp"),
                    }
                elif not traces_map[trace_id]["service"] or traces_map[trace_id]["service"] == "ai4x-inference":
                    # Upgrade the service name from a later span if a real name is present
                    if source.get("service_name"):
                        traces_map[trace_id]["service"] = source.get("service_name")

                # Extract task_type from model span
                if span_name == "model" and not traces_map[trace_id]["task_type"]:
                    traces_map[trace_id]["task_type"] = attrs.get("task_type")

                # Extract url from request span
                if span_name == "request" and not traces_map[trace_id]["url"]:
                    traces_map[trace_id]["url"] = attrs.get("url")

                # Extract status from any span
                if not traces_map[trace_id]["status"] or traces_map[trace_id]["status"] == "unknown":
                    traces_map[trace_id]["status"] = attrs.get("status", "unknown")

        # Emit in the newest-first order established by the collapse page
        data = [traces_map[tid] for tid in paginated_trace_ids if tid in traces_map]

        # Calculate aggregations
        by_level = {}
        by_task = {}
        for trace in data:
            # .get(..., "unknown") does not help when the value is explicitly None
            trace_status = trace.get("status") or "unknown"
            task_type_key = trace.get("task_type") or "unknown"

            by_level[trace_status] = by_level.get(trace_status, 0) + 1
            by_task[task_type_key] = by_task.get(task_type_key, 0) + 1

        return SearchTracesResponse(

            data=data,
            total=total,
            page=page,
            pageSize=page_size,
            aggregations={
                "total": len(data),
                "by_level": by_level,
                "by_task": by_task,
            }
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
        is_admin = _is_admin(request)
        tenant_scope = None if is_admin else _get_tenant_id(request)
        if not is_admin and not tenant_scope:
            raise HTTPException(
                status_code=status.HTTP_403_FORBIDDEN,
                detail="No tenant_id in token for tenant-scoped trace access",
            )

        logger.info(f"Getting trace {trace_id} from OpenSearch")

        # Query OpenSearch for all spans with matching trace_id
        response = opensearch_client.get_trace_by_id(trace_id, source_fields=[
            "@timestamp",
            "name",
            "context.trace_id",
            "context.parent_span_id",
            "status",
            "attributes"
        ])
        hits = response.get("hits", {}).get("hits", [])

        if not hits:
            logger.warning(f"Trace {trace_id} not found")
            raise HTTPException(
                status_code=status.HTTP_404_NOT_FOUND,
                detail=f"Trace {trace_id} not found",
            )

        # Tenant scoping: a non-admin may only read traces in their own tenant.
        # Return 404 (not 403) so trace existence isn't revealed across tenants.
        # Untenanted traces are treated as not-found for tenant-scoped callers.
        if not is_admin:
            span_tenants = {
                hit.get("_source", {}).get("attributes", {}).get("tenantId")
                for hit in hits
            }
            span_tenants.discard(None)
            if tenant_scope not in span_tenants:
                logger.warning(f"Tenant {tenant_scope} denied access to trace {trace_id}")
                raise HTTPException(
                    status_code=status.HTTP_404_NOT_FOUND,
                    detail=f"Trace {trace_id} not found",
                )

        # Transform spans from response
        spans = []
        for hit in hits:
            source = hit.get("_source", {})
            spans.append({
                "name": source.get("name"),
                "context": source.get("context", {}),
                "kind": source.get("kind"),
                "attributes": source.get("attributes", {}),
                "timestamp": source.get("@timestamp") or source.get("timestamp"),
            })

        # @timestamp is Fluent Bit's ingestion time, not the span's real OTel
        # end_time (no Time_Key override in fluent-bit.conf), so all spans in a
        # trace land within a few ms of each other regardless of actual duration
        # -- unusable for chronological ordering, and start_time/end_time never
        # reach this index. Every task type follows the same fixed span
        # sequence, so rank by name instead of by (unreliable) time.
        spans.sort(key=lambda s: _SPAN_ORDER.get(s.get("name"), len(_SPAN_ORDER)))

        trace_response = TraceResponse(
            trace_id=trace_id,
            service="ai4x-inference",
            tenant_id=tenant_scope or "system",
            service_version=settings.service_version,
            environment=settings.environment,
            hostname="unknown",
            spans=spans
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
