#!/usr/bin/env python3
"""
Comprehensive Integration Tests for Indian Languages Request Profiler.

Tests:
1. Model performance validation
2. API endpoint testing
3. Edge case handling
4. Error handling and resilience
"""

import json
import sys
import time
from pathlib import Path
from typing import Dict, List

import pandas as pd
import requests
from sklearn.metrics import accuracy_score, f1_score, mean_absolute_error, r2_score

# Add parent directory to path
sys.path.insert(0, str(Path(__file__).parent.parent))

# Test configuration
API_BASE_URL = "http://localhost:8000"
TEST_DATA_PATH = Path(__file__).parent.parent / 'data' / 'processed' / 'indian_languages_test.csv'
MODELS_DIR = Path(__file__).parent.parent / 'models'

# Test samples for each language and domain
TEST_SAMPLES = {
    'hi_medical': "मधुमेह रोगी को इंसुलिन की नियमित खुराक लेनी चाहिए और रक्त शर्करा की निगरानी करनी चाहिए।",
    'hi_legal': "न्यायालय ने याचिकाकर्ता के पक्ष में निर्णय सुनाया और प्रतिवादी को मुआवजा देने का आदेश दिया।",
    'hi_technical': "कंप्यूटर प्रोग्रामिंग में एल्गोरिदम और डेटा संरचनाएं बहुत महत्वपूर्ण हैं।",
    'hi_finance': "शेयर बाजार में निवेश करने से पहले जोखिम मूल्यांकन करना आवश्यक है।",
    'hi_casual': "आज मौसम बहुत अच्छा है। चलो बाहर घूमने चलते हैं।",
    'hi_general': "भारत विविधता में एकता का देश है जहां अनेक भाषाएं और संस्कृतियां हैं।",
    
    'bn_medical': "রোগীর জ্বর এবং মাথাব্যথা রয়েছে এবং তাকে চিকিৎসার প্রয়োজন।",
    'bn_legal': "আদালত আবেদন গ্রহণ করেছে এবং রায় ঘোষণা করেছে।",
    'bn_technical': "সফটওয়্যার ইঞ্জিনিয়ারিং একটি জটিল এবং চ্যালেঞ্জিং ক্ষেত্র।",
    
    'ta_medical': "நோயாளிக்கு காய்ச்சல் மற்றும் தலைவலி உள்ளது மற்றும் சிகிச்சை தேவை.",
    'ta_legal': "நீதிமன்றம் மனுவை ஏற்றுக்கொண்டது மற்றும் தீர்ப்பு வழங்கியது.",
    
    'te_medical': "రోగికి జ్వరం మరియు తలనొప్పి ఉంది మరియు చికిత్స అవసరం.",
    'te_legal': "న్యాయస్థానం పిటిషన్‌ను అంగీకరించింది మరియు తీర్పు ఇచ్చింది.",
}


class Colors:
    """ANSI color codes for terminal output."""
    GREEN = '\033[92m'
    RED = '\033[91m'
    YELLOW = '\033[93m'
    BLUE = '\033[94m'
    RESET = '\033[0m'


def print_header(text: str):
    """Print formatted header."""
    print(f"\n{'='*80}")
    print(f"{Colors.BLUE}{text}{Colors.RESET}")
    print(f"{'='*80}\n")


def print_success(text: str):
    """Print success message."""
    print(f"{Colors.GREEN}✓ {text}{Colors.RESET}")


def print_error(text: str):
    """Print error message."""
    print(f"{Colors.RED}✗ {text}{Colors.RESET}")


def print_warning(text: str):
    """Print warning message."""
    print(f"{Colors.YELLOW}⚠ {text}{Colors.RESET}")


