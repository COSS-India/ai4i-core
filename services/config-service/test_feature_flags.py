#!/usr/bin/env python3
"""
Comprehensive test script for Feature Flags API
Tests all endpoints and functionality to ensure 100% working status
"""
import asyncio
import json
import sys
from typing import Dict, Any, Optional
import aiohttp
import time


BASE_URL = "http://localhost:8082"
ENVIRONMENT = "development"


class Colors:
    GREEN = "\033[92m"
    RED = "\033[91m"
    YELLOW = "\033[93m"
    BLUE = "\033[94m"
    RESET = "\033[0m"


def print_test(name: str):
    print(f"\n{Colors.BLUE}Testing: {name}{Colors.RESET}")


def print_success(message: str):
    print(f"{Colors.GREEN}✓ {message}{Colors.RESET}")


def print_error(message: str):
    print(f"{Colors.RED}✗ {message}{Colors.RESET}")


def print_info(message: str):
    print(f"{Colors.YELLOW}ℹ {message}{Colors.RESET}")


async def test_create_feature_flag(session: aiohttp.ClientSession, name: str, data: Dict[str, Any]) -> Optional[Dict]:
    """Test creating a feature flag"""
    print_test(f"Create feature flag: {name}")
    try:
        async with session.post(
            f"{BASE_URL}/api/v1/feature-flags/",
            json=data,
        ) as response:
            if response.status == 201:
                result = await response.json()
                print_success(f"Created flag '{name}' with ID {result.get('id')}")
                return result
            else:
                text = await response.text()
                print_error(f"Failed to create flag: {response.status} - {text}")
                return None
    except Exception as e:
        print_error(f"Exception creating flag: {e}")
        return None


async def test_get_feature_flag(session: aiohttp.ClientSession, name: str, environment: str) -> Optional[Dict]:
    """Test getting a feature flag"""
    print_test(f"Get feature flag: {name}")
    try:
        async with session.get(
            f"{BASE_URL}/api/v1/feature-flags/{name}",
            params={"environment": environment},
        ) as response:
            if response.status == 200:
                result = await response.json()
                print_success(f"Retrieved flag '{name}'")
                return result
            else:
                text = await response.text()
                print_error(f"Failed to get flag: {response.status} - {text}")
                return None
    except Exception as e:
        print_error(f"Exception getting flag: {e}")
        return None


async def test_list_feature_flags(
    session: aiohttp.ClientSession,
    environment: Optional[str] = None,
    enabled: Optional[bool] = None,
) -> Optional[list]:
    """Test listing feature flags"""
    print_test("List feature flags")
    try:
        params = {}
        if environment:
            params["environment"] = environment
        if enabled is not None:
            # Convert boolean to string for query parameter
            params["enabled"] = str(enabled).lower()
        
        async with session.get(
            f"{BASE_URL}/api/v1/feature-flags/",
            params=params,
        ) as response:
            if response.status == 200:
                result = await response.json()
                print_success(f"Retrieved {len(result)} flags")
                return result
            else:
                text = await response.text()
                print_error(f"Failed to list flags: {response.status} - {text}")
                return None
    except Exception as e:
        print_error(f"Exception listing flags: {e}")
        return None


async def test_update_feature_flag(
    session: aiohttp.ClientSession,
    name: str,
    environment: str,
    updates: Dict[str, Any],
) -> Optional[Dict]:
    """Test updating a feature flag"""
    print_test(f"Update feature flag: {name}")
    try:
        params = {"environment": environment}
        async with session.put(
            f"{BASE_URL}/api/v1/feature-flags/{name}",
            params=params,
            json=updates,
        ) as response:
            if response.status == 200:
                result = await response.json()
                print_success(f"Updated flag '{name}'")
                return result
            else:
                text = await response.text()
                print_error(f"Failed to update flag: {response.status} - {text}")
                return None
    except Exception as e:
        print_error(f"Exception updating flag: {e}")
        return None


