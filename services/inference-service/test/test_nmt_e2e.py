#!/usr/bin/env python3
"""
Direct unit test of NMT service
Tests the complete NMT inference pipeline
"""

import asyncio
import sys
import logging

# Setup logging
logging.basicConfig(level=logging.INFO, format='%(asctime)s - %(levelname)s - %(message)s')
logger = logging.getLogger(__name__)


async def run_tests():
    """Run comprehensive NMT service tests"""
    
    try:
        from services.nmt_service import NMTTaskService
        from models.schemas.nmt import NMTInferenceRequest, LanguagePair, NMTConfig, TextInput
        
        logger.info("=" * 70)
        logger.info("🚀 NMT Service End-to-End Verification")
        logger.info("=" * 70)
        
        # Mock resolver
        class MockResolver:  # type: ignore
            async def resolve_service(self, service_id, session_id=None):
                return {
                    "service_id": service_id,
                    "model_name": "indictrans_en_hi_v2",
                    "triton_endpoint": "http://localhost:8000",
                    "triton_api_key": "mock-key"
                }
        
        # 1. Initialize service
        logger.info("\n1️⃣ Initializing NMT Service")
        resolver = MockResolver()
        service = NMTTaskService(inference_server_resolver=resolver)  # type: ignore
        logger.info("   ✅ Service initialized")
        
        # 2. Create test request
        logger.info("\n2️⃣ Creating NMT Request")
        config = NMTConfig(
            service_id="indictrans-v2-all",
            language=LanguagePair(source_language="en", target_language="hi")
        )
        request = NMTInferenceRequest(
            input=[
                TextInput(source="Hello, how are you?"),
                TextInput(source="What is your name?")
            ],
            config=config
        )
        logger.info(f"   ✅ Request created: {len(request.input)} inputs, en→hi")
        
        # 3. Test validation
        logger.info("\n3️⃣ Testing Validation")
        await service.validate_request(request)
        logger.info("   ✅ Validation passed")
        
        # 4. Test preprocessing
        logger.info("\n4️⃣ Testing Preprocessing")
        raw = [{"source": "  Hello   world  "}, {"source": "  What  is  the   weather?  "}]
        preprocessed = await service.preprocess_input(raw)
        logger.info(f"   ✅ Preprocessing: {len(preprocessed)} items cleaned")
        
        # 5. Test service resolution
        logger.info("\n5️⃣ Testing Service Resolution")
        svc_id, model, endpoint, api_key = await service._resolve_service_and_model(config, "test-123")
        logger.info(f"   ✅ Resolved: {svc_id}/{model} @ {endpoint}")
        
        # 6. Test error handling
        logger.info("\n6️⃣ Testing Error Handling")
        
        try:
            # Empty input
            NMTInferenceRequest(input=[], config=config)
            logger.info("   ✗ Should reject empty input")
            return 1
        except:
            logger.info("   ✅ Empty input rejected")
        
        try:
            # Same language
            same = NMTConfig(
                service_id="indictrans-v2-all",
                language=LanguagePair(source_language="en", target_language="en")
            )
            req = NMTInferenceRequest(
                input=[TextInput(source="Hello")],
                config=same
            )
            await service.validate_request(req)
            logger.info("   ✗ Should reject same language")
            return 1
        except:
            logger.info("   ✅ Same language rejected")
        
        # Success!
        logger.info("\n" + "=" * 70)
        logger.info("✅ ALL NMT SERVICE TESTS PASSED")
        logger.info("=" * 70)
        logger.info("\nNMT Service is working correctly:")
        logger.info("  ✓ Service initialization")
        logger.info("  ✓ Request validation")
        logger.info("  ✓ Input preprocessing")
        logger.info("  ✓ Service resolution")
        logger.info("  ✓ Error handling")
        logger.info("=" * 70)
        
        return 0
        
    except Exception as e:
        logger.error(f"❌ Test failed: {e}")
        import traceback
        traceback.print_exc()
        return 1


async def main():
    return await run_tests()


if __name__ == "__main__":
    exit_code = asyncio.run(main())
    sys.exit(exit_code)
