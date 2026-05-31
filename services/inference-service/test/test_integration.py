#!/usr/bin/env python3
"""
End-to-end test script for the NMT inference service
Demonstrates the full inference request -> response pipeline
"""

import asyncio
import httpx
import json
import logging
import sys
import time
from typing import Dict, Any

# Setup logging
logging.basicConfig(
    level=logging.INFO,
    format='%(asctime)s - %(levelname)s - %(message)s'
)
logger = logging.getLogger(__name__)


# NMT Sample Payload
NMT_PAYLOAD = {
    "task_type": "NMT",
    "config": {
        "serviceId": "indictrans-v2-all",
        "language": {
            "sourceLanguage": "en",
            "targetLanguage": "hi"
        }
    },
    "input": [
        {"source": "Hello, how are you?"},
        {"source": "What is your name?"}
    ]
}

# ASR Sample Payload (mock)
ASR_PAYLOAD = {
    "task_type": "ASR",
    "config": {
        "language": "en"
    },
    "audio": [
        {"audio_data": "base64_encoded_audio_here"}
    ]
}

# OCR Sample Payload (mock)
OCR_PAYLOAD = {
    "task_type": "OCR",
    "config": {
        "language": "en"
    },
    "image": [
        {"image_data": "base64_encoded_image_here"}
    ]
}


class InferenceServiceTester:
    """Test harness for inference service"""
    
    def __init__(self, base_url: str = "http://localhost:8000"):
        self.base_url = base_url
        self.client = httpx.AsyncClient(timeout=30.0)
    
    async def test_health_check(self) -> bool:
        """Test health check endpoint"""
        try:
            logger.info("🔍 Testing health check endpoint...")
            response = await self.client.get(f"{self.base_url}/health")
            
            if response.status_code == 200:
                data = response.json()
                logger.info(f"   ✓ Health check passed: {data}")
                return True
            else:
                logger.error(f"   ✗ Health check failed with status {response.status_code}")
                return False
        except Exception as e:
            logger.error(f"   ✗ Health check error: {e}")
            return False
    
    async def test_list_tasks(self) -> bool:
        """Test list available tasks"""
        try:
            logger.info("🔍 Testing list tasks endpoint...")
            response = await self.client.get(f"{self.base_url}/api/v1/inference/tasks")
            
            if response.status_code == 200:
                data = response.json()
                tasks = data.get("tasks", [])
                logger.info(f"   ✓ Available tasks: {', '.join(tasks)}")
                return True
            else:
                logger.error(f"   ✗ List tasks failed with status {response.status_code}")
                return False
        except Exception as e:
            logger.error(f"   ✗ List tasks error: {e}")
            return False
    
    async def test_nmt_inference(self) -> bool:
        """Test NMT inference endpoint with sample payload"""
        try:
            logger.info("🔍 Testing NMT inference...")
            logger.info(f"   Payload: {json.dumps(NMT_PAYLOAD, indent=2)}")
            
            headers = {
                "X-User-ID": "user123",
                "X-API-Key-ID": "key456",
                "X-Session-ID": f"session-{int(time.time())}"
            }
            
            start_time = time.time()
            response = await self.client.post(
                f"{self.base_url}/api/v1/inference",
                json=NMT_PAYLOAD,
                headers=headers
            )
            duration_ms = (time.time() - start_time) * 1000
            
            logger.info(f"   Response time: {duration_ms:.2f}ms")
            
            if response.status_code == 200:
                data = response.json()
                logger.info(f"   ✓ NMT inference succeeded")
                logger.info(f"   Response: {json.dumps(data, indent=2)}")
                return True
            else:
                logger.error(f"   ✗ NMT inference failed with status {response.status_code}")
                logger.error(f"   Response: {response.text}")
                return False
        except Exception as e:
            logger.error(f"   ✗ NMT inference error: {e}")
            import traceback
            traceback.print_exc()
            return False
    
    async def test_asr_inference(self) -> bool:
        """Test ASR inference (will be mock)"""
        try:
            logger.info("🔍 Testing ASR inference (mock)...")
            
            response = await self.client.post(
                f"{self.base_url}/api/v1/inference",
                json=ASR_PAYLOAD
            )
            
            if response.status_code == 200:
                logger.info(f"   ✓ ASR inference succeeded (mock)")
                return True
            else:
                logger.warning(f"   ⚠ ASR endpoint returned {response.status_code}")
                return False
        except Exception as e:
            logger.warning(f"   ⚠ ASR inference error (expected): {e}")
            return False
    
    async def run_all_tests(self) -> Dict[str, bool]:
        """Run all tests"""
        results = {
            "health_check": await self.test_health_check(),
            "list_tasks": await self.test_list_tasks(),
            "nmt_inference": await self.test_nmt_inference(),
            "asr_inference": await self.test_asr_inference(),
        }
        return results
    
    async def close(self):
        """Close HTTP client"""
        await self.client.aclose()


async def main():
    """Main test runner"""
    logger.info("=" * 70)
    logger.info("🚀 AI4I Inference Service - End-to-End Test")
    logger.info("=" * 70)
    
    tester = InferenceServiceTester(base_url="http://localhost:8000")
    
    try:
        # Wait a moment for service to be ready
        await asyncio.sleep(2)
        
        # Run tests
        results = await tester.run_all_tests()
        
        # Print summary
        logger.info("\n" + "=" * 70)
        logger.info("📊 TEST SUMMARY")
        logger.info("=" * 70)
        
        passed = sum(1 for v in results.values() if v)
        total = len(results)
        
        for test_name, passed_flag in results.items():
            status = "✅ PASS" if passed_flag else "❌ FAIL"
            logger.info(f"{status} - {test_name}")
        
        logger.info("=" * 70)
        logger.info(f"Overall: {passed}/{total} tests passed")
        logger.info("=" * 70)
        
        return 0 if passed == total else 1
        
    except Exception as e:
        logger.error(f"Test runner error: {e}")
        import traceback
        traceback.print_exc()
        return 1
    finally:
        await tester.close()


if __name__ == "__main__":
    exit_code = asyncio.run(main())
    sys.exit(exit_code)
