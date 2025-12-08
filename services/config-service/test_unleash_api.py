#!/usr/bin/env python3
"""
Test script to inspect Unleash API response structure
"""
import asyncio
import json
import os
import sys
import aiohttp

async def test_unleash_api():
    """Test Unleash API and print response structure"""
    unleash_url = os.getenv('UNLEASH_URL', 'http://unleash:4242/feature-flags/api')
    unleash_api_token = os.getenv('UNLEASH_API_TOKEN', '*:*.unleash-insecure-api-token')
    environment = os.getenv('UNLEASH_ENVIRONMENT', 'development')
    
    # Construct Unleash Admin API URL
    base_url = unleash_url.rstrip('/api')
    admin_url = f"{base_url}/api/admin/projects/default/features"
    
    headers = {
        "Authorization": unleash_api_token,
        "Content-Type": "application/json",
    }
    
    print(f"Testing Unleash API:")
    print(f"  URL: {admin_url}")
    print(f"  Environment: {environment}")
    print(f"  Token: {unleash_api_token[:20]}...")
    print()
    
    async with aiohttp.ClientSession() as session:
        try:
            async with session.get(admin_url, headers=headers, params={"offset": 0, "limit": 10}) as response:
                print(f"Response Status: {response.status}")
                print()
                
                if response.status != 200:
                    error_text = await response.text()
                    print(f"Error Response: {error_text}")
                    return
                
                data = await response.json()
                
                print("=" * 80)
                print("FULL API RESPONSE STRUCTURE:")
                print("=" * 80)
                print(json.dumps(data, indent=2))
                print()
                
                # Analyze structure
                print("=" * 80)
                print("STRUCTURE ANALYSIS:")
                print("=" * 80)
                print(f"Response type: {type(data)}")
                
                if isinstance(data, dict):
                    print(f"Top-level keys: {list(data.keys())}")
                    if "features" in data:
                        features = data["features"]
                        print(f"Number of features: {len(features)}")
                        if features:
                            print("\nFirst feature structure:")
                            print(json.dumps(features[0], indent=2))
                            
                            # Check environment structure
                            first_feature = features[0]
                            if "environments" in first_feature:
                                envs = first_feature["environments"]
                                print(f"\nEnvironments in first feature: {len(envs)}")
                                for i, env in enumerate(envs):
                                    print(f"\nEnvironment {i}:")
                                    if isinstance(env, dict):
                                        print(f"  Keys: {list(env.keys())}")
                                        print(f"  Name: {env.get('name')}")
                                        print(f"  Enabled: {env.get('enabled')}")
                                        if "strategies" in env:
                                            print(f"  Strategies: {len(env.get('strategies', []))}")
                                    else:
                                        print(f"  Type: {type(env)}, Value: {env}")
                elif isinstance(data, list):
                    print(f"Response is a list with {len(data)} items")
                    if data:
                        print("\nFirst item structure:")
                        print(json.dumps(data[0], indent=2))
                
        except Exception as e:
            print(f"Error: {e}", file=sys.stderr)
            import traceback
            traceback.print_exc()

if __name__ == "__main__":
    asyncio.run(test_unleash_api())

