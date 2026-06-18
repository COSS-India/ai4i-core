"""Base class for response-size load testing across inference service types.

Extend this class to add NER, Image, Audio, or Text response tests.
Each subclass provides its own stub responses and the shared machinery
(payload classification, timing, reporting) is inherited from here.
"""

import time
from dataclasses import dataclass, field
from enum import Enum
from typing import Any


class ResponseSize(str, Enum):
    SMALL = "SMALL"
    MEDIUM = "MEDIUM"
    LARGE = "LARGE"


# Payload length thresholds (characters).
# SMALL  : < 200 chars
# MEDIUM : 200–999 chars
# LARGE  : >= 1000 chars
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


class BaseResponseTest:
    """Shared load-test harness for all inference task types.

    Subclasses must implement:
        - stub_response(size: ResponseSize) -> Any
    """

    # Override in subclasses if different thresholds are needed.
    small_threshold: int = SMALL_THRESHOLD
    medium_threshold: int = MEDIUM_THRESHOLD

    def classify_payload(self, payload: str) -> ResponseSize:
        """Return the ResponseSize bucket for a given payload string."""
        length = len(payload)
        if length < self.small_threshold:
            return ResponseSize.SMALL
        if length < self.medium_threshold:
            return ResponseSize.MEDIUM
        return ResponseSize.LARGE

    def stub_response(self, size: ResponseSize) -> Any:
        """Return the pre-defined stub response for *size*. Must be overridden."""
        raise NotImplementedError(
            f"{self.__class__.__name__} must implement stub_response()"
        )

    def run(self, payload: str) -> tuple[InferenceMetrics, Any]:
        """Classify the payload, fetch the stub, measure elapsed time, and return both."""
        size = self.classify_payload(payload)

        start = time.perf_counter() * 1000
        response = self.stub_response(size)
        end = time.perf_counter() * 1000

        metrics = InferenceMetrics(
            payload_size=len(payload),
            response_size=size,
            start_time_ms=start,
            end_time_ms=end,
        )
        return metrics, response
