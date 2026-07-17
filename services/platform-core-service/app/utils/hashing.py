"""
Deterministic ID generation for Model entities.

model_id = sha256(lower(name):lower(version))[:32]

Casing differences do not produce distinct entities.
"""

import hashlib


def generate_model_id(name: str, version: str) -> str:
    """Return the deterministic SHA256-truncated id for (name, version)."""
    normalized = f"{name.strip().lower()}:{version.strip().lower()}"
    return hashlib.sha256(normalized.encode("utf-8")).hexdigest()[:32]
