"""
Utility module for OpenFeature client management and helper functions
"""
import logging
from typing import Any, Optional

from openfeature import api as openfeature_api
from openfeature.client import Client
from openfeature.evaluation_context import EvaluationContext

logger = logging.getLogger(__name__)


def get_openfeature_client() -> Client:
    """
    Return the global OpenFeature client instance
    
    Raises:
        RuntimeError: If client is not initialized
    """
    try:
        client = openfeature_api.get_client()
        if client is None:
            raise RuntimeError("OpenFeature client not initialized")
        return client
    except Exception as e:
        raise RuntimeError(f"Failed to get OpenFeature client: {e}")


def build_evaluation_context(user_id: Optional[str] = None, **attributes) -> EvaluationContext:
    """
    Create EvaluationContext with targeting_key set to user_id
    
    Args:
        user_id: User identifier for targeting
        **attributes: Additional context attributes
    
    Returns:
        EvaluationContext instance
    """
    return EvaluationContext(
        targeting_key=user_id,
        attributes=attributes or {},
    )


async def evaluate_flag_with_fallback(
    client: Client,
    flag_name: str,
    default_value: Any,
    context: EvaluationContext,
    flag_type: str = "boolean",
) -> Any:
    """
    Wrapper that handles errors gracefully
    
    Args:
        client: OpenFeature client instance
        flag_name: Flag identifier
        default_value: Fallback value
        context: Evaluation context
        flag_type: Type of flag (boolean, string, integer, float, object)
    
    Returns:
        Evaluated flag value or default_value on error
    """
    try:
        if flag_type == "boolean":
            details = client.get_boolean_details(flag_name, default_value, context)
            return details.value
        elif flag_type == "string":
            details = client.get_string_details(flag_name, default_value, context)
            return details.value
        elif flag_type == "integer":
            details = client.get_integer_details(flag_name, default_value, context)
            return details.value
        elif flag_type == "float":
            details = client.get_float_details(flag_name, default_value, context)
            return details.value
        elif flag_type == "object":
            details = client.get_object_details(flag_name, default_value, context)
            return details.value
        else:
            logger.warning(f"Unknown flag type: {flag_type}, using default")
            return default_value
    except Exception as e:
        logger.error(f"Error evaluating flag {flag_name}: {e}", exc_info=True)
        return default_value


def map_unleash_context_to_openfeature(unleash_context: dict) -> EvaluationContext:
    """
    Convert Unleash context format to OpenFeature format
    
    Args:
        unleash_context: Unleash context dictionary
    
    Returns:
        EvaluationContext instance
    """
    targeting_key = unleash_context.get("userId")
    attributes = {k: v for k, v in unleash_context.items() if k != "userId"}
    
    return EvaluationContext(
        targeting_key=targeting_key,
        attributes=attributes,
    )


def map_openfeature_context_to_unleash(of_context: EvaluationContext) -> dict:
    """
    Convert OpenFeature context to Unleash format
    
    Args:
        of_context: OpenFeature EvaluationContext
    
    Returns:
        Unleash context dictionary
    """
    context = {}
    
    if of_context.targeting_key:
        context["userId"] = of_context.targeting_key
    
    if of_context.attributes:
        context.update(of_context.attributes)
    
    return context

