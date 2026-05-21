# Unified Service Response Schema

This document defines a consistent JSON schema for all AI4I core service responses and maps each service's current response structure to it.

## Common Unified Response Schema

```json
{
  "taskType": "string (optional - task identifier)",
  "output": [
    {
      "source": "string (input text/content)",
      "target": "string (output translation/transformation)",
      "transcript": "string (ASR output)",
      "prediction": {
        "type": "object or array (service-specific predictions)"
      }
    }
  ],
  "audio": [
    {
      "audioContent": "string (base64 encoded audio)",
      "audioUri": "string (optional HTTP URL)"
    }
  ],
  "config": {
    "serviceId": "string",
    "language": {
      "sourceLanguage": "string",
      "sourceScriptCode": "string (optional)",
      "audioFormat": "string (optional)",
      "encoding": "string (optional)",
      "samplingRate": "number (optional)",
      "audioDuration": "number (optional)"
    }
  },
  "metadata": {
    "taskType": "string (optional)",
    "processingTime": "number (optional)",
    "confidence": "number (optional)"
  },
  "smr_response": "object or null (Smart Model Routing response)"
}
```

## Services Mapping

### 1. ASR Service (Automatic Speech Recognition)
**Current Structure:**
```json
{
  "output": [
    {
      "transcript": "नमस्ते दुनिया"
    }
  ]
}
```

**Mapping to Unified Schema:**
```json
{
  "taskType": "asr",
  "output": [
    {
      "transcript": "नमस्ते दुनिया"
    }
  ]
}
```

**Status:** Needs `taskType` field addition

---

### 2. NMT Service (Neural Machine Translation)
**Current Structure:**
```json
{
  "output": [
    {
      "source": "good",
      "target": "अच्छा है।"
    }
  ],
  "smr_response": null
}
```

**Status:** Already follows unified schema ✓

---

### 3. TTS Service (Text-to-Speech)
**Current Structure:**
```json
{
  "audio": [
    {
      "audioContent": "SUQzBAAAAAAAVVVVVVVVVVVVVVVVVVVVVVQ==",
      "audioUri": null
    }
  ],
  "config": {
    "language": {
      "sourceLanguage": "hi",
      "sourceScriptCode": null
    },
    "audioFormat": "mp3",
    "encoding": "base64",
    "samplingRate": 22050,
    "audioDuration": 0.18519274376417233
  },
  "smr_response": null
}
```

**Status:** Mostly aligned, minor cleanup needed

**Improvements:**
- Move `audioFormat`, `encoding`, `samplingRate`, `audioDuration` into `config.language` or nested `config.media`
- Optionally add `taskType: "tts"`

---

### 4. OCR Service (Optical Character Recognition)
**Current Structure:**
```json
{
  "output": [
    {
      "source": "यह एक परीक्षण है",
      "target": ""
    }
  ]
}
```

**Status:** Already follows unified schema ✓

**Note:** Target field kept empty for ULCA schema compatibility

---

### 5. NER Service (Named Entity Recognition)
**Current Structure:**
```json
{
  "taskType": "ner",
  "output": [
    {
      "source": "India is a country",
      "nerPrediction": [
        {
          "token": "India",
          "tag": "O",
          "tokenIndex": 0,
          "tokenStartIndex": 0,
          "tokenEndIndex": 5
        }
      ]
    }
  ],
  "config": null
}
```

**Mapping to Unified Schema:**
- Rename `nerPrediction` → `prediction.entities` or keep as standardized `nerPrediction`
- Nest prediction under `output[].prediction`
- Move to consistent structure

**Suggested Refactoring:**
```json
{
  "taskType": "ner",
  "output": [
    {
      "source": "India is a country",
      "prediction": [
        {
          "token": "India",
          "tag": "O",
          "tokenIndex": 0,
          "tokenStartIndex": 0,
          "tokenEndIndex": 5
        }
      ]
    }
  ],
  "config": null
}
```

---

### 6. Language Detection Service
**Current Structure:**
```json
{
  "output": [
    {
      "source": "good",
      "langPrediction": [
        {
          "langCode": "mni",
          "scriptCode": "Latn",
          "langScore": 0.9776011109352112,
          "language": "Manipuri (Latin script)"
        }
      ]
    }
  ],
  "config": null
}
```

