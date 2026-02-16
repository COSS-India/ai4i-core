#!/usr/bin/env python3
"""
Diagnostic script to test classification accuracy across languages, domains, and text lengths.
Identifies why the model is misclassifying texts.
"""
import json
import requests
from typing import Dict, List
import pandas as pd

API_URL = "http://localhost:8000/api/v1/profile"

# Test cases across different scenarios
TEST_CASES = {
    # English medical texts (various lengths)
    "en_medical_short": "I have fever",
    "en_medical_medium": "I am having fever and headache since yesterday",
    "en_medical_long": "The patient is experiencing acute myocardial infarction and requires immediate medical intervention with proper cardiac care",
    
    # English other domains
    "en_legal_short": "Sign the contract",
    "en_legal_medium": "This agreement is legally binding for both parties",
    "en_legal_long": "This contract constitutes a legally binding agreement between the parties and shall be governed by applicable laws",
    
    "en_technical_short": "Update the server",
    "en_technical_medium": "Update the server configuration file and restart services",
    "en_technical_long": "The system architecture requires updating the server configuration parameters and implementing proper load balancing mechanisms",
    
    "en_finance_short": "Check the balance",
    "en_finance_medium": "The quarterly financial report shows significant growth",
    "en_finance_long": "The comprehensive financial analysis indicates substantial revenue growth with improved profit margins and strong market performance",
    
    "en_casual_short": "How are you",
    "en_casual_medium": "Hey what's up? How are you doing today?",
    "en_casual_long": "Hey there! What's going on? I was just thinking about you and wanted to check in to see how you're doing",
    
    # Hindi medical texts (from training data)
    "hi_medical_short": "मुझे बुखार है",
    "hi_medical_medium": "रोगी को बुखार और सिरदर्द की शिकायत है",
    "hi_medical_long": "रोगी को तीव्र हृदयाघात हुआ है और तत्काल उपचार की आवश्यकता है जिसमें उचित हृदय देखभाल शामिल है",
    
    # Bengali medical texts
    "bn_medical_short": "আমার জ্বর আছে",
    "bn_medical_medium": "রোগীর জ্বর এবং মাথাব্যথার অভিযোগ রয়েছে",
    "bn_medical_long": "রোগীর তীব্র হৃদরোগ হয়েছে এবং তাৎক্ষণিক চিকিৎসা হস্তক্ষেপ প্রয়োজন",
    
    # Tamil medical texts
    "ta_medical_short": "எனக்கு காய்ச்சல் உள்ளது",
    "ta_medical_medium": "நோயாளிக்கு காய்ச்சல் மற்றும் தலைவலி உள்ளது",
    "ta_medical_long": "நோயாளிக்கு கடுமையான மாரடைப்பு ஏற்பட்டுள்ளது மற்றும் உடனடி மருத்துவ தலையீடு தேவை",
    
    # Telugu medical texts
    "te_medical_short": "నాకు జ్వరం ఉంది",
    "te_medical_medium": "రోగికి జ్వరం మరియు తలనొప్పి ఉంది",
    "te_medical_long": "రోగికి తీవ్రమైన గుండెపోటు వచ్చింది మరియు తక్షణ వైద్య జోక్యం అవసరం",
    
    # Kannada medical texts
    "kn_medical_short": "ನನಗೆ ಜ್ವರವಿದೆ",
    "kn_medical_medium": "ರೋಗಿಗೆ ಜ್ವರ ಮತ್ತು ತಲೆನೋವು ಇದೆ",
    "kn_medical_long": "ರೋಗಿಗೆ ತೀವ್ರ ಹೃದಯಾಘಾತವಾಗಿದೆ ಮತ್ತು ತಕ್ಷಣದ ವೈದ್ಯಕೀಯ ಹಸ್ತಕ್ಷೇಪ ಅಗತ್ಯವಿದೆ",
    
    # Assamese medical texts
    "as_medical_short": "মোৰ জ্বৰ আছে",
    "as_medical_medium": "ৰোগীৰ জ্বৰ আৰু মূৰৰ বিষ আছে",
    "as_medical_long": "ৰোগীৰ তীব্ৰ হৃদৰোগ হৈছে আৰু তাৎক্ষণিক চিকিৎসা হস্তক্ষেপৰ প্ৰয়োজন",
}


def profile_text(text: str) -> Dict:
    """Profile a single text and return the result."""
    try:
        response = requests.post(
            API_URL,
            json={"text": text},
            timeout=10
        )
        if response.status_code == 200:
            return response.json()
        else:
            return {"error": f"HTTP {response.status_code}", "detail": response.text[:200]}
    except Exception as e:
        return {"error": str(e)}


