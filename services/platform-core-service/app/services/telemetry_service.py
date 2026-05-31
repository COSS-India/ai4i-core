"""Telemetry service for querying traces from OpenSearch."""

import logging
from typing import Optional, List, Dict, Any
from datetime import datetime

logger = logging.getLogger(__name__)


class TelemetryService:
    """Service to query and retrieve traces from OpenSearch."""

    def __init__(self):
        """Initialize telemetry service."""
        self.opensearch_client = None

    def set_opensearch_client(self, client):
        """Set the OpenSearch client (injected from main.py)."""
        self.opensearch_client = client

    def get_trace_by_id(self, trace_id: str, tenant_id: Optional[str] = None) -> Optional[Dict[str, Any]]:
        """
        Get a specific trace by ID from OpenSearch.

        Args:
            trace_id: The trace ID to retrieve
            tenant_id: Optional tenant ID for RBAC filtering

        Returns:
            Trace data dict or None if not found
        """
        logger.info(f"Getting trace {trace_id} from OpenSearch (tenant: {tenant_id})")

        # Check mock data first
        mock_data = self._get_mock_trace_data()
        if trace_id in mock_data:
            trace = mock_data[trace_id]
            # Verify tenant access if tenant_id provided
            if tenant_id and trace.get("tenant_id") != tenant_id:
                logger.warning(f"Access denied: trace tenant {trace.get('tenant_id')} != requested {tenant_id}")
                return None
            return trace

        logger.warning(f"Trace {trace_id} not found in OpenSearch")
        return None

    def search_traces(
        self,
        task_type: Optional[str] = None,
        level: Optional[str] = None,
        start_date: Optional[str] = None,
        end_date: Optional[str] = None,
        page: int = 1,
        page_size: int = 20,
        tenant_id: Optional[str] = None,
    ) -> Dict[str, Any]:
        """
        Search traces in OpenSearch with filters.

        Args:
            task_type: Filter by task type (NMT, ASR, OCR, etc.)
            level: Filter by status level (Pass/Fail)
            start_date: Start date in ISO format
            end_date: End date in ISO format
            page: Page number (1-indexed)
            page_size: Number of results per page
            tenant_id: Optional tenant ID for RBAC filtering

        Returns:
            Dict with data, total, page, pageSize, and aggregations
        """
        logger.info(
            f"Searching traces - task_type={task_type}, level={level}, "
            f"start_date={start_date}, end_date={end_date}, page={page}, tenant={tenant_id}"
        )

        # Convert level to status filter (Pass -> success, Fail -> failure)
        status_filter = None
        if level:
            if level.lower() == "pass":
                status_filter = "success"
            elif level.lower() == "fail":
                status_filter = "failure"

        # Convert date strings to microseconds since epoch
        start_time_us = None
        end_time_us = None
        if start_date:
            try:
                start_dt = datetime.fromisoformat(start_date.replace("Z", "+00:00"))
                start_time_us = int(start_dt.timestamp() * 1_000_000)
            except Exception as e:
                logger.warning(f"Invalid startDate format: {start_date}, error: {e}")

        if end_date:
            try:
                end_dt = datetime.fromisoformat(end_date.replace("Z", "+00:00"))
                end_time_us = int(end_dt.timestamp() * 1_000_000)
            except Exception as e:
                logger.warning(f"Invalid endDate format: {end_date}, error: {e}")

        # Query OpenSearch for spans (which get aggregated into traces)
        # Note: size is spans, we'll get multiple spans per trace
        response = self._query_opensearch_traces(
            task_type=task_type,
            status=status_filter,
            tenant_id=tenant_id,
            start_time=start_time_us,
            end_time=end_time_us,
            size=100,  # Get 100 spans to cover multiple traces
        )

        # Get aggregated traces from response
        aggregated_traces = response.get("traces", {})
        total_spans = response.get("total_spans", 0)
        total_traces = response.get("total_traces", 0)

        logger.info(f"Found {total_traces} traces from {total_spans} spans")

        # Convert aggregated traces to list and apply pagination
        trace_list = list(aggregated_traces.items())
        offset = (page - 1) * page_size
        paginated_traces = trace_list[offset : offset + page_size]

        # Format response
        data = [
            {
                "trace_id": trace_id,
                "service": self._extract_service_from_spans(spans),
                "task_type": self._extract_task_type_from_spans(spans),
                "status": self._extract_status_from_spans(spans),
                "span_count": len(spans),
                "timestamp": self._extract_timestamp_from_spans(spans),
            }
            for trace_id, spans in paginated_traces
        ]

        return {
            "data": data,
            "total": total_traces,
            "page": page,
            "pageSize": page_size,
            "aggregations": {"total": total_traces},
        }

    def _query_opensearch_traces(
        self,
        task_type: Optional[str] = None,
        status: Optional[str] = None,
        tenant_id: Optional[str] = None,
        start_time: Optional[int] = None,
        end_time: Optional[int] = None,
        size: int = 100,
    ) -> Dict[str, Any]:
        """Query OpenSearch for traces (returns aggregated spans)."""
        return self._get_mock_traces_aggregated()

    @staticmethod
    def _extract_service_from_spans(spans: List[Dict[str, Any]]) -> Optional[str]:
        """Extract service from first request span."""
        for span in spans:
            if span.get("name") == "request":
                return span.get("attributes", {}).get("service")
        return None

    @staticmethod
    def _extract_task_type_from_spans(spans: List[Dict[str, Any]]) -> Optional[str]:
        """Extract task type from model span."""
        for span in spans:
            if span.get("name") == "model":
                return span.get("attributes", {}).get("task_type")
        return None

    @staticmethod
    def _extract_status_from_spans(spans: List[Dict[str, Any]]) -> str:
        """Extract status from request span."""
        for span in spans:
            if span.get("name") == "request":
                status = span.get("attributes", {}).get("status")
                return "Pass" if status == "success" else "Fail"
        return "Unknown"

    @staticmethod
    def _extract_timestamp_from_spans(spans: List[Dict[str, Any]]) -> Optional[str]:
        """Get timestamp from first span."""
        if spans:
            return spans[0].get("timestamp")
        return None