**Mapping to Unified Schema:**
- Consider standardizing `langPrediction` to `prediction`
- Standardize field names: `langScore` → `confidence`

**Suggested Refactoring:**
```json
{
  "taskType": "language-detection",
  "output": [
    {
      "source": "good",
      "prediction": [
        {
          "langCode": "mni",
          "scriptCode": "Latn",
          "confidence": 0.9776011109352112,
          "language": "Manipuri (Latin script)"
        }
      ]
    }
  ],
  "config": null
}
```

---

### 7. Audio Language Detection Service
**Current Structure:**
```json
{
  "taskType": "audio-lang-detection",
  "output": [
    {
      "language_code": "ta: Tamil",
      "confidence": 0.999923586845398,
      "all_scores": {
        "predicted_language": "ta: Tamil",
        "confidence": 0.999923586845398,
        "top_scores": [0.999923586845398, ...]
      }
    }
  ],
  "config": {
    "serviceId": "356b2b50747f44aa2abed17cae94327c"
  }
}
```

**Mapping to Unified Schema:**
- Convert snake_case to camelCase: `language_code` → `languageCode`
- Nest prediction details under `prediction`

**Suggested Refactoring:**
```json
{
  "taskType": "audio-language-detection",
  "output": [
    {
      "prediction": {
        "languageCode": "ta: Tamil",
        "confidence": 0.999923586845398,
        "allScores": {
          "predictedLanguage": "ta: Tamil",
          "confidence": 0.999923586845398,
          "topScores": [0.999923586845398, ...]
        }
      }
    }
  ],
  "config": {
    "serviceId": "356b2b50747f44aa2abed17cae94327c"
  }
}
```

---

### 8. Language Diarization Service
**Current Structure:**
```json
{
  "taskType": "language-diarization",
  "output": [
    {
      "total_segments": 3,
      "segments": [
        {
          "start_time": 0.0,
          "end_time": 2.5,
          "duration": 2.5,
          "language": "hi: Hindi",
          "confidence": 0.9312
        }
      ],
      "target_language": ""
    }
  ],
  "config": {
    "serviceId": "5d30f31a9653572878e91e954d038649"
  }
}
```

**Mapping to Unified Schema:**
- Convert snake_case to camelCase: `total_segments` → `totalSegments`, `start_time` → `startTime`, etc.
- Nest segment data under `prediction`

**Suggested Refactoring:**
```json
{
  "taskType": "language-diarization",
  "output": [
    {
      "prediction": {
        "totalSegments": 3,
        "segments": [
          {
            "startTime": 0.0,
            "endTime": 2.5,
            "duration": 2.5,
            "language": "hi: Hindi",
            "confidence": 0.9312
          }
        ],
        "targetLanguage": ""
      }
    }
  ],
  "config": {
    "serviceId": "5d30f31a9653572878e91e954d038649"
  }
}
```

---

### 9. Speaker Diarization Service
**Current Structure:**
```json
{
  "taskType": "speaker-diarization",
  "output": [
    {
      "total_segments": 0,
      "num_speakers": 0,
      "speakers": [],
      "segments": []
    }
  ],
  "config": {
    "serviceId": "a9efafbfc2021f9a34dd201eab8f5687",
    "language": null
  }
}
```

**Mapping to Unified Schema:**
- Convert snake_case to camelCase: `total_segments` → `totalSegments`, `num_speakers` → `numSpeakers`
- Nest under `prediction`

**Suggested Refactoring:**
```json
{
  "taskType": "speaker-diarization",
  "output": [
    {
      "prediction": {
        "totalSegments": 0,
        "numSpeakers": 0,
        "speakers": [],
        "segments": []
      }
    }
  ],
  "config": {
    "serviceId": "a9efafbfc2021f9a34dd201eab8f5687",
    "language": null
  }
}
```

---

### 10. Transliteration Service
**Current Structure:**
```json
{
  "output": [
    {
      "source": "good",
      "target": "गुड"
    }
  ]
}
```

**Status:** Already follows unified schema ✓

**Enhancement:** Add `taskType: "transliteration"`

