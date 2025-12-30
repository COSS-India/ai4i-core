"""
AI4ICore Model Management Client
Reusable client library for model management service integration
"""

from .client import ModelManagementClient, ServiceInfo
from .auth_utils import extract_auth_headers

__version__ = "0.1.0"
__all__ = ["ModelManagementClient", "ServiceInfo", "extract_auth_headers"]

