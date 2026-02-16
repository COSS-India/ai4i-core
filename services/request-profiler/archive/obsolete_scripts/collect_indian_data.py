#!/usr/bin/env python3
"""
Data Collection Script for Indian Languages
Collects real-world text data from multiple sources for 12 Indian languages across 6 domains.
"""

import os
import sys
import json
import logging
import unicodedata
from pathlib import Path
from typing import List, Dict, Tuple
import pandas as pd
import requests
from tqdm import tqdm
import time

# Add parent directory to path
sys.path.insert(0, str(Path(__file__).parent.parent))

# Setup logging
logging.basicConfig(
    level=logging.INFO,
    format='%(asctime)s - %(levelname)s - %(message)s'
)
logger = logging.getLogger(__name__)

# Configuration
TARGET_LANGUAGES = {
    'hi': 'Hindi',
    'bn': 'Bengali', 
    'ta': 'Tamil',
    'te': 'Telugu',
    'mr': 'Marathi',
    'gu': 'Gujarati',
    'kn': 'Kannada',
    'ml': 'Malayalam',
    'pa': 'Punjabi',
    'or': 'Odia',
    'as': 'Assamese',
    'ur': 'Urdu'
}

DOMAINS = ['medical', 'legal', 'technical', 'finance', 'casual', 'general']

# Target samples per domain
SAMPLES_PER_DOMAIN = 3000
TOTAL_SAMPLES = len(DOMAINS) * SAMPLES_PER_DOMAIN  # 18,000

# Data directories
DATA_DIR = Path(__file__).parent.parent / 'data'
RAW_DIR = DATA_DIR / 'raw' / 'indian_languages'
PROCESSED_DIR = DATA_DIR / 'processed'

# Create directories
RAW_DIR.mkdir(parents=True, exist_ok=True)
PROCESSED_DIR.mkdir(parents=True, exist_ok=True)


def normalize_unicode(text: str) -> str:
    """Normalize Unicode text for Indic scripts."""
    # Use NFC normalization for Indic scripts
    return unicodedata.normalize('NFC', text)


def detect_script(text: str) -> str:
    """Detect the script of the text."""
    if not text:
        return 'unknown'
    
    # Get the first character's script
    for char in text:
        if char.isalpha():
            try:
                script_name = unicodedata.name(char).split()[0]
                return script_name.lower()
            except:
                continue
    return 'unknown'


def download_wikipedia_dump(lang_code: str, max_articles: int = 500) -> List[Dict]:
    """
    Download Wikipedia articles for a given language.
    Uses Wikipedia API to fetch random articles.
    """
    logger.info(f"Downloading Wikipedia articles for {TARGET_LANGUAGES[lang_code]} ({lang_code})...")
    
    articles = []
    base_url = f"https://{lang_code}.wikipedia.org/w/api.php"
    
    # Fetch random articles in batches
    batch_size = 10
    num_batches = max_articles // batch_size
    
    for batch in tqdm(range(num_batches), desc=f"Wikipedia {lang_code}"):
        try:
            params = {
                'action': 'query',
                'format': 'json',
                'list': 'random',
                'rnnamespace': 0,  # Main namespace only
                'rnlimit': batch_size
            }
            
            response = requests.get(base_url, params=params, timeout=10)
            response.raise_for_status()
            data = response.json()
            
            # Get full content for each article
            for page in data.get('query', {}).get('random', []):
                page_id = page['id']
                
                # Fetch article content
                content_params = {
                    'action': 'query',
                    'format': 'json',
                    'pageids': page_id,
                    'prop': 'extracts',
                    'explaintext': True,
                    'exsectionformat': 'plain'
                }
                
                content_response = requests.get(base_url, params=content_params, timeout=10)
                content_data = content_response.json()
                
                page_data = content_data.get('query', {}).get('pages', {}).get(str(page_id), {})
                extract = page_data.get('extract', '')
                
                if extract and len(extract) > 100:  # Minimum length
                    articles.append({
                        'text': normalize_unicode(extract),
                        'language': lang_code,
                        'source': 'wikipedia',
                        'domain': 'general'  # Default to general, can be refined
                    })
            
            time.sleep(0.1)  # Rate limiting
            
        except Exception as e:
            logger.warning(f"Error fetching Wikipedia batch for {lang_code}: {e}")
            continue
    
    logger.info(f"Downloaded {len(articles)} Wikipedia articles for {lang_code}")
    return articles


def download_huggingface_dataset(dataset_name: str, split: str = 'train', max_samples: int = 1000) -> List[Dict]:
    """
    Download dataset from HuggingFace.
    """
    logger.info(f"Downloading HuggingFace dataset: {dataset_name}...")

    try:
        from datasets import load_dataset

        dataset = load_dataset(dataset_name, split=split, streaming=True)

        samples = []
        for i, example in enumerate(dataset):
            if i >= max_samples:
                break
            samples.append(example)

        logger.info(f"Downloaded {len(samples)} samples from {dataset_name}")
        return samples

    except Exception as e:
        logger.error(f"Error downloading {dataset_name}: {e}")
        return []


