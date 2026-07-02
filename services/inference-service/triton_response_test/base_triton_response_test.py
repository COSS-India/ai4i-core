"""Base class for Triton-level response load testing.

Stubs the raw HTTP JSON that Triton returns so the inference service can be
load-tested without a live model.  The response format matches the KServe v2
infer protocol (``{"model_name": ..., "outputs": [...]}``) which is what
``_call_triton_inference`` receives.

Three size buckets, driven by input payload length (characters or base64 bytes):
  SMALL  : length  < SMALL_THRESHOLD   (200)
  MEDIUM : length  < MEDIUM_THRESHOLD  (1000)
  LARGE  : length >= MEDIUM_THRESHOLD
"""

import time
from dataclasses import dataclass, field
from enum import Enum
from typing import Any


class ResponseSize(str, Enum):
    SMALL = "SMALL"
    MEDIUM = "MEDIUM"
    LARGE = "LARGE"


SMALL_THRESHOLD = 200
MEDIUM_THRESHOLD = 1000


@dataclass
class InferenceMetrics:
    payload_size: int
    response_size: ResponseSize
    start_time_ms: float
    end_time_ms: float
    duration_ms: float = field(init=False)

    def __post_init__(self):
        self.duration_ms = round(self.end_time_ms - self.start_time_ms, 3)

    def __str__(self) -> str:
        return (
            f"Payload Size : {self.payload_size} chars\n"
            f"Response Type: {self.response_size.value}\n"
            f"Response Time: {self.duration_ms:.3f} ms"
        )


class BaseTritonResponseTest:
    """Shared Triton-stub harness for all inference task types.

    Subclasses must implement:
        get_response(size: ResponseSize) -> dict
    """

    small_threshold: int = SMALL_THRESHOLD
    medium_threshold: int = MEDIUM_THRESHOLD

    def classify_payload(self, payload: str) -> ResponseSize:
        length = len(payload)
        if length < self.small_threshold:
            return ResponseSize.SMALL
        if length < self.medium_threshold:
            return ResponseSize.MEDIUM
        return ResponseSize.LARGE

    def get_response(self, _size: ResponseSize) -> Any:
        raise NotImplementedError(f"{self.__class__.__name__} must implement get_response()")

    def run(self, payload: str) -> tuple[InferenceMetrics, Any]:
        size = self.classify_payload(payload)
        start = time.perf_counter() * 1000
        response = self.get_response(size)
        end = time.perf_counter() * 1000
        metrics = InferenceMetrics(
            payload_size=len(payload),
            response_size=size,
            start_time_ms=start,
            end_time_ms=end,
        )
        return metrics, response
