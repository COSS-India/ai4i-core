"""OpenSearch client for the request-completion log line (RequestMiddleware),
backing the OpenSearch-sourced metering request-count KPIs.

Distinct from OpenSearchTraceClient (app/utils/opensearch_client.py), which
queries the ``traces-*`` OTel span index for the Logs Dashboard trace-search
feature. This one queries ``logs-*`` — RequestMiddleware's one-line-per-request
structured log — for exact (non-extrapolated) request counts, replacing
PrometheusClient's ``increase()``/``rate()`` estimates for that purpose. Same
opensearch-py connection plumbing as OpenSearchTraceClient, different index
and query shapes (aggregation-only, no document search).

Query methods are generic ES-DSL execution primitives (filters agg,
date_histogram, terms, composite) — the metering-specific filter/field
knowledge lives in the caller (OpenSearchMeteringService), not here.
"""

import asyncio
import logging
from typing import Any, Optional
from urllib.parse import urlparse

from opensearchpy import OpenSearch

logger = logging.getLogger(__name__)

STATUS_SUCCESS_RANGE: dict = {"gte": 200, "lt": 300}
STATUS_FAILED_RANGE: dict = {"gte": 400}

# Composite aggregation page size — same 10,000-per-request ceiling
# _collect_all_trace_ids (app/routes/telemetry.py) already works around for
# the traces-* index.
_COMPOSITE_PAGE_SIZE = 1000
# Safety cap on composite pages fetched for one call, mirroring
# _MAX_BREAKDOWN_TRACE_IDS's role in app/routes/telemetry.py: bounds how many
# OpenSearch round trips one aggregation can cause. At 1000/page this allows
# up to 200k distinct (tenant_id, path) or (service_id, model_id, path)
# combinations — comfortably above any realistic cardinality (doc §11).
_COMPOSITE_MAX_PAGES = 200


class OpenSearchLogClient:
    """Sync opensearch-py client wrapped for async callers via
    ``asyncio.to_thread`` — same pattern app/routes/telemetry.py already uses
    for OpenSearchTraceClient (opensearch-py has no native asyncio client in
    the version this repo pins)."""

    def __init__(
        self,
        url: str,
        username: str,
        password: str,
        index: str = "logs-*",
        verify_certs: bool = False,
    ) -> None:
        self.index = index
        parsed = urlparse(url)
        host = parsed.hostname or "localhost"
        port = parsed.port or (443 if parsed.scheme == "https" else 9200)
        self._client = OpenSearch(
            hosts=[{"host": host, "port": port}],
            http_auth=(username, password),
            use_ssl=parsed.scheme == "https",
            verify_certs=verify_certs,
            ssl_show_warn=False,
        )

    # ── low-level ────────────────────────────────────────────────────────

    def _search(self, body: dict) -> dict:
        try:
            return self._client.search(index=self.index, body=body)
        except Exception:
            logger.warning("OpenSearchLogClient search failed", exc_info=True)
            return {}

    async def _asearch(self, body: dict) -> dict:
        return await asyncio.to_thread(self._search, body)

    # ── aggregation primitives ──────────────────────────────────────────

    async def count(self, query: dict) -> int:
        """Exact document count matching ``query`` — ``track_total_hits``
        bypasses OpenSearch's default 10,000-hit cap on ``hits.total`` (doc
        §11)."""
        body = {"size": 0, "track_total_hits": True, "query": query}
        response = await self._asearch(body)
        return int(response.get("hits", {}).get("total", {}).get("value", 0))

    async def aggregate(self, query: dict, aggs: dict) -> dict:
        """Run a ``size: 0`` aggregation-only search. Returns
        ``response["aggregations"]``, or ``{}`` on any failure (connection
        error, malformed query, cluster down) — callers treat that the same
        as "no data", matching PrometheusClient's own fail-soft contract for
        this codebase's dashboard queries."""
        body = {"size": 0, "query": query, "aggs": aggs}
        response = await self._asearch(body)
        return response.get("aggregations", {})

    async def composite_all(
        self,
        query: dict,
        sources: list[dict],
        sub_aggs: Optional[dict] = None,
        page_size: int = _COMPOSITE_PAGE_SIZE,
        max_pages: int = _COMPOSITE_MAX_PAGES,
    ) -> list[dict]:
        """Collect every bucket of a composite aggregation, paginating via
        ``after_key`` — mirrors ``_collect_all_trace_ids``
        (app/routes/telemetry.py), the same pattern already proven against
        the traces-* index, applied here to logs-*.

        Each returned bucket is the raw OpenSearch bucket dict: ``{"key":
        {...}, "doc_count": N, <sub_agg_name>: {...}}``. Stops when a page
        comes back with no ``after_key`` (all buckets collected) or
        ``max_pages`` is reached (a cardinality safety valve, not expected
        to trigger at this dashboard's realistic scale — doc §11).
        """
        buckets: list[dict] = []
        after_key: Optional[dict] = None

        for _ in range(max_pages):
            composite: dict[str, Any] = {"size": page_size, "sources": sources}
            if after_key:
                composite["after"] = after_key

            aggs: dict = {"buckets": {"composite": composite}}
            if sub_aggs:
                aggs["buckets"]["aggs"] = sub_aggs

            aggregations = await self.aggregate(query, aggs)
            page = aggregations.get("buckets", {})
            page_buckets = page.get("buckets", [])
            if not page_buckets:
                break

            buckets.extend(page_buckets)
            after_key = page.get("after_key")
            if not after_key:
                break

        return buckets
