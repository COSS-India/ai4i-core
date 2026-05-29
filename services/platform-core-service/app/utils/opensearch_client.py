"""OpenSearch client for querying traces."""

import logging
import json
from typing import Optional, Dict, Any, List
from opensearchpy import OpenSearch
from collections import defaultdict

logger = logging.getLogger(__name__)


class OpenSearchTraceClient:
    """Client for querying traces from OpenSearch."""

    def __init__(
        self,
        url: str = "http://localhost:9203",
        username: str = "admin",
        password: str = "admin",
        index: str = "traces",
        verify_certs: bool = False,
    ):
        """
        Initialize OpenSearch client.

        Args:
            url: OpenSearch URL (e.g., http://localhost:9203)
            username: OpenSearch username
            password: OpenSearch password
            index: Index name for traces
            verify_certs: Whether to verify SSL certificates
        """
        self.url = url
        self.username = username
        self.password = password
        self.index = index
        self.verify_certs = verify_certs
        self.client: Optional[OpenSearch] = None

    def connect(self):
        """Connect to OpenSearch."""
        try:
            # Parse URL to extract host and port
            from urllib.parse import urlparse
            parsed = urlparse(self.url)
            host = parsed.hostname or "localhost"
            port = parsed.port or (443 if parsed.scheme == "https" else 9200)

            self.client = OpenSearch(
                hosts=[{"host": host, "port": port}],
                http_auth=(self.username, self.password),
                use_ssl=parsed.scheme == "https",
                verify_certs=self.verify_certs,
                ssl_show_warn=False,
            )
            logger.info(f"Connected to OpenSearch at {host}:{port}")
            return True
        except Exception as e:
            logger.error(f"Failed to connect to OpenSearch: {e}")
            return False

    def _parse_span_from_document(self, doc: Dict[str, Any]) -> Optional[Dict[str, Any]]:
        """Parse a span from an OpenSearch document (message field contains nested JSON)."""
        try:
            source = doc.get("_source", {})
            message_str = source.get("message", "{}")

            # Parse the nested JSON message
            message_data = json.loads(message_str)

            # Extract span info from nested message
            nested_message = message_data.get("message", "{}")
            if isinstance(nested_message, str):
                nested_message = json.loads(nested_message)

            # Extract trace_id from the context inside the nested message (hex format)
            context = nested_message.get("context", {})
            trace_id = context.get("trace_id")
            if not trace_id:
                return None

            # Extract timestamp from message_data (root level of JSON in message field)
            timestamp = message_data.get("timestamp")

            span = {
                "name": nested_message.get("name"),
                "context": context,
                "kind": nested_message.get("kind"),
                "attributes": nested_message.get("attributes", {}),
                "timestamp": timestamp,
                "logger": message_data.get("logger"),
            }

            return {
                "trace_id": trace_id,
                "service": message_data.get("service"),
                "tenant_id": message_data.get("tenant_id"),
                "span": span,
                "timestamp": timestamp,
            }
        except (json.JSONDecodeError, KeyError, TypeError) as e:
            logger.debug(f"Error parsing span from document: {e}")
            return None

    def aggregate_spans_into_traces(
        self,
        response: Dict[str, Any]
    ) -> Dict[str, List[Dict[str, Any]]]:
        """
        Aggregate individual spans into complete traces.

        Args:
            response: Raw OpenSearch response with individual spans

        Returns:
            Dict mapping trace_id to list of spans with tenant_id metadata
        """
        traces = defaultdict(lambda: {"spans": [], "tenant_id": None, "service": None})

        hits = response.get("hits", {}).get("hits", [])
        for doc in hits:
            parsed = self._parse_span_from_document(doc)
            if parsed:
                trace_id = parsed["trace_id"]
                traces[trace_id]["spans"].append(parsed["span"])
                # Store tenant_id and service from first document (consistent across trace)
                if traces[trace_id]["tenant_id"] is None:
                    traces[trace_id]["tenant_id"] = parsed.get("tenant_id")
                if traces[trace_id]["service"] is None:
                    traces[trace_id]["service"] = parsed.get("service")

        return dict(traces)

    def search_traces(
        self,
        query: Optional[Dict[str, Any]] = None,
        size: int = 100,  # Increased to get more spans per trace
        from_: int = 0,
    ) -> Dict[str, Any]:
        """
        Search traces in OpenSearch.

        Now returns aggregated traces (spans grouped by trace_id).

        Args:
            query: Elasticsearch/OpenSearch query (if None, returns all)
            size: Number of results (spans, not traces)
            from_: Offset for pagination

        Returns:
            Dict with aggregated traces
        """
        if not self.client:
            logger.warning("OpenSearch client not connected")
            return {"traces": {}, "total": 0}

        try:
            if query is None:
                query = {"match_all": {}}

            body = {"query": query, "size": size, "from": from_}

            logger.debug(f"Executing OpenSearch query: {body}")
            response = self.client.search(index=self.index, body=body)

            # Aggregate spans into complete traces
            traces = self.aggregate_spans_into_traces(response)

            return {
                "traces": traces,
                "total_spans": response.get("hits", {}).get("total", {}).get("value", 0),
                "total_traces": len(traces)
            }

        except Exception as e:
            logger.error(f"Error searching OpenSearch: {e}")
            return {"traces": {}, "total_spans": 0, "total_traces": 0}

    def get_trace_by_id(self, trace_id: str) -> Optional[Dict[str, Any]]:
        """
        Get a specific trace by trace_id.

        Args:
            trace_id: The trace ID to retrieve

        Returns:
            Trace document or None
        """
        if not self.client:
            logger.warning("OpenSearch client not connected")
            return None

        try:
            query = {"query": {"match": {"trace_id": trace_id}}}
            response = self.client.search(index=self.index, body=query)
            hits = response.get("hits", {}).get("hits", [])
            if hits:
                return hits[0].get("_source")
            return None
        except Exception as e:
            logger.error(f"Error getting trace {trace_id}: {e}")
            return None

    def search_by_task_type(
        self,
        task_type: str,
        size: int = 20,
        from_: int = 0,
    ) -> Dict[str, Any]:
        """
        Search traces by task type.

        Args:
            task_type: Task type to filter (NMT, ASR, OCR, etc.)
            size: Number of results
            from_: Offset for pagination

        Returns:
            OpenSearch response
        """
        query = {"match": {"message": task_type}}
        return self.search_traces(query=query, size=size, from_=from_)

    def search_by_status(
        self,
        status: str,
        size: int = 20,
        from_: int = 0,
    ) -> Dict[str, Any]:
        """
        Search traces by status.

        Args:
            status: Status to filter (success, failure)
            size: Number of results
            from_: Offset for pagination

        Returns:
            OpenSearch response
        """
        query = {"match": {"message": status}}
        return self.search_traces(query=query, size=size, from_=from_)

    def search_by_tenant(
        self,
        tenant_id: str,
        size: int = 20,
        from_: int = 0,
    ) -> Dict[str, Any]:
        """
        Search traces by tenant_id.

        Args:
            tenant_id: Tenant ID to filter
            size: Number of results
            from_: Offset for pagination

        Returns:
            OpenSearch response
        """
        query = {"match": {"message": tenant_id}}
        return self.search_traces(query=query, size=size, from_=from_)

    def search_by_date_range(
        self,
        start_date: Optional[str] = None,
        end_date: Optional[str] = None,
        size: int = 20,
        from_: int = 0,
    ) -> Dict[str, Any]:
        """
        Search traces by date range (searches timestamp field in message JSON).

        Args:
            start_date: Start date (ISO format)
            end_date: End date (ISO format)
            size: Number of results
            from_: Offset for pagination

        Returns:
            OpenSearch response
        """
        range_query = {}
        if start_date:
            range_query["gte"] = start_date
        if end_date:
            range_query["lte"] = end_date

        # @timestamp is at root level in the message field
        query = {"range": {"@timestamp": range_query}} if range_query else {"match_all": {}}
        return self.search_traces(query=query, size=size, from_=from_)

    def build_complex_query(
        self,
        task_type: Optional[str] = None,
        status: Optional[str] = None,
        tenant_id: Optional[str] = None,
        start_date: Optional[str] = None,
        end_date: Optional[str] = None,
    ) -> Dict[str, Any]:
        """
        Build a complex query with multiple filters.

        Args:
            task_type: Task type filter (searched in message JSON)
            status: Status filter (searched in message JSON)
            tenant_id: Tenant ID filter (searched in message JSON)
            start_date: Start date filter (searched in message JSON)
            end_date: End date filter (searched in message JSON)

        Returns:
            Query dict for OpenSearch
        """
        must_clauses = []

        # Note: tenant_id, task_type, and status are nested inside the message JSON field
        # Use match query to search for exact field:value patterns in the message text

        if tenant_id:
            # Search for exact tenant_id pattern: "tenant_id": "value"
            must_clauses.append({"match": {"message": tenant_id}})
            logger.info(f"Adding tenant_id filter: {tenant_id}")

        if task_type:
            # Search for exact task_type pattern
            must_clauses.append({"match": {"message": task_type}})

        if status:
            # Search for exact status pattern
            must_clauses.append({"match": {"message": status}})

        if start_date or end_date:
            range_query = {}
            if start_date:
                range_query["gte"] = start_date
            if end_date:
                range_query["lte"] = end_date
            must_clauses.append({"range": {"@timestamp": range_query}})

        if not must_clauses:
            return {"match_all": {}}

        query = {"bool": {"must": must_clauses}}
        logger.info(f"Built OpenSearch query: {query}")
        return query
