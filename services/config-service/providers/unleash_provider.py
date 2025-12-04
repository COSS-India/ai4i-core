"""
OpenFeature provider implementation for Unleash
"""
import logging
from typing import Any, Dict, List, Optional

from openfeature.evaluation_context import EvaluationContext
from openfeature.flag_evaluation import FlagEvaluationDetails, FlagResolutionDetails, FlagType, Reason
from openfeature.provider import AbstractProvider, Metadata
from UnleashClient import UnleashClient
from UnleashClient.constants import FEATURES_URL

logger = logging.getLogger(__name__)


class UnleashFeatureProvider(AbstractProvider):
    """OpenFeature provider that wraps Unleash Python SDK"""

    def __init__(
        self,
        url: str,
        app_name: str,
        instance_id: str,
        api_token: str,
        environment: str = "development",
        refresh_interval: int = 15,
        metrics_interval: int = 60,
        disable_metrics: bool = False,
    ):
        """
        Initialize Unleash provider

        Args:
            url: Unleash server URL (e.g., http://unleash:4242/feature-flags/api)
            app_name: Application name
            instance_id: Instance identifier
            api_token: API token for authentication
            environment: Environment name (development/staging/production)
            refresh_interval: Flag refresh interval in seconds
            metrics_interval: Metrics reporting interval in seconds
            disable_metrics: Whether to disable metrics
        """
        self.url = url
        self.app_name = app_name
        self.instance_id = instance_id
        self.api_token = api_token
        self.environment = environment
        self.refresh_interval = refresh_interval
        self.metrics_interval = metrics_interval
        self.disable_metrics = disable_metrics
        self.client: Optional[UnleashClient] = None
        self._initialized = False

    def get_metadata(self) -> Metadata:
        """Return provider metadata"""
        return Metadata(name="UnleashProvider")

    def get_provider_hooks(self) -> List:
        """Return provider hooks (empty for now)"""
        return []

    def initialize(self, evaluation_context: EvaluationContext) -> None:
        """Initialize the Unleash client"""
        try:
            self.client = UnleashClient(
                url=self.url,
                app_name=self.app_name,
                instance_id=self.instance_id,
                custom_headers={"Authorization": self.api_token},
                refresh_interval=self.refresh_interval,
                metrics_interval=self.metrics_interval,
                disable_metrics=self.disable_metrics,
                environment=self.environment,
            )
            self.client.initialize_client()
            self._initialized = True
            logger.info(f"Unleash provider initialized for {self.app_name}")
        except Exception as e:
            logger.error(f"Failed to initialize Unleash client: {e}", exc_info=True)
            self._initialized = False
            raise

    def shutdown(self) -> None:
        """Shutdown the Unleash client gracefully"""
        if self.client:
            try:
                self.client.destroy()
                logger.info("Unleash client shutdown complete")
            except Exception as e:
                logger.warning(f"Error shutting down Unleash client: {e}")
            finally:
                self.client = None
                self._initialized = False

    def _build_unleash_context(self, evaluation_context: EvaluationContext) -> Dict[str, Any]:
        """Map OpenFeature EvaluationContext to Unleash context format"""
        context = {}
        
        # Map targeting_key to userId
        if evaluation_context.targeting_key:
            context["userId"] = evaluation_context.targeting_key
        
        # Map sessionId if present
        if hasattr(evaluation_context, "session_id") and evaluation_context.session_id:
            context["sessionId"] = evaluation_context.session_id
        
        # Map all attributes to properties
        if evaluation_context.attributes:
            for key, value in evaluation_context.attributes.items():
                context[key] = value
        
        # Use environment from context attributes if provided, otherwise use default
        # This allows per-request environment selection
        if evaluation_context.attributes and "environment" in evaluation_context.attributes:
            context["environment"] = evaluation_context.attributes["environment"]
        else:
            context["environment"] = self.environment
        
        return context

    def _map_reason(self, enabled: bool, variant_enabled: Optional[bool] = None) -> str:
        """Map Unleash result to OpenFeature reason"""
        if variant_enabled is False:
            return Reason.DISABLED
        if enabled:
            return Reason.TARGETING_MATCH
        return Reason.DEFAULT

    def resolve_boolean_details(
        self,
        flag_key: str,
        default_value: bool,
        evaluation_context: EvaluationContext,
    ) -> FlagResolutionDetails[bool]:
        """Resolve boolean flag value"""
        try:
            if not self._initialized or not self.client:
                logger.warning("Unleash client not initialized, returning default")
                return FlagResolutionDetails(
                    value=default_value,
                    reason=Reason.ERROR,
                )
            
            unleash_context = self._build_unleash_context(evaluation_context)
            is_enabled = self.client.is_enabled(flag_key, unleash_context, default_value)
            
            reason = self._map_reason(is_enabled)
            
            return FlagResolutionDetails(
                value=is_enabled,
                reason=reason,
            )
        except Exception as e:
            logger.error(f"Error evaluating boolean flag {flag_key}: {e}", exc_info=True)
            return FlagResolutionDetails(
                value=default_value,
                reason=Reason.ERROR,
            )

    def resolve_string_details(
        self,
        flag_key: str,
        default_value: str,
        evaluation_context: EvaluationContext,
    ) -> FlagResolutionDetails[str]:
        """Resolve string flag value (variant)"""
        try:
            if not self._initialized or not self.client:
                logger.warning("Unleash client not initialized, returning default")
                return FlagResolutionDetails(
                    value=default_value,
                    reason=Reason.ERROR,
                )
            
            unleash_context = self._build_unleash_context(evaluation_context)
            variant = self.client.get_variant(flag_key, unleash_context)
            
            variant_name = None
            if variant and variant.enabled:
                variant_name = variant.name
                value = variant.name if variant.name else default_value
                if variant.payload and variant.payload.get("value"):
                    value = str(variant.payload["value"])
                reason = Reason.TARGETING_MATCH
            else:
                value = default_value
                reason = Reason.DEFAULT
            
            return FlagResolutionDetails(
                value=value,
                reason=reason,
                variant=variant_name,
            )
        except Exception as e:
            logger.error(f"Error evaluating string flag {flag_key}: {e}", exc_info=True)
            return FlagResolutionDetails(
                value=default_value,
                reason=Reason.ERROR,
            )

    def resolve_integer_details(
        self,
        flag_key: str,
        default_value: int,
        evaluation_context: EvaluationContext,
    ) -> FlagResolutionDetails[int]:
        """Resolve integer flag value"""
        try:
            if not self._initialized or not self.client:
                logger.warning("Unleash client not initialized, returning default")
                return FlagResolutionDetails(
                    value=default_value,
                    reason=Reason.ERROR,
                )
            
            unleash_context = self._build_unleash_context(evaluation_context)
            variant = self.client.get_variant(flag_key, unleash_context)
            
            if variant and variant.enabled and variant.payload:
                try:
                    payload_value = variant.payload.get("value")
                    if payload_value is not None:
                        value = int(payload_value)
                        reason = Reason.TARGETING_MATCH
                    else:
                        value = default_value
                        reason = Reason.DEFAULT
                except (ValueError, TypeError):
                    value = default_value
                    reason = Reason.ERROR
            else:
                value = default_value
                reason = Reason.DEFAULT
            
            return FlagResolutionDetails(
                value=value,
                reason=reason,
            )
        except Exception as e:
            logger.error(f"Error evaluating integer flag {flag_key}: {e}", exc_info=True)
            return FlagResolutionDetails(
                value=default_value,
                reason=Reason.ERROR,
            )

    def resolve_float_details(
        self,
        flag_key: str,
        default_value: float,
        evaluation_context: EvaluationContext,
    ) -> FlagResolutionDetails[float]:
        """Resolve float flag value"""
        try:
            if not self._initialized or not self.client:
                logger.warning("Unleash client not initialized, returning default")
                return FlagResolutionDetails(
                    value=default_value,
                    reason=Reason.ERROR,
                )
            
            unleash_context = self._build_unleash_context(evaluation_context)
            variant = self.client.get_variant(flag_key, unleash_context)
            
            if variant and variant.enabled and variant.payload:
                try:
                    payload_value = variant.payload.get("value")
                    if payload_value is not None:
                        value = float(payload_value)
                        reason = Reason.TARGETING_MATCH
                    else:
                        value = default_value
                        reason = Reason.DEFAULT
                except (ValueError, TypeError):
                    value = default_value
                    reason = Reason.ERROR
            else:
                value = default_value
                reason = Reason.DEFAULT
            
            return FlagResolutionDetails(
                value=value,
                reason=reason,
            )
        except Exception as e:
            logger.error(f"Error evaluating float flag {flag_key}: {e}", exc_info=True)
            return FlagResolutionDetails(
                value=default_value,
                reason=Reason.ERROR,
            )

    def resolve_object_details(
        self,
        flag_key: str,
        default_value: dict,
        evaluation_context: EvaluationContext,
    ) -> FlagResolutionDetails[dict]:
        """Resolve object flag value (JSON)"""
        try:
            if not self._initialized or not self.client:
                logger.warning("Unleash client not initialized, returning default")
                return FlagResolutionDetails(
                    value=default_value,
                    reason=Reason.ERROR,
                )
            
            unleash_context = self._build_unleash_context(evaluation_context)
            variant = self.client.get_variant(flag_key, unleash_context)
            
            variant_name = None
            if variant and variant.enabled and variant.payload:
                variant_name = variant.name
                try:
                    payload_value = variant.payload.get("value")
                    if payload_value is not None:
                        import json
                        if isinstance(payload_value, str):
                            value = json.loads(payload_value)
                        elif isinstance(payload_value, dict):
                            value = payload_value
                        else:
                            value = default_value
                        reason = Reason.TARGETING_MATCH
                    else:
                        value = default_value
                        reason = Reason.DEFAULT
                except (json.JSONDecodeError, TypeError, ValueError):
                    value = default_value
                    reason = Reason.ERROR
            else:
                value = default_value
                reason = Reason.DEFAULT
            
            return FlagResolutionDetails(
                value=value,
                reason=reason,
                variant=variant_name,
            )
        except Exception as e:
            logger.error(f"Error evaluating object flag {flag_key}: {e}", exc_info=True)
            return FlagResolutionDetails(
                value=default_value,
                reason=Reason.ERROR,
            )