def analyze_results():
    """Run all test cases and analyze results."""
    print("=" * 100)
    print("CLASSIFICATION DIAGNOSTIC REPORT")
    print("=" * 100)
    print()
    
    results = []
    
    for test_id, text in TEST_CASES.items():
        lang, domain, length = test_id.split('_')
        
        print(f"\nTesting: {test_id}")
        print(f"  Text: {text[:60]}{'...' if len(text) > 60 else ''}")
        print(f"  Expected: domain={domain}, language={lang}")
        
        result = profile_text(text)
        
        if "error" in result:
            print(f"  ❌ ERROR: {result['error']}")
            results.append({
                "test_id": test_id,
                "expected_lang": lang,
                "expected_domain": domain,
                "expected_length": length,
                "text_length": len(text),
                "word_count": len(text.split()),
                "status": "ERROR",
                "error": result.get("error", "Unknown")
            })
            continue
        
        profile = result.get("profile", {})
        predicted_domain = profile.get("domain", {}).get("label", "unknown")
        domain_confidence = profile.get("domain", {}).get("confidence", 0.0)
        detected_lang = profile.get("language", {}).get("primary", "unknown")
        complexity = profile.get("scores", {}).get("complexity_score", 0.0)
        
        # Check if prediction is correct
        domain_correct = predicted_domain == domain
        lang_correct = detected_lang == lang
        
        status = "✓" if domain_correct else "✗"
        print(f"  {status} Predicted: domain={predicted_domain} ({domain_confidence:.2%}), language={detected_lang}")
        print(f"     Complexity: {complexity:.3f}, Words: {len(text.split())}")
        
        # Get top 3 domains
        top_3 = profile.get("domain", {}).get("top_3", [])
        if top_3:
            top_3_str = ', '.join([f"{d['label']}({d['confidence']:.2%})" for d in top_3[:3]])
            print(f"     Top 3: {top_3_str}")

        results.append({
            "test_id": test_id,
            "expected_lang": lang,
            "expected_domain": domain,
            "expected_length": length,
            "text_length": len(text),
            "word_count": len(text.split()),
            "predicted_domain": predicted_domain,
            "domain_confidence": domain_confidence,
            "detected_lang": detected_lang,
            "complexity": complexity,
            "domain_correct": domain_correct,
            "lang_correct": lang_correct,
            "status": "PASS" if domain_correct else "FAIL"
        })
    
    # Summary statistics
    print("\n" + "=" * 100)
    print("SUMMARY STATISTICS")
    print("=" * 100)
    
    df = pd.DataFrame(results)
    
    # Overall accuracy
    total = len(df)
    domain_correct = df["domain_correct"].sum()
    lang_correct = df["lang_correct"].sum()
    
    print(f"\nOverall Accuracy:")
    print(f"  Domain Classification: {domain_correct}/{total} ({domain_correct/total*100:.1f}%)")
    print(f"  Language Detection: {lang_correct}/{total} ({lang_correct/total*100:.1f}%)")
    
    # By language
    print(f"\nAccuracy by Language:")
    for lang in df["expected_lang"].unique():
        lang_df = df[df["expected_lang"] == lang]
        correct = lang_df["domain_correct"].sum()
        total_lang = len(lang_df)
        print(f"  {lang}: {correct}/{total_lang} ({correct/total_lang*100:.1f}%)")
    
    # By domain
    print(f"\nAccuracy by Domain:")
    for domain in df["expected_domain"].unique():
        domain_df = df[df["expected_domain"] == domain]
        correct = domain_df["domain_correct"].sum()
        total_domain = len(domain_df)
        print(f"  {domain}: {correct}/{total_domain} ({correct/total_domain*100:.1f}%)")
    
    # By text length
    print(f"\nAccuracy by Text Length:")
    for length in df["expected_length"].unique():
        length_df = df[df["expected_length"] == length]
        correct = length_df["domain_correct"].sum()
        total_length = len(length_df)
        print(f"  {length}: {correct}/{total_length} ({correct/total_length*100:.1f}%)")
    
    # Confidence analysis
    print(f"\nConfidence Analysis:")
    print(f"  Average confidence (correct): {df[df['domain_correct']]['domain_confidence'].mean():.2%}")
    print(f"  Average confidence (incorrect): {df[~df['domain_correct']]['domain_confidence'].mean():.2%}")
    
    # Save detailed results
    df.to_csv("diagnostic_results.csv", index=False)
    print(f"\n✓ Detailed results saved to: diagnostic_results.csv")
    
    return df


if __name__ == "__main__":
    df = analyze_results()

