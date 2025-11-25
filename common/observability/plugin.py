"""
Main Observability Plugin for Dhruva Platform

Provides enterprise-grade observability features including metrics, monitoring,
and business analytics for the Dhruva Platform.
"""
from typing import Optional, Dict, Any
from fastapi import FastAPI, Response
from fastapi.responses import JSONResponse
from .metrics import MetricsCollector, prometheus_latest_text
from .config import PluginConfig
from .middleware import ObservabilityMiddleware


class ObservabilityPlugin:
    """Main plugin class for Dhruva Observability."""
    
    def __init__(self, config: Optional[PluginConfig] = None):
        """Initialize the observability plugin."""
        self.config = config or PluginConfig()
        self.metrics = MetricsCollector(config=self.config.to_dict())
        self._initialized = False
    
    def register_middleware(self, app: FastAPI) -> None:
        """Register middleware with FastAPI application."""
        if not self.config.enabled:
            return
        
        # Add middleware to the app using the correct FastAPI pattern
        app.add_middleware(
            ObservabilityMiddleware,
            metrics_collector=self.metrics,
            config=self.config
        )
        
        if self.config.debug:
            print("✅ Dhruva Observability middleware registered")
    
    def register_endpoints(self, app: FastAPI) -> None:
        """Register enterprise endpoints with FastAPI application."""
        if not self.config.enabled:
            return
        
        # Metrics endpoint
        @app.get(self.config.metrics_path)
        async def metrics_endpoint():
            """Prometheus metrics endpoint."""
            return Response(
                content=self.metrics.get_metrics_text(),
                media_type="text/plain"
            )
        
        # Health endpoint
        @app.get(self.config.health_path)
        async def health_endpoint():
            """Health check endpoint."""
            return JSONResponse({
                "status": "healthy",
                "plugin": "dhruva-enterprise",
                "version": "1.0.3",
                "enabled": self.config.enabled,
                "customers": self.config.customers,
                "apps": self.config.apps
            })
        
        # Configuration endpoint
        @app.get("/enterprise/config")
        async def config_endpoint():
            """Configuration endpoint."""
            return JSONResponse(self.config.to_dict())
        
        if self.config.debug:
            print("✅ Dhruva Observability endpoints registered")
    
    def register_plugin(self, app: FastAPI) -> None:
        """Register the complete plugin with FastAPI application."""
        if not self.config.enabled:
            if self.config.debug:
                print("⚠️  Dhruva Observability plugin is disabled")
            return
        
        self.register_middleware(app)
        self.register_endpoints(app)
        
        # Initialize customer quotas
        self._initialize_customer_quotas()
        
        self._initialized = True
        
        if self.config.debug:
            print("🚀 Dhruva Observability plugin initialized successfully")
    
    def _initialize_customer_quotas(self):
        """Initialize customer quotas."""
        try:
            for customer in self.config.customers:
                # MetricsCollector exposes update_organization_quotas (not update_customer_quotas)
                # call the correct method and pass the organization name
                self.metrics.update_organization_quotas(
                    organization=customer,
                    llm_quota=1000000,  # 1M tokens per month
                    tts_quota=1000000,  # 1M characters per month
                    nmt_quota=1000000,  # 1M characters per month
                    asr_quota=1000000   # 1M audio-seconds per month (approx)
                )
        except Exception as e:
            if self.config.debug:
                print(f"⚠️ Customer quota initialization failed: {e}")
    
    def get_metrics_collector(self) -> MetricsCollector:
        """Get the metrics collector instance."""
        return self.metrics
    
    def get_config(self) -> PluginConfig:
        """Get the configuration instance."""
        return self.config
    
    def is_initialized(self) -> bool:
        """Check if plugin is initialized."""
        return self._initialized
    
    def update_config(self, new_config: Dict[str, Any]) -> None:
        """Update plugin configuration."""
        self.config = PluginConfig.from_dict(new_config)
        if self.config.debug:
            print("📝 Configuration updated")
    
    def get_status(self) -> Dict[str, Any]:
        """Get plugin status information."""
        return {
            "initialized": self._initialized,
            "enabled": self.config.enabled,
            "debug": self.config.debug,
            "customers": self.config.customers,
            "apps": self.config.apps,
            "metrics_path": self.config.metrics_path,
            "health_path": self.config.health_path,
        }


# Convenience function for easy integration
def create_observability_plugin(config: Optional[PluginConfig] = None) -> ObservabilityPlugin:
    """Create and return an ObservabilityPlugin instance."""
    return ObservabilityPlugin(config)


def register_observability_plugin(app: FastAPI, config: Optional[PluginConfig] = None) -> ObservabilityPlugin:                                                                                                          
    """Create and register observability plugin with FastAPI app."""
    plugin = ObservabilityPlugin(config)
    plugin.register_plugin(app)
    return plugin
