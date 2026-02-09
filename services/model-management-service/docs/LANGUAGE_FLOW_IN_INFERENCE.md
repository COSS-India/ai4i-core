# Language Flow in Inference - User Perspective

## Overview

This document explains what "language" means for a user making an inference request and how it flows through the system from the user's request to the actual model inference.

## What Language Means for Users

**Language** represents the **natural language** (e.g., Hindi, English, Tamil) that the user's input data is in, or the language they want the output in. It's specified by the user in their inference request.

### Examples:
- **ASR (Speech-to-Text)**: Language of the spoken audio (`"hi"` for Hindi audio)
- **TTS (Text-to-Speech)**: Language of the text to convert to speech (`"en"` for English text)
- **NMT (Translation)**: Source and target languages (`sourceLanguage: "hi"`, `targetLanguage: "en"`)
- **OCR**: Language of the text in the image (`"hi"` for Hindi text in image)
- **Services without language**: Some services like general-purpose models may not use language at all

## Complete Flow: User Request → Inference

### Step 1: User Makes Request

The user sends an HTTP POST request to the API Gateway with language specified in the request body.

**Example ASR Request:**
```json
POST /api/v1/asr/inference
{
  "audio": [
    {
      "audioContent": "base64-encoded-audio-data"
    }
  ],
  "config": {
    "serviceId": "asr-hindi-v1",
    "language": {
      "sourceLanguage": "hi"  // ← User specifies Hindi
    },
    "audioFormat": "wav",
    "samplingRate": 16000
  }
}
```

**Example NMT Request:**
```json
POST /api/v1/nmt/inference
{
  "input": [
    {"source": "नमस्ते"}
  ],
  "config": {
    "serviceId": "nmt-hi-en-v1",
    "language": {
      "sourceLanguage": "hi",  // ← Source: Hindi
      "targetLanguage": "en"    // ← Target: English
    }
  }
}
```

### Step 2: API Gateway Receives Request

The API Gateway:
1. **Authenticates** the user (Bearer token or API key)
2. **Extracts** the request payload
3. **Proxies** the request to the appropriate service

**Code Location:** `services/api-gateway-service/main.py`
- ASR endpoint: `@app.post("/api/v1/asr/inference")` (line ~4176)
- NMT endpoint: `@app.post("/api/v1/nmt/inference")` (line ~4491)
- Other services follow similar pattern

### Step 3: Service Receives Request

The service (e.g., ASR service) receives the request and extracts the language from the request body.

**Example from ASR Service:**
```python
# services/asr-service/services/asr_service.py (line ~85)
language = request.config.language.sourceLanguage  # Extracts "hi"
```

**Service-specific language extraction:**
- **ASR**: `request.config.language.sourceLanguage`
- **TTS**: `request.config.language.sourceLanguage`
- **NMT**: `request.config.language.sourceLanguage` and `request.config.language.targetLanguage`
- **OCR**: `request.config.language.sourceLanguage`
- **Transliteration**: `request.config.language.sourceLanguage` and `request.config.language.targetLanguage`

### Step 4: Service Validates Language

The service validates that the language is supported by the model.

**Example from ASR Service:**
```python
# services/asr-service/services/asr_service.py (line ~92-98)
from utils.validation_utils import SUPPORTED_LANGUAGES, InvalidLanguageCodeError

if language not in SUPPORTED_LANGUAGES:
    raise InvalidLanguageCodeError(
        f"Language '{language}' is not supported by the IndicASR model. "
        f"Supported languages: {', '.join(SUPPORTED_LANGUAGES)}."
    )
```

### Step 5: Service Gets Model Details (with A/B Testing)

The service uses the Model Management Service to get the actual model endpoint and configuration. **This is where language is used for A/B testing.**

**A/B Testing Variant Selection:**
```python
# The service calls Model Management Service to check for active experiments
POST /experiments/select-variant
{
  "task_type": "asr",           # Extracted from service type
  "language": "hi",             # ← Language from user's request
  "request_id": "optional-id",  # Used for hashing when user_id absent (e.g. anonymous)
  "user_id": "optional-id"      # When set, same user => same variant (sticky assignment)
}
```
Routing: when `user_id` is provided, the same user always gets the same variant; otherwise `request_id` or a random value is used for the hash.

**What happens:**
1. Model Management Service checks for active A/B testing experiments
2. Filters experiments by:
   - **Task type**: `"asr"` matches experiments with `task_type: ["asr"]` or `null`
   - **Language**: `"hi"` matches experiments with:
     - `languages: null` (matches all languages)
     - `languages: []` (matches all languages)
     - `languages: ["hi", "en"]` (contains "hi")
