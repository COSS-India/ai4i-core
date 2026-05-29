"""Telemetry API endpoints for querying traces."""

import logging
from typing import Optional

from fastapi import APIRouter, Depends, HTTPException, Query, Request, status

from app.schemas.telemetry import SearchTracesResponse, TraceResponse
from app.services.telemetry_service import TelemetryService
from app.utils.opensearch_client import OpenSearchTraceClient

logger = logging.getLogger(__name__)

router = APIRouter(prefix="/telemetry", tags=["Telemetry"])
telemetry_service = TelemetryService()


def get_telemetry_service() -> TelemetryService:
    """Get telemetry service instance."""
    return telemetry_service


def _extract_tenant_id_from_jwt(request: Request) -> Optional[str]:
    """Extract tenant_id from Authorization header (mocked for now)."""
    auth_header = request.headers.get("Authorization", "")
    if auth_header.startswith("Bearer "):
        # Mock: return tenant_id "2" when Bearer token is present
        return "2"
    return None


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
OPENSEARCH_INDEX = "trace-*"  # Wildcard to match trace-001, trace-002, trace-003, etc.

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
    TaskType: Optional[str] = Query(None, description="Filter by task type (NMT, ASR, OCR, etc.)"),
    Level: Optional[str] = Query(None, description="Filter by status/level (Pass/Fail)"),
    startDate: Optional[str] = Query(None, description="Start date in ISO format"),
    endDate: Optional[str] = Query(None, description="End date in ISO format"),
    PageCount: int = Query(1, ge=1, description="Page number for pagination"),
    pageSize: int = Query(20, ge=1, le=100, description="Number of traces per page"),
) -> SearchTracesResponse:
    """
    Search traces from OpenSearch.

    This endpoint queries the actual OpenSearch traces index.
    Spans are automatically aggregated into complete traces.

    Args:
        TaskType: Filter by task type (NMT, ASR, OCR, etc.)
        Level: Filter by status (Pass/Fail)
        startDate: Start date ISO format
        endDate: End date ISO format
        PageCount: Page number
        pageSize: Results per page (note: applies to spans, not traces)
    """
    try:
        is_admin = _is_user_admin(request)
        is_tenant_admin = _is_user_tenant_admin(request)
        jwt_tenant_id = _extract_tenant_id_from_jwt(request)

        tenant_filter = None
        if is_admin:
            logger.info("ADMIN user - can see all traces from OpenSearch")
            tenant_filter = None
        elif is_tenant_admin:
            if not jwt_tenant_id:
                raise HTTPException(
                    status_code=status.HTTP_403_FORBIDDEN,
                    detail="TENANT ADMIN account has no tenant_id in token",
                )
            tenant_filter = jwt_tenant_id
        else:
            if not jwt_tenant_id:
                logger.warning("Regular user has no tenant_id, denying access")
                raise HTTPException(
                    status_code=status.HTTP_403_FORBIDDEN,
                    detail="You must have a valid tenant_id to access traces",
                )
            tenant_filter = jwt_tenant_id

        logger.info(
            f"Searching OpenSearch - TaskType={TaskType}, Level={Level}, "
            f"Page={PageCount}, tenant={tenant_filter}"
        )

        # Build OpenSearch query (searches spans, not traces)
        query = _opensearch_client.build_complex_query(
            task_type=TaskType,
            status=None,  # Don't filter by status in query (will extract from spans)
            tenant_id=tenant_filter,
            start_date=startDate,
            end_date=endDate,
        )

        # Execute search with pagination
        offset = (PageCount - 1) * pageSize
        response = _opensearch_client.search_traces(query=query, size=pageSize, from_=offset)

        # Extract aggregated traces
        traces_dict = response.get("traces", {})
        total_spans = response.get("total_spans", 0)
        total_traces = len(traces_dict)

        logger.info(f"Found {total_traces} traces with {total_spans} spans in OpenSearch")

        # Transform aggregated traces to response format
        data = []
        for trace_id, spans in traces_dict.items():
            task_type = None
            status = None
            url = None
            timestamp = None

            # Extract metadata directly from span attributes (from OpenSearch message)
            for span in spans:
                attrs = span.get("attributes", {})
                span_name = span.get("name")

                if span_name == "model" and not task_type:
                    task_type = attrs.get("task_type")

                if not status:
                    status = attrs.get("status")

                if span_name == "request" and not url:
                    url = attrs.get("url")

                if not timestamp:
                    timestamp = span.get("timestamp")

            if trace_id:
                data.append({
                    "trace_id": trace_id,
                    "service": "ai4x-inference",
                    "task_type": task_type,
                    "status": status,
                    "url": url,
                    "tenant_id": tenant_filter or "system",
                    "timestamp": timestamp,
                })

        return SearchTracesResponse(
            data=data,
            total=total_traces,
            page=PageCount,
            pageSize=pageSize,
            aggregations={
                "total": total_traces,
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

    Requires 'traces.read' permission.
    Traces are retrieved from OpenSearch traces index.
    Returns 404 if trace not found or not accessible to the user's organization.

    Args:
        trace_id: The trace ID to retrieve (hex format, e.g., 0xc78a7cde764dd2b4022ff59a0b3d91a7)

    Returns:
        Complete trace with all spans
    """
    try:
        # Check role types
        is_admin = _is_user_admin(request)
        is_tenant_admin = _is_user_tenant_admin(request)

        # Extract tenant_id from JWT token
        jwt_tenant_id = _extract_tenant_id_from_jwt(request)

        # Determine tenant filter based on role
        tenant_filter = None
        if is_admin:
            logger.info("ADMIN user - can see all traces")
            tenant_filter = None
        elif is_tenant_admin:
            if not jwt_tenant_id:
                raise HTTPException(
                    status_code=status.HTTP_403_FORBIDDEN,
                    detail="TENANT ADMIN account has no tenant_id in token",
                )
            tenant_filter = jwt_tenant_id
        else:
            # Regular user
            if not jwt_tenant_id:
                logger.warning("Regular user has no tenant_id, denying access")
                raise HTTPException(
                    status_code=status.HTTP_403_FORBIDDEN,
                    detail="You must have a valid tenant_id to access traces",
                )
            tenant_filter = jwt_tenant_id

        logger.info(f"Getting trace {trace_id} from OpenSearch with tenant filter: {tenant_filter}")

        # Query OpenSearch for all spans (trace_id is nested in message JSON)
        # We'll filter by trace_id in Python after parsing
        response = _opensearch_client.search_traces(query={"match_all": {}}, size=1000)
        traces_dict = response.get("traces", {})

        # Get the trace data
        if trace_id not in traces_dict or not traces_dict[trace_id]:
            logger.warning(f"Trace {trace_id} not found or not accessible")
            raise HTTPException(
                status_code=status.HTTP_404_NOT_FOUND,
                detail=f"Trace {trace_id} not found or not accessible",
            )

        spans = traces_dict[trace_id]

        # Build response
        # Extract service info from first span
        service_name = "ai4x-inference"
        tenant_id = tenant_filter or "system"
        service_version = "1.0.0"
        environment = "development"
        hostname = "unknown"

        trace_response = TraceResponse(
            trace_id=trace_id,
            service=service_name,
            tenant_id=tenant_id,
            service_version=service_version,
            environment=environment,
            hostname=hostname,
            spans=[{
                "name": span.get("name"),
                "context": span.get("context", {}),
                "kind": span.get("kind"),
                "attributes": span.get("attributes", {}),
                "timestamp": span.get("timestamp"),
                "logger": span.get("logger"),
            } for span in spans]
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
