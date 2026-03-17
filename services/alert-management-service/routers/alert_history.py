"""
Router for alert history (read-only audit log of triggered alerts).
"""
from fastapi import APIRouter, Depends, Query, HTTPException
from typing import Optional, List, Any

from alert_management import record_alert_history_from_webhook, list_alert_history
from utils.auth_deps import require_alerts_read
from fastapi.security import HTTPBearer, HTTPAuthorizationCredentials
from ai4icore_logging import get_logger

logger = get_logger(__name__)

router = APIRouter(
    prefix="/alerts/history",
    tags=["Alerts", "Alert History"],
)

bearer_scheme = HTTPBearer(auto_error=False)


@router.post("/webhook")
async def alert_history_webhook(payload: dict):
    """
    Receive Alertmanager webhook (v4 payload). Inserts one row per alert into alert_history.
    No auth - called by Alertmanager. Ensure this URL is only reachable from your Alertmanager instance.
    """
    try:
        alerts = (payload or {}).get("alerts") or (payload or {}).get("Alerts") or []
        logger.info(
            "Alert history webhook received",
            extra={"context": {"receiver": (payload or {}).get("receiver"), "status": (payload or {}).get("status"), "alert_count": len(alerts), "payload_keys": list((payload or {}).keys())}}
        )
        count = await record_alert_history_from_webhook(payload)
        logger.info("Alert history webhook recorded", extra={"context": {"recorded": count}})
        return {"status": "ok", "recorded": count}
    except Exception as e:
        logger.exception("Alert history webhook failed: %s", e, extra={"context": {"error": str(e)}})
        raise HTTPException(status_code=500, detail={"status": "error", "message": str(e)})


@router.get("")
async def list_alert_history_endpoint(
    category: Optional[str] = Query(None, description="Filter by category: application, infrastructure"),
    severity: Optional[str] = Query(None, description="Filter by severity: critical, warning, info"),
    date_from: Optional[str] = Query(None, description="Filter triggered_at >= (ISO 8601 or YYYY-MM-DD)"),
    date_to: Optional[str] = Query(None, description="Filter triggered_at <= (ISO 8601 or YYYY-MM-DD)"),
    search: Optional[str] = Query(None, description="Search in alert name and notified audience"),
    limit: int = Query(50, ge=1, le=200),
    offset: int = Query(0, ge=0),
    _: None = Depends(require_alerts_read),
):
    """
    List alert history (chronological audit log of triggered alerts).
    Supports filters: category, severity, date range, search. Paginated.
    """
    items, total = await list_alert_history(
        category=category,
        severity=severity,
        date_from=date_from,
        date_to=date_to,
        search=search,
        limit=limit,
        offset=offset,
    )
    return {"items": items, "total": total, "limit": limit, "offset": offset}
