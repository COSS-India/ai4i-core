
# Translation Request Profiler – Production Grade Design

## 🎯 Goal

Build an **independent, production‑ready request profiler** that:

```
text → profile JSON
```

Helps select the **best translation model** (small MT / domain MT / LLM).

This is **NOT just a complexity classifier**.  
It is a **multi-signal profiler** that outputs structured signals for routing.

---

# ✅ Why NOT only “complexity”?

Many very different requests can all be “HIGH” complexity:

| Case | Best Model |
|------|-----------| legal sentence | legal MT |
| medical text | medical MT |
| code-mixed | LLM |
| long casual | small/medium MT |

So a single label loses information.

👉 We need multiple signals.

---

# ✅ Final Output (recommended schema)

```json
{
  "length": {
    "words": 184,
    "sentences": 9,
    "bucket": "MEDIUM"
  },
  "language": {
    "primary": "en",
    "num_languages": 2,
    "mix_ratio": 0.31
  },
  "domain": "medical",
  "structure": {
    "entity_density": 0.18,
    "terminology_density": 0.42,
    "numeric_density": 0.12
  },
  "scores": {
    "complexity_score": 0.78,
    "complexity_level": "HIGH"
  }
}
```

Router uses this to pick best model.

---

# 🧠 Architecture

```
text
  ↓
Feature extractors
  ↓
Domain classifier (ML)
Complexity regressor (ML)
  ↓
Profile JSON
```

---

# ✅ Signals to Compute (production quality)

## 1. Structural complexity
- char_count
- word_count
- sentence_count
- avg_sentence_len
- punctuation_ratio
- special_char_ratio

## 2. Language + code-mixing
Use fastText language ID:

- primary_language
- num_languages
- mix_ratio
- language_switches

## 3. Domain classifier
Classes:
- general
- legal
- medical
- technical
- finance
- casual

Model:
TF-IDF + Logistic Regression

## 4. Terminology density
- avg word length
- unique ratio
- rare word ratio
- digit ratio

## 5. Entity density
spaCy NER count / word_count

## 6. Complexity score
RandomForestRegressor → 0–1 score

Bucket:
- <0.3 LOW
- <0.6 MEDIUM
- else HIGH

---

# ✅ Models to Use

| Task | Model | Why |
|--------|----------|---------|
| Domain | Logistic Regression + TFIDF | fast & accurate |
| Complexity | RandomForestRegressor | robust |
| Language | fastText | best CPU accuracy |
| NER | spaCy small | lightweight |

NO GPU required.

---

# ✅ Hardware

MacBook Air M4 is MORE than enough.

Training time:
- few seconds to < 1 minute

CPU only.

---

# ✅ Data Requirements

You DO need labeled data.

## Recommended size

- 2k–5k texts per domain
- total 10k–20k samples

## Sources

### Medical
- PubMed abstracts
- WHO reports

### Legal
- contracts
- ToS pages
- court docs

### Technical
- StackOverflow
- docs
- GitHub READMEs

### Finance
- financial news
- reports

### Casual
- chats
- tweets
- blogs

---

# ✅ Labeling Strategy

### Domain
Manual or source-based labeling

### Complexity
Use heuristic auto-label:
- long + domain + code-mix → HIGH
- short + simple → LOW
Then manually fix ~500 examples

---

# ✅ Tech Stack

Install:

```
pip install scikit-learn fasttext spacy pandas numpy joblib
```

Download:
- lid.176.bin (fastText language model)

---

# ✅ Project Structure

```
request_profiler/
    features.py
    train.py
    profiler.py
    domain.pkl
    complexity.pkl
    lid.176.bin
    data.csv
```

---

# ✅ Training Flow

## train.py

1. Load CSV
2. Train domain model
3. Train complexity model
4. Save models

---

# Example Training Code

```python
domain_pipeline = Pipeline([
    ("tfidf", TfidfVectorizer(max_features=3000)),
    ("clf", LogisticRegression(max_iter=1000))
])

domain_pipeline.fit(texts, domains)
joblib.dump(domain_pipeline, "domain.pkl")

features = [extract_features(t) for t in texts]

rf = RandomForestRegressor(n_estimators=300)
rf.fit(features, complexity_scores)

joblib.dump(rf, "complexity.pkl")
```

---

# ✅ Runtime Usage

```python
from profiler import profile

result = profile(text)
print(result)
```

---

# ✅ Day-by-Day Build Plan

## Day 1 (4–5 hours)
- collect data
- label
- write feature extractor
- train models
- save models

## Day 2
- tuning
- evaluation
- integration

---

# ✅ Final Advice

Do NOT build just a complexity classifier.

Build:
👉 Request Profiler (multi-signal)

Because routing needs more than one number.

This design is:
- scalable
- explainable
- fast
- CPU only
- production friendly

---

# End