def collect_domain_samples(domain: str, target_count: int) -> List[Dict]:
    """
    Collect samples for a specific domain across all languages.
    """
    logger.info(f"Collecting {target_count} samples for domain: {domain}")

    samples = []
    samples_per_lang = target_count // len(TARGET_LANGUAGES)

    for lang_code, lang_name in TARGET_LANGUAGES.items():
        logger.info(f"Collecting {samples_per_lang} {domain} samples for {lang_name}...")

        if domain == 'general':
            # Use Wikipedia for general domain
            wiki_samples = download_wikipedia_dump(lang_code, max_articles=samples_per_lang)
            for sample in wiki_samples:
                sample['domain'] = domain
                samples.append(sample)

        elif domain == 'casual':
            # Use IndicSentiment for casual domain
            # For now, create placeholder - will be replaced with actual dataset
            logger.info(f"Casual domain for {lang_name} - using placeholder")
            # TODO: Download from ai4bharat/IndicSentiment

        elif domain == 'medical':
            # Medical domain - placeholder for MILU health & medicine
            logger.info(f"Medical domain for {lang_name} - using placeholder")
            # TODO: Download from MILU dataset (requires access)

        elif domain == 'legal':
            # Legal domain - placeholder for MILU law & governance
            logger.info(f"Legal domain for {lang_name} - using placeholder")
            # TODO: Download from MILU dataset (requires access)

        elif domain == 'technical':
            # Technical domain - placeholder for MILU engineering & science
            logger.info(f"Technical domain for {lang_name} - using placeholder")
            # TODO: Download from MILU dataset (requires access)

        elif domain == 'finance':
            # Finance domain - placeholder for MILU business
            logger.info(f"Finance domain for {lang_name} - using placeholder")
            # TODO: Download from MILU dataset (requires access)

    logger.info(f"Collected {len(samples)} samples for {domain} domain")
    return samples


def estimate_complexity(text: str) -> float:
    """
    Estimate text complexity using heuristics.
    Returns a score between 0.0 and 1.0.
    """
    if not text:
        return 0.0

    # Normalize text
    text = normalize_unicode(text)

    # Calculate features
    words = text.split()
    sentences = text.split('।') + text.split('.') + text.split('?') + text.split('!')
    sentences = [s.strip() for s in sentences if s.strip()]

    num_words = len(words)
    num_sentences = max(len(sentences), 1)

    # Average sentence length
    avg_sentence_len = num_words / num_sentences

    # Average word length
    avg_word_len = sum(len(w) for w in words) / max(num_words, 1)

    # Complexity score based on heuristics
    complexity = 0.0

    # Sentence length contribution (0-0.4)
    if avg_sentence_len > 30:
        complexity += 0.4
    elif avg_sentence_len > 20:
        complexity += 0.3
    elif avg_sentence_len > 10:
        complexity += 0.2
    else:
        complexity += 0.1

    # Word length contribution (0-0.3)
    if avg_word_len > 8:
        complexity += 0.3
    elif avg_word_len > 6:
        complexity += 0.2
    else:
        complexity += 0.1

    # Text length contribution (0-0.3)
    if num_words > 200:
        complexity += 0.3
    elif num_words > 100:
        complexity += 0.2
    else:
        complexity += 0.1

    return min(complexity, 1.0)


def create_dataset() -> pd.DataFrame:
    """
    Create the complete dataset by collecting samples from all sources.
    """
    logger.info("Starting data collection for Indian languages...")
    logger.info(f"Target: {TOTAL_SAMPLES} samples across {len(DOMAINS)} domains")

    all_samples = []

    # Collect samples for each domain
    for domain in DOMAINS:
        domain_samples = collect_domain_samples(domain, SAMPLES_PER_DOMAIN)
        all_samples.extend(domain_samples)

    # Convert to DataFrame
    df = pd.DataFrame(all_samples)

    # Add complexity scores
    logger.info("Calculating complexity scores...")
    df['complexity'] = df['text'].apply(estimate_complexity)

    # Add metadata
    df['script'] = df['text'].apply(detect_script)
    df['text_length'] = df['text'].apply(len)
    df['word_count'] = df['text'].apply(lambda x: len(x.split()))

    logger.info(f"Created dataset with {len(df)} samples")
    logger.info(f"Domain distribution:\n{df['domain'].value_counts()}")
    logger.info(f"Language distribution:\n{df['language'].value_counts()}")

    return df


def main():
    """Main execution function."""
    logger.info("=" * 80)
    logger.info("INDIAN LANGUAGES DATA COLLECTION")
    logger.info("=" * 80)

    # Create dataset
    df = create_dataset()

    # Save raw dataset
    raw_output_path = PROCESSED_DIR / 'indian_languages_dataset_raw.csv'
    df.to_csv(raw_output_path, index=False, encoding='utf-8')
    logger.info(f"Saved raw dataset to: {raw_output_path}")

    # Split into train/val/test (70/15/15)
    from sklearn.model_selection import train_test_split

    train_df, temp_df = train_test_split(df, test_size=0.3, random_state=42, stratify=df['domain'])
    val_df, test_df = train_test_split(temp_df, test_size=0.5, random_state=42, stratify=temp_df['domain'])

    logger.info(f"Train set: {len(train_df)} samples")
    logger.info(f"Validation set: {len(val_df)} samples")
    logger.info(f"Test set: {len(test_df)} samples")

    # Save splits
    train_df.to_csv(PROCESSED_DIR / 'indian_train.csv', index=False, encoding='utf-8')
    val_df.to_csv(PROCESSED_DIR / 'indian_val.csv', index=False, encoding='utf-8')
    test_df.to_csv(PROCESSED_DIR / 'indian_test.csv', index=False, encoding='utf-8')

    logger.info("=" * 80)
    logger.info("DATA COLLECTION COMPLETE")
    logger.info("=" * 80)


if __name__ == '__main__':
    main()

