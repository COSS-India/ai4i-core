"""
Deterministic ID generation for Model and Service entities.

Both IDs are SHA256 hashes truncated to 32 hex characters. This produces
stable identifiers that consumers can rely on without coordinating with
a centralized ID-issuing service.

  model_id   = sha256("{name}:{version}")[:32]
  service_id = sha256("{name}")[:32]

The model_id input is intentionally `lower(name):lower(version)` so casing
differences do not produce distinct entities.
"""

import hashlib


def generate_model_id(name: str, version: str) -> str:
    """Return the deterministic SHA256-truncated id for (name, version)."""
    normalized = f"{name.strip().lower()}:{version.strip().lower()}"
    return hashlib.sha256(normalized.encode("utf-8")).hexdigest()[:32]


def generate_service_id(name: str) -> str:
    """Return the deterministic SHA256-truncated id for a service name."""
    normalized = name.strip().lower()
    return hashlib.sha256(normalized.encode("utf-8")).hexdigest()[:32]