---

### 11. LLM Service
**Status:** Data not provided

---

## Standardization Rules

### 1. **Naming Conventions**
- Use **camelCase** for all response keys (not snake_case)
- Consistent naming across all services:
  - `totalSegments` (not `total_segments`)
  - `startTime` (not `start_time`)
  - `languageCode` (not `language_code`)
  - `allScores` (not `all_scores`)

### 2. **Response Structure**
All responses should follow:
```json
{
  "taskType": "string (service identifier)",
  "output": [{ /* results */ }],
  "config": { /* echo of input config */ },
  "metadata": { /* optional processing metadata */ },
  "smr_response": null
}
```

### 3. **Output Field**
- Always include `output` array (even if empty)
- For single results, still use array with one element
- Never use plain objects at response root for multiple results

### 4. **Prediction Data**
Group service-specific predictions under `output[].prediction`:
- **NER**: `prediction` (array of entity objects)
- **Language Detection**: `prediction` (array of language scores)
- **Audio Language Detection**: `prediction` (language detection results)
- **Language Diarization**: `prediction` (segments array)
- **Speaker Diarization**: `prediction` (speakers and segments)

### 5. **Task Type Field**
- Include `taskType` in all responses (lowercase-hyphenated)
- Examples: `"asr"`, `"nmt"`, `"ocr"`, `"ner"`, `"language-detection"`, `"audio-language-detection"`, `"language-diarization"`, `"speaker-diarization"`, `"transliteration"`, `"tts"`

### 6. **Config Echo**
- Include `config` object echoing relevant input configuration
- Include `serviceId` if present in input

### 7. **Metadata (Optional)**
For optional metadata tracking:
```json
{
  "metadata": {
    "processingTimeMs": 145,
    "modelVersion": "1.0.0",
    "inputTokens": 50,
    "outputTokens": 60
  }
}
```

### 8. **Confidence/Score Fields**
- Use consistent naming: `confidence` (not `langScore`, `probability`, etc.)
- Always range 0-1
- Include for all prediction-based services

---

## Implementation Priority

### Phase 1: High Priority (Naming Standardization)
Services to update snake_case → camelCase:
1. **Audio Language Detection** - `language_code`, `all_scores`, `predicted_language`
2. **Language Diarization** - `total_segments`, `start_time`, `end_time`, `target_language`
3. **Speaker Diarization** - `total_segments`, `num_speakers`

### Phase 2: Medium Priority (Structural Improvements)
1. **NER Service** - Rename `nerPrediction` → `prediction`
2. **Language Detection** - Rename `langPrediction` → `prediction`, standardize `langScore` → `confidence`
3. **ASR Service** - Add `taskType` field
4. **TTS Service** - Add `taskType` field, optionally restructure config
5. **OCR Service** - Add `taskType` field
6. **Transliteration Service** - Add `taskType` field

### Phase 3: Documentation & SDKs
- Update API documentation with unified schema
- Generate TypeScript/Java/Python models from schema
- Update response parsing in client SDKs

---

## Unified Response Validation Schema (JSON Schema)

```json
{
  "$schema": "http://json-schema.org/draft-07/schema#",
  "title": "AI4I Service Response",
  "type": "object",
  "properties": {
    "taskType": {
      "type": "string",
      "enum": [
        "asr",
        "nmt",
        "tts",
        "ocr",
        "ner",
        "language-detection",
        "audio-language-detection",
        "language-diarization",
        "speaker-diarization",
        "transliteration"
      ]
    },
    "output": {
      "type": "array",
      "items": {
        "type": "object",
        "properties": {
          "source": { "type": "string" },
          "target": { "type": "string" },
          "transcript": { "type": "string" },
          "prediction": { "oneOf": [
            { "type": "array" },
            { "type": "object" }
          ]},
          "nerPrediction": {
            "type": "array",
            "deprecated": true,
            "description": "Use prediction instead"
          },
          "langPrediction": {
            "type": "array",
            "deprecated": true,
            "description": "Use prediction instead"
          }
        }
      }
    },
    "audio": {
      "type": "array",
      "items": {
        "type": "object",
        "properties": {
          "audioContent": { "type": "string" },
          "audioUri": { "type": ["string", "null"] }
        }
      }
    },
    "config": {
      "type": ["object", "null"],
      "properties": {
        "serviceId": { "type": "string" },
        "language": { "type": "object" }
      }
    },
    "metadata": {
      "type": ["object", "null"],
      "properties": {
        "processingTimeMs": { "type": "number" },
        "modelVersion": { "type": "string" },
        "confidence": { "type": "number" }
      }
    },
    "smr_response": {
      "type": ["object", "null"]
    }
  },
  "required": ["taskType", "output"]
}
```

