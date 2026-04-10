#!/usr/bin/env python3
"""
Test script to query Triton servers and list available models
Fetches NMT services from model management service and tests their Triton endpoints
"""

import os
import sys
import asyncio

# Add the parent directory to the path so app.* imports work
parent_dir = os.path.dirname(os.path.dirname(os.path.abspath(__file__)))
sys.path.insert(0, parent_dir)

from ai4icore_env import app_env

# Check if tritonclient is available
try:
    import tritonclient.http as http_client
except ImportError:
    print("Error: tritonclient module not found. Please install dependencies:")
    print("  pip install tritonclient[http]")
    sys.exit(1)

from ai4icore_model_management import TritonClient, ModelManagementClient


def test_triton_endpoint(endpoint: str, service_id: str = None, expected_model: str = None):
    """Test a specific Triton endpoint"""
    if service_id:
        print(f"Service: {service_id}")
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
                marker = " ← Expected" if expected_model and model == expected_model else ""
                print(f"    - {model}{marker}")
            
            # Check if expected model exists
            if expected_model:
                exists = expected_model in models if models else False
                status = "✓ FOUND" if exists else "✗ NOT FOUND"
                print(f"  Expected Model '{expected_model}': {status}")
        else:
            print(f"  Warning: Server not ready, cannot list models")
            
    except Exception as e:
        print(f"  Error: {e}")
        import traceback
        traceback.print_exc()
    
    print()


async def test_all_nmt_services():
    """Fetch all NMT services from model management and test their Triton endpoints"""
    
    print("=" * 80)
    print("Triton Model Discovery Test")
    print("=" * 80)
    print()
    
    # Initialize model management client
    model_mgmt_url = app_env.model_management_service_url
    model_mgmt_api_key = app_env.model_management_service_api_key
    
    print(f"Connecting to Model Management Service: {model_mgmt_url}")
    print()
    
    client = ModelManagementClient(
        base_url=model_mgmt_url,
        api_key=model_mgmt_api_key,
        cache_ttl_seconds=0  # Don't cache for testing
    )
    
    try:
        # Fetch all NMT services
        print("Fetching NMT services from model management service...")
        services = await client.list_services(
            use_cache=False,
            task_type="nmt"
        )
        
        if not services:
            print("No NMT services found in model management service.")
            print()
            print("You can also test a specific endpoint directly:")
            print("  python test_triton_models.py <endpoint_url>")
            await client.close()
            return
        
        print(f"Found {len(services)} NMT service(s)")
        print()
        
        # Get unique endpoints
        unique_endpoints = {}
        for service in services:
            if service.endpoint:
                endpoint = service.endpoint
                if endpoint not in unique_endpoints:
                    unique_endpoints[endpoint] = []
                unique_endpoints[endpoint].append({
                    "service_id": service.service_id,
                    "model_name": service.triton_model or "nmt"
                })
        
        print("-" * 80)
        print("Querying Triton Servers...")
        print("-" * 80)
        print()
        
        # Test each unique endpoint
        for endpoint, service_info_list in unique_endpoints.items():
            # Use the first service's expected model name
            expected_model = service_info_list[0]["model_name"]
            service_id = service_info_list[0]["service_id"]
            
            if len(service_info_list) > 1:
                print(f"Note: Multiple services use this endpoint:")
                for info in service_info_list:
                    print(f"  - {info['service_id']} (model: {info['model_name']})")
                print()
            
            test_triton_endpoint(endpoint, service_id, expected_model)
        
        await client.close()
        
    except Exception as e:
        print(f"Error fetching services from model management service: {e}")
        import traceback
        traceback.print_exc()
        await client.close()
        print()
        print("Falling back to direct endpoint testing...")
        print("Usage: python test_triton_models.py <endpoint_url>")
        return


def test_single_endpoint(endpoint: str):
    """Test a single endpoint provided as argument"""
    print("-" * 80)
    print("Querying Triton Server...")
    print("-" * 80)
    print()
    
    test_triton_endpoint(endpoint)


def main():
    """Main entry point"""
    # Check if endpoint provided as argument
    if len(sys.argv) > 1:
        endpoint = sys.argv[1]
        test_single_endpoint(endpoint)
    elif app_env.triton_endpoint:
        endpoint = app_env.triton_endpoint
        test_single_endpoint(endpoint)
    else:
        # Fetch from model management service
        asyncio.run(test_all_nmt_services())
    
    print("=" * 80)
    print("Test Complete")
    print("=" * 80)


if __name__ == "__main__":
    main()

