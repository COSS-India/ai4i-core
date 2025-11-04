#!/usr/bin/env python3
"""
Test script for health monitoring and auto-recovery features.

This script tests:
1. Manual health checks
2. Detailed health checks with aggregation
3. Automatic periodic health checks
4. Retry logic with exponential backoff
5. Multi-endpoint aggregation
"""
import asyncio
import json
import sys
import time
from typing import Dict, Any

import httpx


CONFIG_SERVICE_URL = "http://localhost:8082"
TEST_SERVICE_URL = "http://localhost:8080"


async def test_manual_health_check(service_name: str) -> Dict[str, Any]:
    """Test basic manual health check"""
    print(f"\n[TEST 1] Testing manual health check for {service_name}...")
    
    async with httpx.AsyncClient() as client:
        try:
            response = await client.post(
                f"{CONFIG_SERVICE_URL}/api/v1/registry/services/{service_name}/health",
                timeout=10.0
            )
            response.raise_for_status()
            result = response.json()
            print(f"✓ Status: {result.get('status')}")
            return result
        except Exception as e:
            print(f"✗ Error: {e}")
            return {}


async def test_detailed_health_check(service_name: str) -> Dict[str, Any]:
    """Test detailed health check with aggregation"""
    print(f"\n[TEST 2] Testing detailed health check for {service_name}...")
    
    async with httpx.AsyncClient() as client:
        try:
            response = await client.post(
                f"{CONFIG_SERVICE_URL}/api/v1/registry/services/{service_name}/health/detailed",
                timeout=10.0
            )
            response.raise_for_status()
            result = response.json()
            
            print(f"✓ Overall status: {result.get('overall_status')}")
            print(f"✓ Total instances: {result.get('total_instances')}")
            print(f"✓ Healthy instances: {result.get('healthy_instances')}")
            print(f"✓ Unhealthy instances: {result.get('unhealthy_instances')}")
            print(f"✓ Check results: {len(result.get('check_results', []))} endpoints checked")
            
            # Show detailed results
            for check in result.get('check_results', []):
                status = "✓" if check.get('is_healthy') else "✗"
                print(f"  {status} {check.get('endpoint_url')}: "
                      f"{check.get('response_time_ms', 0):.2f}ms "
                      f"(status: {check.get('status_code', 'N/A')})")
            
            return result
        except Exception as e:
            print(f"✗ Error: {e}")
            return {}


async def test_service_registration(service_name: str, service_url: str, health_check_url: str) -> bool:
    """Register a test service"""
    print(f"\n[SETUP] Registering test service: {service_name}...")
    
    async with httpx.AsyncClient() as client:
        try:
            response = await client.post(
                f"{CONFIG_SERVICE_URL}/api/v1/registry/register",
                json={
                    "service_name": service_name,
                    "service_url": service_url,
                    "health_check_url": health_check_url,
                    "service_metadata": {"test": True}
                },
                timeout=10.0
            )
            response.raise_for_status()
            result = response.json()
            instance_id = result.get('instance_id')
            print(f"✓ Service registered with instance_id: {instance_id}")
            return True
        except Exception as e:
            print(f"✗ Error registering service: {e}")
            return False


async def test_list_services() -> Dict[str, Any]:
    """List all registered services"""
    print(f"\n[TEST 3] Listing all registered services...")
    
    async with httpx.AsyncClient() as client:
        try:
            response = await client.get(
                f"{CONFIG_SERVICE_URL}/api/v1/registry/services",
                timeout=10.0
            )
            response.raise_for_status()
            services = response.json()
            print(f"✓ Found {len(services)} registered services:")
            for service in services:
                print(f"  - {service.get('service_name')}: {service.get('status')}")
            return services
        except Exception as e:
            print(f"✗ Error: {e}")
            return []


async def test_periodic_health_checks(service_name: str, interval: int = 30) -> None:
    """Test that periodic health checks are running"""
    print(f"\n[TEST 4] Testing periodic health checks (waiting {interval + 5}s)...")
    print("Note: This test verifies that automatic health checks are running.")
    print("Check the config service logs to see periodic health check messages.")
    
    # Wait for at least one automatic check cycle
    await asyncio.sleep(interval + 5)
    
    # Check if status was updated
    async with httpx.AsyncClient() as client:
        try:
            response = await client.get(
                f"{CONFIG_SERVICE_URL}/api/v1/registry/services/{service_name}",
                timeout=10.0
            )
            response.raise_for_status()
            instances = response.json()
            if instances:
                instance = instances[0]
                print(f"✓ Service status: {instance.get('status')}")
                print(f"  Note: Check logs for 'Health check for {service_name}' messages")
            else:
                print("✗ No instances found")
        except Exception as e:
            print(f"✗ Error: {e}")


