#!/usr/bin/env python3
"""
Triton Inference Server Endpoints Configuration
================================================

This file contains the Triton server URLs for all AI services.
These URLs point to remote GPU servers running the actual AI models.

HOW TO USE:
-----------
1. Get the latest Triton URLs from your team (shared offline)
2. Update the TRITON_ENDPOINTS dict below with the correct URLs
3. Run this script to apply endpoints to all service .env files:
      python infrastructure/triton_endpoints.py
4. Optionally, update the model_management_db with:
      python infrastructure/triton_endpoints.py --update-db

IMPORTANT:
- These URLs change when Triton servers are redeployed
- Always verify URLs are reachable before starting services
- The LLM endpoint may be on a different cloud provider
"""

import os
import sys
import re

# ============================================================================
# TRITON SERVER ENDPOINTS - UPDATE THESE WITH YOUR ACTUAL URLs
# ============================================================================

TRITON_ENDPOINTS = {
    # Service Name                   Triton URL                          Port Info
    "asr-service":                   "http://13.200.133.97:5000",       # ASR (Conformer Hindi)
    "tts-service":                   "http://13.200.133.97:9000",       # TTS (FastPitch Hindi)
    "nmt-service":                   "http://13.200.133.97:8000",       # NMT (IndicTrans2 En-Hi)
    "llm-service":                   "http://52.200.236.126:8001",      # LLM (Indic Chat) - US East
    "ner-service":                   "http://65.1.35.3:8300",           # NER (IndicNER)
    "ocr-service":                   "http://65.1.35.3:8400",           # OCR (IndicOCR)
    "language-detection-service":    "http://65.1.35.3:8000",           # Language Detection (IndicLID)
    "transliteration-service":       "http://65.1.35.3:8200",           # Transliteration (IndicXlit)
    "speaker-diarization-service":   "http://65.1.35.3:8700",           # Speaker Diarization (Pyannote)
    "audio-lang-detection-service":  "http://65.1.35.3:8100",           # Audio Language Detection (Whisper)
    "language-diarization-service":  "http://65.1.35.3:8600",           # Language Diarization
}

# Model Management DB - service name to endpoint mapping (for seeder)
# These are used when seeding the model_management_db
MODEL_MANAGEMENT_ENDPOINTS = {
    "asr-hindi-prod":           TRITON_ENDPOINTS["asr-service"],
    "tts-hindi-prod":           TRITON_ENDPOINTS["tts-service"],
    "nmt-en-hi-prod":           TRITON_ENDPOINTS["nmt-service"],
    "gpu-t4":                   TRITON_ENDPOINTS["nmt-service"],  # ai4bharat/indictrans--gpu-t4 service
    "llm-indic-prod":           TRITON_ENDPOINTS["llm-service"],
    "ner-indic-prod":           TRITON_ENDPOINTS["ner-service"],
    "ocr-indic-prod":           TRITON_ENDPOINTS["ocr-service"],
    "langdetect-prod":          TRITON_ENDPOINTS["language-detection-service"],
    "xlit-indic-prod":          TRITON_ENDPOINTS["transliteration-service"],
    "speaker-diarize-prod":     TRITON_ENDPOINTS["speaker-diarization-service"],
    "audio-langdetect-prod":    TRITON_ENDPOINTS["audio-lang-detection-service"],
    "lang-diarize-prod":        TRITON_ENDPOINTS["language-diarization-service"],
}


def update_env_files():
    """Update TRITON_ENDPOINT in each service's .env file."""
    base_dir = os.path.dirname(os.path.dirname(os.path.abspath(__file__)))
    services_dir = os.path.join(base_dir, "services")
    updated = 0

    for service_name, triton_url in TRITON_ENDPOINTS.items():
        env_path = os.path.join(services_dir, service_name, ".env")
        if not os.path.exists(env_path):
            print(f"  SKIP  {service_name}: .env not found")
            continue

        with open(env_path, "r") as f:
            content = f.read()

        # Replace TRITON_ENDPOINT line
        if "TRITON_ENDPOINT=" in content:
            new_content = re.sub(
                r"TRITON_ENDPOINT=.*",
                f"TRITON_ENDPOINT={triton_url}",
                content,
            )
            if new_content != content:
                with open(env_path, "w") as f:
                    f.write(new_content)
                print(f"  OK    {service_name}: {triton_url}")
                updated += 1
            else:
                print(f"  SAME  {service_name}: already set to {triton_url}")
        else:
            # Append TRITON_ENDPOINT if not present
            with open(env_path, "a") as f:
                f.write(f"\nTRITON_ENDPOINT={triton_url}\n")
            print(f"  ADD   {service_name}: {triton_url}")
            updated += 1

    return updated


def update_database():
    """Update Triton endpoints in model_management_db via SQL."""
    try:
        import psycopg2
    except ImportError:
        print("ERROR: psycopg2 not installed. Run: pip install psycopg2-binary")
        sys.exit(1)

    db_url = os.getenv(
        "DATABASE_URL",
        "postgresql://dhruva_user:dhruva_secure_password_2024@localhost:5434/model_management_db",
    )

    # Parse simple postgres URL
    conn = psycopg2.connect(db_url)
    conn.autocommit = True
    cur = conn.cursor()

    updated = 0
    for service_name, endpoint in MODEL_MANAGEMENT_ENDPOINTS.items():
        cur.execute(
            "UPDATE services SET endpoint = %s WHERE name = %s",
            (endpoint, service_name),
        )
        if cur.rowcount > 0:
            print(f"  OK    {service_name}: {endpoint}")
            updated += 1
        else:
            print(f"  SKIP  {service_name}: not found in DB")

    cur.close()
    conn.close()
    return updated


def print_summary():
    """Print a summary table of all endpoints."""
    print("\n" + "=" * 75)
    print("TRITON ENDPOINT CONFIGURATION")
    print("=" * 75)
    print(f"{'Service':<35} {'Triton URL':<40}")
    print("-" * 75)
    for service, url in TRITON_ENDPOINTS.items():
        print(f"{service:<35} {url:<40}")
    print("=" * 75)


if __name__ == "__main__":
    print_summary()

    if "--update-db" in sys.argv:
        print("\nUpdating model_management_db endpoints...")
        count = update_database()
        print(f"\nUpdated {count} service endpoints in database.")
    elif "--help" in sys.argv:
        print("\nUsage:")
        print("  python infrastructure/triton_endpoints.py              Show endpoints + update .env files")
        print("  python infrastructure/triton_endpoints.py --update-db  Also update model_management_db")
        print("  python infrastructure/triton_endpoints.py --dry-run    Show endpoints only (no changes)")
    elif "--dry-run" in sys.argv:
        print("\nDry run - no changes made.")
    else:
        print("\nUpdating service .env files...")
        count = update_env_files()
        print(f"\nUpdated {count} .env files.")
        print("\nTIP: Run with --update-db to also update the database endpoints.")
