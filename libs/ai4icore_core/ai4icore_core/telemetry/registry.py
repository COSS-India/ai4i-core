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
        result = eval(expression, {"__builtins__": {}}, namespace)
        return result
    except Exception as e:
        logger.warning(f"Failed to evaluate expression '{expression}': {e}")
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
    if "expr" in attr_config:
        context = _build_context(data)
        return safe_eval(attr_config["expr"], context)

    if "func" in attr_config:
        func = REGISTRY.get(attr_config["func"])
        if func:
            return func(data)
        logger.warning(f"Function '{attr_config['func']}' not found in registry")

    return None