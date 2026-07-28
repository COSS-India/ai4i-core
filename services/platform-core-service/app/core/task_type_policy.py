"""Task-type enablement policy.

platform-core is the single owner of ``ENABLED_TASK_TYPES`` (see
docs/design/ENABLED_TASK_TYPES.md). This module turns that config value into the
enabled set and exposes the two things callers need:

- ``is_task_type_enabled(name)`` — the gate used by listings, resolution, usage.
- ``get_enabled_inference_types()`` — the full yaml entries ∩ enabled, for the
  ``/inference-types`` discovery endpoint the frontend builds its catalog from.

The canonical vocabulary is the yaml (``ai4i_core.ppu.get_inference_types``); this
module only intersects it with the operator's allowlist. System/coarse consumers
(billing, migrations) keep using ``get_inference_types()`` directly and are not
gated here.
"""

from functools import lru_cache
from typing import Any, Dict, List

from ai4i_core.ppu import get_inference_types

from app.core.config import settings


# The metering SERVICE_BREAKDOWN_CONFIG and alert INFERENCE_TASKS spell audio
# language detection as "audio_language_detection", but the yaml canonical name
# is "audio-lang-detection". Fold that one spelling onto the canonical form so
# the enabled set gates it. (Same bridge the frontend applies — useInferenceTypes.ts.)
_ALIASES = {"audio-language-detection": "audio-lang-detection"}


def _normalize(name: str) -> str:
    """Normalize any task-type spelling to the canonical yaml form (lower-hyphen).

    Task types appear in several forms across the codebase — hyphen
    (`mm_models.task["type"]`, the yaml), underscore (metering
    `SERVICE_BREAKDOWN_CONFIG`, alert `INFERENCE_TASKS`), and mixed casing.
    Collapsing case + underscore→hyphen (plus the audio-lang alias) lets one
    enabled set gate all of them.
    """
    key = (name or "").strip().lower().replace("_", "-")
    return _ALIASES.get(key, key)


@lru_cache(maxsize=1)
def enabled_task_type_names() -> frozenset:
    """The set of enabled task-type names, parsed once from config."""
    return frozenset(
        _normalize(s) for s in settings.enabled_task_types.split(",") if s.strip()
    )


def is_task_type_enabled(name: str) -> bool:
    """True if ``name`` (any casing) is enabled for this deployment."""
    return _normalize(name) in enabled_task_type_names()


def get_enabled_inference_types() -> List[Dict[str, Any]]:
    """Full yaml inference-type entries, filtered to the enabled set."""
    enabled = enabled_task_type_names()
    return [t for t in get_inference_types() if _normalize(t["name"]) in enabled]
