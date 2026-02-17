#!/usr/bin/env python3
"""
Real-World Data Collection Script for Indian Languages
Collects authentic text from public sources across 6 languages and 6 domains.
Replaces all synthetic data with real-world corpus.
"""

import os
import sys
import json
import logging
import unicodedata
import random
import time
import requests
from pathlib import Path
from typing import List, Dict, Set, Optional
from collections import Counter
import pandas as pd
from tqdm import tqdm

# Add parent directory to path
sys.path.insert(0, str(Path(__file__).parent.parent))

# Import complexity utilities
try:
    from request_profiler.complexity_utils import estimate_complexity
except ImportError:
    # Fallback if module structure is different
    sys.path.insert(0, str(Path(__file__).parent.parent.parent))
    from request_profiler.request_profiler.complexity_utils import estimate_complexity

# Setup logging
logging.basicConfig(
    level=logging.INFO,
    format='%(asctime)s - %(levelname)s - %(message)s',
    handlers=[
        logging.FileHandler('data_collection.log'),
        logging.StreamHandler()
    ]
)
logger = logging.getLogger(__name__)

# Configuration
TARGET_LANGUAGES = {
    'hi': 'Hindi',
    'bn': 'Bengali', 
    'ta': 'Tamil',
    'te': 'Telugu',
    'kn': 'Kannada',
    'as': 'Assamese'
}

SCRIPT_NAMES = {
    'hi': 'devanagari',
    'bn': 'bengali',
    'ta': 'tamil',
    'te': 'telugu',
    'kn': 'kannada',
    'as': 'assamese'
}

DOMAINS = ['medical', 'legal', 'technical', 'finance', 'casual', 'general']

# Target: 900 samples per domain, 150 per language per domain = 5,400 total
SAMPLES_PER_DOMAIN = 900
SAMPLES_PER_LANGUAGE = 150
TOTAL_SAMPLES = len(DOMAINS) * SAMPLES_PER_DOMAIN

# Data directories
DATA_DIR = Path(__file__).parent.parent / 'data'
RAW_DIR = DATA_DIR / 'raw' / 'indian_languages'
PROCESSED_DIR = DATA_DIR / 'processed'
RAW_DIR.mkdir(parents=True, exist_ok=True)
PROCESSED_DIR.mkdir(parents=True, exist_ok=True)

# Wikipedia language codes
WIKI_LANG_CODES = {
    'hi': 'hi',
    'bn': 'bn',
    'ta': 'ta',
    'te': 'te',
    'kn': 'kn',
    'as': 'as'
}

# Request configuration
REQUEST_TIMEOUT = 30
MAX_RETRIES = 3
RETRY_DELAY = 2


def normalize_unicode(text: str) -> str:
    """Normalize Unicode text for Indic scripts using NFC normalization."""
    if not text:
        return ""
    return unicodedata.normalize('NFC', text.strip())


def is_valid_text(text: str, min_length: int = 20) -> bool:
    """
    Validate text quality.
    
    Args:
        text: Text to validate
        min_length: Minimum character length
        
    Returns:
        True if text is valid, False otherwise
    """
    if not text or len(text) < min_length:
        return False
    
    # Check for minimum word count
    words = text.split()
    if len(words) < 5:
        return False
    
    # Check for excessive repetition (simple heuristic)
    unique_words = set(words)
    if len(unique_words) / len(words) < 0.3:  # Less than 30% unique words
        return False
    
    return True


def detect_script(text: str) -> str:
    """Detect the primary script of the text."""
    if not text:
        return 'unknown'
    
    script_counts = Counter()
    for char in text:
        if char.isalpha():
            try:
                char_name = unicodedata.name(char)
                for script_key, script_name in SCRIPT_NAMES.items():
                    if script_name.upper() in char_name:
                        script_counts[script_name] += 1
                        break
            except:
                continue
    
    if not script_counts:
        return 'unknown'
    
    return script_counts.most_common(1)[0][0]


