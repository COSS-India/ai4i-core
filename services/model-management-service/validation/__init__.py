"""
Endpoint validation for hosted inference URLs.

Public entry points are stable for reuse (e.g. a future ``POST /services/validate-endpoint`` API).
"""

from validation.inference_probe import validate_hosted_inference_endpoint
from validation.model_metadata import (
    extract_model_name_from_inference_endpoint,
    extract_schema_request_response,
)
from validation.task_payloads import build_generic_probe_body, merge_schema_request_defaults
from validation.types import (
    EndpointValidationFailure,
    EndpointValidationResult,
    ValidationStage,
)
from validation.url import normalize_http_url, validate_http_url

__all__ = [
    "validate_hosted_inference_endpoint",
    "extract_model_name_from_inference_endpoint",
    "extract_schema_request_response",
    "build_generic_probe_body",
    "merge_schema_request_defaults",
    "EndpointValidationFailure",
    "EndpointValidationResult",
    "ValidationStage",
    "normalize_http_url",
    "validate_http_url",
]
