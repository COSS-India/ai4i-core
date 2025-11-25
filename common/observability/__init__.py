"""
Dhruva Observability Plugin

This package provides enterprise-grade observability features for the Dhruva Platform,
including comprehensive metrics, monitoring, and business analytics.

Universal Framework Support:
- FastAPI: ObservabilityPlugin (built-in)
- Flask: FlaskObservabilityAdapter
- Django: DjangoObservabilityAdapter
- Generic: GenericObservabilityAdapter
- Manual: ManualObservabilityAdapter
"""

__version__ = "1.0.9"
__author__ = "AI4X Team"
__email__ = "team@ai4x.com"

from .plugin import ObservabilityPlugin
from .metrics import MetricsCollector
from .config import PluginConfig
from .middleware import ObservabilityMiddleware

# Import adapters for universal framework support
# from .adapters import (
#     FlaskObservabilityAdapter,
#     DjangoObservabilityAdapter,
#     DjangoObservabilityMiddleware,
#     GenericObservabilityAdapter,
#     ManualObservabilityAdapter,
# )

# Import dashboard utilities
from .dashboards import (
    get_dashboard_path,
    get_dashboard_json,
    list_available_dashboards
)

__all__ = [
    "ObservabilityPlugin",
    "MetricsCollector", 
    "PluginConfig",
    "ObservabilityMiddleware",
    # # Framework adapters
    # "FlaskObservabilityAdapter",
    # "DjangoObservabilityAdapter",
    # "DjangoObservabilityMiddleware", 
    # "GenericObservabilityAdapter",
    # "ManualObservabilityAdapter",
    # Dashboard utilities
    "get_dashboard_path",
    "get_dashboard_json"
    "list_available_dashboards",
    # "AVAILABLE_DASHBOARDS",
]