def test_model_performance():
    """Test 1: Validate model performance on test set."""
    print_header("TEST 1: Model Performance Validation")
    
    try:
        # Load test data
        test_df = pd.read_csv(TEST_DATA_PATH)
        print(f"Loaded {len(test_df)} test samples")
        
        # Load models
        import joblib
        domain_model = joblib.load(MODELS_DIR / 'domain_pipeline.pkl')
        complexity_model = joblib.load(MODELS_DIR / 'complexity_regressor.pkl')
        
        # Test domain classifier
        print("\nDomain Classifier Performance:")
        X_test = test_df['text'].tolist()
        y_true_domain = test_df['domain'].tolist()
        y_pred_domain = domain_model.predict(X_test)
        
        accuracy = accuracy_score(y_true_domain, y_pred_domain)
        f1_macro = f1_score(y_true_domain, y_pred_domain, average='macro')
        
        print(f"  Accuracy: {accuracy:.4f}")
        print(f"  F1-macro: {f1_macro:.4f}")
        
        if accuracy >= 0.90:
            print_success(f"Domain classifier meets target (≥0.90)")
        else:
            print_warning(f"Domain classifier below target: {accuracy:.4f} < 0.90")
        
        # Test complexity regressor
        print("\nComplexity Regressor Performance:")
        from request_profiler.features import extract_numeric_features
        
        X_test_features = [extract_numeric_features(text) for text in X_test]
        y_true_complexity = test_df['complexity'].values
        y_pred_complexity = complexity_model.predict(X_test_features)
        
        r2 = r2_score(y_true_complexity, y_pred_complexity)
        mae = mean_absolute_error(y_true_complexity, y_pred_complexity)
        
        print(f"  R²: {r2:.4f}")
        print(f"  MAE: {mae:.4f}")
        
        if r2 >= 0.70:
            print_success(f"Complexity regressor meets target (R² ≥0.70)")
        else:
            print_warning(f"Complexity regressor below target: R²={r2:.4f} < 0.70")
        
        return True
        
    except Exception as e:
        print_error(f"Model performance test failed: {e}")
        import traceback
        traceback.print_exc()
        return False


def test_api_health():
    """Test 2: Check API health and readiness."""
    print_header("TEST 2: API Health Check")

    try:
        response = requests.get(f"{API_BASE_URL}/api/v1/health", timeout=5)

        if response.status_code == 200:
            data = response.json()
            print(f"Status: {data.get('status')}")
            print(f"Models loaded: {data.get('models_loaded')}")
            print_success("API is healthy")
            return True
        else:
            print_error(f"Health check failed with status {response.status_code}")
            print(f"Response: {response.text}")
            return False

    except requests.exceptions.ConnectionError:
        print_error("Cannot connect to API. Is the server running?")
        print("  Start server with: uvicorn request_profiler.main:app --reload")
        return False
    except Exception as e:
        print_error(f"Health check failed: {e}")
        return False

def test_api_profiling():
    """Test 3: Test API profiling with real Indian language samples."""
    print_header("TEST 3: API Profiling Tests")

    passed = 0
    failed = 0

    for sample_id, text in TEST_SAMPLES.items():
        lang, domain = sample_id.split('_')

        try:
            response = requests.post(
                f"{API_BASE_URL}/api/v1/profile",
                json={"text": text},
                timeout=10
            )

            if response.status_code == 200:
                data = response.json()
                # The response structure is: {request_id, profile, metadata}
                profile = data.get('profile', {})

                # Validate response structure
                assert 'domain' in profile, f"Missing 'domain' in profile. Keys: {list(profile.keys())}"
                assert 'scores' in profile, f"Missing 'scores' in profile. Keys: {list(profile.keys())}"
                assert 'language' in profile, f"Missing 'language' in profile. Keys: {list(profile.keys())}"

                predicted_domain = profile['domain']['label']
                complexity_score = profile['scores']['complexity_score']

                # Check if complexity score is in valid range
                assert 0.0 <= complexity_score <= 1.0, f"Invalid complexity score: {complexity_score}"

                print(f"  ✓ {sample_id}: domain={predicted_domain}, complexity={complexity_score:.2f}")
                passed += 1
            else:
                print_error(f"{sample_id}: HTTP {response.status_code} - {response.text[:200]}")
                failed += 1

        except Exception as e:
            print_error(f"{sample_id}: {e}")
            failed += 1

    print(f"\nResults: {passed} passed, {failed} failed")

    if failed == 0:
        print_success("All API profiling tests passed")
        return True
    else:
        print_warning(f"{failed} tests failed")
        return False