def make_request_with_retry(url: str, params: Dict = None, timeout: int = REQUEST_TIMEOUT) -> Optional[requests.Response]:
    """
    Make HTTP request with retry logic and exponential backoff.

    Args:
        url: URL to request
        params: Query parameters
        timeout: Request timeout in seconds

    Returns:
        Response object or None if all retries failed
    """
    for attempt in range(MAX_RETRIES):
        try:
            response = requests.get(url, params=params, timeout=timeout)
            response.raise_for_status()
            return response
        except requests.exceptions.RequestException as e:
            if attempt < MAX_RETRIES - 1:
                wait_time = RETRY_DELAY * (2 ** attempt)  # Exponential backoff
                logger.warning(f"Request failed (attempt {attempt + 1}/{MAX_RETRIES}): {e}. Retrying in {wait_time}s...")
                time.sleep(wait_time)
            else:
                logger.error(f"Request failed after {MAX_RETRIES} attempts: {e}")
                return None
    return None


def download_wikipedia_articles(lang_code: str, target_count: int, domain: str = 'general') -> List[Dict]:
    """
    Download Wikipedia articles for a specific language.

    Args:
        lang_code: Language code (e.g., 'hi', 'bn')
        target_count: Number of articles to download
        domain: Domain label for the articles

    Returns:
        List of article dictionaries
    """
    logger.info(f"Downloading {target_count} Wikipedia articles for {TARGET_LANGUAGES[lang_code]}...")

    wiki_code = WIKI_LANG_CODES.get(lang_code, lang_code)
    base_url = f"https://{wiki_code}.wikipedia.org/w/api.php"

    articles = []
    batch_size = 10
    num_batches = (target_count + batch_size - 1) // batch_size

    for batch in tqdm(range(num_batches), desc=f"Wikipedia {lang_code}"):
        # Get random article titles
        params = {
            'action': 'query',
            'format': 'json',
            'list': 'random',
            'rnnamespace': 0,  # Main namespace only
            'rnlimit': batch_size
        }

        response = make_request_with_retry(base_url, params)
        if not response:
            continue

        try:
            data = response.json()
        except json.JSONDecodeError:
            logger.warning(f"Failed to parse JSON response for batch {batch}")
            continue

        # Get full content for each article
        for page in data.get('query', {}).get('random', []):
            if len(articles) >= target_count:
                break

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

            content_response = make_request_with_retry(base_url, content_params)
            if not content_response:
                continue

            try:
                content_data = content_response.json()
            except json.JSONDecodeError:
                continue

            page_data = content_data.get('query', {}).get('pages', {}).get(str(page_id), {})
            extract = page_data.get('extract', '')

            # Split into paragraphs and take valid ones
            paragraphs = [p.strip() for p in extract.split('\n') if p.strip()]
            for para in paragraphs:
                if len(articles) >= target_count:
                    break

                normalized_text = normalize_unicode(para)
                if is_valid_text(normalized_text, min_length=50):
                    articles.append({
                        'text': normalized_text,
                        'language': lang_code,
                        'domain': domain,
                        'source': 'wikipedia',
                        'script': SCRIPT_NAMES[lang_code]
                    })

        # Rate limiting
        time.sleep(0.5)

    logger.info(f"Downloaded {len(articles)} Wikipedia articles for {TARGET_LANGUAGES[lang_code]}")
    return articles[:target_count]


