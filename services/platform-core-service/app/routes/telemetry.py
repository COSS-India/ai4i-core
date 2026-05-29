"""Telemetry API endpoints for querying traces."""

import logging
from typing import Optional

from fastapi import APIRouter, HTTPException, Query, Request, status

from app.schemas.telemetry import SearchTracesResponse, TraceResponse
from app.utils.opensearch_client import OpenSearchTraceClient

logger = logging.getLogger(__name__)

router = APIRouter(prefix="/telemetry", tags=["Telemetry"])


def _extract_tenant_id_from_jwt(request: Request) -> Optional[str]:
    """Extract tenant_id from X-Tenant-Id header."""
    return request.headers.get("X-Tenant-Id")


def _is_user_admin(request: Request) -> bool:
    """Check if user has ADMIN role."""
    roles = request.headers.get("X-Roles", "").split(",") if request.headers.get("X-Roles") else []
    return "ADMIN" in roles


def _is_user_tenant_admin(request: Request) -> bool:
    """Check if user has TENANT ADMIN role."""
    roles = request.headers.get("X-Roles", "").split(",") if request.headers.get("X-Roles") else []
    return "TENANT ADMIN" in roles


# Real OpenSearch client (singleton)
# TODO: Move these to environment variables
OPENSEARCH_URL = "http://localhost:9204"
OPENSEARCH_USERNAME = "admin"
OPENSEARCH_PASSWORD = "admin"
OPENSEARCH_INDEX = "traces-*"  # Wildcard to match traces-YYYY.MM.DD indices

_opensearch_client = OpenSearchTraceClient(
    url=OPENSEARCH_URL,
    username=OPENSEARCH_USERNAME,
    password=OPENSEARCH_PASSWORD,
    index=OPENSEARCH_INDEX,
)
if not _opensearch_client.connect():
    logger.warning("Could not connect to OpenSearch - real traces endpoint will return empty results")


@router.get("/traces/search", response_model=SearchTracesResponse)
async def search_traces_opensearch(
    request: Request,
    task_type: Optional[str] = Query(None, description="Filter by task type (NMT, ASR, OCR, etc.)"),
    status_filter: Optional[str] = Query(None, description="Filter by status (success, failure, etc.)"),
    tenant_id: Optional[str] = Query(None, description="Filter by tenant_id (ADMIN only for other tenants)"),
    start_date: Optional[str] = Query(None, description="Start date in ISO format"),
    end_date: Optional[str] = Query(None, description="End date in ISO format"),
    page: int = Query(1, ge=1, description="Page number for pagination"),
    page_size: int = Query(20, ge=1, le=100, description="Number of traces per page"),
) -> SearchTracesResponse:
    """
    Search traces from OpenSearch using direct queries on nested fields.
    """
    try:
        is_admin = _is_user_admin(request)
        is_tenant_admin = _is_user_tenant_admin(request)
        jwt_tenant_id = _extract_tenant_id_from_jwt(request)

        # Authorization: only ADMIN and TENANT_ADMIN can see traces
        if not is_admin and not is_tenant_admin:
            logger.warning("Regular user attempted to access traces - access denied")
            raise HTTPException(
                status_code=status.HTTP_403_FORBIDDEN,
                detail="Regular users cannot access traces. Only ADMIN and TENANT_ADMIN roles are allowed.",
            )

        # Determine tenant filter based on role
        tenant_filter = None
        if is_admin:
            if tenant_id:
                tenant_filter = tenant_id
                logger.info(f"ADMIN user - filtering by tenant_id={tenant_id}")
        else:
            if not jwt_tenant_id:
                raise HTTPException(
                    status_code=status.HTTP_403_FORBIDDEN,
                    detail="TENANT_ADMIN account has no tenant_id in token",
                )
            tenant_filter = jwt_tenant_id

        # Build OpenSearch query with direct nested field queries
        must_clauses = []

        if tenant_filter:
            must_clauses.append({"match_phrase": {"tenant_id": tenant_filter}})

        if task_type:
            must_clauses.append({"match_phrase": {"attributes.task_type": task_type}})

        if status_filter:
            must_clauses.append({"match_phrase": {"attributes.status": status_filter}})

        if start_date or end_date:
            range_query = {}
            if start_date:
                range_query["gte"] = start_date
            if end_date:
                range_query["lte"] = end_date
            must_clauses.append({"range": {"@timestamp": range_query}})

        if must_clauses:
            query = {"bool": {"must": must_clauses}}
        else:
            query = {"match_all": {}}

        logger.info(f"Searching traces - task_type={task_type}, status={status_filter}, tenant={tenant_filter}")

        # Execute search with pagination
        offset = (page - 1) * page_size
        response = _opensearch_client.search_traces(
            query=query,
            size=page_size,
            from_=offset,
            source_fields=[
                "@timestamp",
                "name",
                "context.trace_id",
                "attributes"
            ]
        )

        # Transform response to match expected format
        hits = response.get("hits", {}).get("hits", [])
        total = response.get("hits", {}).get("total", {}).get("value", 0)

        data = []
        seen_traces = set()

        for hit in hits:
            source = hit.get("_source", {})
            trace_id = source.get("context", {}).get("trace_id")

            # Skip duplicates in same page
            if trace_id in seen_traces:
                continue
            seen_traces.add(trace_id)

            span_name = source.get("name")
            attrs = source.get("attributes", {})

            task_type_val = attrs.get("task_type") if span_name == "model" else None
            status_val = attrs.get("status", "unknown")
            url = attrs.get("url") if span_name == "request" else None

            if trace_id:
                data.append({
                    "trace_id": trace_id,
                    "service": "ai4x-inference",
                    "task_type": task_type_val,
                    "status": status_val,
                    "url": url,
                    "tenant_id": tenant_filter or "system",
                    "timestamp": source.get("@timestamp") or source.get("timestamp"),
                })

        return SearchTracesResponse(
            data=data,
            total=total,
            page=page,
            pageSize=page_size,
            aggregations={
                "total": total,
                "by_level": {},
                "by_task": {},
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
) -> TraceResponse:
    """
    Get a specific trace by ID from OpenSearch.

    Args:
        trace_id: The trace ID to retrieve (hex format)

    Returns:
        Complete trace with all spans
    """
    try:
        is_admin = _is_user_admin(request)
        is_tenant_admin = _is_user_tenant_admin(request)
        jwt_tenant_id = _extract_tenant_id_from_jwt(request)

        if not is_admin and not is_tenant_admin:
            raise HTTPException(
                status_code=status.HTTP_403_FORBIDDEN,
                detail="You don't have permission to access traces",
            )

        if not is_admin and not jwt_tenant_id:
            raise HTTPException(
                status_code=status.HTTP_403_FORBIDDEN,
                detail="TENANT_ADMIN account has no tenant_id in token",
            )

        logger.info(f"Getting trace {trace_id} from OpenSearch")

        # Query OpenSearch for all spans with matching trace_id
        response = _opensearch_client.get_trace_by_id(trace_id, source_fields=[
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

        trace_response = TraceResponse(
            trace_id=trace_id,
            service="ai4x-inference",
            tenant_id=jwt_tenant_id or "system",
            service_version="1.0.0",
            environment="development",
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
