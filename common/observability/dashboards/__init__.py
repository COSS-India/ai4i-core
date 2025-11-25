"""
Grafana dashboards for Dhruva Observability Plugin

Provides pre-built Grafana dashboards for enterprise monitoring.
"""
import os
import json
from pathlib import Path

# Get the package directory
PACKAGE_DIR = Path(__file__).parent

def get_dashboard_path(dashboard_name: str) -> str:
    """Get the path to a dashboard JSON file."""
    return str(PACKAGE_DIR / f"{dashboard_name}.json")

def get_dashboard_json(dashboard_name: str) -> dict:
    """Load a dashboard JSON file and return as dict."""
    dashboard_path = get_dashboard_path(dashboard_name)
    with open(dashboard_path, 'r') as f:
        return json.load(f)

def list_available_dashboards() -> list:
    """List all available dashboard files."""
    dashboard_dir = PACKAGE_DIR
    return [f.stem for f in dashboard_dir.glob("*.json")]
