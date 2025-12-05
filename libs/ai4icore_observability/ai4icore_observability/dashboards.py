"""
Dashboard utilities for AI4ICore Observability Plugin
"""
import os
from typing import List, Dict, Any, Optional
from pathlib import Path


def get_dashboard_path(dashboard_name: str) -> Optional[str]:
    """
    Get the path to a dashboard JSON file.
    
    Args:
        dashboard_name: Name of the dashboard
    
    Returns:
        Path to dashboard JSON file or None if not found
    """
    # Default dashboard directory
    dashboard_dir = os.getenv(
        "AI4ICORE_DASHBOARD_DIR",
        os.path.join(os.path.dirname(__file__), "dashboards")
    )
    
    dashboard_path = os.path.join(dashboard_dir, f"{dashboard_name}.json")
    
    if os.path.exists(dashboard_path):
        return dashboard_path
    
    return None


def get_dashboard_json(dashboard_name: str) -> Optional[Dict[str, Any]]:
    """
    Get dashboard JSON content.
    
    Args:
        dashboard_name: Name of the dashboard
    
    Returns:
        Dashboard JSON as dictionary or None if not found
    """
    import json
    
    dashboard_path = get_dashboard_path(dashboard_name)
    if not dashboard_path:
        return None
    
    try:
        with open(dashboard_path, 'r') as f:
            return json.load(f)
    except Exception:
        return None


def list_available_dashboards() -> List[str]:
    """
    List all available dashboards.
    
    Returns:
        List of dashboard names
    """
    dashboard_dir = os.getenv(
        "AI4ICORE_DASHBOARD_DIR",
        os.path.join(os.path.dirname(__file__), "dashboards")
    )
    
    if not os.path.exists(dashboard_dir):
        return []
    
    dashboards = []
    for file in os.listdir(dashboard_dir):
        if file.endswith('.json'):
            dashboards.append(file[:-5])  # Remove .json extension
    
    return dashboards

