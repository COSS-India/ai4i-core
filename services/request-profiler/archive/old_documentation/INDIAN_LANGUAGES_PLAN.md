# Indian Languages Retraining Plan

## Overview
Retrain the Translation Request Profiler models using real-world datasets focused on Indian languages instead of synthetic data.

## Target Languages (12 languages)
1. **Hindi** (hi) - Devanagari script
2. **Bengali** (bn) - Bengali script
3. **Tamil** (ta) - Tamil script
4. **Telugu** (te) - Telugu script
5. **Marathi** (mr) - Devanagari script
6. **Gujarati** (gu) - Gujarati script
7. **Kannada** (kn) - Kannada script
8. **Malayalam** (ml) - Malayalam script
9. **Punjabi** (pa) - Gurmukhi script
10. **Odia** (or) - Odia script
11. **Assamese** (as) - Bengali script
12. **Urdu** (ur) - Perso-Arabic script

## Data Sources

### 1. AI4Bharat Datasets (Primary Source)
- **MILU** (ai4bharat/MILU): 80K questions across 11 languages, 8 domains, 41 subjects
  - Domains: Arts & Humanities, Business, Engineering & Tech, Environmental Sciences, Health & Medicine, Law & Governance, Science, Social Sciences
  - Languages: Bengali, Gujarati, Hindi, Kannada, Malayalam, Marathi, Odia, Punjabi, Tamil, Telugu, English
  - **Status**: Gated dataset (requires access request)

- **Sangraha** (ai4bharat/sangraha): 268M samples for pretraining
  - Largest Indic language corpus
  - 22 Indian languages

- **IndicCorp v2**: Monolingual corpus
  - 20.9 billion tokens
  - 24 constitutionally recognized languages

- **IndicSentiment**: Sentiment analysis dataset
  - 11 languages
  - Can be used for casual/general domain

- **IndicQA**: Question answering dataset
  - Multiple Indic languages
  - Can be used for general/technical domains

### 2. Wikipedia Dumps
- Download Wikipedia dumps for all 12 target languages
- Extract articles for general domain
- Use category information to classify into domains

### 3. Domain-Specific Sources
- **Medical**: Extract from MILU health & medicine category
- **Legal**: Extract from MILU law & governance category
- **Technical**: Extract from MILU engineering & tech, science categories
- **Finance**: Extract from MILU business studies category
- **Casual**: Use IndicSentiment, social media text
- **General**: Wikipedia, news articles

## Data Collection Strategy

### Target: 18,000 samples (3,000 per domain)
- **Medical**: 3,000 samples
- **Legal**: 3,000 samples
- **Technical**: 3,000 samples
- **Finance**: 3,000 samples
- **Casual**: 3,000 samples
- **General**: 3,000 samples

### Language Distribution (aim for balanced coverage)
- ~1,500 samples per language across all domains
- Prioritize high-resource languages: Hindi, Bengali, Tamil, Telugu
- Ensure minimum 500 samples for low-resource languages: Assamese, Odia

## Model Updates

### 1. Language Detection
- **Current**: fastText lid.176.ftz (supports 176 languages including Indic)
- **Action**: Verify performance on Indic scripts, keep if adequate
- **Alternative**: Train custom model if needed

### 2. NER Model
- **Current**: spaCy en_core_web_sm (English only)
- **Replacement Options**:
  - **IndicNER** (ai4bharat/IndicNER): Supports 11 Indic languages
  - **MuRIL** (google/muril-base-cased): Multilingual model for Indian languages
  - **IndicBERT v2** (ai4bharat/IndicBERTv2-MLM-only): 24 languages
- **Action**: Use IndicNER or MuRIL for entity extraction

### 3. Feature Extraction
- **Updates needed**:
  - Handle Indic scripts (Devanagari, Bengali, Tamil, Telugu, etc.)
  - Unicode normalization for Indic text
  - Script-specific character counting
  - Handle zero-width joiners and combining characters
  - Support for code-mixed text (e.g., Hindi-English)

### 4. Domain Classifier
- **Retrain** on real Indian language data
- **Expected performance**: 85-95% accuracy (lower than synthetic due to real-world complexity)

### 5. Complexity Regressor
- **Retrain** on real Indian language data
- **Expected performance**: R²=0.85-0.95 (lower than synthetic)

## Implementation Steps

### Phase 1: Data Collection (Current)
1. ✅ Research and identify datasets
2. ⏳ Request access to gated datasets (MILU, IndicVoices, etc.)
3. ⏳ Download and preprocess data
4. ⏳ Create unified dataset with domain labels
5. ⏳ Perform train/val/test split (70/15/15)

### Phase 2: Feature Engineering Updates
1. Update feature extraction for Indic scripts
2. Add Unicode normalization
3. Handle code-mixed text
4. Test on sample Indic text

### Phase 3: Model Selection & Setup
1. Download IndicNER or MuRIL for NER
2. Verify fastText language detection on Indic languages
3. Update model loading code

### Phase 4: Model Training
1. Train domain classifier on Indian language data
2. Train complexity regressor on Indian language data
3. Evaluate on test set
4. Generate language-specific performance metrics

### Phase 5: Testing & Validation
1. Test all API endpoints with Indic text
2. Verify handling of different scripts
3. Test code-mixed text (Hindi-English, etc.)
4. Generate performance reports per language

### Phase 6: Documentation
1. Document data sources used
2. Create language-specific performance breakdown
3. Update model_metadata.json
4. Create examples for each language

## Expected Outcomes

### Model Performance (Realistic Targets)
- **Domain Classifier**: 85-95% accuracy (vs 100% on synthetic)
- **Complexity Regressor**: R²=0.85-0.95, MAE=0.01-0.05 (vs R²=0.9997 on synthetic)
- **Language Detection**: 95%+ accuracy on Indic languages
- **NER**: 70-85% F1 score on Indic entities

### Challenges
1. **Script diversity**: 8+ different scripts to handle
2. **Code-mixing**: Common in Indian languages (Hindi-English, Tamil-English)
3. **Resource imbalance**: Hindi/Bengali have more data than Assamese/Odia
4. **Domain coverage**: Some domains may have limited data in certain languages
5. **Complexity labeling**: No ground truth for complexity in real data

## Next Steps
1. Request access to AI4Bharat gated datasets
2. Start downloading publicly available datasets
3. Create data collection script for Indian languages
4. Begin preprocessing and domain classification

