"""
Benchmark all metering endpoints concurrently with time_range=30d.

Usage:
    python tests/benchmark_metering_30d.py [BASE_URL] [TOKEN]

    BASE_URL  defaults to http://localhost:8095
    TOKEN     optional Bearer token

All 12 endpoints are fired at the same time using asyncio + httpx.
Results are printed as a table sorted by response time.
"""
import asyncio
import sys
import time
from typing import Any

import httpx

BASE_URL = (sys.argv[1] if len(sys.argv) > 1 else "http://localhost:8095").rstrip("/")
TOKEN    = sys.argv[2] if len(sys.argv) > 2 else None

HEADERS: dict[str, str] = {"Content-Type": "application/json"}
if TOKEN:
    HEADERS["Authorization"] = f"Bearer {TOKEN}"

# Each tuple: (label, path_suffix, request_body)
ENDPOINTS: list[tuple[str, str, dict[str, Any]]] = [
    (
        "requesttotal",
        "/api/v1/metering/requesttotal",
        {"time_range": "30d", "inference_only": True},
    ),
    (
        "active-tenants",
        "/api/v1/metering/active-tenants",
        {"time_range": "30d"},
    ),
    (
        "avg-requests-per-tenant",
        "/api/v1/metering/avg-requests-per-tenant",
        {"time_range": "30d"},
    ),
    (
        "top-inference-services",
        "/api/v1/metering/top-inference-services",
        {"time_range": "30d", "limit": 10},
    ),
    (
        "usage-concentration",
        "/api/v1/metering/usage-concentration",
        {"time_range": "30d", "limit": 5},
    ),
    (
        "request-volume-health",
        "/api/v1/metering/request-volume-health",
        {"time_range": "30d", "inference_only": True},
    ),
    (
        "service-breakdown",
        "/api/v1/metering/service-breakdown",
        {"time_range": "30d"},
    ),
    (
        "tenant-ranking",
        "/api/v1/metering/tenant-ranking",
        {"time_range": "30d", "limit": 10},
    ),
    (
        "throughput",
        "/api/v1/metering/throughput",
        {"time_range": "30d", "inference_only": True},
    ),
    (
        "top-tenants-throughput",
        "/api/v1/metering/top-tenants-throughput",
        {"time_range": "30d", "limit": 10, "inference_only": True},
    ),
    (
        "tenant-count",
        "/api/v1/metering/tenant-count",
        {"time_range": "30d"},
    ),
    (
        "usage-by-tenant-service",
        "/api/v1/metering/usage-by-tenant-service",
        {"time_range": "30d", "limit": 10},
    ),
]


async def call(
    client: httpx.AsyncClient,
    label: str,
    url: str,
    body: dict[str, Any],
) -> dict[str, Any]:
    t0 = time.perf_counter()
    try:
        resp = await client.post(url, json=body, headers=HEADERS, timeout=120)
        elapsed = time.perf_counter() - t0
        return {
            "endpoint": label,
            "status":   resp.status_code,
            "elapsed":  elapsed,
            "ok":       resp.is_success,
            "error":    None if resp.is_success else resp.text[:200],
        }
    except Exception as exc:
        elapsed = time.perf_counter() - t0
        return {
            "endpoint": label,
            "status":   None,
            "elapsed":  elapsed,
            "ok":       False,
            "error":    str(exc)[:200],
        }


async def main() -> None:
    print(f"\nTarget : {BASE_URL}")
    print(f"Auth   : {'Bearer ***' if TOKEN else 'none'}")
    print(f"Firing {len(ENDPOINTS)} endpoints simultaneously with time_range=30d …\n")

    wall_start = time.perf_counter()

    async with httpx.AsyncClient() as client:
        tasks = [
            call(client, label, BASE_URL + path, body)
            for label, path, body in ENDPOINTS
        ]
        # all launched at the same time
        results = await asyncio.gather(*tasks)

    wall_elapsed = time.perf_counter() - wall_start

    # sort by elapsed time
    results.sort(key=lambda r: r["elapsed"])

    col_w = max(len(r["endpoint"]) for r in results) + 2
    header = f"{'ENDPOINT':<{col_w}}  {'STATUS':>6}  {'TIME (s)':>9}  RESULT"
    print(header)
    print("-" * len(header))

    for r in results:
        status_str = str(r["status"]) if r["status"] else "ERR"
        result_str = "OK" if r["ok"] else f"FAIL — {r['error']}"
        print(f"{r['endpoint']:<{col_w}}  {status_str:>6}  {r['elapsed']:>9.3f}  {result_str}")

    print("-" * len(header))
    slowest  = max(r["elapsed"] for r in results)
    fastest  = min(r["elapsed"] for r in results)
    failures = sum(1 for r in results if not r["ok"])

    print(f"\nWall-clock (all concurrent) : {wall_elapsed:.3f} s")
    print(f"Fastest endpoint            : {fastest:.3f} s")
    print(f"Slowest endpoint            : {slowest:.3f} s")
    print(f"Failed                      : {failures}/{len(results)}\n")


if __name__ == "__main__":
    asyncio.run(main())