async def test_evaluate_feature_flag(
    session: aiohttp.ClientSession,
    flag_name: str,
    environment: str,
    user_id: str,
) -> Optional[Dict]:
    """Test evaluating a feature flag"""
    print_test(f"Evaluate feature flag: {flag_name} for user: {user_id}")
    try:
        async with session.post(
            f"{BASE_URL}/api/v1/feature-flags/evaluate",
            json={
                "flag_name": flag_name,
                "environment": environment,
                "user_id": user_id,
            },
        ) as response:
            if response.status == 200:
                result = await response.json()
                print_success(
                    f"Evaluation result: enabled={result.get('enabled')}, reason={result.get('reason')}"
                )
                return result
            else:
                text = await response.text()
                print_error(f"Failed to evaluate flag: {response.status} - {text}")
                return None
    except Exception as e:
        print_error(f"Exception evaluating flag: {e}")
        return None


async def test_batch_evaluate(
    session: aiohttp.ClientSession,
    flags: list,
    environment: str,
    user_id: str,
) -> Optional[Dict]:
    """Test batch evaluation"""
    print_test(f"Batch evaluate {len(flags)} flags for user: {user_id}")
    try:
        params = {"user_id": user_id, "environment": environment}
        async with session.post(
            f"{BASE_URL}/api/v1/feature-flags/evaluate/batch",
            params=params,
            json=flags,
        ) as response:
            if response.status == 200:
                result = await response.json()
                print_success(f"Batch evaluation completed for {len(result)} flags")
                return result
            else:
                text = await response.text()
                print_error(f"Failed to batch evaluate: {response.status} - {text}")
                return None
    except Exception as e:
        print_error(f"Exception batch evaluating: {e}")
        return None


async def test_get_history(
    session: aiohttp.ClientSession,
    name: str,
    environment: str,
) -> Optional[list]:
    """Test getting feature flag history"""
    print_test(f"Get history for flag: {name}")
    try:
        async with session.get(
            f"{BASE_URL}/api/v1/feature-flags/{name}/history",
            params={"environment": environment},
        ) as response:
            if response.status == 200:
                result = await response.json()
                print_success(f"Retrieved {len(result)} history entries")
                return result
            else:
                text = await response.text()
                print_error(f"Failed to get history: {response.status} - {text}")
                return None
    except Exception as e:
        print_error(f"Exception getting history: {e}")
        return None


async def test_delete_feature_flag(session: aiohttp.ClientSession, name: str, environment: str) -> bool:
    """Test deleting a feature flag"""
    print_test(f"Delete feature flag: {name}")
    try:
        async with session.delete(
            f"{BASE_URL}/api/v1/feature-flags/{name}",
            params={"environment": environment},
        ) as response:
            if response.status == 204:
                print_success(f"Deleted flag '{name}'")
                return True
            else:
                text = await response.text()
                print_error(f"Failed to delete flag: {response.status} - {text}")
                return False
    except Exception as e:
        print_error(f"Exception deleting flag: {e}")
        return False


async def test_rollout_percentage(session: aiohttp.ClientSession):
    """Test percentage rollout functionality"""
    print_test("Testing percentage rollout")
    
    flag_name = "test_rollout_percentage"
    
    # Create flag with 50% rollout
    flag = await test_create_feature_flag(
        session,
        flag_name,
        {
            "name": flag_name,
            "description": "Test rollout percentage",
            "is_enabled": True,
            "rollout_percentage": 50.0,
            "environment": ENVIRONMENT,
        },
    )
    
    if not flag:
        return False
    
    # Test with multiple users - should get consistent results
    results = {}
    for user_id in ["user1", "user2", "user3", "user4", "user5"]:
        eval_result = await test_evaluate_feature_flag(session, flag_name, ENVIRONMENT, user_id)
        if eval_result:
            results[user_id] = eval_result.get("enabled")
    
    enabled_count = sum(1 for v in results.values() if v)
    print_info(f"Out of 5 users, {enabled_count} got the feature enabled")
    
    # Cleanup
    await test_delete_feature_flag(session, flag_name, ENVIRONMENT)
    return True


