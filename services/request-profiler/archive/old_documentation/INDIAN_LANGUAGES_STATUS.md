# Indian Languages Retraining - Current Status

## Summary

I have completed the research and planning phase for retraining the Translation Request Profiler models on real-world Indian language datasets. Here's what has been accomplished and what remains to be done.

## ✅ Completed Tasks

### 1. Research & Data Source Identification
- **AI4Bharat** identified as the primary source for Indic language data
- **MILU Dataset**: 80K questions across 11 languages, 8 domains (gated - requires access request)
- **Sangraha**: 268M samples, 22 languages (public)
- **IndicCorp v2**: 20.9B tokens, 24 languages (public)
- **IndicSentiment**: Sentiment data for 11 languages (public)
- **Wikipedia**: Available for all 12 target languages

### 2. Implementation Plan Created
- **File**: `INDIAN_LANGUAGES_PLAN.md`
- Detailed 6-phase implementation plan
- 12 target languages identified with scripts
- 6 domains mapped to data sources
- Expected performance targets documented

### 3. Data Collection Guide
- **File**: `DATA_COLLECTION_GUIDE.md`
- Step-by-step instructions for accessing datasets
- HuggingFace setup and authentication guide
- Data processing requirements
- Expected dataset structure

### 4. Infrastructure Setup
- **Dependencies installed**: `datasets==2.16.1`, `tqdm==4.66.1`
- **Data collection script created**: `scripts/collect_indian_data.py`
- Unicode normalization functions implemented
- Script detection functions implemented
- Complexity estimation heuristics implemented

## ⏳ Pending Tasks

### Phase 1: Data Collection (IN PROGRESS)

#### Immediate Actions Required:
1. **Request Access to Gated Datasets**
   - Visit https://huggingface.co/datasets/ai4bharat/MILU
   - Click "Request Access" and fill in the form
   - Explain use case: "Training a translation request profiler for Indian languages"
   - Wait for approval (typically 1-2 days)

2. **HuggingFace Authentication**
   ```bash
   pip install huggingface-hub
   huggingface-cli login
   # Enter your HuggingFace token
   ```

3. **Download Public Datasets**
   ```python
   from datasets import load_dataset
   
   # IndicSentiment for casual domain
   sentiment = load_dataset("ai4bharat/IndicSentiment")
   
   # Sangraha for general domain (use streaming for large dataset)
   sangraha = load_dataset("ai4bharat/sangraha", streaming=True)
   
   # IndicQA for general/technical domains
   qa = load_dataset("ai4bharat/IndicQA")
   ```

4. **Download Wikipedia Data**
   - The script `scripts/collect_indian_data.py` has Wikipedia download functionality
   - Currently configured to download 500 articles per language
   - Can be run once access is set up

### Phase 2: Feature Extraction Updates

**File to modify**: `request_profiler/features.py`

Required changes:
1. Add Unicode normalization for all text processing
2. Update character counting to handle combining characters
3. Add script detection for Indic languages
4. Handle zero-width joiners and special Indic characters
5. Support code-mixed text (e.g., Hindi-English)

### Phase 3: NER Model Update

**File to modify**: `request_profiler/profiler.py`

Required changes:
1. Replace `en_core_web_sm` with IndicNER or MuRIL
2. Download IndicNER: `ai4bharat/IndicNER`
3. Or use MuRIL: `google/muril-base-cased`
4. Update entity extraction code to use new model

### Phase 4: Model Retraining

**File to modify**: `scripts/train_models.py`

Steps:
1. Load Indian language dataset
2. Extract features using updated feature extraction
3. Train domain classifier (TF-IDF + Logistic Regression)
4. Train complexity regressor (RandomForestRegressor)
5. Evaluate on test set
6. Generate language-specific performance metrics
7. Save models and metadata

### Phase 5: Testing & Validation

Steps:
1. Test all 6 API endpoints with Indic text samples
2. Verify handling of different scripts
3. Test code-mixed text (Hindi-English, Tamil-English)
4. Generate performance reports per language
5. Create confusion matrices for domain classification

### Phase 6: Documentation

Steps:
1. Document all data sources used with citations
2. Create language-specific performance breakdown
3. Update `model_metadata.json` with new metrics
4. Create API examples for each language

## 📊 Expected Outcomes

### Model Performance (Realistic Targets)
- **Domain Classifier**: 85-95% accuracy (vs 100% on synthetic data)
- **Complexity Regressor**: R²=0.85-0.95, MAE=0.01-0.05 (vs R²=0.9997 on synthetic)
- **Language Detection**: 95%+ accuracy on Indic languages (fastText already supports this)
- **NER**: 70-85% F1 score on Indic entities

### Challenges to Address
1. **Script Diversity**: 8+ different scripts (Devanagari, Bengali, Tamil, Telugu, Gujarati, Kannada, Malayalam, Gurmukhi, Odia, Perso-Arabic)
2. **Code-Mixing**: Common in Indian languages (Hindi-English, Tamil-English)
3. **Resource Imbalance**: Hindi/Bengali have more data than Assamese/Odia
4. **Domain Coverage**: Some domains may have limited data in certain languages
5. **Complexity Labeling**: No ground truth for complexity in real data (using heuristics)

## 🚀 Recommended Next Steps

### Option 1: Wait for Real Data (Recommended for Production)
1. Request access to MILU dataset
2. Wait for approval (1-2 days)
3. Download all datasets
4. Process and combine into unified dataset
5. Proceed with feature updates and model retraining

**Timeline**: 3-5 days (including waiting for access)

### Option 2: Use Demo Data (Quick Testing)
1. Create synthetic Indian language samples for testing
2. Update feature extraction for Indic scripts
3. Test the complete pipeline
4. Replace with real data later

**Timeline**: 1-2 days

## 📁 Files Created

1. **`INDIAN_LANGUAGES_PLAN.md`**: Comprehensive implementation plan
2. **`DATA_COLLECTION_GUIDE.md`**: Step-by-step data collection guide
3. **`scripts/collect_indian_data.py`**: Data collection script (348 lines)
4. **`requirements.txt`**: Updated with `datasets` and `tqdm`

## 🔗 Useful Links

- **AI4Bharat Organization**: https://huggingface.co/ai4bharat
- **MILU Dataset**: https://huggingface.co/datasets/ai4bharat/MILU
- **Sangraha**: https://huggingface.co/datasets/ai4bharat/sangraha
- **IndicSentiment**: https://huggingface.co/datasets/ai4bharat/IndicSentiment
- **IndicNER**: https://huggingface.co/ai4bharat/IndicNER
- **MuRIL**: https://huggingface.co/google/muril-base-cased
- **IndicBERT v2**: https://huggingface.co/ai4bharat/IndicBERTv2-MLM-only

## ❓ Questions to Consider

1. **Do you want to proceed with Option 1 (wait for real data) or Option 2 (demo data for testing)?**
2. **Do you have a HuggingFace account? If not, I can guide you through creating one.**
3. **Which NER model should we use: IndicNER or MuRIL?** (IndicNER is specifically for NER, MuRIL is more general-purpose)
4. **Should we prioritize certain languages over others?** (e.g., focus on Hindi, Bengali, Tamil, Telugu first)

## 📝 Notes

- The existing service infrastructure (FastAPI, endpoints, schemas) remains unchanged
- Only the data, models, and feature extraction need updates
- The API will continue to work exactly as before, but with better support for Indian languages
- All 6 endpoints will be tested with Indic text samples

---

**Status**: Ready to proceed with data collection once you provide direction on Option 1 vs Option 2.

