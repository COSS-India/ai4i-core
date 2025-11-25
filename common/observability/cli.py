"""
Command line interface for Dhruva Observability Plugin
"""
import argparse
import sys
from .config import PluginConfig
from .metrics import MetricsCollector


def main():
    """Main CLI entry point."""
    parser = argparse.ArgumentParser(description="Dhruva Observability Plugin CLI")
    parser.add_argument("--version", action="version", version="1.0.3")
    parser.add_argument("--config", help="Show current configuration")
    parser.add_argument("--metrics", help="Show current metrics")
    parser.add_argument("--health", help="Check plugin health")
    
    args = parser.parse_args()
    
    if args.config:
        config = PluginConfig()
        print("Current Configuration:")
        print(f"  Enabled: {config.enabled}")
        print(f"  Debug: {config.debug}")
        print(f"  Customers: {config.customers}")
        print(f"  Apps: {config.apps}")
        print(f"  Metrics Path: {config.metrics_path}")
        print(f"  Health Path: {config.health_path}")
    
    elif args.metrics:
        metrics = MetricsCollector()
        print("Current Metrics:")
        print(metrics.get_metrics_text())
    
    elif args.health:
        config = PluginConfig()
        print("Plugin Health:")
        print(f"  Status: {'Healthy' if config.enabled else 'Disabled'}")
        print(f"  Version: 1.0.3")
        print(f"  Configuration: {'Valid' if config.enabled else 'Disabled'}")
    
    else:
        parser.print_help()


if __name__ == "__main__":
    main()