def download_indicsentiment_data(lang_code: str, target_count: int) -> List[Dict]:
    """
    Download data from AI4Bharat IndicSentiment dataset for casual domain.

    Args:
        lang_code: Language code
        target_count: Number of samples to collect

    Returns:
        List of sample dictionaries
    """
    try:
        from datasets import load_dataset
        logger.info(f"Loading IndicSentiment for {TARGET_LANGUAGES[lang_code]}...")

        # Load dataset
        dataset = load_dataset("ai4bharat/IndicSentiment", split="train")

        samples = []
        for sample in dataset:
            if len(samples) >= target_count:
                break

            if sample.get('language') == lang_code:
                text = sample.get('text', '')
                normalized_text = normalize_unicode(text)

                if is_valid_text(normalized_text):
                    samples.append({
                        'text': normalized_text,
                        'language': lang_code,
                        'domain': 'casual',
                        'source': 'indicsentiment',
                        'script': SCRIPT_NAMES[lang_code]
                    })

        logger.info(f"Loaded {len(samples)} IndicSentiment samples for {TARGET_LANGUAGES[lang_code]}")
        return samples[:target_count]

    except Exception as e:
        logger.warning(f"Could not load IndicSentiment for {lang_code}: {e}")
        return []


# Complexity estimation is now imported from complexity_utils module


def collect_domain_data(domain: str, samples_per_lang: int) -> List[Dict]:
    """
    Collect data for a specific domain across all languages.

    Args:
        domain: Domain name
        samples_per_lang: Number of samples per language

    Returns:
        List of collected samples
    """
    logger.info(f"\n{'='*80}")
    logger.info(f"Collecting data for domain: {domain.upper()}")
    logger.info(f"{'='*80}")

    all_samples = []

    for lang_code, lang_name in TARGET_LANGUAGES.items():
        logger.info(f"\nCollecting {samples_per_lang} {domain} samples for {lang_name}...")

        samples = []

        if domain == 'casual':
            # Try IndicSentiment first
            samples = download_indicsentiment_data(lang_code, samples_per_lang)

            # Fallback to Wikipedia if needed
            if len(samples) < samples_per_lang:
                needed = samples_per_lang - len(samples)
                logger.info(f"Need {needed} more samples, using Wikipedia...")
                wiki_samples = download_wikipedia_articles(lang_code, needed, domain)
                samples.extend(wiki_samples)

        elif domain == 'general':
            # Use Wikipedia for general domain
            samples = download_wikipedia_articles(lang_code, samples_per_lang, domain)

        else:
            # For specialized domains (medical, legal, technical, finance)
            # Use Wikipedia as fallback (ideally would use domain-specific sources)
            logger.info(f"Using Wikipedia for {domain} domain (specialized sources not available)")
            samples = download_wikipedia_articles(lang_code, samples_per_lang, domain)

        # Add complexity scores
        for sample in samples:
            sample['complexity'] = estimate_complexity(sample['text'])

        all_samples.extend(samples)
        logger.info(f"✓ Collected {len(samples)} samples for {lang_name} - {domain}")

    return all_samples


def remove_duplicates(samples: List[Dict]) -> List[Dict]:
    """
    Remove duplicate texts from samples.

    Args:
        samples: List of sample dictionaries

    Returns:
        Deduplicated list of samples
    """
    seen_texts = set()
    unique_samples = []

    for sample in samples:
        text_normalized = sample['text'].lower().strip()
        if text_normalized not in seen_texts:
            seen_texts.add(text_normalized)
            unique_samples.append(sample)

    duplicates_removed = len(samples) - len(unique_samples)
    if duplicates_removed > 0:
        logger.info(f"Removed {duplicates_removed} duplicate samples")

    return unique_samples


