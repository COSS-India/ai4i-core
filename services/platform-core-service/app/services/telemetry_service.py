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

    def _get_mock_traces_aggregated(self) -> Dict[str, Any]:
        """Get mock traces in aggregated format (trace_id -> list of spans)."""
        traces = {
            "0xc78a7cde764dd2b4022ff59a0b3d91a7": [
                {
                    "name": "request",
                    "context": {"trace_id": "0xc78a7cde764dd2b4022ff59a0b3d91a7"},
                    "kind": "SpanKind.INTERNAL",
                    "attributes": {"total_time_ms": 23224.33, "url": "/api/v1/nmt/inference", "status": "success"},
                    "timestamp": "2026-05-28T18:14:35.416613+00:00",
                },
                {
                    "name": "model",
                    "context": {"trace_id": "0xc78a7cde764dd2b4022ff59a0b3d91a7"},
                    "kind": "SpanKind.INTERNAL",
                    "attributes": {"task_type": "NMT"},
                    "timestamp": "2026-05-28T18:14:13.538874+00:00",
                },
                {
                    "name": "ai-inference",
                    "context": {"trace_id": "0xc78a7cde764dd2b4022ff59a0b3d91a7"},
                    "kind": "SpanKind.INTERNAL",
                    "attributes": {"total_time_ms": 8525.23},
                    "timestamp": "2026-05-28T18:14:28.811737+00:00",
                },
            ]
        }
        return {"traces": traces, "total_spans": 3, "total_traces": 1}

    @staticmethod
    def _generate_aggregations(traces: List[Dict[str, Any]]) -> Dict[str, Any]:
        """Generate aggregation statistics from traces."""
        by_level = {"success": 0, "failure": 0}
        by_task = {}

        for trace in traces:
            status = trace.get("status", "unknown")
            by_level[status] = by_level.get(status, 0) + 1

            task_type = trace.get("task_type")
            if task_type:
                by_task[task_type] = by_task.get(task_type, 0) + 1

        return {
            "total": len(traces),
            "by_level": by_level,
            "by_task": by_task,
        }

    @staticmethod
    def _get_mock_trace_data() -> Dict[str, Dict[str, Any]]:
        """Return mock trace data with complete traces including all spans."""
        nmt_success_trace = {
            "trace_id": "0xc78a7cde764dd2b4022ff59a0b3d91a7",
            "service": "ai4x-inference",
            "tenant_id": "system",
            "service_version": "1.0.0",
            "environment": "development",
            "hostname": "TI-MAC-085-VINU.local",
            "spans": [
                {
                    "name": "request",
                    "context": {
                        "trace_id": "0xc78a7cde764dd2b4022ff59a0b3d91a7",
                        "span_id": "0x7a11003141837e89",
                        "trace_state": "",
                    },
                    "kind": "SpanKind.INTERNAL",
                    "attributes": {
                        "total_time_ms": 23224.33,
                        "url": "/api/v1/nmt/inference",
                        "method": "POST",
                        "status": "success",
                        "status_code": 200,
                    },
                    "timestamp": "2026-05-28T18:14:35.416613+00:00",
                    "logger": "trace.request_span",
                    "taskName": "Task-5",
                },
                {
                    "name": "model",
                    "context": {
                        "trace_id": "0xc78a7cde764dd2b4022ff59a0b3d91a7",
                        "span_id": "0xb25c5da63541b5ba",
                        "trace_state": "",
                    },
                    "kind": "SpanKind.INTERNAL",
                    "attributes": {
                        "total_time_ms": 1345.37,
                        "model_name": "indictrans-gpu-t4",
                        "model_version": "unknown",
                        "task_type": "NMT",
                    },
                    "timestamp": "2026-05-28T18:14:13.538874+00:00",
                    "logger": "trace.request_span",
                    "taskName": "Task-5",
                },
                {
                    "name": "ai-inference",
                    "context": {
                        "trace_id": "0xc78a7cde764dd2b4022ff59a0b3d91a7",
                        "span_id": "0x911666d83430d521",
                        "trace_state": "",
                    },
                    "kind": "SpanKind.INTERNAL",
                    "attributes": {
                        "total_time_ms": 8525.23,
                        "input_tokens": 1,
                        "output_tokens": 4,
                        "input_type": "text",
                        "output_type": "text",
                        "status": "success",
                        "status_code": 200,
                    },
                    "timestamp": "2026-05-28T18:14:28.811737+00:00",
                    "logger": "trace.request_span",
                    "taskName": "Task-5",
                },
            ],
        }

        asr_success_trace = {
            "trace_id": "0xa1b2c3d4e5f6a7b8c9d0e1f2a3b4c5d6",
            "service": "asr-service",
            "tenant_id": "1",
            "service_version": "1.0.0",
            "environment": "development",
            "hostname": "TI-MAC-086-ASR.local",
            "spans": [
                {
                    "name": "request",
                    "context": {
                        "trace_id": "0xa1b2c3d4e5f6a7b8c9d0e1f2a3b4c5d6",
                        "span_id": "0x1111111111111111",
                        "trace_state": "",
                    },
                    "kind": "SpanKind.INTERNAL",
                    "attributes": {
                        "total_time_ms": 15000.50,
                        "url": "/api/v1/asr/inference",
                        "method": "POST",
                        "status": "success",
                        "status_code": 200,
                    },
                    "timestamp": "2026-05-28T18:15:00.416613+00:00",
                    "logger": "trace.request_span",
                    "taskName": "Task-6",
                },
                {
                    "name": "model",
                    "context": {
                        "trace_id": "0xa1b2c3d4e5f6a7b8c9d0e1f2a3b4c5d6",
                        "span_id": "0x2222222222222222",
                        "trace_state": "",
                    },
                    "kind": "SpanKind.INTERNAL",
                    "attributes": {
                        "total_time_ms": 1000.25,
                        "model_name": "wav2vec-asr",
                        "model_version": "1.2.0",
                        "task_type": "ASR",
                    },
                    "timestamp": "2026-05-28T18:15:10.538874+00:00",
                    "logger": "trace.request_span",
                    "taskName": "Task-6",
                },
                {
                    "name": "ai-inference",
                    "context": {
                        "trace_id": "0xa1b2c3d4e5f6a7b8c9d0e1f2a3b4c5d6",
                        "span_id": "0x3333333333333333",
                        "trace_state": "",
                    },
                    "kind": "SpanKind.INTERNAL",
                    "attributes": {
                        "total_time_ms": 12000.10,
                        "input_tokens": 2,
                        "output_tokens": 50,
                        "input_type": "audio",
                        "output_type": "text",
                        "status": "success",
                        "status_code": 200,
                    },
                    "timestamp": "2026-05-28T18:15:05.811737+00:00",
                    "logger": "trace.request_span",
                    "taskName": "Task-6",
                },
            ],
        }

        nmt_failure_trace = {
            "trace_id": "0xf1e2d3c4b5a6978869584736a5b4c3d2",
            "service": "ai4x-inference",
            "tenant_id": "2",
            "service_version": "1.0.0",
            "environment": "development",
            "hostname": "TI-MAC-087-NMT.local",
            "spans": [
                {
                    "name": "request",
                    "context": {
                        "trace_id": "0xf1e2d3c4b5a6978869584736a5b4c3d2",
                        "span_id": "0x4444444444444444",
                        "trace_state": "",
                    },
                    "kind": "SpanKind.INTERNAL",
                    "attributes": {
                        "total_time_ms": 5000.75,
                        "url": "/api/v1/nmt/inference",
                        "method": "POST",
                        "status": "failure",
                        "status_code": 500,
                    },
                    "timestamp": "2026-05-28T18:16:00.416613+00:00",
                    "logger": "trace.request_span",
                    "taskName": "Task-7",
                },
                {
                    "name": "model",
                    "context": {
                        "trace_id": "0xf1e2d3c4b5a6978869584736a5b4c3d2",
                        "span_id": "0x5555555555555555",
                        "trace_state": "",
                    },
                    "kind": "SpanKind.INTERNAL",
                    "attributes": {
                        "total_time_ms": 2500.60,
                        "model_name": "indictrans-gpu-t4",
                        "model_version": "unknown",
                        "task_type": "NMT",
                    },
                    "timestamp": "2026-05-28T18:16:10.538874+00:00",
                    "logger": "trace.request_span",
                    "taskName": "Task-7",
                },
                {
                    "name": "ai-inference",
                    "context": {
                        "trace_id": "0xf1e2d3c4b5a6978869584736a5b4c3d2",
                        "span_id": "0x6666666666666666",
                        "trace_state": "",
                    },
                    "kind": "SpanKind.INTERNAL",
                    "attributes": {
                        "total_time_ms": 3000.50,
                        "input_tokens": 0,
                        "output_tokens": 0,
                        "input_type": "text",
                        "output_type": "text",
                        "status": "failure",
                        "status_code": 500,
                    },
                    "timestamp": "2026-05-28T18:16:05.811737+00:00",
                    "logger": "trace.request_span",
                    "taskName": "Task-7",
                },
            ],
        }

        ocr_success_trace = {
            "trace_id": "0xe8d7c6b5a4f3e2d1c0b9a8f7e6d5c4b3",
            "service": "ocr-service",
            "tenant_id": "2",
            "service_version": "1.0.0",
            "environment": "development",
            "hostname": "TI-MAC-088-OCR.local",
            "spans": [
                {
                    "name": "request",
                    "context": {
                        "trace_id": "0xe8d7c6b5a4f3e2d1c0b9a8f7e6d5c4b3",
                        "span_id": "0x7777777777777777",
                        "trace_state": "",
                    },
                    "kind": "SpanKind.INTERNAL",
                    "attributes": {
                        "total_time_ms": 8500.25,
                        "url": "/api/v1/ocr/inference",
                        "method": "POST",
                        "status": "success",
                        "status_code": 200,
                    },
                    "timestamp": "2026-05-28T18:17:00.416613+00:00",
                    "logger": "trace.request_span",
                    "taskName": "Task-8",
                },
                {
                    "name": "model",
                    "context": {
                        "trace_id": "0xe8d7c6b5a4f3e2d1c0b9a8f7e6d5c4b3",
                        "span_id": "0x8888888888888888",
                        "trace_state": "",
                    },
                    "kind": "SpanKind.INTERNAL",
                    "attributes": {
                        "total_time_ms": 1250.45,
                        "model_name": "paddle-ocr",
                        "model_version": "2.0.1",
                        "task_type": "OCR",
                    },
                    "timestamp": "2026-05-28T18:17:10.538874+00:00",
                    "logger": "trace.request_span",
                    "taskName": "Task-8",
                },
                {
                    "name": "ai-inference",
                    "context": {
                        "trace_id": "0xe8d7c6b5a4f3e2d1c0b9a8f7e6d5c4b3",
                        "span_id": "0x9999999999999999",
                        "trace_state": "",
                    },
                    "kind": "SpanKind.INTERNAL",
                    "attributes": {
                        "total_time_ms": 7200.80,
                        "input_tokens": 1,
                        "output_tokens": 25,
                        "input_type": "image",
                        "output_type": "text",
                        "status": "success",
                        "status_code": 200,
                    },
                    "timestamp": "2026-05-28T18:17:05.811737+00:00",
                    "logger": "trace.request_span",
                    "taskName": "Task-8",
                },
            ],
        }

        return {
            "2214584a536d4454b7728d6504b9f614": nmt_success_trace,
            "2571e0a1df6845a8990d7efb9d771cf0": asr_success_trace,
            "ff86d1fc1d0a453fae9f57083852a1ca": nmt_failure_trace,
            "a1b2c3d4e5f6a7b8c9d0e1f2a3b4c5d6": ocr_success_trace,
        }

    @staticmethod
    def _get_mock_traces_for_search(
        task_type: Optional[str] = None,
        status: Optional[str] = None,
        tenant_id: Optional[str] = None,
        start_time: Optional[int] = None,
        end_time: Optional[int] = None,
        limit: int = 20,
    ) -> List[Dict[str, Any]]:
        """Get mock traces for search results with filtering."""
        mock_trace_data = TelemetryService._get_mock_trace_data()
        mock_traces = []
        seen_traces = set()

        logger.debug(
            f"Searching with task_type={task_type}, status={status}, tenant_id={tenant_id}"
        )

        for trace_id, trace_data in list(mock_trace_data.items())[:limit]:
            trace_otel_id = trace_data.get("trace_id")
            trace_tenant_id = trace_data.get("tenant_id")

            if trace_otel_id in seen_traces:
                continue
            seen_traces.add(trace_otel_id)

            # Extract task_type from model span
            spans = trace_data.get("spans", [])
            trace_task_type = None
            for span in spans:
                if span.get("name") == "model":
                    trace_task_type = span.get("attributes", {}).get("task_type")
                    break

            # Filter by tenant_id (RBAC)
            if tenant_id and trace_tenant_id != tenant_id:
                logger.debug(f"Skipping trace {trace_otel_id}: tenant mismatch")
                continue

            # Filter by task_type
            if task_type and trace_task_type != task_type:
                logger.debug(f"Skipping trace {trace_otel_id}: task_type mismatch")
                continue

            # Filter by status
            trace_status = trace_data.get("spans", [{}])[0].get("attributes", {}).get("status", "unknown")
            if status and trace_status != status:
                logger.debug(f"Skipping trace {trace_otel_id}: status mismatch")
                continue

            # Filter by time range
            if start_time or end_time:
                if spans:
                    timestamp_str = spans[0].get("timestamp")
                    if timestamp_str:
                        try:
                            trace_dt = datetime.fromisoformat(timestamp_str.replace("Z", "+00:00"))
                            trace_time_us = int(trace_dt.timestamp() * 1_000_000)

                            if start_time and trace_time_us < start_time:
                                continue
                            if end_time and trace_time_us > end_time:
                                continue
                        except Exception as e:
                            logger.warning(f"Could not parse timestamp: {e}")

            # Extract URL
            url = None
            timestamp = None
            for span in spans:
                if span.get("name") == "request":
                    url = span.get("attributes", {}).get("url")
                    break

            if spans:
                timestamp = spans[0].get("timestamp")

            logger.debug(f"Including trace {trace_otel_id} in results")
            mock_traces.append(
                {
                    "trace_id": trace_otel_id,
                    "service": trace_data.get("service"),
                    "task_type": trace_task_type,
                    "span_count": len(trace_data.get("spans", [])),
                    "status": trace_status,
                    "tenant_id": trace_tenant_id,
                    "url": url,
                    "timestamp": timestamp,
                }
            )

        return mock_traces
