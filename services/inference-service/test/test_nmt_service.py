#!/usr/bin/env python3
"""Test NMT Service directly with sample payloads."""

import asyncio
import sys
import json
from unittest.mock import AsyncMock

sys.path.insert(0, '.')

from services.models.text_default_model import TextDefaultModel
from models.schemas.nmt import NMTInferenceRequest, NMTConfig, LanguagePair, TextInput


async def test_nmt_validation():
    """Test NMT request validation."""
    print("\n" + "="*70)
    print("TEST 1: NMT Request Validation")
    print("="*70)

    # Create mock resolver
    mock_resolver = AsyncMock()
    mock_resolver.resolve_service = AsyncMock(return_value={
        'model_name': 'indictrans_en_hi',
        'triton_endpoint': 'http://localhost:8000',
        'api_key': None
    })

    # Create NMT service
    service = TextDefaultModel(inference_server_resolver=mock_resolver)
    print("✓ NMT Service initialized")

    # Create valid request
    request = NMTInferenceRequest(
        input=[
            TextInput(source="Hello, how are you?"),
            TextInput(source="What is the weather?")
        ],
        config=NMTConfig(
            service_id="indictrans-v2-all",
            language=LanguagePair(
                source_language="en",
                target_language="hi"
            )
        )
    )
    print("✓ Test request created")
    print(f"  Input items: {len(request.input)}")
    print(f"  Translation: {request.config.language.source_language} → {request.config.language.target_language}")

    # Validate
    try:
        await service.validate_request(request)
        print("✓ Validation PASSED")
    except Exception as e:
        print(f"✗ Validation FAILED: {e}")
        return False

    return True


async def test_nmt_preprocessing():
    """Test NMT input preprocessing."""
    print("\n" + "="*70)
    print("TEST 2: NMT Input Preprocessing")
    print("="*70)

    mock_resolver = AsyncMock()
    service = NMTTaskService(inference_server_resolver=mock_resolver)

    # Test with messy input
    raw_input = [
        {"source": "  Hello   world  "},
        {"source": "  What  is  the   weather?  "},
        {"source": "Another text"}
    ]
    print("Raw input:")
    for i, item in enumerate(raw_input):
        print(f"  [{i}]: '{item['source']}'")

    try:
        cleaned = await service.preprocess_input(raw_input)
        print("\n✓ Preprocessing PASSED")
        print("Cleaned input:")
        for i, item in enumerate(cleaned):
            print(f"  [{i}]: '{item['source']}'")
    except Exception as e:
        print(f"✗ Preprocessing FAILED: {e}")
        return False

    return True


async def test_nmt_service_resolution():
    """Test service/model resolution."""
    print("\n" + "="*70)
    print("TEST 3: NMT Service Resolution")
    print("="*70)

    mock_resolver = AsyncMock()
    mock_resolver.resolve_service = AsyncMock(return_value={
        'model_name': 'indictrans_en_hi_v2',
        'triton_endpoint': 'http://triton.example.com:8000',
        'api_key': 'secret-key-123'
    })

    service = NMTTaskService(inference_server_resolver=mock_resolver)

    config = NMTConfig(
        service_id="indictrans-v2-all",
        language=LanguagePair(source_language="en", target_language="hi")
    )

    try:
        service_id, model_name, endpoint, api_key = await service._resolve_service_and_model(
            config, session_id="test-123"
        )
        print("✓ Service Resolution PASSED")
        print(f"  Service ID: {service_id}")
        print(f"  Model Name: {model_name}")
        print(f"  Endpoint: {endpoint}")
        print(f"  API Key: {'[REDACTED]' if api_key else 'None'}")
    except Exception as e:
        print(f"✗ Service Resolution FAILED: {e}")
        return False

    return True


async def test_nmt_error_scenarios():
    """Test error handling."""
    print("\n" + "="*70)
    print("TEST 4: NMT Error Scenarios")
    print("="*70)

    mock_resolver = AsyncMock()
    service = NMTTaskService(inference_server_resolver=mock_resolver)

    # Test 1: Empty input
    print("\nTest 4a: Empty input array")
    try:
        invalid_request = NMTInferenceRequest(
            input=[],  # Empty!
            config=NMTConfig(
                service_id="indictrans-v2-all",
                language=LanguagePair(source_language="en", target_language="hi")
            )
        )
        await service.validate_request(invalid_request)
        print("✗ Should have failed on empty input")
        return False
    except ValueError as e:
        print(f"✓ Correctly rejected: {e}")

    # Test 2: Same source and target language
    print("\nTest 4b: Same source and target language")
    try:
        invalid_request = NMTInferenceRequest(
            input=[TextInput(source="Hello")],
            config=NMTConfig(
                service_id="indictrans-v2-all",
                language=LanguagePair(source_language="en", target_language="en")
            )
        )
        await service.validate_request(invalid_request)
        print("✗ Should have failed on same language")
        return False
    except ValueError as e:
        print(f"✓ Correctly rejected: {e}")

    # Test 3: Missing language pair
    print("\nTest 4c: Missing target language")
    try:
        invalid_request = NMTInferenceRequest(
            input=[TextInput(source="Hello")],
            config=NMTConfig(
                service_id="indictrans-v2-all",
                language=LanguagePair(source_language="en", target_language="")  # Empty!
            )
        )
        await service.validate_request(invalid_request)
        print("✗ Should have failed on missing language")
        return False
    except ValueError as e:
        print(f"✓ Correctly rejected: {e}")

    print("\n✓ All error scenarios handled correctly")
    return True


async def main():
    """Run all tests."""
    print("\n" + "╔" + "="*68 + "╗")
    print("║" + " "*15 + "NMT SERVICE VERIFICATION TESTS" + " "*23 + "║")
    print("╚" + "="*68 + "╝")

    results = []

    # Run tests
    results.append(("Validation", await test_nmt_validation()))
    results.append(("Preprocessing", await test_nmt_preprocessing()))
    results.append(("Service Resolution", await test_nmt_service_resolution()))
    results.append(("Error Scenarios", await test_nmt_error_scenarios()))

    # Summary
    print("\n" + "="*70)
    print("TEST SUMMARY")
    print("="*70)
    for name, passed in results:
        status = "✅ PASSED" if passed else "❌ FAILED"
        print(f"{name:<30} {status}")

    all_passed = all(r[1] for r in results)
    print("\n" + "="*70)
    if all_passed:
        print("✅ ALL TESTS PASSED - NMT Service is working correctly!")
    else:
        print("❌ SOME TESTS FAILED - Check output above")
    print("="*70)

    return 0 if all_passed else 1


if __name__ == "__main__":
    exit_code = asyncio.run(main())
    sys.exit(exit_code)