async def test_target_users(session: aiohttp.ClientSession):
    """Test targeted users functionality"""
    print_test("Testing targeted users")
    
    flag_name = "test_target_users"
    target_user = "special_user_123"
    
    # Create flag with specific target user
    flag = await test_create_feature_flag(
        session,
        flag_name,
        {
            "name": flag_name,
            "description": "Test targeted users",
            "is_enabled": True,
            "rollout_percentage": 0.0,
            "target_users": [target_user],
            "environment": ENVIRONMENT,
        },
    )
    
    if not flag:
        return False
    
    # Test with targeted user
    result1 = await test_evaluate_feature_flag(session, flag_name, ENVIRONMENT, target_user)
    assert result1 and result1.get("enabled") is True, "Targeted user should have access"
    
    # Test with non-targeted user
    result2 = await test_evaluate_feature_flag(session, flag_name, ENVIRONMENT, "other_user")
    assert result2 and result2.get("enabled") is False, "Non-targeted user should not have access"
    
    # Cleanup
    await test_delete_feature_flag(session, flag_name, ENVIRONMENT)
    return True


async def test_same_name_different_env(session: aiohttp.ClientSession):
    """Test that same flag name can exist in different environments"""
    print_test("Testing same name in different environments")
    
    # Use a unique name with timestamp to avoid conflicts
    import time
    flag_name = f"multi_env_flag_{int(time.time())}"
    
    # Clean up any existing flags with this name (in case of previous failed runs)
    try:
        await test_delete_feature_flag(session, flag_name, "development")
    except:
        pass
    try:
        await test_delete_feature_flag(session, flag_name, "staging")
    except:
        pass
    
    # Create in development
    flag1 = await test_create_feature_flag(
        session,
        flag_name,
        {
            "name": flag_name,
            "description": "Development flag",
            "is_enabled": True,
            "rollout_percentage": 100.0,
            "environment": "development",
        },
    )
    
    # Create in staging
    flag2 = await test_create_feature_flag(
        session,
        flag_name,
        {
            "name": flag_name,
            "description": "Staging flag",
            "is_enabled": False,
            "rollout_percentage": 0.0,
            "environment": "staging",
        },
    )
    
    if flag1 and flag2:
        print_success("Same flag name can exist in different environments")
        # Cleanup
        await test_delete_feature_flag(session, flag_name, "development")
        await test_delete_feature_flag(session, flag_name, "staging")
        return True
    else:
        print_error("Failed to create flags with same name in different environments")
        # Try to clean up even on failure
        try:
            await test_delete_feature_flag(session, flag_name, "development")
        except:
            pass
        try:
            await test_delete_feature_flag(session, flag_name, "staging")
        except:
            pass
        return False


async def test_history_tracking(session: aiohttp.ClientSession):
    """Test that history is tracked on updates"""
    print_test("Testing history tracking")
    
    flag_name = "test_history_flag"
    
    # Create flag
    flag = await test_create_feature_flag(
        session,
        flag_name,
        {
            "name": flag_name,
            "description": "Test history",
            "is_enabled": False,
            "rollout_percentage": 0.0,
            "environment": ENVIRONMENT,
        },
    )
    
    if not flag:
        return False
    
    # Wait a bit
    await asyncio.sleep(1)
    
    # Update flag
    await test_update_feature_flag(
        session,
        flag_name,
        ENVIRONMENT,
        {"is_enabled": True, "rollout_percentage": 50.0},
    )
    
    # Wait a bit
    await asyncio.sleep(1)
    
    # Update again
    await test_update_feature_flag(
        session,
        flag_name,
        ENVIRONMENT,
        {"rollout_percentage": 100.0},
    )
    
    # Check history
    history = await test_get_history(session, flag_name, ENVIRONMENT)
    
    if history and len(history) >= 2:
        print_success(f"History tracking works - found {len(history)} entries")
        # Cleanup
        await test_delete_feature_flag(session, flag_name, ENVIRONMENT)
        return True
    else:
        print_error(f"History tracking failed - expected at least 2 entries, got {len(history) if history else 0}")
        return False


