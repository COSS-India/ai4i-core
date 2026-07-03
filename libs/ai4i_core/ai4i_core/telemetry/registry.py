"""
Registry for complex attribute computations.
Simple expressions (len, field access) are evaluated directly from JSON.
Complex business logic goes here.
"""

import logging
from typing import Any, Union, Dict, List

logger = logging.getLogger(__name__)

def compute_first_item_source(data: List[Any]) -> str:
    """Get source text from first item in list."""
    if isinstance(data, list) and data:
        item = data[0]
        if isinstance(item, dict):
            return item.get("source", "")
        return getattr(item, "source", "")
    return ""

def compute_request_status(response: Dict[str, Any]) -> str:
    """Determine request success status from response."""
    if response is None:
        return "failed"
    if isinstance(response, dict):
        error = response.get("error")
        detail = response.get("detail")
        if error or detail:
            return "failed"
    return "success"

def compute_service_used(response: Dict[str, Any]) -> str:
    """Extract service name from response (typically NMT for text services)."""
    if isinstance(response, dict):
        service = (response.get("service_used") or response.get("service_name")
                  or response.get("task_type", "").lower() or "nmt")
        return str(service).lower()
    return "nmt"

def compute_elapsed_time(response: Dict[str, Any]) -> int:
    """Compute elapsed time in milliseconds from response."""
    if isinstance(response, dict):
        elapsed = response.get("elapsed_time_ms") or response.get("elapsed_time") or response.get("duration_ms") or 0
        return int(elapsed)
    return 0

def compute_endpoint(request: Dict[str, Any]) -> str:
    """Extract endpoint path from request, fallback to context."""
    if isinstance(request, dict):
        endpoint = request.get("endpoint") or request.get("path") or request.get("route")
        if endpoint:
            return endpoint

    # Fallback to context for services that don't enrich request dict (e.g., StandardSpanManager)
    from ai4i_core.context import get_endpoint_path
    endpoint = get_endpoint_path()
    return endpoint or ""

def compute_http_status_code(response: Dict[str, Any]) -> int:
    """Extract HTTP status code from response."""
    if isinstance(response, dict):
        status = response.get("status_code") or response.get("http_status") or 200
        return int(status)
    return 200

def compute_tenant_id(request: Dict[str, Any]) -> str:
    """Extract tenant ID from request data, fallback to context.

    Tries request config first, then context (set by middleware from JWT).
    """
    # Try request config first
    config = request.get("config", {})
    if isinstance(config, dict):
        tid = config.get("tenantId") or config.get("tenant_id")
        if tid:
            return str(tid)
    else:
        tid = getattr(config, "tenantId", None) or getattr(config, "tenant_id", None)
        if tid:
            return str(tid)

    # Try top-level tenant_id field
    tid = request.get("tenantId") or request.get("tenant_id")
    if tid:
        return str(tid)

    # Fallback to context (set by middleware from JWT)
    from ai4i_core.context import get_tenant_id
    tenant_id = get_tenant_id()
    return tenant_id or ""

def compute_user_id_attr(request: Dict[str, Any]) -> str:
    """Extract user ID from request data, fallback to context.

    Tries request config first, then context (set by middleware from JWT).
    """
    # Try request config first
    config = request.get("config", {})
    if isinstance(config, dict):
        uid = config.get("userId") or config.get("user_id")
        if uid:
            return str(uid)
    else:
        uid = getattr(config, "userId", None) or getattr(config, "user_id", None)
        if uid:
            return str(uid)

    # Try top-level userId field
    uid = request.get("userId") or request.get("user_id")
    if uid:
        return str(uid)

    # Fallback to context (set by middleware from JWT)
    from ai4i_core.context import get_user_id
    user_id = get_user_id()
    return user_id or ""

def compute_model_name(data: Dict[str, Any]) -> str:
    """Extract model name from data (response from service resolution).

    Tries multiple sources where model name might be returned.
    """
    if isinstance(data, dict):
        model = (data.get("model_name")
                or data.get("model")
                or data.get("name")
                or data.get("model_used")
                or "unknown")
        return str(model)
    return "unknown"

def compute_model_version(data: Dict[str, Any]) -> str:
    """Extract model version from data (request or response).

    Tries multiple sources:
    - response.model_version (from service resolution)
    - response.version
    - request.config.model_version (from client config)
    - defaults to "1"
    """
    if isinstance(data, dict):
        version = (data.get("model_version")
                  or data.get("version")
                  or data.get("config", {}).get("model_version"))
        if version:
            return str(version)
    return "1"

