"""
AuditService — persists redaction audit records to the PII database.

Kafka has been removed. The database is the single sink.
All writes are fire-and-forget (FastAPI BackgroundTasks) so they never
block the response path.
"""

import logging
from typing import Any, Dict, List, Optional

from app.repositories.pii_management.audit_log_repository import AuditLogRepository
from app.core.pii_database import _pii_session_factory

logger = logging.getLogger(__name__)


class AuditService:
    """Writes audit records to the audit_logs table."""

    async def log_event(
        self,
        trace_id: Optional[str],
        tenant_id: Optional[str],
        domain_id: str,
        target_context: str,
        pii_count: int,
        processing_ms: int,
        trace_log: List[Dict[str, Any]],
    ) -> None:
        """
        Persist one audit record.  Called as a BackgroundTask — errors are
        logged but never propagate to the caller.
        """
        if _pii_session_factory is None:
            logger.warning("AuditService: PII DB not ready, skipping audit log.")
            return

        payload: Dict[str, Any] = {
            "trace_id":      trace_id,
            "tenant_id":     tenant_id,
            "domain_id":     domain_id,
            "target_context": target_context,
            "pii_count":     pii_count,
            "processing_ms": processing_ms,
            "trace_json":    trace_log,
        }

        try:
            async with _pii_session_factory() as db:
                repo = AuditLogRepository(db)
                await repo.create(payload)
        except Exception as exc:
            logger.error("Audit DB insert failed: %s", exc)
