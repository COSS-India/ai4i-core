"""
Example code showing how other services can consume feature flags
"""
import httpx
import asyncio
from typing import Optional, Dict, Any


class FeatureFlagClient:
    """
    HTTP API client for feature flag evaluation
    
    Example usage:
        client = FeatureFlagClient("http://config-service:8082")
        enabled = await client.is_enabled("new-ui-enabled", user_id="user-123")
    """
    
    def __init__(self, config_service_url: str):
        self.base_url = f"{config_service_url}/api/v1/feature-flags"
    
    async def is_enabled(
        self,
        flag_name: str,
        user_id: Optional[str] = None,
        context: Dict[str, Any] = None,
        environment: str = "development",
    ) -> bool:
        """
        Evaluate a boolean feature flag
        
        Args:
            flag_name: Name of the feature flag
            user_id: User identifier for targeting
            context: Additional context attributes
            environment: Environment name
        
        Returns:
            Boolean indicating if flag is enabled
        """
        async with httpx.AsyncClient() as client:
            response = await client.post(
                f"{self.base_url}/evaluate/boolean",
                json={
                    "flag_name": flag_name,
                    "user_id": user_id,
                    "context": context or {},
                    "default_value": False,
                    "environment": environment,
                },
            )
            response.raise_for_status()
            return response.json()["value"]


# Example 1: HTTP API Client Usage
async def example_http_client():
    """Example using HTTP API client"""
    client = FeatureFlagClient("http://config-service:8082")
    
    # Simple boolean flag
    enabled = await client.is_enabled("new-ui-enabled", user_id="user-123")
    if enabled:
        print("Show new UI")
    
    # With context
    enabled = await client.is_enabled(
        "premium-features",
        user_id="user-456",
        context={"subscription_tier": "gold", "region": "us-west"},
    )
    if enabled:
        print("Show premium features")


# Example 2: Direct OpenFeature SDK Usage
def example_openfeature_sdk():
    """
    Example using OpenFeature SDK directly
    
    Note: This requires the OpenFeature SDK to be initialized in the service.
    The provider is set up in config-service, but other services would need
    to configure their own provider or use HTTP API.
    """
    from openfeature import api
    from openfeature.evaluation_context import EvaluationContext
    
    # Initialize once at application startup
    # Provider is already set up in config-service
    # Other services can use a simple HTTP provider or shared client
    pass


def check_feature(flag_name: str, user_id: str = None, **context) -> bool:
    """
    Helper function to check feature flag using OpenFeature SDK
    
    Args:
        flag_name: Feature flag name
        user_id: User identifier
        **context: Additional context attributes
    
    Returns:
        Boolean flag value
    """
    from openfeature import api
    from openfeature.evaluation_context import EvaluationContext
    
    client = api.get_client()
    ctx = EvaluationContext(
        targeting_key=user_id,
        attributes=context,
    )
    return client.get_boolean_value(flag_name, False, ctx)


# Example 3: Gradual Rollout
async def gradual_rollout_example():
    """Example of gradual rollout usage"""
    client = FeatureFlagClient("http://config-service:8082")
    
    # This flag might be enabled for 25% of users
    enabled = await client.is_enabled(
        "new-algorithm",
        user_id="user-123",  # Consistent user_id ensures sticky behavior
        environment="production",
    )
    
    if enabled:
        return new_algorithm()
    else:
        return old_algorithm()


def new_algorithm():
    """Placeholder for new algorithm"""
    return "new algorithm result"


def old_algorithm():
    """Placeholder for old algorithm"""
    return "old algorithm result"


if __name__ == "__main__":
    # Run HTTP client example
    asyncio.run(example_http_client())
    
    # Example usage of check_feature helper
    if check_feature("dark-mode", user_id="user-789", theme_preference="dark"):
        print("Enable dark mode")