def compute_task_type(data: Dict[str, Any]) -> str:
    """Extract or infer task type from data (request or response).

    Tries multiple sources:
    1. Explicit "task_type", "taskType", or "type" field in data
    2. Infer from model_name if available
    """
    if isinstance(data, dict):
        # Try explicit task_type field
        task = (data.get("task_type")
                or data.get("taskType")
                or data.get("type"))
        if task:
            return str(task)

        # Infer from model_name: "lang-diarization-gpu" → "language_diarization"
        model_name = data.get("model_name") or data.get("model") or ""
        if model_name:
            # Map common model patterns to task types
            model_lower = str(model_name).lower()
            if "diarization" in model_lower:
                if "language" in model_lower or "lang" in model_lower:
                    return "language_diarization"
                if "speaker" in model_lower:
                    return "speaker_diarization"
                if "audio_language" in model_lower or "ald" in model_lower:
                    return "audio_language_diarization"
            if "indictrans" in model_lower or "nmt" in model_lower or "translation" in model_lower:
                return "nmt"
            if "asr" in model_lower or "speech" in model_lower:
                return "asr"
            if "tts" in model_lower or "speech_synthesis" in model_lower:
                return "tts"
            if "ner" in model_lower or "entity" in model_lower:
                return "ner"
            if "ocr" in model_lower:
                return "ocr"
            if "transliteration" in model_lower:
                return "transliteration"
            if "language_detection" in model_lower or "lang_detect" in model_lower:
                return "language_detection"

    return ""

def compute_input_tokens(request: Dict[str, Any]) -> int:
    """Extract input token count from request."""
    if isinstance(request, dict):
        tokens = request.get("input_tokens") or request.get("tokens") or 0
        return int(tokens) if tokens else 0
    return 0

def compute_output_tokens(response: Dict[str, Any]) -> int:
    """Extract output token count from response."""
    if isinstance(response, dict):
        tokens = response.get("output_tokens") or response.get("tokens_generated") or 0
        return int(tokens) if tokens else 0
    return 0

def _detect_data_type(data: Any) -> str:
    """Detect data type: text, audio, image, binary, dict, list, or unknown."""
    try:
        import filetype
        has_filetype = True
    except ImportError:
        has_filetype = False

    if data is None:
        return "unknown"

    # Check if it's bytes/binary
    if isinstance(data, bytes):
        if has_filetype:
            kind = filetype.guess(data)
            if kind:
                return kind.mime.split("/")[0]  # 'audio', 'image', 'video', etc.
        return "binary"

    # Check if it's string/text
    if isinstance(data, str):
        return "text"

    # Check if it's a dict
    if isinstance(data, dict):
        return "dict"

    # Check if it's a list — inspect first item
    if isinstance(data, list):
        if not data:
            return "list"
        first = data[0]
        if isinstance(first, dict):
            # Infer from dict content
            if any(k in first for k in ["audio_content", "audioContent", "audio_uri", "audioUri"]):
                return "audio"
            if any(k in first for k in ["source", "target", "text", "content", "transcript"]):
                return "text"
            if any(k in first for k in ["segment", "segments", "start", "end", "confidence"]):
                return "audio"  # Likely segmentation output (diarization, ASR with timing)
            return "list"  # Generic list of dicts
        if isinstance(first, bytes):
            return "binary"
        if isinstance(first, str):
            return "text"
        return "list"

    return "unknown"


def compute_input_type(request: Dict[str, Any]) -> str:
    """Determine input type from request data."""
    if not isinstance(request, dict):
        return "unknown"

    # Check for input field (text services)
    if "input" in request:
        return _detect_data_type(request.get("input"))

    # Check for audio field (audio services)
    if "audio" in request:
        return _detect_data_type(request.get("audio"))

    # Check for image field (vision services)
    if "image" in request or "images" in request:
        return _detect_data_type(request.get("image") or request.get("images"))

    return "unknown"


def compute_output_type(response: Dict[str, Any]) -> str:
    """Determine output type from response data."""
    if not isinstance(response, dict):
        return "unknown"

    # Check multiple common output field names
    for field in ["output", "result", "outputs", "data", "response_data", "response"]:
        if field in response:
            return _detect_data_type(response.get(field))

    return "unknown"

def compute_records_saved(response: Dict[str, Any]) -> int:
    """Count records saved to database."""
    if isinstance(response, dict):
        saved = response.get("records_saved") or response.get("row_count") or 0
        return int(saved)
    return 0