def test_edge_cases():
    """Test 4: Test edge cases and error handling."""
    print_header("TEST 4: Edge Cases and Error Handling")

    test_cases = [
        ("Empty string", "", 422),  # FastAPI validation error
        ("Very short text", "Hi", 422),  # Less than 2 words
        ("Very long text", "A" * 100000, 422),  # Exceeds max length
        ("Special characters", "!@#$%^&*()", 422),  # Less than 2 words
        ("Numbers only", "123456789", 422),  # Less than 2 words
        ("Mixed scripts", "Hello नमस्ते مرحبا", 200),  # Valid multi-script text
    ]

    passed = 0
    failed = 0

    for test_name, text, expected_status in test_cases:
        try:
            response = requests.post(
                f"{API_BASE_URL}/api/v1/profile",
                json={"text": text},
                timeout=10
            )

            if response.status_code == expected_status:
                print_success(f"{test_name}: Got expected status {expected_status}")
                passed += 1
            else:
                print_error(f"{test_name}: Expected {expected_status}, got {response.status_code}")
                failed += 1

        except Exception as e:
            print_error(f"{test_name}: {e}")
            failed += 1

    print(f"\nResults: {passed} passed, {failed} failed")
    return failed == 0


def test_batch_profiling():
    """Test 5: Test batch profiling endpoint."""
    print_header("TEST 5: Batch Profiling")

    try:
        # Test with small batch
        batch_texts = [
            TEST_SAMPLES['hi_medical'],
            TEST_SAMPLES['bn_legal'],
            TEST_SAMPLES['ta_medical']
        ]

        response = requests.post(
            f"{API_BASE_URL}/api/v1/profile/batch",
            json={"texts": batch_texts},
            timeout=30
        )

        if response.status_code == 200:
            data = response.json()
            # The response structure is: {request_id, profiles, metadata}
            profiles = data.get('profiles', [])

            if len(profiles) == len(batch_texts):
                print_success(f"Batch profiling successful: {len(profiles)} results")
                return True
            else:
                print_error(f"Expected {len(batch_texts)} results, got {len(profiles)}")
                print(f"Response keys: {list(data.keys())}")
                return False
        else:
            print_error(f"Batch profiling failed with status {response.status_code}")
            print(f"Response: {response.text[:200]}")
            return False

    except Exception as e:
        print_error(f"Batch profiling test failed: {e}")
        import traceback
        traceback.print_exc()
        return False


def test_performance():
    """Test 6: Test API response time."""
    print_header("TEST 6: Performance Testing")

    try:
        text = TEST_SAMPLES['hi_medical']

        # Warm-up request
        requests.post(f"{API_BASE_URL}/api/v1/profile", json={"text": text}, timeout=10)

        # Measure response time
        times = []
        for _ in range(10):
            start = time.time()
            response = requests.post(
                f"{API_BASE_URL}/api/v1/profile",
                json={"text": text},
                timeout=10
            )
            duration = time.time() - start
            times.append(duration)

        avg_time = sum(times) / len(times)
        max_time = max(times)
        min_time = min(times)

        print(f"  Average response time: {avg_time*1000:.2f}ms")
        print(f"  Min: {min_time*1000:.2f}ms, Max: {max_time*1000:.2f}ms")

        if avg_time < 0.5:  # 500ms target
            print_success("Response time meets target (<500ms)")
            return True
        else:
            print_warning(f"Response time above target: {avg_time*1000:.2f}ms > 500ms")
            return False

    except Exception as e:
        print_error(f"Performance test failed: {e}")
        return False


def main():
    """Run all integration tests."""
    print_header("INDIAN LANGUAGES REQUEST PROFILER - INTEGRATION TESTS")

    results = {
        "Model Performance": test_model_performance(),
        "API Health": test_api_health(),
        "API Profiling": test_api_profiling(),
        "Edge Cases": test_edge_cases(),
        "Batch Profiling": test_batch_profiling(),
        "Performance": test_performance(),
    }

    # Summary
    print_header("TEST SUMMARY")

    passed = sum(1 for v in results.values() if v)
    total = len(results)

    for test_name, result in results.items():
        status = "PASS" if result else "FAIL"
        color = Colors.GREEN if result else Colors.RED
        print(f"{color}{status}{Colors.RESET} - {test_name}")

    print(f"\n{passed}/{total} test suites passed")

    if passed == total:
        print_success("\n🎉 All tests passed!")
        return 0
    else:
        print_error(f"\n❌ {total - passed} test suite(s) failed")
        return 1


if __name__ == '__main__':
    sys.exit(main())
