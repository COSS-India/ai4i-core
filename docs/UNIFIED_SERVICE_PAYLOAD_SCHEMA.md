# Unified Service Payload Schema

This document defines a consistent JSON schema for all AI4I core services and maps each service's current payload structure to it.

## Common Unified Schema

```json
{
  "task_type": "string (optional - for media processing services)",
  "input": [
    {
      "source": "string (text content)"
    }
  ],
  "audio": [
    {
      "audioContent": "string (base64 encoded)",
      "audioUri": "string (optional HTTP URL)"
    }
  ],
  "image": [
    {
      "imageContent": "string (base64 encoded)",
      "imageUri": "string (optional HTTP URL)"
    }
  ],
  "config": {
    "serviceId": "string (required)",
    "language": {
      "sourceLanguage": "string (required)",
      "targetLanguage": "string (optional)",
      "sourceScriptCode": "string (optional)",
      "targetScriptCode": "string (optional)"
    },
    "media": {
      "gender": "string (optional - TTS)",
      "samplingRate": "number (optional - TTS)",
      "audioFormat": "string (optional - TTS)"
    },
    "processing": {
      "textDetection": "boolean (optional - OCR)",
      "isSentence": "boolean (optional - Transliteration)",
      "numSuggestions": "number (optional - Transliteration)"
    }
  },
  "controlConfig": {
    "dataTracking": "boolean (optional)"
  }
}
```

## Services Mapping

### 1. ASR Service
**Current Structure:**
```json
{
  "task_type": "ASR",
  "audio": [{"audio_content": "...", "audio_uri": "..."}],
  "config": {
    "service_id": "...",
    "language": {"source_language": "..."}
  }
}
```

**Mapping to Unified Schema:**
- `task_type` → Standardize as `"ASR"`
- `audio[].audio_content` → `audio[].audioContent` (camelCase)
- `audio[].audio_uri` → `audio[].audioUri` (camelCase)
- `config.service_id` → `config.serviceId` (camelCase)
- `config.language.source_language` → `config.language.sourceLanguage` (camelCase)

**Supported Languages:** as, bn, brx, doi, gu, hi, kn, ks, kok, mai, ml, mr, mni, ne, or, pa, sa, sat, sd, ta, te, ur

---

### 2. NMT Service (Neural Machine Translation)
**Current Structure:**
```json
{
  "input": [{"source": "..."}],
  "config": {
    "language": {
      "sourceLanguage": "...",
      "targetLanguage": "...",
      "sourceScriptCode": "",
      "targetScriptCode": ""
    },
    "serviceId": "..."
  },
  "controlConfig": {"dataTracking": false}
}
```

**Status:** Already follows unified schema ✓

---

### 3. TTS Service (Text-to-Speech)
**Current Structure:**
```json
{
  "input": [{"source": "..."}],
  "config": {
    "language": {"sourceLanguage": "..."},
    "serviceId": "...",
    "gender": "...",
    "samplingRate": 22050,
    "audioFormat": "..."
  },
  "controlConfig": {"dataTracking": false}
}
```

**Status:** Already follows unified schema ✓

**Enhancements:** Consider nesting media options:
```json
{
  "input": [{"source": "..."}],
  "config": {
    "serviceId": "...",
    "language": {"sourceLanguage": "..."},
    "media": {
      "gender": "female",
      "samplingRate": 22050,
      "audioFormat": "mp3"
    }
  },
  "controlConfig": {"dataTracking": false}
}
```

---

### 4. OCR Service
**Current Structure:**
```json
{
  "task_type": "OCR",
  "image": [{"imageContent": "...", "imageUri": "..."}],
  "config": {
    "serviceId": "...",
    "language": {
      "sourceLanguage": "...",
      "sourceScriptCode": "..."
    },
    "textDetection": false
  }
}
```

**Status:** Mostly aligned, minor adjustment needed

**Mapping:**
- Nest `textDetection` under `config.processing.textDetection`

**Supported Languages:** hi, ta, te, bn, mr, gu, kn, ml

---

### 5. NER Service (Named Entity Recognition)
**Current Structure:**
```json
{
  "input": [{"source": "..."}],
  "config": {
    "serviceId": "...",
    "language": {"sourceLanguage": "..."}
  }
}
```

**Status:** Already follows unified schema ✓

---

### 6. Language Detection Service
**Current Structure:**
```json
{
  "input": [{"source": "..."}],
  "config": {"serviceId": "..."}
}
```

**Status:** Already follows unified schema ✓

---

### 7. Audio Language Detection Service
**Current Structure:**
```json
{
  "controlConfig": {"dataTracking": true},
  "config": {"serviceId": "..."},
  "audio": [{"audioContent": "..."}]
}
```

**Status:** Already follows unified schema ✓

---

### 8. Language Diarization Service
**Current Structure:**
```json
{
  "controlConfig": {"dataTracking": true},
  "config": {"serviceId": "..."},
  "audio": [{"audioContent": "..."}]
}
```

**Status:** Already follows unified schema ✓

---

### 9. Speaker Diarization Service
**Current Structure:**
```json
{
  "audio": [{"audioContent": "..."}],
  "config": {"serviceId": "..."}
}
```

