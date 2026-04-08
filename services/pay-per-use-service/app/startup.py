import asyncio
import json
import logging

import httpx

from app.config import settings
from app.redis_client import get_redis

logger = logging.getLogger("pay-per-use-startup")


async def warm_pricing_cache() -> None:
    base = settings.policy_engine_url.rstrip("/")
    url = f"{base}/policies"
    for attempt in range(1, 4):
        try:
            async with httpx.AsyncClient(timeout=30.0) as client:
                r = await client.get(url)
                if r.status_code != 200:
                    logger.warning("Policy engine GET /policies failed: %s %s", r.status_code, r.text)
                    await asyncio.sleep(2 * attempt)
                    continue
                plans = r.json()
                rds = await get_redis()
                for plan in plans:
                    tier = plan.get("tier") or ""
                    pid = plan.get("id")
                    svcs: list = []
                    if pid:
                        pr = await client.get(f"{base}/policies/{pid}/services")
                        if pr.status_code == 200:
                            svcs = pr.json()
                    for svc in svcs:
                        sid = str(svc.get("service_id") or "")
                        if not sid:
                            continue
                        cpu = float(svc.get("cost_per_unit") or 0)
                        await rds.set(f"pricing:{sid}:{tier}", str(cpu))
            logger.info("Warmed pricing cache for %d plans", len(plans))
            return
        except Exception as e:
            logger.warning("warm_pricing_cache attempt %s failed: %s", attempt, e)
            await asyncio.sleep(2 * attempt)
