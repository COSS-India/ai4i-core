"""Inference package initialization."""

from inference.inference_server_resolver import (
    InferenceServerResolver,
    ServiceNotFoundError,
)

__all__ = [
    "InferenceServerResolver",
    "ServiceNotFoundError",
]
