"""Alert-history domain service.

Two responsibilities:
  - Record an Alertmanager v4 webhook payload (one ``alert_history`` row per alert).
  - List the audit log with filters + pagination.

Rewritten from alert-management-service/alert_management.py:2782-end.
``organization`` column dropped; webhook auth is enforced at the gateway.
"""

from __future__ import annotations

from datetime import datetime, timezone
from typing import Any, Dict, List, Optional, Tuple

from app.models.alert_management.alert_history import AlertHistory
from app.repositories.alert_management.alert_history_repository import AlertHistoryRepository
from app.schemas.alert_management.history import AlertHistoryItem


class AlertHistoryService:
    """Business logic for the triggered-alert audit log."""

    def __init__(self, repo: AlertHistoryRepository) -> None:
        self._repo = repo

    # ── Webhook ingest ──

    async def record_from_webhook(self, payload: Dict[str, Any]) -> int:
        """Parse an Alertmanager v4 webhook and append one row per alert.

        Returns the number of rows inserted. Tolerant of both ``alerts``/``Alerts``
        casings and missing timestamps.
        """
        alerts = (payload or {}).get("alerts") or (payload or {}).get("Alerts") or []
        if not isinstance(alerts, list) or not alerts:
            return 0
        receiver = (payload or {}).get("receiver") or "unknown"
        status = ((payload or {}).get("status") or "firing").lower()

        entries: List[AlertHistory] = []
        for alert in alerts:
            if not isinstance(alert, dict):
                continue
            labels = alert.get("labels") or alert.get("Labels") or {}
            annotations = alert.get("annotations") or alert.get("Annotations") or {}

            triggered_at_raw = alert.get("startsAt") or alert.get("StartsAt")
            if not triggered_at_raw:
                continue
            triggered_at = self._parse_ts(triggered_at_raw) or datetime.now(timezone.utc)

            resolved_at = None
            ends_at_raw = alert.get("endsAt") or alert.get("EndsAt")
            if ends_at_raw and str(ends_at_raw) != "0001-01-01T00:00:00Z":
                resolved_at = self._parse_ts(ends_at_raw)

            category = (labels.get("category") or "application").lower()
            if category not in ("application", "infrastructure"):
                category = "application"
            severity = (labels.get("severity") or "warning").lower()
            if severity not in ("critical", "warning", "info"):
                severity = "warning"
            tenant = labels.get("tenant")

            entries.append(
                AlertHistory(
                    alert_name=labels.get("alertname") or "Unknown",
                    category=category,
                    severity=severity,
                    triggered_at=triggered_at,
                    resolved_at=resolved_at,
                    status=status,
                    receiver=receiver,
                    notified_display=self._notified_display(tenant),
                    tenant=tenant,
                    labels=dict(labels),
                    annotations=dict(annotations),
                    fingerprint=alert.get("fingerprint"),
                )
            )

        inserted = await self._repo.bulk_add(entries)
        await self._repo.commit()
        return inserted

    # ── Read ──

    async def list(
        self,
        *,
        category: Optional[str] = None,
        severity: Optional[str] = None,
        date_from: Optional[str] = None,
        date_to: Optional[str] = None,
        search: Optional[str] = None,
        limit: int = 50,
        offset: int = 0,
    ) -> Tuple[List[AlertHistoryItem], int]:
        items, total = await self._repo.list(
            category=category,
            severity=severity,
            date_from=self._parse_ts(date_from) if date_from else None,
            date_to=self._parse_ts(date_to) if date_to else None,
            search=search,
            limit=limit,
            offset=offset,
        )
        return [self._to_item(e) for e in items], total

    # ── Helpers ──

    @staticmethod
    def _parse_ts(value: Any) -> Optional[datetime]:
        if not value:
            return None
        try:
            return datetime.fromisoformat(str(value).replace("Z", "+00:00"))
        except Exception:
            return None

    @staticmethod
    def _notified_display(tenant: Optional[str]) -> str:
        if not tenant or str(tenant).strip().lower() == "unknown":
            return "Admin"
        return f"Tenant Admin - {str(tenant).strip()}"

    @staticmethod
    def _to_item(entry: AlertHistory) -> AlertHistoryItem:
        return AlertHistoryItem(
            id=entry.id,
            alert_name=entry.alert_name,
            category=entry.category,
            severity=entry.severity,
            triggered_at=entry.triggered_at,
            resolved_at=entry.resolved_at,
            status=entry.status,
            receiver=entry.receiver,
            notified_display=entry.notified_display,
            tenant=entry.tenant,
            labels=entry.labels,
            annotations=entry.annotations,
            fingerprint=entry.fingerprint,
            created_at=entry.created_at,
        )
