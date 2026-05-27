"""
RedactionService — orchestrates the full /redact pipeline.

Steps
-----
1. Resolve tenant → domain via PolicySyncService.
2. Load policy rules for the domain.
3. Run DetectionEngine (AI + regex + quasi-identifiers).
4. Apply redaction actions in reverse-index order (safe in-place replacement).
5. Schedule audit log write as a background task.
6. Return redacted text, detected entities, trace log, and metadata.
"""

import logging
import time
from typing import Any, Dict, List, Optional, Tuple

from fastapi import BackgroundTasks, HTTPException

from app.schemas.pii_management.redaction import (
    DetectedEntity,
    RedactionMetadata,
    RedactionResponse,
)
from .audit_service import AuditService
from .detection_service import DetectionEngine
from .policy_sync_service import PolicySyncService

logger = logging.getLogger(__name__)

_FALLBACK_DOMAIN = "logistics"


class RedactionService:
    """Stateless orchestrator; all state lives in its injected collaborators."""

    def __init__(
        self,
        policy_sync: PolicySyncService,
        detection_engine: DetectionEngine,
        audit_service: AuditService,
    ) -> None:
        self._policy_sync = policy_sync
        self._detection = detection_engine
        self._audit = audit_service

    async def redact(
        self,
        text: str,
        tenant_id: Optional[str],
        language: str,
        target: str,
        include_original: bool,
        background_tasks: BackgroundTasks,
    ) -> RedactionResponse:
        start = time.time()
        trace_id = ""
        trace_log: List[Dict[str, Any]] = [
            {"step": "Request", "status": "Success", "details": f"Target: {target}, Lang: {language}"}
        ]

        # ── Domain resolution ──────────────────────────────────────────────
        effective_domain, fallback_message = self._resolve_domain(tenant_id, trace_log)

        # ── Policy lookup ──────────────────────────────────────────────────
        policy = self._policy_sync.get_policy(effective_domain)
        if not policy:
            raise HTTPException(
                status_code=400,
                detail=(
                    f"Unknown domain '{effective_domain}'. "
                    "Create the domain or fix tenant_pii_domain_map."
                ),
            )

        # ── Detection ─────────────────────────────────────────────────────
        is_strict = target.lower() != "user"
        rules = policy.get("rules", [])
        entities = await self._detection.detect(text, rules, trace_log, is_strict, language)
        entities.sort(key=lambda e: e.start_index)

        # ── Redaction (reverse order to preserve indices) ──────────────────
        redacted = self._apply_redactions(text, entities, rules)

        # ── Audit (fire and forget) ────────────────────────────────────────
        ms = int((time.time() - start) * 1000)
        background_tasks.add_task(
            self._audit.log_event,
            trace_id, tenant_id, effective_domain,
            target, len(entities), ms, trace_log,
        )

        # ── Response ──────────────────────────────────────────────────────
        response = RedactionResponse(
            redacted_text=redacted,
            pii_detected=entities,
            trace=trace_log,
            metadata=RedactionMetadata(
                processing_time_ms=ms,
                language=language,
                domain=effective_domain,
                tenant_id=tenant_id or "unknown",
                message=fallback_message,
            ),
        )
        if include_original:
            response.original_text = text
        return response

    # ── Helpers ───────────────────────────────────────────────────────────

    def _resolve_domain(
        self,
        tenant_id: Optional[str],
        trace_log: List[Dict[str, Any]],
    ) -> Tuple[str, Optional[str]]:
        """Return (effective_domain, fallback_message_or_None)."""
        if not tenant_id:
            trace_log.append({
                "step": "DomainResolution", "status": "Fallback",
                "details": "Token missing tenant_id. Using 'logistics'.",
            })
            return _FALLBACK_DOMAIN, (
                "Token has no tenant_id claim. Using 'logistics' as fallback. "
                "Map/authenticate with tenant context for tenant-specific redaction."
            )

        domain = self._policy_sync.resolve_domain_for_tenant(tenant_id)
        if domain:
            return domain, None

        trace_log.append({
            "step": "DomainResolution", "status": "Fallback",
            "details": f"Tenant '{tenant_id}' has no mapped domain. Using 'logistics'.",
        })
        return _FALLBACK_DOMAIN, (
            "No domain is mapped to this tenant. Using 'logistics' as fallback. "
            "Map the tenant to the appropriate domain for specific redaction behavior."
        )

    @staticmethod
    def _apply_redactions(
        text: str,
        entities: List[DetectedEntity],
        rules: List[Dict[str, Any]],
    ) -> str:
        """Replace detected entities in reverse order to preserve character indices."""
        rules_by_type = {r["entity_type"]: r for r in rules}
        for entity in sorted(entities, key=lambda e: e.start_index, reverse=True):
            rule = rules_by_type.get(entity.entity_type)
            if not rule:
                continue
            action = rule.get("action", "REDACT")
            config = rule.get("config", {})

            if action == "REDACT_TAG":
                replacement = config.get("tag_label", f"[{entity.entity_type}]")
            elif action == "MASK":
                char = config.get("mask_char", "X")
                replacement = char * len(entity.text_segment)
            else:  # REDACT
                replacement = "[REDACTED]"

            text = text[: entity.start_index] + replacement + text[entity.end_index :]
        return text
