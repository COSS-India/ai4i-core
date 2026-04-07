"""
Endpoint Validation Module
~~~~~~~~~~~~~~~~~~~~~~~~~~

Provides reusable, two-level validation for inference endpoints:

  Level 1 - URL format check  (synchronous, always blocking)
  Level 2 - Live inference test (async, uses task-type-aware dummy payloads)

All public functions are standalone so they can be called from routers
during model/service creation *or* exposed directly via a dedicated
validation API in the future.
"""

import httpx
from enum import Enum
from typing import Optional, Dict, Any, List
from urllib.parse import urlparse
from pydantic import BaseModel
from logger import get_logger

logger = get_logger("endpoint-validator")


# ---------------------------------------------------------------------------
# Result models
# ---------------------------------------------------------------------------

class ValidationLevel(str, Enum):
    URL_FORMAT = "url_format"
    INFERENCE = "inference"


class ValidationStatus(str, Enum):
    PASSED = "passed"
    FAILED = "failed"
    SKIPPED = "skipped"


class ValidationDetail(BaseModel):
    level: ValidationLevel
    status: ValidationStatus
    message: str


class EndpointValidationResult(BaseModel):
    is_valid: bool
    endpoint: str
    details: List[ValidationDetail]


# ---------------------------------------------------------------------------
# Level 1 – URL format validation
# ---------------------------------------------------------------------------

_ALLOWED_SCHEMES = {"http", "https"}


def validate_url_format(url: str) -> ValidationDetail:
    """Validate that *url* is a well-formed HTTP(S) URL."""
    try:
        parsed = urlparse(url)

        if not parsed.scheme:
            return ValidationDetail(
                level=ValidationLevel.URL_FORMAT,
                status=ValidationStatus.FAILED,
                message=f"URL missing scheme (http/https). Got: '{url}'",
            )

        if parsed.scheme.lower() not in _ALLOWED_SCHEMES:
            return ValidationDetail(
                level=ValidationLevel.URL_FORMAT,
                status=ValidationStatus.FAILED,
                message=f"URL scheme must be http or https. Got: '{parsed.scheme}'",
            )

        if not parsed.netloc:
            return ValidationDetail(
                level=ValidationLevel.URL_FORMAT,
                status=ValidationStatus.FAILED,
                message=f"URL missing host. Got: '{url}'",
            )

        return ValidationDetail(
            level=ValidationLevel.URL_FORMAT,
            status=ValidationStatus.PASSED,
            message="URL format is valid.",
        )
    except Exception as exc:
        return ValidationDetail(
            level=ValidationLevel.URL_FORMAT,
            status=ValidationStatus.FAILED,
            message=f"URL parsing error: {exc}",
        )


# ---------------------------------------------------------------------------
# Level 2 – Inference test helpers
# ---------------------------------------------------------------------------

_DUMMY_PAYLOADS: Dict[str, Dict[str, Any]] = {
    "nmt": {
        "input": [{"source": "Hello, how are you?"}],
        "config": {
            "language": {"sourceLanguage": "en", "targetLanguage": "hi"},
        },
    },
    "tts": {
        "input": [{"source": "Hello"}],
        "config": {
            "language": {"sourceLanguage": "en"},
            "gender": "female",
        },
    },
    "asr": {
        "audio": [{"audioContent": ""}],
        "config": {
            "language": {"sourceLanguage": "en"},
        },
    },
    "llm": {
        "input": [{"source": "Hello"}],
        "config": {},
    },
    "transliteration": {
        "input": [{"source": "namaste"}],
        "config": {
            "language": {"sourceLanguage": "hi", "targetLanguage": "en"},
        },
    },
    "language-detection": {
        "input": [{"source": "Hello, how are you?"}],
        "config": {},
    },
    "ocr": {
        "image": [{"imageContent": ""}],
        "config": {
            "language": {"sourceLanguage": "en"},
        },
    },
    "ner": {
        "input": [{"source": "John went to New York."}],
        "config": {
            "language": {"sourceLanguage": "en"},
        },
    },
    "speaker-diarization": {
        "audio": [{"audioContent": ""}],
        "config": {},
    },
    "audio-lang-detection": {
        "audio": [{"audioContent": ""}],
        "config": {},
    },
    "language-diarization": {
        "audio": [{"audioContent": ""}],
        "config": {},
    },
}


def build_inference_payload(
    task_type: str,
    request_schema: Optional[Dict[str, Any]] = None,
) -> Dict[str, Any]:
    """
    Build a minimal test payload for a given *task_type*.

    If *request_schema* (the ``Schema.request`` dict stored on the model)
    contains meaningful keys, they are used with placeholder values.
    Otherwise a built-in default for the task type is returned.
    """
    if request_schema:
        payload: Dict[str, Any] = {}
        for key, value in request_schema.items():
            if isinstance(value, str):
                payload[key] = "test"
            elif isinstance(value, dict):
                payload[key] = value
            elif isinstance(value, list):
                payload[key] = value if value else ["test"]
            else:
                payload[key] = value
        if payload:
            logger.info(
                f"Using model schema.request for test payload "
                f"(task_type={task_type}): {payload}"
            )
            return payload

    if task_type in _DUMMY_PAYLOADS:
        logger.info(
            f"Using built-in dummy payload for task_type={task_type} "
            f"(model schema.request is empty or not provided)"
        )
        return _DUMMY_PAYLOADS[task_type]

    fallback = {"input": [{"source": "test"}]}
    logger.info(
        f"Using generic fallback payload for unknown task_type={task_type} "
        f"(no model schema.request, no built-in dummy): {fallback}"
    )
    return fallback