async def run_all_tests():
    """Run all feature flag tests"""
    print(f"\n{Colors.BLUE}{'='*60}")
    print("Feature Flags API Comprehensive Test Suite")
    print(f"{'='*60}{Colors.RESET}\n")
    
    timeout = aiohttp.ClientTimeout(total=30)
    async with aiohttp.ClientSession(timeout=timeout) as session:
        # Check if service is running
        try:
            async with session.get(f"{BASE_URL}/health") as response:
                if response.status != 200:
                    print_error("Service health check failed")
                    return False
                print_success("Service is running")
        except Exception as e:
            print_error(f"Cannot connect to service at {BASE_URL}: {e}")
            print_info("Make sure the config-service is running on port 8082")
            return False
        
        test_results = []
        
        # Basic CRUD tests
        flag_name = "test_flag_basic"
        
        # Create
        flag = await test_create_feature_flag(
            session,
            flag_name,
            {
                "name": flag_name,
                "description": "Test feature flag",
                "is_enabled": True,
                "rollout_percentage": 100.0,
                "environment": ENVIRONMENT,
            },
        )
        test_results.append(("Create", flag is not None))
        
        if flag:
            # Get
            retrieved = await test_get_feature_flag(session, flag_name, ENVIRONMENT)
            test_results.append(("Get", retrieved is not None))
            
            # List
            listed = await test_list_feature_flags(session, ENVIRONMENT)
            test_results.append(("List", listed is not None and len(listed) > 0))
            
            # List with filter
            listed_enabled = await test_list_feature_flags(session, ENVIRONMENT, enabled=True)
            test_results.append(("List (filtered)", listed_enabled is not None))
            
            # Update
            updated = await test_update_feature_flag(
                session,
                flag_name,
                ENVIRONMENT,
                {"rollout_percentage": 50.0},
            )
            test_results.append(("Update", updated is not None))
            
            # Evaluate
            eval_result = await test_evaluate_feature_flag(session, flag_name, ENVIRONMENT, "test_user")
            test_results.append(("Evaluate", eval_result is not None))
            
            # Batch evaluate
            batch_result = await test_batch_evaluate(
                session,
                [flag_name],
                ENVIRONMENT,
                "test_user",
            )
            test_results.append(("Batch Evaluate", batch_result is not None))
            
            # Get history
            history = await test_get_history(session, flag_name, ENVIRONMENT)
            test_results.append(("History", history is not None))
            
            # Delete
            deleted = await test_delete_feature_flag(session, flag_name, ENVIRONMENT)
            test_results.append(("Delete", deleted))
        
        # Advanced tests
        test_results.append(("Rollout Percentage", await test_rollout_percentage(session)))
        test_results.append(("Target Users", await test_target_users(session)))
        test_results.append(("Multi-Environment", await test_same_name_different_env(session)))
        test_results.append(("History Tracking", await test_history_tracking(session)))
        
        # Summary
        print(f"\n{Colors.BLUE}{'='*60}")
        print("Test Summary")
        print(f"{'='*60}{Colors.RESET}\n")
        
        passed = sum(1 for _, result in test_results if result)
        total = len(test_results)
        
        for test_name, result in test_results:
            if result:
                print_success(f"{test_name}: PASSED")
            else:
                print_error(f"{test_name}: FAILED")
        
        print(f"\n{Colors.BLUE}{'='*60}{Colors.RESET}")
        if passed == total:
            print_success(f"All tests passed! ({passed}/{total})")
            return True
        else:
            print_error(f"Some tests failed: {passed}/{total} passed")
            return False


if __name__ == "__main__":
    try:
        success = asyncio.run(run_all_tests())
        sys.exit(0 if success else 1)
    except KeyboardInterrupt:
        print("\n\nTests interrupted by user")
        sys.exit(1)
    except Exception as e:
        print_error(f"Unexpected error: {e}")
        import traceback
        traceback.print_exc()
        sys.exit(1)

