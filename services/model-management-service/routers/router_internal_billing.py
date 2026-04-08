"""Internal billing fields by registered service id (no auth — use only on trusted network)."""

from fastapi import APIRouter, HTTPException

from db_operations import get_service_details
from logger import logger

router = APIRouter(tags=["internal-billing"])


def _task_type_from_service_payload(data: dict) -> str:
    model = data.get("model")
    if not isinstance(model, dict):
        return ""
    task = model.get("task")
    if isinstance(task, dict):
        t = task.get("type") or task.get("taskType")
        if t is not None:
            return str(t).strip().upper()
    if isinstance(task, str) and task.strip():
        return task.strip().upper()
    return ""


@router.get("/internal/service-billing/{service_id:path}")
async def internal_service_billing(service_id: str):
    """
    Return cost_per_unit / tier / unit_type / display name for pay-per-use and dashboards.
    Looks up by services.service_id (SMR hash) or UUID primary key.
    """
    try:
        data = await get_service_details(service_id)
    except HTTPException as e:
        if e.status_code == 404:
            raise HTTPException(status_code=404, detail="Service not found") from e
        raise
    except Exception:
        logger.exception("internal_service_billing failed for service_id=%s", service_id)
        raise HTTPException(status_code=500, detail="billing lookup failed") from None

    cpu = data.get("cost_per_unit")
    return {
        "service_id": data.get("serviceId") or service_id,
        "name": data.get("name") or "",
        "task_type": _task_type_from_service_payload(data),
        "cost_per_unit": float(cpu) if cpu is not None else 0.0,
        "unit_type": data.get("unit_type") or "",
        "tier": data.get("tier") or "",
    }
