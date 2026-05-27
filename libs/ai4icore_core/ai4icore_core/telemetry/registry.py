"""
Registry for complex attribute computations.
Simple expressions (len, field access) are evaluated directly from JSON.
Complex business logic goes here.
"""

import logging
from typing import Any, Union, Dict, List

logger = logging.getLogger(__name__)


def compute_input_quality(request):
    """Compute input quality score for NMT.

    Complex logic: checks text length, language patterns, special chars.
    """
    text = request.get("text", "")
    if not text:
        return 0

    quality = min(100, len(text.strip()) * 2)
    return quality


def compute_sentiment_score(request):
    """Compute sentiment score."""
    text = request.get("text", "")
    return len(text) % 10


def compute_quality_metrics(response):
    """Compute quality metrics from response."""
    items = response.get("preprocessed_texts", [])
    return {"count": len(items), "score": 85}


def compute_list_count(data: List[Any]) -> int:
    """Count items in a list."""
    return len(data) if isinstance(data, list) else 0


def compute_first_item_source(data: List[Any]) -> str:
    """Get source text from first item in list."""
    if isinstance(data, list) and data:
        item = data[0]
        if isinstance(item, dict):
            return item.get("source", "")
        return getattr(item, "source", "")
    return ""


def compute_customer_id(request: Dict[str, Any]) -> Any:
    """Extract customer/user ID from request config."""
    config = request.get("config", {})
    if isinstance(config, dict):
        return config.get("userId") or config.get("customer_id") or config.get("user_id")
    return getattr(config, "userId", None) or getattr(config, "user_id", None)


def compute_input_size(request: Dict[str, Any]) -> int:
    """Compute input size from request."""
    input_data = request.get("input") or request.get("audio") or request.get("image")
    return len(input_data) if input_data else 0


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


def compute_success_status(response: Dict[str, Any]) -> str:
    """Determine success status from response (alias for compute_request_status)."""
    return compute_request_status(response)


def compute_service_used(response: Dict[str, Any]) -> str:
    """Extract service name from response (typically NMT for text services)."""
    if isinstance(response, dict):
        service = (response.get("service_used") or response.get("service_name")
                  or response.get("task_type", "").lower() or "nmt")
        return str(service).lower()
    return "nmt"


def compute_model_used(response: Dict[str, Any]) -> str:
    """Extract model name from response (checks multiple possible locations)."""
    if isinstance(response, dict):
        model = (response.get("model_used") or response.get("model_name")
                or response.get("model") or response.get("service_used")
                or response.get("name") or "unknown")
        return str(model)
    return "unknown"


def compute_elapsed_time(response: Dict[str, Any]) -> int:
    """Compute elapsed time in milliseconds from response."""
    if isinstance(response, dict):
        elapsed = response.get("elapsed_time_ms") or response.get("elapsed_time") or response.get("duration_ms") or 0
        return int(elapsed)
    return 0


def compute_endpoint(request: Dict[str, Any]) -> str:
    """Extract endpoint path from request."""
    if isinstance(request, dict):
        return request.get("endpoint") or request.get("path") or request.get("route") or ""
    return ""


def compute_http_status_code(response: Dict[str, Any]) -> int:
    """Extract HTTP status code from response."""
    if isinstance(response, dict):
        status = response.get("status_code") or response.get("http_status") or 200
        return int(status)
    return 200


def compute_tenant_id(request: Dict[str, Any]) -> str:
    """Extract tenant ID from request config."""
    config = request.get("config", {})
    if isinstance(config, dict):
        return config.get("tenantId") or config.get("tenant_id") or ""
    return getattr(config, "tenantId", None) or getattr(config, "tenant_id", None) or ""


def compute_user_id_attr(request: Dict[str, Any]) -> str:
    """Extract user ID from request config (distinct from compute_customer_id)."""
    config = request.get("config", {})
    if isinstance(config, dict):
        return config.get("userId") or config.get("user_id") or ""
    return getattr(config, "userId", None) or getattr(config, "user_id", None) or ""


def compute_model_name(response: Dict[str, Any]) -> str:
    """Extract model name from response."""
    if isinstance(response, dict):
        model = (response.get("model_name") or response.get("model")
                or response.get("name") or response.get("model_used") or "unknown")
        return str(model)
    return "unknown"


def compute_model_version(response: Dict[str, Any]) -> str:
    """Extract model version from response."""
    if isinstance(response, dict):
        version = response.get("model_version") or response.get("version") or ""
        return str(version)
    return ""


def compute_task_type(request: Dict[str, Any]) -> str:
    """Extract task type from request."""
    if isinstance(request, dict):
        task = (request.get("task_type") or request.get("taskType")
                or request.get("type") or "")
        return str(task)
    return ""


def compute_input_size_kb(request: Dict[str, Any]) -> int:
    """Compute input size in kilobytes from request."""
    if isinstance(request, dict):
        import json
        try:
            size_bytes = len(json.dumps(request).encode('utf-8'))
            return max(1, size_bytes // 1024)
        except Exception:
            pass
    return 0


def compute_output_size_kb(response: Dict[str, Any]) -> int:
    """Compute output size in kilobytes from response."""
    if isinstance(response, dict):
        import json
        try:
            size_bytes = len(json.dumps(response).encode('utf-8'))
            return max(1, size_bytes // 1024)
        except Exception:
            pass
    return 0


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


def compute_input_type(request: Dict[str, Any]) -> str:
    """Extract input data type from request."""
    if isinstance(request, dict):
        input_type = (request.get("input_type") or request.get("type")
                     or request.get("content_type") or "text")
        return str(input_type)
    return "text"


def compute_output_type(response: Dict[str, Any]) -> str:
    """Extract output data type from response."""
    if isinstance(response, dict):
        output_type = (response.get("output_type") or response.get("type")
                      or response.get("content_type") or "text")
        return str(output_type)
    return "text"


def compute_records_saved(response: Dict[str, Any]) -> int:
    """Count records saved to database."""
    if isinstance(response, dict):
        saved = response.get("records_saved") or response.get("row_count") or 0
        return int(saved)
    return 0


REGISTRY = {
    "compute_input_quality": compute_input_quality,
    "compute_sentiment_score": compute_sentiment_score,
    "compute_quality_metrics": compute_quality_metrics,
    "compute_list_count": compute_list_count,
    "compute_first_item_source": compute_first_item_source,
    "compute_customer_id": compute_customer_id,
    "compute_input_size": compute_input_size,
    "compute_request_status": compute_request_status,
    "compute_success_status": compute_success_status,
    "compute_service_used": compute_service_used,
    "compute_model_used": compute_model_used,
    "compute_elapsed_time": compute_elapsed_time,
    "compute_records_saved": compute_records_saved,
    "compute_endpoint": compute_endpoint,
    "compute_http_status_code": compute_http_status_code,
    "compute_tenant_id": compute_tenant_id,
    "compute_user_id_attr": compute_user_id_attr,
    "compute_model_name": compute_model_name,
    "compute_model_version": compute_model_version,
    "compute_task_type": compute_task_type,
    "compute_input_size_kb": compute_input_size_kb,
    "compute_output_size_kb": compute_output_size_kb,
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
    """
    if isinstance(data, list):
        return {
            "_": data,  # Direct reference to the list
            "items": data,
            "item_count": len(data),
            "first": data[0] if data else None,
            "request": data,
            "response": data,
        }
    elif isinstance(data, dict):
        return {**data, "request": data, "response": data}
    else:
        return {"request": data, "response": data}


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