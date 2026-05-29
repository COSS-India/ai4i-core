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
    task_type: Optional[str] = Query(None, description="Filter by task type (NMT, ASR, OCR, etc.)"),
    status: Optional[str] = Query(None, description="Filter by status (success, failure, etc.)"),
    tenant_id: Optional[str] = Query(None, description="Filter by tenant_id (ADMIN only for other tenants)"),
    start_date: Optional[str] = Query(None, description="Start date in ISO format"),
    end_date: Optional[str] = Query(None, description="End date in ISO format"),
    page: int = Query(1, ge=1, description="Page number for pagination"),
    page_size: int = Query(20, ge=1, le=100, description="Number of traces per page"),
) -> SearchTracesResponse:
    """
    Search traces from OpenSearch.

    This endpoint queries the actual OpenSearch traces index.
    Spans are automatically aggregated into complete traces.

    Args:
        task_type: Filter by task type (NMT, ASR, OCR, etc.)
        status: Filter by status (success, failure, etc.)
        tenant_id: Filter by tenant_id (ADMIN can view any tenant, TENANT_ADMIN/users can only view their own)
        start_date: Start date in ISO format
        end_date: End date in ISO format
        page: Page number
        page_size: Results per page (note: applies to spans, not traces)
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
            # ADMIN: can see any tenant, optionally filter by tenant_id param
            if tenant_id:
                tenant_filter = tenant_id
                logger.info(f"ADMIN user - filtering by tenant_id={tenant_id}")
            else:
                logger.info("ADMIN user - can see all traces from OpenSearch")
                tenant_filter = None
        else:
            # TENANT_ADMIN: can only see their own tenant, tenant_id param is ignored
            if not jwt_tenant_id:
                raise HTTPException(
                    status_code=status.HTTP_403_FORBIDDEN,
                    detail="TENANT_ADMIN account has no tenant_id in token",
                )
            tenant_filter = jwt_tenant_id
            if tenant_id and tenant_id != jwt_tenant_id:
                logger.warning(f"TENANT_ADMIN tried to filter by different tenant - using their own tenant_id={jwt_tenant_id}")
            logger.info(f"TENANT_ADMIN user - viewing only their own tenant_id={jwt_tenant_id}")

        logger.info(
            f"Searching OpenSearch - task_type={task_type}, status={status}, "
            f"page={page}, tenant={tenant_filter}"
        )

        # Build OpenSearch query (get all traces, then filter in Python)
        query = _opensearch_client.build_complex_query(
            task_type=None,  # Filter in Python below
            status=None,  # Filter in Python below
            tenant_id=tenant_filter,
            start_date=start_date,
            end_date=end_date,
        )

        # Execute search with large size to get enough data for filtering
        response = _opensearch_client.search_traces(query=query, size=1000, from_=0)

        # Extract aggregated traces
        traces_dict = response.get("traces", {})

        # Filter traces by task_type and status in Python
        filtered_traces = {}
        for trace_id, trace_data in traces_dict.items():
            spans = trace_data.get("spans", []) if isinstance(trace_data, dict) else trace_data

            # Check if trace matches filters
            task_type_match = True
            status_match = True

            # Check task_type filter
            if task_type:
                for span in spans:
                    if span.get("name") == "model":
                        span_task_type = span.get("attributes", {}).get("task_type")
                        task_type_match = (span_task_type == task_type)
                        break

            # Check status filter
            if status:
                for span in spans:
                    span_status = span.get("attributes", {}).get("status")
                    if span_status == status:
                        status_match = True
                        break
                    status_match = False

            if task_type_match and status_match:
                filtered_traces[trace_id] = trace_data

        # Apply pagination to filtered results
        trace_list = list(filtered_traces.items())
        offset = (page - 1) * page_size
        paginated_traces = trace_list[offset : offset + page_size]
        total_traces = len(trace_list)

        logger.info(
            f"Found {total_traces} traces (filters: task_type={task_type}, status={status})"
        )

        # Transform aggregated traces to response format
        data = []
        for trace_id, trace_data in paginated_traces:
            spans = trace_data.get("spans", []) if isinstance(trace_data, dict) else trace_data
            trace_tenant_id = trace_data.get("tenant_id") if isinstance(trace_data, dict) else None
            trace_service = trace_data.get("service") if isinstance(trace_data, dict) else None

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
                    "service": trace_service or "ai4x-inference",
                    "task_type": task_type,
                    "status": status,
                    "url": url,
                    "tenant_id": trace_tenant_id or "system",
                    "timestamp": timestamp,
                })

        return SearchTracesResponse(
            data=data,
            total=total_traces,
            page=page,
            pageSize=page_size,
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

        trace_data = traces_dict[trace_id]
        spans = trace_data.get("spans", []) if isinstance(trace_data, dict) else trace_data
        trace_tenant_id = trace_data.get("tenant_id") if isinstance(trace_data, dict) else None
        trace_service = trace_data.get("service") if isinstance(trace_data, dict) else None

        # Build response
        service_name = trace_service or "ai4x-inference"
        tenant_id = trace_tenant_id or "system"
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
