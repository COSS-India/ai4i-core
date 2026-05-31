"""OpenSearch client for querying traces."""

import logging
from typing import Optional, Dict, Any
from opensearchpy import OpenSearch

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

    def search_traces(
        self,
        query: Optional[Dict[str, Any]] = None,
        size: int = 100,
        from_: int = 0,
        source_fields: Optional[list] = None,
        sort: Optional[list] = None,
        collapse: Optional[Dict[str, Any]] = None,
        aggs: Optional[Dict[str, Any]] = None,
    ) -> Dict[str, Any]:
        """
        Search traces in OpenSearch.

        Args:
            query: OpenSearch query
            size: Number of results
            from_: Offset for pagination
            source_fields: Fields to include in response
            sort: OpenSearch sort clause; defaults to newest-first by @timestamp
            collapse: OpenSearch field-collapsing clause (e.g. group by trace_id)
            aggs: OpenSearch aggregations clause

        Returns:
            Raw OpenSearch response
        """
        if not self.client:
            logger.warning("OpenSearch client not connected")
            return {"hits": {"hits": [], "total": {"value": 0}}}

        try:
            if query is None:
                query = {"match_all": {}}

            body = {
                "query": query,
                "size": size,
                "from": from_,
                "sort": sort or [{"@timestamp": {"order": "desc"}}],
            }
            if source_fields:
                body["_source"] = source_fields
            if collapse:
                body["collapse"] = collapse
            if aggs:
                body["aggs"] = aggs

            logger.debug(f"Executing OpenSearch query: {body}")
            response = self.client.search(index=self.index, body=body)
            return response

        except Exception as e:
            logger.error(f"Error searching OpenSearch: {e}")
            return {"hits": {"hits": [], "total": {"value": 0}}}

    def get_trace_by_id(self, trace_id: str, source_fields: Optional[list] = None) -> Dict[str, Any]:
        """
        Get all spans for a specific trace by trace_id.

        Args:
            trace_id: The trace ID to retrieve (hex format)
            source_fields: Fields to include in response

        Returns:
            OpenSearch response with matching spans
        """
        if not self.client:
            logger.warning("OpenSearch client not connected")
            return {"hits": {"hits": []}}

        try:
            query = {
                "match_phrase": {
                    "context.trace_id": trace_id
                }
            }

            logger.debug(f"Querying for trace_id={trace_id}")
            response = self.search_traces(
                query=query,
                size=100,
                source_fields=source_fields
            )

            hits = response.get("hits", {}).get("hits", [])
            logger.info(f"Found {len(hits)} spans for trace {trace_id}")

            return response
        except Exception as e:
            logger.error(f"Error getting trace {trace_id}: {e}")
            return {"hits": {"hits": []}}