**Status:** Already follows unified schema ✓

---

### 10. Transliteration Service
**Current Structure:**
```json
{
  "input": [{"source": "..."}],
  "config": {
    "serviceId": "...",
    "language": {
      "sourceLanguage": "...",
      "targetLanguage": "..."
    },
    "isSentence": true,
    "numSuggestions": 0
  }
}
```

**Status:** Mostly aligned

**Mapping:**
- Nest `isSentence` and `numSuggestions` under `config.processing`

---

## Standardization Rules

### 1. **Naming Conventions**
- Use **camelCase** for all keys (not snake_case)
- Consistent naming across all services:
  - `serviceId` (not `service_id` or `service_Id`)
  - `audioContent` (not `audio_content`)
  - `sourceLanguage` (not `source_language`)
  - `targetLanguage` (not `target_language`)

### 2. **Required Fields**
- `config.serviceId` - **Always required**

### 3. **Content Payload**
- For **text**: Use `input[].source`
- For **audio**: Use `audio[].audioContent` (base64) or `audio[].audioUri` (HTTP URL)
- For **image**: Use `image[].imageContent` (base64) or `image[].imageUri` (HTTP URL)
- Multiple items supported in arrays

### 4. **Language Configuration**
- `config.language.sourceLanguage` - Source language code
- `config.language.targetLanguage` - Target language (when applicable)
- `config.language.sourceScriptCode` - Script code (when applicable)
- `config.language.targetScriptCode` - Target script code (when applicable)

### 5. **Service-Specific Options**
Group service-specific parameters:
- **Media options** → `config.media.*` (gender, samplingRate, audioFormat)
- **Processing options** → `config.processing.*` (textDetection, isSentence, numSuggestions)

### 6. **Control Configuration**
- `controlConfig.dataTracking` - Optional flag for data tracking/privacy

---

## Implementation Priority

### Phase 1: High Priority (Breaking but necessary)
- ASR Service: Rename snake_case to camelCase
  - `audio_content` → `audioContent`
  - `audio_uri` → `audioUri`
  - `service_id` → `serviceId`
  - `source_language` → `sourceLanguage`

### Phase 2: Medium Priority (Structural improvements)
- TTS Service: Nest media options under `config.media`
- OCR Service: Nest `textDetection` under `config.processing`
- Transliteration Service: Nest `isSentence`, `numSuggestions` under `config.processing`

### Phase 3: Documentation
- Update API documentation with unified schema
- Update client SDKs
- Update Postman collection
- Add JSON Schema validation

---

## Unified Validation Schema (JSON Schema)

```json
{
  "$schema": "http://json-schema.org/draft-07/schema#",
  "title": "AI4I Service Payload",
  "type": "object",
  "properties": {
    "task_type": {
      "type": "string",
      "enum": ["ASR", "OCR"]
    },
    "input": {
      "type": "array",
      "items": {
        "type": "object",
        "properties": {
          "source": { "type": "string" }
        },
        "required": ["source"]
      }
    },
    "audio": {
      "type": "array",
      "items": {
        "type": "object",
        "properties": {
          "audioContent": { "type": "string" },
          "audioUri": { "type": "string" }
        }
      }
    },
    "image": {
      "type": "array",
      "items": {
        "type": "object",
        "properties": {
          "imageContent": { "type": "string" },
          "imageUri": { "type": "string" }
        }
      }
    },
    "config": {
      "type": "object",
      "properties": {
        "serviceId": { "type": "string" },
        "language": {
          "type": "object",
          "properties": {
            "sourceLanguage": { "type": "string" },
            "targetLanguage": { "type": "string" },
            "sourceScriptCode": { "type": "string" },
            "targetScriptCode": { "type": "string" }
          }
        },
        "media": {
          "type": "object",
          "properties": {
            "gender": { "type": "string" },
            "samplingRate": { "type": "number" },
            "audioFormat": { "type": "string" }
          }
        },
        "processing": {
          "type": "object",
          "properties": {
            "textDetection": { "type": "boolean" },
            "isSentence": { "type": "boolean" },
            "numSuggestions": { "type": "number" }
          }
        }
      },
      "required": ["serviceId"]
    },
    "controlConfig": {
      "type": "object",
      "properties": {
        "dataTracking": { "type": "boolean" }
      }
    }
  }
}
```

---

## Benefits of Standardization

1. **Consistency**: All services follow the same pattern
2. **Developer Experience**: Easier to learn and use all services
3. **Maintainability**: Single documentation and validation logic
4. **SDKs**: Unified client libraries across platforms
5. **Testing**: Consistent test cases and fixtures
6. **Monitoring**: Standardized payload logging and tracing

---

## Migration Path

### For Services to Update
1. ASR Service (Priority: High)
2. TTS Service (Priority: Medium - optional nesting)
3. OCR Service (Priority: Medium - optional nesting)
4. Transliteration Service (Priority: Medium - optional nesting)

### For Services Already Compliant
- NMT Service ✓
- NER Service ✓
- Language Detection Service ✓
- Audio Language Detection Service ✓
- Language Diarization Service ✓
- Speaker Diarization Service ✓
