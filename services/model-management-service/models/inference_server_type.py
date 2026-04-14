from enum import Enum


class InferenceServerType(str, Enum):
    """Backend protocol for inference traffic (health probes, client selection)."""

    triton = "triton"
    http = "http"
