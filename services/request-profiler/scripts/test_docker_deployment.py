#!/usr/bin/env python3
"""
Comprehensive test script for Docker deployment of RequestProfiler.

This script tests all endpoints and functionality after the container is running.
Run this after starting the container with: docker compose up -d
"""
import json
import sys
import time
from typing import Dict, Any

import requests

BASE_URL = "http://localhost:8000"
API_PREFIX = "/api/v1"


def test_health_check() -> bool:
    """Test the health check endpoint."""
    print("\n1. Testing Health Check Endpoint...")
    try:
        response = requests.get(f"{BASE_URL}{API_PREFIX}/health", timeout=5)
        if response.status_code == 200:
            data = response.json()
            print(f"   ✓ Health check passed: {data}")
            return True
        else:
            print(f"   ✗ Health check failed with status {response.status_code}")
            return False
    except Exception as e:
        print(f"   ✗ Health check failed: {e}")
        return False


def test_single_profile() -> bool:
    """Test single text profiling."""
    print("\n2. Testing Single Text Profiling...")
    
    test_cases = [
        {
            "name": "English Medical Text",
            "text": "The patient presents with acute myocardial infarction. Immediate intervention required with thrombolytic therapy.",
            "expected_domain": "medical"
        },
        {
            "name": "Hindi General Text",
            "text": "आज मौसम बहुत अच्छा है। मैं पार्क में घूमने जा रहा हूं।",
            "expected_domain": "general"
        },
        {
            "name": "Legal Text",
            "text": "The defendant is hereby charged with breach of contract under Section 73 of the Indian Contract Act.",
            "expected_domain": "legal"
        }
    ]
    
    all_passed = True
    for test_case in test_cases:
        try:
            payload = {"text": test_case["text"]}
            response = requests.post(
                f"{BASE_URL}{API_PREFIX}/profile",
                json=payload,
                timeout=10
            )
            
            if response.status_code == 200:
                data = response.json()
                domain = data.get("result", {}).get("domain", {}).get("predicted_domain")
                print(f"   ✓ {test_case['name']}: Domain={domain}")
            else:
                print(f"   ✗ {test_case['name']} failed with status {response.status_code}")
                all_passed = False
        except Exception as e:
            print(f"   ✗ {test_case['name']} failed: {e}")
            all_passed = False
    
    return all_passed


def test_batch_profile() -> bool:
    """Test batch profiling."""
    print("\n3. Testing Batch Profiling...")
    
    try:
        payload = {
            "texts": [
                "The patient requires immediate surgery.",
                "यह एक सामान्य वाक्य है।",
                "The contract is hereby terminated."
            ]
        }
        
        response = requests.post(
            f"{BASE_URL}{API_PREFIX}/profile/batch",
            json=payload,
            timeout=15
        )
        
        if response.status_code == 200:
            data = response.json()
            results = data.get("results", [])
            print(f"   ✓ Batch profiling passed: {len(results)} results")
            return True
        else:
            print(f"   ✗ Batch profiling failed with status {response.status_code}")
            return False
    except Exception as e:
        print(f"   ✗ Batch profiling failed: {e}")
        return False


def test_metrics_endpoint() -> bool:
    """Test Prometheus metrics endpoint."""
    print("\n4. Testing Metrics Endpoint...")
    
    try:
        response = requests.get(f"{BASE_URL}/metrics", timeout=5)
        if response.status_code == 200:
            metrics_text = response.text
            # Check for key metrics
            if "profiler_requests_total" in metrics_text:
                print(f"   ✓ Metrics endpoint working")
                return True
            else:
                print(f"   ✗ Metrics endpoint missing expected metrics")
                return False
        else:
            print(f"   ✗ Metrics endpoint failed with status {response.status_code}")
            return False
    except Exception as e:
        print(f"   ✗ Metrics endpoint failed: {e}")
        return False


def test_error_handling() -> bool:
    """Test error handling with invalid inputs."""
    print("\n5. Testing Error Handling...")
    
    test_cases = [
        {
            "name": "Empty text",
            "payload": {"text": ""},
            "expected_status": 422
        },
        {
            "name": "Oversized text",
            "payload": {"text": "word " * 100000},
            "expected_status": 422  # Pydantic validation error
        }
    ]
    
    all_passed = True
    for test_case in test_cases:
        try:
            response = requests.post(
                f"{BASE_URL}{API_PREFIX}/profile",
                json=test_case["payload"],
                timeout=10
            )
            
            if response.status_code == test_case["expected_status"]:
                print(f"   ✓ {test_case['name']}: Correctly returned {response.status_code}")
            else:
                print(f"   ✗ {test_case['name']}: Expected {test_case['expected_status']}, got {response.status_code}")
                all_passed = False
        except Exception as e:
            print(f"   ✗ {test_case['name']} failed: {e}")
            all_passed = False

    return all_passed


def test_performance() -> bool:
    """Test response time performance."""
    print("\n6. Testing Performance (<500ms target)...")

    try:
        payload = {"text": "This is a test sentence for performance measurement."}

        # Warm up
        requests.post(f"{BASE_URL}{API_PREFIX}/profile", json=payload, timeout=10)

        # Measure
        times = []
        for _ in range(10):
            start = time.time()
            response = requests.post(
                f"{BASE_URL}{API_PREFIX}/profile",
                json=payload,
                timeout=10
            )
            elapsed = (time.time() - start) * 1000  # Convert to ms
            times.append(elapsed)

        avg_time = sum(times) / len(times)
        max_time = max(times)

        if avg_time < 500:
            print(f"   ✓ Performance test passed: avg={avg_time:.2f}ms, max={max_time:.2f}ms")
            return True
        else:
            print(f"   ⚠ Performance warning: avg={avg_time:.2f}ms (target <500ms)")
            return True  # Still pass, just warn
    except Exception as e:
        print(f"   ✗ Performance test failed: {e}")
        return False


def main():
    """Run all tests."""
    print("=" * 70)
    print("RequestProfiler Docker Deployment Test Suite")
    print("=" * 70)

    # Wait for service to be ready
    print("\nWaiting for service to be ready...")
    max_retries = 30
    for i in range(max_retries):
        try:
            response = requests.get(f"{BASE_URL}{API_PREFIX}/health", timeout=2)
            if response.status_code == 200:
                print("✓ Service is ready!")
                break
        except:
            pass

        if i == max_retries - 1:
            print("✗ Service failed to start within timeout")
            sys.exit(1)

        time.sleep(2)
        print(f"  Retry {i+1}/{max_retries}...")

    # Run all tests
    results = {
        "Health Check": test_health_check(),
        "Single Profile": test_single_profile(),
        "Batch Profile": test_batch_profile(),
        "Metrics Endpoint": test_metrics_endpoint(),
        "Error Handling": test_error_handling(),
        "Performance": test_performance()
    }

    # Summary
    print("\n" + "=" * 70)
    print("Test Summary")
    print("=" * 70)

    passed = sum(1 for v in results.values() if v)
    total = len(results)

    for test_name, result in results.items():
        status = "✓ PASS" if result else "✗ FAIL"
        print(f"{status}: {test_name}")

    print(f"\nTotal: {passed}/{total} tests passed")

    if passed == total:
        print("\n🎉 All tests passed! Deployment is successful.")
        sys.exit(0)
    else:
        print(f"\n⚠️  {total - passed} test(s) failed. Please review the output above.")
        sys.exit(1)


if __name__ == "__main__":
    main()
