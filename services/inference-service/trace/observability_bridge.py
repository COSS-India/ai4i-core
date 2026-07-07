"""Optional bridge from inference trace data to ObservabilityMiddleware.

Importing ai4i_core observability is isolated here so span attribute code
stays free of Prometheus / middleware dependencies.
"""

import logging
from typing import Any, Dict

logger = logging.getLogger(__name__)


def publish_inference_payload_metrics(
    payload: Dict[str, Any], span_attrs: Dict[str, Any], task_name: str
) -> None:
    """Store a payload metrics snapshot for ObservabilityMiddleware after success."""
    try:
        from ai4i_core.observability.middleware import set_inference_payload_metrics
        from trace.payload_analysis import build_observability_metrics

        set_inference_payload_metrics(
            build_observability_metrics(payload, span_attrs, task_name)
        )
    except Exception as exc:
        logger.debug("Could not publish observability payload metrics: %s", exc)
