from sqlalchemy import text
from app.database import AsyncSessionLocal
from app.models import LatencyPolicy, CostPolicy, AccuracyPolicy
import logging

logger = logging.getLogger("policy-repo")

async def get_tenant_policy(tenant_id: str):
    """
    Fetches the 3D Policy Configuration for a given Tenant.
    Returns: dict with policy enums or None if not found.
    """
    async with AsyncSessionLocal() as session:
        try:
            # Simple raw SQL for speed
            result = await session.execute(
                text("SELECT latency_policy, cost_policy, accuracy_policy FROM smr_tenant_policies WHERE tenant_id = :tid"),
                {"tid": tenant_id}
            )
            row = result.fetchone()
            
            if row:
                return {
                    "latency": LatencyPolicy(row[0]),
                    "cost": CostPolicy(row[1]),
                    "accuracy": AccuracyPolicy(row[2])
                }
            return None
        except Exception as e:
            logger.error(f"DB Lookup Failed for {tenant_id}: {e}")
            return None # Return None triggers default fallback in logic
