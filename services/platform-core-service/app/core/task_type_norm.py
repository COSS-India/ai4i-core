"""Canonical task-type name normalization.

A single, dependency-free normalizer shared by ``config`` (the ENABLED_TASK_TYPES
validator) and ``task_type_policy`` (the runtime enabled-set gate). Keeping one
definition avoids the two drifting apart — a past bug where they normalized
differently.

Task types appear in several spellings across the codebase:
- hyphen (`mm_models.task["type"]`, the yaml, HTTP endpoints)
- underscore (metering ``SERVICE_BREAKDOWN_CONFIG``, alert ``INFERENCE_TASKS``)
- mixed casing

``normalize_task_type`` collapses case + underscore→hyphen so one enabled set
gates them all. It also folds known spelling aliases onto the canonical yaml
name — the vocabulary is split upstream (endpoint/metric/yaml use
``audio-lang-detection`` while the UI ServiceId, metering key, and alert task
name use ``audio-language-detection``); the frontend already bridges this, and
this alias is the backend's matching bridge.
"""

# Non-canonical spelling → canonical yaml `name`. Applied after case +
# underscore→hyphen folding, so keys/values are all lower-hyphen.
_ALIASES = {
    "audio-language-detection": "audio-lang-detection",
}


def normalize_task_type(name: str) -> str:
    """Normalize any task-type spelling to the canonical yaml form (lower-hyphen)."""
    key = (name or "").strip().lower().replace("_", "-")
    return _ALIASES.get(key, key)