def validate_dataset(df: pd.DataFrame) -> Dict:
    """
    Validate dataset quality and distribution.

    Args:
        df: Dataset DataFrame

    Returns:
        Validation metrics dictionary
    """
    logger.info("\n" + "="*80)
    logger.info("DATASET VALIDATION")
    logger.info("="*80)

    metrics = {}

    # Check total samples
    metrics['total_samples'] = len(df)
    logger.info(f"Total samples: {len(df)}")

    # Check for duplicates
    duplicates = df['text'].duplicated().sum()
    metrics['duplicates'] = duplicates
    logger.info(f"Duplicate texts: {duplicates}")

    # Language distribution
    lang_dist = df['language'].value_counts().to_dict()
    metrics['language_distribution'] = lang_dist
    logger.info(f"\nLanguage distribution:")
    for lang, count in sorted(lang_dist.items()):
        logger.info(f"  {TARGET_LANGUAGES[lang]}: {count}")

    # Domain distribution
    domain_dist = df['domain'].value_counts().to_dict()
    metrics['domain_distribution'] = domain_dist
    logger.info(f"\nDomain distribution:")
    for domain, count in sorted(domain_dist.items()):
        logger.info(f"  {domain}: {count}")

    # Complexity distribution
    complexity_stats = df['complexity'].describe()
    metrics['complexity_stats'] = complexity_stats.to_dict()
    logger.info(f"\nComplexity statistics:")
    logger.info(f"  Mean: {complexity_stats['mean']:.3f}")
    logger.info(f"  Std:  {complexity_stats['std']:.3f}")
    logger.info(f"  Min:  {complexity_stats['min']:.3f}")
    logger.info(f"  Max:  {complexity_stats['max']:.3f}")

    # Text length statistics
    df['text_length'] = df['text'].apply(len)
    df['word_count'] = df['text'].apply(lambda x: len(x.split()))

    logger.info(f"\nText length statistics:")
    logger.info(f"  Mean chars: {df['text_length'].mean():.1f}")
    logger.info(f"  Mean words: {df['word_count'].mean():.1f}")

    # Source distribution
    source_dist = df['source'].value_counts().to_dict()
    metrics['source_distribution'] = source_dist
    logger.info(f"\nSource distribution:")
    for source, count in sorted(source_dist.items()):
        logger.info(f"  {source}: {count}")

    # Validation checks
    issues = []

    if duplicates > 0:
        issues.append(f"Found {duplicates} duplicate texts")

    # Check language balance (should be roughly equal)
    lang_counts = list(lang_dist.values())
    if max(lang_counts) / min(lang_counts) > 1.5:
        issues.append("Language distribution is imbalanced")

    # Check domain balance
    domain_counts = list(domain_dist.values())
    if max(domain_counts) / min(domain_counts) > 1.5:
        issues.append("Domain distribution is imbalanced")

    if issues:
        logger.warning("\n⚠️  Validation issues found:")
        for issue in issues:
            logger.warning(f"  - {issue}")
    else:
        logger.info("\n✓ All validation checks passed!")

    metrics['validation_issues'] = issues

    return metrics


def split_dataset(df: pd.DataFrame) -> tuple:
    """
    Split dataset into train/val/test (80/10/10).

    Args:
        df: Complete dataset DataFrame

    Returns:
        Tuple of (train_df, val_df, test_df)
    """
    from sklearn.model_selection import train_test_split

    logger.info("\n" + "="*80)
    logger.info("SPLITTING DATASET")
    logger.info("="*80)

    # First split: 80% train, 20% temp
    train_df, temp_df = train_test_split(
        df,
        test_size=0.2,
        random_state=42,
        stratify=df['domain']
    )

    # Second split: 10% val, 10% test (50/50 of the 20%)
    val_df, test_df = train_test_split(
        temp_df,
        test_size=0.5,
        random_state=42,
        stratify=temp_df['domain']
    )

    logger.info(f"Train: {len(train_df)} samples ({len(train_df)/len(df)*100:.1f}%)")
    logger.info(f"Val:   {len(val_df)} samples ({len(val_df)/len(df)*100:.1f}%)")
    logger.info(f"Test:  {len(test_df)} samples ({len(test_df)/len(df)*100:.1f}%)")

    # Verify no overlap
    train_texts = set(train_df['text'])
    val_texts = set(val_df['text'])
    test_texts = set(test_df['text'])

    assert len(train_texts & val_texts) == 0, "Train and val sets overlap!"
    assert len(train_texts & test_texts) == 0, "Train and test sets overlap!"
    assert len(val_texts & test_texts) == 0, "Val and test sets overlap!"

    logger.info("✓ No overlap between splits verified")

    return train_df, val_df, test_df