REGISTRY = {

    "compute_first_item_source": compute_first_item_source,
    "compute_request_status": compute_request_status,
    "compute_service_used": compute_service_used,
    "compute_elapsed_time": compute_elapsed_time,
    "compute_endpoint": compute_endpoint,
    "compute_http_status_code": compute_http_status_code,
    "compute_tenant_id": compute_tenant_id,
    "compute_user_id_attr": compute_user_id_attr,
    "compute_model_name": compute_model_name,
    "compute_model_version": compute_model_version,
    "compute_task_type": compute_task_type,
    "compute_input_tokens": compute_input_tokens,
    "compute_output_tokens": compute_output_tokens,
    "compute_input_type": compute_input_type,
    "compute_output_type": compute_output_type,
}

def _build_context(data: Union[Dict[str, Any], List[Any]]) -> Dict[str, Any]:
    """
    Build evaluation context from data, handling both dicts and lists.

    For dicts: unpacks as-is
    For lists: provides list-specific variables like 'items', 'item_count', 'first'
    Also includes async context variables (tenant_id, user_id, endpoint_path).
    """
    # Fetch async context variables
    from ai4i_core.context import (
        get_tenant_id, get_user_id, get_endpoint_path
    )

    ctx_vars = {
        "tenant_id_ctx": get_tenant_id(),
        "user_id_ctx": get_user_id(),
        "endpoint_path": get_endpoint_path(),
    }

    if isinstance(data, list):
        return {
            "_": data,  # Direct reference to the list
            "items": data,
            "item_count": len(data),
            "first": data[0] if data else None,
            "request": data,
            "response": data,
            **ctx_vars,
        }
    elif isinstance(data, dict):
        return {**data, "request": data, "response": data, **ctx_vars}
    else:
        return {"request": data, "response": data, **ctx_vars}

def safe_eval(expression: str, context: Dict[str, Any]) -> Any:
    """
    Safely evaluate JSON expressions with limited built-in functions.

    Args:
        expression: String expression like "len(items)" or "first.get('source')"
        context: Dictionary with variable names to values

    Returns:
        Computed value or None if evaluation fails
    """
    safe_builtins = {
        "len": len,
        "str": str,
        "int": int,
        "float": float,
        "bool": bool,
    }

    try:
        namespace = {**context, **safe_builtins}
        logger.debug(f"[EXPR DEBUG] expr='{expression}', namespace_keys={list(namespace.keys())}")
        result = eval(expression, {"__builtins__": {}}, namespace)
        logger.debug(f"[EXPR SUCCESS] expr='{expression}' -> {result}")
        return result
    except Exception as e:
        logger.error(f"[EXPR ERROR] Failed to evaluate '{expression}': {type(e).__name__}: {e}")
        logger.debug(f"[EXPR DEBUG] Context keys available: {list(context.keys())}")
        return None

def get_attribute_value(attr_config: Dict[str, str], data: Union[Dict[str, Any], List[Any]]) -> Any:
    """
    Get attribute value from expression or registry function.
    Handles both dict (request/response) and list (preprocessing) data.

    Args:
        attr_config: Dict with "expr" or "func" key
        data: Request/response object (dict) or list data

    Returns:
        Computed value or None if evaluation fails
    """
    attr_name = attr_config.get("attr", "unknown")
    logger.debug(f"[ATTR DEBUG] Computing {attr_name}: config={attr_config}, data_type={type(data).__name__}")

    if "expr" in attr_config:
        context = _build_context(data)
        logger.debug(f"[ATTR DEBUG] {attr_name}: Evaluating expr='{attr_config['expr']}' with context keys={list(context.keys())}")
        result = safe_eval(attr_config["expr"], context)
        logger.debug(f"[ATTR DEBUG] {attr_name}: expr result={result}")
        return result

    if "func" in attr_config:
        func = REGISTRY.get(attr_config["func"])
        if func:
            logger.debug(f"[ATTR DEBUG] {attr_name}: Calling func='{attr_config['func']}'")
            result = func(data)
            logger.debug(f"[ATTR DEBUG] {attr_name}: func result={result}")
            return result
        logger.warning(f"[ATTR ERROR] Function '{attr_config['func']}' not found in registry for {attr_name}")

    logger.warning(f"[ATTR ERROR] No expr or func in config for {attr_name}: {attr_config}")
    return None