---

## Service Response Examples (Unified Format)

### ASR Service
```json
{
  "taskType": "asr",
  "output": [
    {
      "transcript": "नमस्ते दुनिया"
    }
  ]
}
```

### NMT Service
```json
{
  "taskType": "nmt",
  "output": [
    {
      "source": "good",
      "target": "अच्छा है।"
    }
  ],
  "smr_response": null
}
```

### NER Service (Refactored)
```json
{
  "taskType": "ner",
  "output": [
    {
      "source": "India is a country",
      "prediction": [
        {
          "token": "India",
          "tag": "O",
          "tokenIndex": 0,
          "tokenStartIndex": 0,
          "tokenEndIndex": 5
        }
      ]
    }
  ]
}
```

### Language Detection (Refactored)
```json
{
  "taskType": "language-detection",
  "output": [
    {
      "source": "good",
      "prediction": [
        {
          "langCode": "mni",
          "scriptCode": "Latn",
          "confidence": 0.9776011109352112,
          "language": "Manipuri (Latin script)"
        }
      ]
    }
  ]
}
```

### Language Diarization (Refactored)
```json
{
  "taskType": "language-diarization",
  "output": [
    {
      "prediction": {
        "totalSegments": 3,
        "segments": [
          {
            "startTime": 0.0,
            "endTime": 2.5,
            "duration": 2.5,
            "language": "hi: Hindi",
            "confidence": 0.9312
          }
        ],
        "targetLanguage": ""
      }
    }
  ],
  "config": {
    "serviceId": "5d30f31a9653572878e91e954d038649"
  }
}
```

---

## Benefits of Standardization

1. **Consistency**: All service responses follow the same pattern
2. **Predictability**: Clients always know where to find results
3. **Type Safety**: Easier to generate typed models for SDKs
4. **Validation**: Single validation schema for all responses
5. **Logging/Monitoring**: Standardized response structure for tracking
6. **Error Handling**: Consistent error response format

---

## Backward Compatibility

### Deprecation Strategy
1. **Phase 1**: Keep old field names alongside new ones (e.g., both `nerPrediction` and `prediction`)
2. **Phase 2**: Document migration path in API changelog
3. **Phase 3**: Set deprecation date (e.g., 6 months) for old field names
4. **Phase 4**: Remove old field names in next major version

### Migration Timeline
- Month 1-2: Release with both old and new formats
- Month 2-4: Encourage migration in documentation
- Month 4-6: Announce deprecation warnings
- Month 6+: Remove old format in next major version

---

## Field Mapping Reference

| Service | Current Field | New Field | Type |
|---------|---------------|-----------|------|
| Audio Lang Detection | `language_code` | `languageCode` | Move to `output[].prediction` |
| Audio Lang Detection | `all_scores` | `allScores` | Move to `output[].prediction` |
| Language Diarization | `total_segments` | `totalSegments` | Move to `output[].prediction` |
| Language Diarization | `start_time` | `startTime` | Move to `output[].prediction.segments[]` |
| Language Diarization | `end_time` | `endTime` | Move to `output[].prediction.segments[]` |
| Language Diarization | `target_language` | `targetLanguage` | Move to `output[].prediction` |
| Speaker Diarization | `total_segments` | `totalSegments` | Move to `output[].prediction` |
| Speaker Diarization | `num_speakers` | `numSpeakers` | Move to `output[].prediction` |
| NER Service | `nerPrediction` | `prediction` | Rename |
| Language Detection | `langPrediction` | `prediction` | Rename |
| Language Detection | `langScore` | `confidence` | Rename field within prediction |
| All Services | (missing) | `taskType` | Add consistently |