def main():
    """Main data collection pipeline."""
    logger.info("="*80)
    logger.info("REAL-WORLD INDIAN LANGUAGES DATA COLLECTION")
    logger.info("="*80)
    logger.info(f"Target: {TOTAL_SAMPLES} samples across {len(DOMAINS)} domains and {len(TARGET_LANGUAGES)} languages")
    logger.info(f"Languages: {', '.join(TARGET_LANGUAGES.values())}")
    logger.info(f"Domains: {', '.join(DOMAINS)}")
    logger.info("="*80)

    try:
        # Collect data for all domains
        all_samples = []

        for domain in DOMAINS:
            domain_samples = collect_domain_data(domain, SAMPLES_PER_LANGUAGE)
            all_samples.extend(domain_samples)

            logger.info(f"✓ Collected {len(domain_samples)} samples for {domain} domain")
            logger.info(f"Total samples so far: {len(all_samples)}")

        # Remove duplicates
        logger.info(f"\nRemoving duplicates from {len(all_samples)} samples...")
        all_samples = remove_duplicates(all_samples)
        logger.info(f"After deduplication: {len(all_samples)} samples")

        # Convert to DataFrame
        df = pd.DataFrame(all_samples)

        # Validate dataset
        validation_metrics = validate_dataset(df)

        # Save validation metrics
        metrics_file = PROCESSED_DIR / 'dataset_validation_metrics.json'
        with open(metrics_file, 'w', encoding='utf-8') as f:
            # Convert non-serializable objects to strings
            serializable_metrics = {}
            for key, value in validation_metrics.items():
                if isinstance(value, dict):
                    serializable_metrics[key] = {str(k): float(v) if isinstance(v, (int, float)) else str(v)
                                                  for k, v in value.items()}
                elif isinstance(value, list):
                    serializable_metrics[key] = value
                else:
                    serializable_metrics[key] = str(value) if not isinstance(value, (int, float)) else value

            json.dump(serializable_metrics, f, indent=2, ensure_ascii=False)
        logger.info(f"✓ Saved validation metrics to: {metrics_file}")

        # Split dataset
        train_df, val_df, test_df = split_dataset(df)

        # Save datasets
        logger.info("\n" + "="*80)
        logger.info("SAVING DATASETS")
        logger.info("="*80)

        # Save complete dataset
        output_file = PROCESSED_DIR / 'indian_languages_dataset.csv'
        df.to_csv(output_file, index=False, encoding='utf-8')
        logger.info(f"✓ Saved complete dataset: {output_file} ({len(df)} samples)")

        # Save splits
        train_file = PROCESSED_DIR / 'indian_languages_train.csv'
        val_file = PROCESSED_DIR / 'indian_languages_val.csv'
        test_file = PROCESSED_DIR / 'indian_languages_test.csv'

        train_df.to_csv(train_file, index=False, encoding='utf-8')
        val_df.to_csv(val_file, index=False, encoding='utf-8')
        test_df.to_csv(test_file, index=False, encoding='utf-8')

        logger.info(f"✓ Saved train split: {train_file} ({len(train_df)} samples)")
        logger.info(f"✓ Saved val split: {val_file} ({len(val_df)} samples)")
        logger.info(f"✓ Saved test split: {test_file} ({len(test_df)} samples)")

        # Print summary
        logger.info("\n" + "="*80)
        logger.info("DATA COLLECTION COMPLETE!")
        logger.info("="*80)
        logger.info(f"Total samples collected: {len(df)}")
        logger.info(f"Train: {len(train_df)} | Val: {len(val_df)} | Test: {len(test_df)}")
        logger.info(f"All files saved to: {PROCESSED_DIR}")

        if validation_metrics.get('validation_issues'):
            logger.warning("\n⚠️  Please review validation issues in the log above")
            return False

        logger.info("\n✓ All quality checks passed!")
        return True

    except Exception as e:
        logger.error(f"\n❌ Error during data collection: {e}")
        import traceback
        traceback.print_exc()
        return False


if __name__ == '__main__':
    success = main()
    sys.exit(0 if success else 1)

