# Indian Languages Data Collection Guide

## Overview
This guide explains how to collect real-world datasets for training the Translation Request Profiler on Indian languages.

## Target: 18,000 samples across 6 domains and 12 languages

### Languages (12)
- Hindi (hi), Bengali (bn), Tamil (ta), Telugu (te)
- Marathi (mr), Gujarati (gu), Kannada (kn), Malayalam (ml)
- Punjabi (pa), Odia (or), Assamese (as), Urdu (ur)

### Domains (6)
- Medical (3,000 samples)
- Legal (3,000 samples)
- Technical (3,000 samples)
- Finance (3,000 samples)
- Casual (3,000 samples)
- General (3,000 samples)

## Data Sources

### 1. AI4Bharat Datasets (Primary Source)

#### MILU Dataset (Gated - Requires Access Request)
- **URL**: https://huggingface.co/datasets/ai4bharat/MILU
- **Content**: 80K questions across 11 languages, 8 domains, 41 subjects
- **Languages**: Bengali, Gujarati, Hindi, Kannada, Malayalam, Marathi, Odia, Punjabi, Tamil, Telugu, English
- **Domains**: Arts & Humanities, Business, Engineering & Tech, Environmental Sciences, Health & Medicine, Law & Governance, Science, Social Sciences
- **How to Access**:
  1. Create HuggingFace account
  2. Request access at the dataset page
  3. Wait for approval (usually 1-2 days)
  4. Use HuggingFace CLI to download: `huggingface-cli login` then `datasets.load_dataset("ai4bharat/MILU")`

#### Sangraha (Public)
- **URL**: https://huggingface.co/datasets/ai4bharat/sangraha
- **Content**: 268M samples for pretraining, 22 Indian languages
- **Use**: General domain, large-scale monolingual corpus
- **Download**: `datasets.load_dataset("ai4bharat/sangraha")`

#### IndicSentiment (Public)
- **URL**: https://huggingface.co/datasets/ai4bharat/IndicSentiment
- **Content**: Sentiment analysis dataset, 11 languages
- **Use**: Casual domain (social media, reviews)
- **Download**: `datasets.load_dataset("ai4bharat/IndicSentiment")`

#### IndicQA (Public)
- **URL**: https://huggingface.co/datasets/ai4bharat/IndicQA
- **Content**: Question answering dataset, multiple Indic languages
- **Use**: General/Technical domains
- **Download**: `datasets.load_dataset("ai4bharat/IndicQA")`

### 2. Wikipedia Dumps

#### Download Wikipedia for Each Language
```python
import requests

def download_wikipedia(lang_code, max_articles=500):
    base_url = f"https://{lang_code}.wikipedia.org/w/api.php"
    # Use Wikipedia API to fetch random articles
    # See scripts/collect_indian_data.py for implementation
```

**Languages**: hi, bn, ta, te, mr, gu, kn, ml, pa, or, as, ur

### 3. Domain-Specific Mapping

#### Medical Domain
- **MILU**: Health & Medicine category
- **Additional**: Medical Wikipedia articles, health forums

#### Legal Domain
- **MILU**: Law & Governance category
- **Additional**: Legal Wikipedia articles, government documents

#### Technical Domain
- **MILU**: Engineering & Tech, Science categories
- **Additional**: Technical Wikipedia articles, documentation

#### Finance Domain
- **MILU**: Business Studies category
- **Additional**: Finance Wikipedia articles, business news

#### Casual Domain
- **IndicSentiment**: Social media text, reviews
- **Additional**: Casual conversations, forums

#### General Domain
- **Wikipedia**: General articles
- **Sangraha**: General monolingual text

## Data Collection Steps

### Step 1: Setup HuggingFace
```bash
pip install datasets huggingface-hub
huggingface-cli login
```

### Step 2: Request Access to Gated Datasets
1. Visit https://huggingface.co/datasets/ai4bharat/MILU
2. Click "Request Access"
3. Fill in the form explaining your use case
4. Wait for approval

### Step 3: Download Public Datasets
```python
from datasets import load_dataset

# Download IndicSentiment
sentiment_data = load_dataset("ai4bharat/IndicSentiment")

# Download Sangraha (large - use streaming)
sangraha_data = load_dataset("ai4bharat/sangraha", streaming=True)

# Download IndicQA
qa_data = load_dataset("ai4bharat/IndicQA")
```

### Step 4: Download Wikipedia
```bash
python scripts/collect_indian_data.py --source wikipedia --languages hi,bn,ta,te,mr,gu,kn,ml,pa,or,as,ur
```

### Step 5: Process and Combine
```bash
python scripts/collect_indian_data.py --combine-all --output data/processed/indian_languages_dataset.csv
```

## Data Processing Requirements

### Unicode Normalization
```python
import unicodedata

def normalize_text(text):
    # Use NFC normalization for Indic scripts
    return unicodedata.normalize('NFC', text)
```

### Script Detection
- Devanagari: Hindi, Marathi
- Bengali: Bengali, Assamese
- Tamil, Telugu, Gujarati, Kannada, Malayalam, Gurmukhi (Punjabi), Odia, Perso-Arabic (Urdu)

### Complexity Labeling
Since real data doesn't have ground truth complexity labels, use heuristics:
- Sentence length (avg words per sentence)
- Word complexity (avg characters per word)
- Entity density
- Technical term frequency

## Expected Dataset Structure

```csv
text,language,domain,complexity,source,script
"मधुमेह एक चयापचय रोग है...",hi,medical,0.75,milu,devanagari
"সুপ্রিম কোর্ট রায় দিয়েছে...",bn,legal,0.82,milu,bengali
"இந்த தொழில்நுட்பம்...",ta,technical,0.68,wikipedia,tamil
...
```

## Next Steps After Data Collection

1. **Feature Extraction Update**: Modify `request_profiler/features.py` to handle Indic scripts
2. **NER Model Update**: Replace spaCy with IndicNER or MuRIL
3. **Model Training**: Retrain domain classifier and complexity regressor
4. **Validation**: Test on held-out test set for each language
5. **API Testing**: Verify all endpoints work with Indic text

## Current Status

✅ Plan documented
✅ Data sources identified
⏳ Awaiting access to MILU dataset
⏳ Wikipedia download in progress
⏳ Feature extraction updates needed
⏳ Model retraining pending