3. If experiment found, returns variant details (different service/model)
4. If no experiment, returns `is_experiment: false`

**Response (if experiment active):**
```json
{
  "experiment_id": "exp-123",
  "variant_id": "var-456",
  "variant_name": "variant-a",
  "service_id": "asr-hindi-v2",  // ← Different service for A/B test
  "model_id": "model-v2",
  "endpoint": "http://triton:8000",
  "api_key": "key-123",
  "is_experiment": true
}
```

**Response (if no experiment):**
```json
{
  "is_experiment": false
}
```

### Step 6: Service Routes to Model

The service routes the request to the appropriate model endpoint:

- **If A/B test active**: Uses the variant's endpoint and model
- **If no A/B test**: Uses the default service endpoint and model

**Code Flow:**
```python
# Service gets model details
if experiment_response.is_experiment:
    endpoint = experiment_response.endpoint
    model_name = experiment_response.model_id
else:
    # Get default service details
    service_info = await model_mgmt_client.get_service(service_id)
    endpoint = service_info.endpoint
    model_name = service_info.triton_model
```

### Step 7: Model Inference

The service sends the request to the Triton Inference Server with:
- **Model name**: Determined from service or A/B test variant
- **Language**: Used by the model to process the input correctly
- **Input data**: User's audio/text/image

**Example Triton Request:**
```python
# The language is embedded in the model input or used to select the right model
inputs = prepare_inputs(
    audio_data=request.audio,
    language=language,  # ← Language used here
    model_name=model_name
)
result = triton_client.send_triton_request(model_name, inputs, outputs)
```

### Step 8: Response to User

The service processes the model output and returns the result to the user.

**Example ASR Response:**
```json
{
  "output": [
    {
      "source": "नमस्ते, मैं कैसे मदद कर सकता हूं"  // Transcribed Hindi text
    }
  ],
  "config": {
    "serviceId": "asr-hindi-v1",
    "language": "hi"
  }
}
```

## Language in A/B Testing Context

### For Services WITH Language (ASR, TTS, NMT, etc.)

1. **User specifies language** in request: `"hi"`, `"en"`, etc.
2. **Service extracts language** from request: `language = request.config.language.sourceLanguage`
3. **A/B testing uses language** to filter experiments:
   - Experiment with `languages: ["hi"]` → Only matches Hindi requests
   - Experiment with `languages: null` → Matches all languages
4. **Variant selection** considers language for routing

### For Services WITHOUT Language (OCR, General Models)

1. **User doesn't specify language** (or it's optional)
2. **Service passes `language=None`** to variant selection
3. **A/B testing filters** to only match experiments with `languages: null` or `languages: []`
4. **Language-specific experiments are excluded** (they won't match)

## Key Points

1. **Language is user-provided**: The user specifies the language of their input/output in the request
2. **Language flows through the system**: From request → service → A/B testing → model
3. **A/B testing uses language as a filter**: To route specific language requests to specific experiment variants
4. **Language determines model behavior**: The model uses language to process the input correctly
5. **Services without language**: Pass `language=None` and only match language-agnostic experiments

## Example: Complete ASR Flow

```
User Request:
  POST /api/v1/asr/inference
  { "config": { "language": { "sourceLanguage": "hi" } } }
         ↓
API Gateway:
  - Authenticates user
  - Proxies to asr-service
         ↓
ASR Service:
  - Extracts: language = "hi"
  - Validates: "hi" is in SUPPORTED_LANGUAGES
  - Calls: POST /experiments/select-variant
           { "task_type": "asr", "language": "hi" }
         ↓
Model Management Service:
  - Finds experiment with languages: ["hi"] or null
  - Returns variant (or is_experiment: false)
         ↓
ASR Service:
  - Routes to model endpoint (variant or default)
  - Sends inference request with language="hi"
         ↓
Triton Inference Server:
  - Processes audio with Hindi model
  - Returns transcription
         ↓
ASR Service:
  - Returns response to user
```

## Summary

**Language** in inference is the natural language code (e.g., `"hi"`, `"en"`, `"ta"`) that:
1. **Users specify** in their request to indicate the language of their input/output
2. **Services extract** from the request body
3. **A/B testing uses** to filter which experiments apply to which requests
4. **Models use** to process the input correctly

The language flows from the user's request through the entire system, enabling language-specific routing, A/B testing, and model selection.
