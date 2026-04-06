"""Shared types for endpoint / inference validation (reusable for future APIs)."""

from __future__ import annotations

from dataclasses import dataclass, field
from enum import Enum
from typing import Any, Dict, Optional


class ValidationStage(str, Enum):
    """Ordered stages reported in validation results."""

    URL = "url"
    CONNECTIVITY = "connectivity"
    TRITON_HEALTH = "triton_health"
    TRITON_MODEL_READY = "triton_model_ready"
    TRITON_INFER = "triton_infer"
    GENERIC_JSON_PROBE = "generic_json_probe"


@dataclass
class EndpointValidationResult:
    """Outcome of validating a hosted model endpoint (create/update or future API)."""

    ok: bool
    stage: ValidationStage
    message: str
    details: Dict[str, Any] = field(default_factory=dict)


class EndpointValidationFailure(Exception):
    """Raised when validation fails; carries structured context for HTTP mapping."""

    def __init__(
        self,
        stage: ValidationStage,
        message: str,
        *,
        details: Optional[Dict[str, Any]] = None,
    ):
        self.stage = stage
        self.message = message
        self.details = details or {}
        super().__init__(message)