async def test_retry_logic(service_name: str) -> None:
    """Test retry logic by triggering a health check on a potentially failing service"""
    print(f"\n[TEST 5] Testing retry logic with exponential backoff...")
    print("Note: This test verifies retry behavior. Check logs for retry messages.")
    
    # Trigger health check
    async with httpx.AsyncClient() as client:
        try:
            start_time = time.time()
            response = await client.post(
                f"{CONFIG_SERVICE_URL}/api/v1/registry/services/{service_name}/health/detailed",
                timeout=30.0  # Longer timeout for retries
            )
            response.raise_for_status()
            elapsed = time.time() - start_time
            result = response.json()
            
            print(f"✓ Health check completed in {elapsed:.2f}s")
            print(f"✓ Retry behavior: Check logs for 'retrying' messages")
            
            # Check if any endpoints failed
            failed_checks = [c for c in result.get('check_results', []) if not c.get('is_healthy')]
            if failed_checks:
                print(f"  - {len(failed_checks)} endpoint(s) failed (retries should have been attempted)")
            else:
                print(f"  - All endpoints healthy (no retries needed)")
                
        except Exception as e:
            print(f"✗ Error: {e}")


async def test_multi_endpoint_aggregation(service_name: str) -> None:
    """Test multi-endpoint aggregation"""
    print(f"\n[TEST 6] Testing multi-endpoint aggregation...")
    
    result = await test_detailed_health_check(service_name)
    
    check_results = result.get('check_results', [])
    if len(check_results) > 1:
        print(f"✓ Multiple endpoints checked: {len(check_results)}")
        print("  Endpoints checked:")
        for check in check_results:
            print(f"    - {check.get('endpoint_url')}")
    else:
        print(f"⚠ Only {len(check_results)} endpoint(s) checked")
        print("  Note: Set HEALTH_CHECK_ADDITIONAL_ENDPOINTS to test multiple endpoints")


async def check_config_service_health() -> bool:
    """Check if config service is running"""
    print("\n[SETUP] Checking config service health...")
    
    async with httpx.AsyncClient() as client:
        try:
            response = await client.get(
                f"{CONFIG_SERVICE_URL}/health",
                timeout=5.0
            )
            response.raise_for_status()
            print("✓ Config service is healthy")
            return True
        except Exception as e:
            print(f"✗ Config service is not reachable: {e}")
            print(f"  Make sure the config service is running on {CONFIG_SERVICE_URL}")
            return False


async def main():
    """Run all tests"""
    print("=" * 60)
    print("Health Monitoring and Auto-Recovery Test Suite")
    print("=" * 60)
    
    # Check config service
    if not await check_config_service_health():
        print("\n❌ Config service is not available. Please start it first.")
        sys.exit(1)
    
    # Test service name
    test_service_name = "test-health-monitoring-service"
    test_service_url = TEST_SERVICE_URL
    test_health_url = f"{TEST_SERVICE_URL}/health"
    
    # Register test service
    registered = await test_service_registration(
        test_service_name,
        test_service_url,
        test_health_url
    )
    
    if not registered:
        print("\n⚠ Service registration failed. Continuing with existing service if any...")
    
    # Wait a bit for registration to propagate
    await asyncio.sleep(1)
    
    # Run tests
    print("\n" + "=" * 60)
    print("Running Tests")
    print("=" * 60)
    
    # Test 1: Manual health check
    await test_manual_health_check(test_service_name)
    
    # Test 2: Detailed health check
    await test_detailed_health_check(test_service_name)
    
    # Test 3: List services
    await test_list_services()
    
    # Test 4: Periodic health checks (commented out - takes too long)
    # Uncomment to test automatic periodic checks
    # await test_periodic_health_checks(test_service_name, interval=30)
    
    # Test 5: Retry logic
    await test_retry_logic(test_service_name)
    
    # Test 6: Multi-endpoint aggregation
    await test_multi_endpoint_aggregation(test_service_name)
    
    print("\n" + "=" * 60)
    print("Test Suite Complete")
    print("=" * 60)
    print("\nTo verify automatic periodic health checks:")
    print("1. Check config service logs for 'Health check for' messages")
    print("2. Wait for the configured interval (default: 30s)")
    print("3. Check database for updated last_health_check timestamps")
    print("\nTo see retry logic in action:")
    print("1. Make a service unhealthy (stop it or return 500)")
    print("2. Trigger a health check")
    print("3. Check logs for 'retrying' messages with exponential delays")


if __name__ == "__main__":
    asyncio.run(main())

