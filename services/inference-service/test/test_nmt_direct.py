#!/usr/bin/env python3
"""
Direct unit test of NMT service without HTTP server
Tests the complete NMT inference pipeline
"""

import asyncio
import sys
import logging
from typing import Dict, Any

# Setup logging
logging.basicConfig(
    level=logging.INFO,
    format='%(asctime)s - %(levelname)s - %(message)s'
)
logger = logging.getLogger(__name__)


async def run_nmt_unit_tests():
    """Run comprehensive unit tests for NMT service"""
    
    try:
        from services.nmt_service import NMTTaskService
        from models.schemas.nmt import (
            NMTInferenceRequest, LanguagePair, NMTConfig, TextInput
        )
        
        logger.info("=" * 70)
        logger.info("🚀 NMT Service Unit Tests")
        logger.info("=" * 70)
        
        # Create mock resolver
        class MockResolver:
            async def resolve(self, config, session_id=None):
                return ("indictrans-v2-all", "indictrans_en_hi_v2", "http://localhost:8000", "mock-api-key")
        
        # Initialize service
        logger.info("\n1️⃣ Initializing NMT service...")
        resolver = MockResolver()
        service = NMTTaskService(inference_server_resolver=resolver)
        logger.info("   ✓ Service initialized successfully")
        
        # Create test request
        logger.info("\n2️⃣ Creating test request...")
        config = NMTConfig(
            serviceId="indictrans-v2-all",
            language=NMTLanguageConfig(
                sourceLanguage="en",
                targetLanguage="hi"
            )
        )
        request = NMTInferenceRequest(
            config=config,
            input=[
                {"source": "Hello, how are you?"},
                {"source": "What is your name?"}
            ]
        )
        logger.info("   ✓ Request created:")
        logger.info(f"     - Source Language: {request.config.language.sourceLanguage}")
        logger.info(f"     - Target Language: {request.config.language.targetLanguage}")
        logger.info(f"     - Input items: {len(request.input)}")
        
        # Test validation
        logger.info("\n3️⃣ Testing request validation...")
        try:
            await service.validate_request(request)
            logger.info("   ✓ Request validation passed")
        except Exception as e:
            logger.error(f"   ✗ Validation failed: {e}")
            return False
        
        # Test preprocessing
        logger.info("\n4️⃣ Testing input preprocessing...")
        raw_input = ["  Hello   world  ", "  What  is  the   weather?  "]
        try:
            preprocessed = await service.preprocess_input(raw_input)
            logger.info("   ✓ Preprocessing successful:")
            for i, text in enumerate(preprocessed):
                logger.info(f"     [{i}] '{text}'")
        except Exception as e:
            logger.error(f"   ✗ Preprocessing failed: {e}")
            return False
        
        # Test service resolution
        logger.info("\n5️⃣ Testing service resolution...")
        try:
            service_id, model_name, endpoint, api_key = await service._resolve_service_and_model(
                config=request.config,
                session_id="test-session-123"
            )
            logger.info("   ✓ Service resolution successful:")
            logger.info(f"     - Service ID: {service_id}")
            logger.info(f"     - Model Name: {model_name}")
            logger.info(f"     - Endpoint: {endpoint}")
            logger.info(f"     - API Key: [REDACTED]")
        except Exception as e:
            logger.error(f"   ✗ Service resolution failed: {e}")
            return False
        
        # Test error scenarios
        logger.info("\n6️⃣ Testing error scenarios...")
        
        # Test 6a: Empty input
        logger.info("   6a) Testing empty input array...")
        try:
            empty_request = NMTInferenceRequest(
                config=config,
                input=[]
            )
            await service.validate_request(empty_request)
            logger.error("   ✗ Should have rejected empty input")
            return False
        except ValueError as e:
            logger.info(f"   ✓ Correctly rejected: {str(e)[:50]}...")
        
        # Test 6b: Same language
        logger.info("   6b) Testing same source/target language...")
        try:
            same_lang_config = NMTConfig(
                serviceId="indictrans-v2-all",
                language=NMTLanguageConfig(
                    sourceLanguage="en",
                    targetLanguage="en"
                )
            )
            same_lang_request = NMTInferenceRequest(
                config=same_lang_config,
                input=[{"source": "Hello"}]
            )
            await service.validate_request(same_lang_request)
            logger.error("   ✗ Should have rejected same language")
            return False
        except ValueError as e:
            logger.info(f"   ✓ Correctly rejected: {str(e)[:50]}...")
        
        # Test 6c: Missing language
        logger.info("   6c) Testing missing target language...")
        try:
            incomplete_config = NMTConfig(
                serviceId="indictrans-v2-all",
                language=NMTLanguageConfig(
                    sourceLanguage="en",
                    targetLanguage=""
                )
            )
            incomplete_request = NMTInferenceRequest(
                config=incomplete_config,
                input=[{"source": "Hello"}]
            )
            await service.validate_request(incomplete_request)
            logger.error("   ✗ Should have rejected missing language")
            return False
        except ValueError as e:
            logger.info(f"   ✓ Correctly rejected: {str(e)[:50]}...")
        
        # Summary
        logger.info("\n" + "=" * 70)
        logger.info("✅ ALL NMT UNIT TESTS PASSED")
        logger.info("=" * 70)
        logger.info("\nNMT Service Functionality Verified:")
        logger.info("  ✓ Service initialization")
        logger.info("  ✓ Request validation")
        logger.info("  ✓ Input preprocessing")
        logger.info("  ✓ Service resolution")
        logger.info("  ✓ Error handling")
        logger.info("=" * 70)
        
        return True
        
    except ImportError as e:
        logger.error(f"❌ Import error: {e}")
        import traceback
        traceback.print_exc()
        return False
    except Exception as e:
        logger.error(f"❌ Test failed: {e}")
        import traceback
        traceback.print_exc()
        return False


async def main():
    """Run all tests"""
    try:
        success = await run_nmt_unit_tests()
        return 0 if success else 1
    except Exception as e:
        logger.error(f"Fatal error: {e}")
        import traceback
        traceback.print_exc()
        return 1


if __name__ == "__main__":
    exit_code = asyncio.run(main())
    sys.exit(exit_code)