_VALIDATION_MODE_THRESHOLDS: Dict[str, int] = {
    "lenient": 500,   # 4xx treated as pass (server reachable)
    "strict":  400,   # only 2xx/3xx pass; 4xx is a failure
}


async def test_inference(
    endpoint: str,
    task_type: str,
    request_schema: Optional[Dict[str, Any]] = None,
    api_key: Optional[str] = None,
    timeout: float = 15.0,
    validation_mode: str = "lenient",
) -> ValidationDetail:
    """
    POST a dummy payload to *endpoint* and check the response status.

    *validation_mode* controls which HTTP codes are acceptable:
      - ``"lenient"`` (default): status < 500 passes (4xx = reachable).
      - ``"strict"``:  status < 400 passes (4xx = client error → fail).
    """
    fail_threshold = _VALIDATION_MODE_THRESHOLDS.get(
        validation_mode, _VALIDATION_MODE_THRESHOLDS["lenient"]
    )

    payload = build_inference_payload(task_type, request_schema)

    headers: Dict[str, str] = {"Content-Type": "application/json"}
    if api_key:
        headers["Authorization"] = f"Bearer {api_key}"

    logger.info(
        f"Inference test request to {endpoint}: "
        f"task_type={task_type}, validation_mode={validation_mode}, payload={payload}"
    )

    try:
        async with httpx.AsyncClient(timeout=timeout, verify=False) as client:
            response = await client.post(endpoint, json=payload, headers=headers)

        try:
            body = response.json()
        except Exception:
            body = response.text[:500] or "(empty)"

        logger.info(
            f"Inference test response from {endpoint}: "
            f"status={response.status_code}, body={body}"
        )

        if response.status_code < fail_threshold:
            return ValidationDetail(
                level=ValidationLevel.INFERENCE,
                status=ValidationStatus.PASSED,
                message=(
                    f"Inference endpoint is reachable and responded with "
                    f"HTTP {response.status_code}."
                ),
            )

        return ValidationDetail(
            level=ValidationLevel.INFERENCE,
            status=ValidationStatus.FAILED,
            message=(
                f"Inference endpoint returned HTTP {response.status_code} "
                f"(validation_mode={validation_mode}): {body}"
            ),
        )

    except httpx.ConnectError:
        return ValidationDetail(
            level=ValidationLevel.INFERENCE,
            status=ValidationStatus.FAILED,
            message=f"Could not connect to endpoint: {endpoint}",
        )
    except httpx.TimeoutException:
        return ValidationDetail(
            level=ValidationLevel.INFERENCE,
            status=ValidationStatus.FAILED,
            message=f"Request timed out after {timeout}s: {endpoint}",
        )
    except Exception as exc:
        return ValidationDetail(
            level=ValidationLevel.INFERENCE,
            status=ValidationStatus.FAILED,
            message=f"Inference test error: {exc}",
        )


# ---------------------------------------------------------------------------
# Orchestrator
# ---------------------------------------------------------------------------

async def validate_endpoint(
    endpoint: str,
    task_type: Optional[str] = None,
    request_schema: Optional[Dict[str, Any]] = None,
    api_key: Optional[str] = None,
    run_inference_test: bool = True,
    timeout: float = 15.0,
    validation_mode: str = "lenient",
) -> EndpointValidationResult:
    """
    Run all applicable validation levels against an inference *endpoint*.

    Parameters
    ----------
    endpoint : str
        The URL to validate.
    task_type : str, optional
        Task type (e.g. ``"nmt"``, ``"asr"``). Required for inference test.
    request_schema : dict, optional
        The model's ``Schema.request`` dict — used to build the test payload.
    api_key : str, optional
        Bearer token / API key sent with the inference request.
    run_inference_test : bool
        Whether to execute the Level 2 live inference test.
    timeout : float
        HTTP timeout (seconds) for the inference request.
    validation_mode : str
        ``"lenient"`` (4xx=pass) or ``"strict"`` (4xx=fail).

    Returns
    -------
    EndpointValidationResult
        Aggregated result with per-level detail entries.
    """
    details: List[ValidationDetail] = []

    # Level 1
    url_result = validate_url_format(endpoint)
    details.append(url_result)

    if url_result.status == ValidationStatus.FAILED:
        return EndpointValidationResult(
            is_valid=False,
            endpoint=endpoint,
            details=details,
        )

    # Level 2
    if run_inference_test and task_type:
        inference_result = await test_inference(
            endpoint=endpoint,
            task_type=task_type,
            request_schema=request_schema,
            api_key=api_key,
            timeout=timeout,
            validation_mode=validation_mode,
        )
        details.append(inference_result)
        logger.info(
            f"Endpoint validation [{inference_result.status.value}] "
            f"for {endpoint} (task={task_type}): {inference_result.message}"
        )
    elif run_inference_test and not task_type:
        details.append(
            ValidationDetail(
                level=ValidationLevel.INFERENCE,
                status=ValidationStatus.SKIPPED,
                message="Inference test skipped: task_type not provided.",
            )
        )

    is_valid = all(
        d.status in (ValidationStatus.PASSED, ValidationStatus.SKIPPED)
        for d in details
    )

    return EndpointValidationResult(
        is_valid=is_valid,
        endpoint=endpoint,
        details=details,
    )
