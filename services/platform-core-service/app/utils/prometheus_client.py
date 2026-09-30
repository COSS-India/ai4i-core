"""Prometheus HTTP API client."""
import logging
import time as _time
from typing import Optional

import httpx
from fastapi import HTTPException, status

logger = logging.getLogger(__name__)


class PrometheusClient:
    def __init__(self, prometheus_url: str, client: httpx.AsyncClient, timeout: float = 10.0):
        self.base_url = prometheus_url.rstrip("/")
        self._client = client
        self.timeout = timeout

    async def query(self, promql: str, time: Optional[float] = None) -> list:
        """Execute an instant PromQL query and return the raw result vector.

        ``time`` (epoch seconds) evaluates it at that instant instead of now,
        via the API's standard ``time`` parameter."""
        url = f"{self.base_url}/api/v1/query"
        params: dict = {"query": promql}
        if time is not None:
            params["time"] = time
        try:
            resp = await self._client.get(url, params=params, timeout=self.timeout)
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

    async def storage_retention(self) -> Optional[str]:
        """Prometheus's own configured retention, as reported by
        ``/api/v1/status/runtimeinfo`` (``storageRetention``, e.g. "90d" or
        "30d or 512MiB"). None when it can't be read: an HTTP or connection
        error, a proxy that doesn't serve this endpoint (Thanos, Mimir), or a
        response without the field.

        Unlike query()/query_range(), this never raises: callers fall back to
        PROMETHEUS_RETENTION_DAYS (see metering_promql_builder.retention_days).
        """
        url = f"{self.base_url}/api/v1/status/runtimeinfo"
        try:
            resp = await self._client.get(url, timeout=self.timeout)
            resp.raise_for_status()
            value = resp.json().get("data", {}).get("storageRetention")
        except Exception as exc:
            logger.warning("Could not read Prometheus runtimeinfo: %s", type(exc).__name__)
            return None
        return value if isinstance(value, str) and value.strip() else None

    async def lowest_sample_timestamp(self) -> Optional[float]:
        """Epoch seconds of the oldest sample Prometheus actually holds, from
        its self-scraped ``prometheus_tsdb_lowest_timestamp_seconds`` (the
        ``job_name: "prometheus"`` target). ``storageRetention`` is only the
        configured maximum; after a fresh start or a redeploy without its
        volume the data is shallower than that.

        ``max()`` across series, so with several Prometheus instances the
        youngest data wins, which is the safe side. None when the metric
        isn't scraped, the query fails, or the value is not a past instant
        (an empty TSDB reports a far-future sentinel). Never raises.
        """
        try:
            result = await self.query("max(prometheus_tsdb_lowest_timestamp_seconds)")
        except Exception as exc:
            logger.warning("Could not read prometheus_tsdb_lowest_timestamp_seconds: %s", type(exc).__name__)
            return None
        if not result:
            return None
        ts = self._safe_float(result[0].get("value", [None, None])[1], default=0.0)
        if ts <= 0 or ts > _time.time():
            return None
        return ts

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
