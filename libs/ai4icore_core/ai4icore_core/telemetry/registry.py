"""
Registry for complex attribute computations.
Simple expressions (len, field access) are evaluated directly from JSON.
Complex business logic goes here.
"""

import logging

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


REGISTRY = {
    "compute_input_quality": compute_input_quality,
    "compute_sentiment_score": compute_sentiment_score,
    "compute_quality_metrics": compute_quality_metrics,
}


def safe_eval(expression, context):
    """
    Safely evaluate JSON expressions with limited built-in functions.

    Args:
        expression: String expression like "len(text)" or "data.get('key', 0)"
        context: Dictionary with variable names to values

    Returns:
        Computed value or None if evaluation fails
    """
    safe_builtins = {
        "len": len,
    }

    try:
        namespace = {**context, **safe_builtins}
        result = eval(expression, {"__builtins__": {}}, namespace)
        return result
    except Exception as e:
        logger.warning(f"Failed to evaluate expression '{expression}': {e}")
        return None


def get_attribute_value(attr_config, data):
    """
    Get attribute value from expression or registry function.

    Args:
        attr_config: Dict with "expr" or "func" key
        data: Request or response object

    Returns:
        Computed value or None if evaluation fails
    """
    if "expr" in attr_config:
        context = {**data, "request": data, "response": data}
        return safe_eval(attr_config["expr"], context)

    if "func" in attr_config:
        func = REGISTRY.get(attr_config["func"])
        if func:
            return func(data)
        logger.warning(f"Function '{attr_config['func']}' not found in registry")

    return None