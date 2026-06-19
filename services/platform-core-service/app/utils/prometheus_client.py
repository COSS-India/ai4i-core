"""Prometheus HTTP API client."""
import logging

import httpx
from fastapi import HTTPException, status

logger = logging.getLogger(__name__)


class PrometheusClient:
    def __init__(self, prometheus_url: str, client: httpx.AsyncClient, timeout: float = 10.0):
        self.base_url = prometheus_url.rstrip("/")
        self._client = client
        self.timeout = timeout

    async def query(self, promql: str) -> list:
        """Execute an instant PromQL query and return the raw result vector."""
        url = f"{self.base_url}/api/v1/query"
        try:
            resp = await self._client.get(url, params={"query": promql}, timeout=self.timeout)
            resp.raise_for_status()
            data = resp.json()
        except httpx.HTTPStatusError as exc:
            logger.error("Prometheus returned %s for query: %s", exc.response.status_code, promql)
            raise HTTPException(
                status_code=status.HTTP_502_BAD_GATEWAY,
                detail=f"Prometheus returned HTTP {exc.response.status_code}.",
            )
        except httpx.RequestError as exc:
            logger.error("Cannot reach Prometheus: %s", exc)
            raise HTTPException(
                status_code=status.HTTP_502_BAD_GATEWAY,
                detail="Cannot reach Prometheus.",
            )
        return data.get("data", {}).get("result", [])

    async def scalar(self, promql: str) -> float:
        """Execute a PromQL query that returns a single number (e.g. sum(...))."""
        result = await self.query(promql)
        if not result:
            return 0.0
        return self._safe_float(result[0]["value"][1])

    async def query_range(
        self,
        promql: str,
        start: float,
        end: float,
        step: str,
    ) -> list:
        """Execute a range PromQL query and return the raw result matrix.

        Each element: {"metric": {...}, "values": [[ts, "val"], ...]}
        """
        url = f"{self.base_url}/api/v1/query_range"
        try:
            resp = await self._client.get(
                url,
                params={"query": promql, "start": start, "end": end, "step": step},
                timeout=self.timeout,
            )
            resp.raise_for_status()
            data = resp.json()
        except httpx.HTTPStatusError as exc:
            logger.error("Prometheus returned %s for range query: %s", exc.response.status_code, promql)
            raise HTTPException(
                status_code=status.HTTP_502_BAD_GATEWAY,
                detail=f"Prometheus returned HTTP {exc.response.status_code}.",
            )
        except httpx.RequestError as exc:
            logger.error("Cannot reach Prometheus: %s", exc)
            raise HTTPException(
                status_code=status.HTTP_502_BAD_GATEWAY,
                detail="Cannot reach Prometheus.",
            )
        return data.get("data", {}).get("result", [])

    @staticmethod
    def _safe_float(value: str, default: float = 0.0) -> float:
        """Parse a Prometheus value string, coercing NaN/Inf to default."""
        try:
            v = float(value)
            if v != v or v == float("inf") or v == float("-inf"):
                return default
            return v
        except (TypeError, ValueError):
            return default
