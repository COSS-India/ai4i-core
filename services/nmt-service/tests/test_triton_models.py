#!/usr/bin/env python3
"""
Test script to query Triton servers and list available models
This helps identify the correct model names for each endpoint
"""

import sys
import os

# Check if tritonclient is available
try:
    import tritonclient.http as http_client
except ImportError:
    print("Error: tritonclient module not found. Please install dependencies:")
    print("  pip install tritonclient[http]")
    sys.exit(1)

# Add the parent directory to the path to import modules
# (test file is in tests/ subdirectory, need to go up one level)
parent_dir = os.path.dirname(os.path.dirname(os.path.abspath(__file__)))
sys.path.insert(0, parent_dir)

from utils.triton_client import TritonClient
from services.nmt_service import NMTService


def test_triton_models():
    """Query all Triton endpoints and list available models"""
    
    print("=" * 80)
    print("Triton Model Discovery Test")
    print("=" * 80)
    print()
    
    # Get all unique endpoints from service registry
    unique_endpoints = set()
    for service_id, (endpoint, model_name) in NMTService.SERVICE_REGISTRY.items():
        unique_endpoints.add(endpoint)
        print(f"Service '{service_id}' -> Endpoint: {endpoint}, Model: {model_name}")
    
    print()
    print("-" * 80)
    print("Querying Triton Servers...")
    print("-" * 80)
    print()
    
    for endpoint in unique_endpoints:
        print(f"Endpoint: {endpoint}")
        print("-" * 40)
        
        try:
            # Create Triton client
            triton_client = TritonClient(triton_url=endpoint)
            
            # Check if server is ready
            is_ready = triton_client.is_server_ready()
            print(f"  Server Ready: {is_ready}")
            
            if is_ready:
                # List available models
                models = triton_client.list_models()
                print(f"  Available Models ({len(models)}):")
                for model in models:
                    print(f"    - {model}")
                
                # Check which models from registry exist
                print(f"  Registry Model Check:")
                for service_id, (ep, model_name) in NMTService.SERVICE_REGISTRY.items():
                    if ep == endpoint:
                        exists = model_name in models if models else False
                        status = "✓ FOUND" if exists else "✗ NOT FOUND"
                        print(f"    - '{model_name}' ({service_id}): {status}")
            else:
                print(f"  Warning: Server not ready, cannot list models")
                
        except Exception as e:
            print(f"  Error: {e}")
            import traceback
            traceback.print_exc()
        
        print()
    
    print("=" * 80)
    print("Test Complete")
    print("=" * 80)


if __name__ == "__main__":
    test_triton_models()

