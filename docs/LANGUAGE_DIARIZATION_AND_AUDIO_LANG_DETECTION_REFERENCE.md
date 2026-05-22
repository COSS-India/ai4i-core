# Language Diarization & Audio Language Detection — API and Triton Reference

End-to-end reference for the two services: direct-port CURL, request/response shapes, Triton I/O contracts, and the pre-/post-processing logic that translates between them.

All facts below are sourced from the current code on this branch. File:line citations are included so the doc stays verifiable as code drifts.

---

## 1. Language Diarization Service

Segments an audio file by spoken language. Returns one or more time-bounded segments per audio input, each tagged with a language and confidence.

### 1.1 Service binding

| Property | Value | Source |
|---|---|---|
| FastAPI service port | `8090` | [env.template:7](services/language-diarization-service/env.template#L7), [Dockerfile EXPOSE](services/language-diarization-service/Dockerfile) |
| FastAPI HTTP path | `POST /api/v1/language-diarization/inference` | [routes/inference.py:18,29-30](services/language-diarization-service/app/routes/inference.py#L18-L30) |
| Triton server port | `8600` | Triton deployment (see §1.5 direct-Triton curl) |
| Triton model name | `lang_diarization` (hardcoded) | [service.py:27](services/language-diarization-service/app/services/language_diarization_service.py#L27), [triton_client.py:101](services/language-diarization-service/app/clients/triton_client.py#L101) |
| Default serviceId | `ai4bharat/language-diarization` | [env.template:42](services/language-diarization-service/env.template#L42) |

> Note: the service's README mentions port 9002, but the live env.template and Dockerfile both bind 8090. The README is stale; trust 8090.

### 1.2 Direct-port CURL sample

ServiceId used throughout this section: `5d30f31a9653572878e91e954d038649`.
The base64 string below is a minimal 44-byte WAV header (8 kHz, mono, 8-bit, zero samples) — useful as a smoke-test payload, but Triton will likely return an empty `segments` array on it. Replace with a full base64-encoded clip for real inference.

```bash
curl -X POST http://localhost:8090/api/v1/language-diarization/inference \
  -H "Content-Type: application/json" \
  -H "Authorization: Bearer <JWT_OR_API_KEY>" \
  -d '{
    "controlConfig": {
      "dataTracking": true
    },
    "config": {
      "serviceId": "5d30f31a9653572878e91e954d038649"
    },
    "audio": [
      {
        "audioContent": "UklGRiQAAABXQVZFZm10IBAAAAABAAEAQB8AAEAfAAABAAgAZGF0YQAAAAA="
      }
    ]
  }'
```

Alternative form using a remote URL:

```bash
curl -X POST http://localhost:8090/api/v1/language-diarization/inference \
  -H "Content-Type: application/json" \
  -H "Authorization: Bearer <JWT_OR_API_KEY>" \
  -d '{
    "config": { "serviceId": "5d30f31a9653572878e91e954d038649" },
    "audio":  [ { "audioUri": "https://example.com/sample.wav" } ]
  }'
```

`audioContent` (base64) and `audioUri` (downloadable URL) are alternatives — at least one is required per audio item ([schemas/inference.py:42-49](services/language-diarization-service/app/schemas/inference.py#L42-L49)).

### 1.3 API input format

Schema: `LanguageDiarizationInferenceRequest` ([schemas/inference.py:52-74](services/language-diarization-service/app/schemas/inference.py#L52-L74)).

```jsonc
{
  "controlConfig": {                 // optional
    "dataTracking": true             // bool, default true
  },
  "config": {                        // required
    "serviceId": "<string>"          // required — identifier for model routing
  },
  "audio": [                         // required, min_items=1
    {
      "audioContent": "<base64>",    // optional ── one of these two is required
      "audioUri":     "<https url>"  // optional ──┘
    }
  ]
}
```

Validation: each `AudioInput` must supply at least one of `audioContent`/`audioUri`; the request must contain at least one audio item ([schemas/inference.py:42-49,65-70](services/language-diarization-service/app/schemas/inference.py#L42-L70)).

**Concrete sample request** (this is exactly what the JSON body in §1.2 deserialises to):

```json
{
  "controlConfig": {
    "dataTracking": true
  },
  "config": {
    "serviceId": "5d30f31a9653572878e91e954d038649"
  },
  "audio": [
    {
      "audioContent": "UklGRiQAAABXQVZFZm10IBAAAAABAAEAQB8AAEAfAAABAAgAZGF0YQAAAAA="
    }
  ]
}
```

### 1.4 API output format

Schema: `LanguageDiarizationInferenceResponse` ([schemas/inference.py:80-128](services/language-diarization-service/app/schemas/inference.py#L80-L128)).

```jsonc
{
  "taskType": "language-diarization",
  "output": [                                // one entry per audio input, preserving order
    {
      "total_segments": <int>,
      "segments": [
        {
          "start_time": <float>,             // seconds
          "end_time":   <float>,
          "duration":   <float>,
          "language":   "<code>: <name>",    // e.g. "hi: Hindi"
          "confidence": <float>
        }
      ],
      "target_language": "<string>"          // echoes Triton's target_language; "" = all languages
    }
  ],
  "config": {
    "serviceId": "<echoed from request>"
  }
}
```

**Concrete sample response** (illustrative — actual segment counts/timestamps depend on the audio):

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
        },
        {
          "start_time": 2.5,
          "end_time": 5.1,
          "duration": 2.6,
          "language": "en: English",
          "confidence": 0.8745
        },
        {
          "start_time": 5.1,
          "end_time": 7.8,
          "duration": 2.7,
          "language": "hi: Hindi",
          "confidence": 0.9023
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

On per-item failure (download error, Triton error, empty Triton response), an **empty output** `{ total_segments: 0, segments: [], target_language: "" }` is returned in that array slot rather than aborting the whole batch ([service.py:264-271](services/language-diarization-service/app/services/language_diarization_service.py#L264-L271)):

```json
{
  "total_segments": 0,
  "segments": [],
  "target_language": ""
}
```

### 1.5 Triton input format

Model: `lang_diarization`, version `"1"`. Two BYTES tensors.

| Tensor name | dtype | Shape | Contents |
|---|---|---|---|
| `AUDIO_DATA` | BYTES | `[1, 1]` | Single-element 2D array; element = base64-encoded audio string |
| `LANGUAGE`   | BYTES | `[1, 1]` | Single-element 2D array; element = target language code (default `""` for all languages) |

Built explicitly with `_get_string_tensor_2d(...)` ([triton_client.py:73-77,145-157](services/language-diarization-service/app/clients/triton_client.py#L73-L157)):

```python
inputs = [
    self._get_string_tensor_2d([[audio_base64]],    "AUDIO_DATA"),
    self._get_string_tensor_2d([[target_language]], "LANGUAGE"),
]
```

The helper wraps the values list with `numpy.array(values, dtype=object)`, takes its `.shape` (`[1, 1]`), and converts via `np_to_triton_dtype` — yielding a BYTES tensor.

**Concrete Triton input values** (what the client sends for the §1.2 curl payload):

```python
# As constructed in Python:
audio_base64    = "UklGRiQAAABXQVZFZm10IBAAAAABAAEAQB8AAEAfAAABAAgAZGF0YQAAAAA="
target_language = ""  # hardcoded; not configurable from the API

# numpy representation of each tensor's data:
# AUDIO_DATA — shape (1, 1), dtype object/BYTES:
#   [["UklGRiQAAABXQVZFZm10IBAAAAABAAEAQB8AAEAfAAABAAgAZGF0YQAAAAA="]]
# LANGUAGE   — shape (1, 1), dtype object/BYTES:
#   [[""]]
```

Equivalent KServe v2 HTTP request body sent to Triton (`POST http://<triton-host>:8600/v2/models/lang_diarization/infer`):

```json
{
  "inputs": [
    {
      "name": "AUDIO_DATA",
      "shape": [1, 1],
      "datatype": "BYTES",
      "data": [["UklGRiQAAABXQVZFZm10IBAAAAABAAEAQB8AAEAfAAABAAgAZGF0YQAAAAA="]]
    },
    {
      "name": "LANGUAGE",
      "shape": [1, 1],
      "datatype": "BYTES",
      "data": [[""]]
    }
  ],
  "outputs": [
    { "name": "DIARIZATION_RESULT" }
  ]
}
```

**Direct-to-Triton curl** (bypasses the FastAPI wrapper — useful for debugging the model):

```bash
# First encode your audio file to base64
AUDIO_B64=$(base64 -w 0 /path/to/audio.wav)

# Then make the request
curl -X POST http://localhost:8600/v2/models/lang_diarization/infer \
  -H "Content-Type: application/json" \
  -d "{
    \"inputs\": [
      {
        \"name\": \"AUDIO_DATA\",
        \"shape\": [1, 1],
        \"datatype\": \"BYTES\",
        \"data\": [[\"$AUDIO_B64\"]]
      },
      {
        \"name\": \"LANGUAGE\",
        \"shape\": [1, 1],
        \"datatype\": \"BYTES\",
        \"data\": [[\"\"]]
      }
    ],
    \"outputs\": [
      {
        \"name\": \"DIARIZATION_RESULT\"
      }
    ]
  }"
```

### 1.6 Triton output format

| Tensor name | dtype | Shape | Contents |
|---|---|---|---|
| `DIARIZATION_RESULT` | BYTES | `[1, 1]` | Element `[0][0]` is a UTF-8-encoded JSON string |

Requested via `InferRequestedOutput("DIARIZATION_RESULT")` ([triton_client.py:78](services/language-diarization-service/app/clients/triton_client.py#L78)).

Inner JSON shape (inferred from how the client reads it at [triton_client.py:114-140](services/language-diarization-service/app/clients/triton_client.py#L114-L140) and [service.py:273-294](services/language-diarization-service/app/services/language_diarization_service.py#L273-L294)):

```jsonc
{
  "segments": [
    {
      "start_time": <float>,
      "end_time":   <float>,
      "duration":   <float>,      // optional — derived from end-start if absent
      "language":   "<string>",   // e.g. "hi: Hindi"
      "confidence": <float>
    }
    // ...
  ],
  "target_language": "<string>"   // echoed back; may be "" or "all"
}
```

If the response is empty, missing, or non-JSON, the client returns `{}` and the service substitutes an empty output ([triton_client.py:115-117,135-140](services/language-diarization-service/app/clients/triton_client.py#L115-L140)).

**Concrete Triton output values** (what would come back for the §1.4 sample response above):

Equivalent KServe v2 HTTP response body from Triton:

```json
{
  "model_name": "lang_diarization",
  "model_version": "1",
  "outputs": [
    {
      "name": "DIARIZATION_RESULT",
      "shape": [1, 1],
      "datatype": "BYTES",
      "data": [
        ["{\"segments\":[{\"start_time\":0.0,\"end_time\":2.5,\"duration\":2.5,\"language\":\"hi: Hindi\",\"confidence\":0.9312},{\"start_time\":2.5,\"end_time\":5.1,\"duration\":2.6,\"language\":\"en: English\",\"confidence\":0.8745},{\"start_time\":5.1,\"end_time\":7.8,\"duration\":2.7,\"language\":\"hi: Hindi\",\"confidence\":0.9023}],\"target_language\":\"\"}"]
      ]
    }
  ]
}
```

What the Python client sees after `response.as_numpy("DIARIZATION_RESULT")`:

```python
# numpy array, shape (1, 1), dtype object — element [0][0] is bytes:
result = np.array(
    [[b'{"segments":[{"start_time":0.0,"end_time":2.5,"duration":2.5,"language":"hi: Hindi","confidence":0.9312},{"start_time":2.5,"end_time":5.1,"duration":2.6,"language":"en: English","confidence":0.8745},{"start_time":5.1,"end_time":7.8,"duration":2.7,"language":"hi: Hindi","confidence":0.9023}],"target_language":""}']],
    dtype=object,
)

# After result[0][0].decode("utf-8") + json.loads(...):
{
    "segments": [
        {"start_time": 0.0, "end_time": 2.5, "duration": 2.5, "language": "hi: Hindi",   "confidence": 0.9312},
        {"start_time": 2.5, "end_time": 5.1, "duration": 2.6, "language": "en: English", "confidence": 0.8745},
        {"start_time": 5.1, "end_time": 7.8, "duration": 2.7, "language": "hi: Hindi",   "confidence": 0.9023}
    ],
    "target_language": ""
}
```

### 1.7 Pre-processing (API input → Triton input)

Source: [service.py:97-208](services/language-diarization-service/app/services/language_diarization_service.py#L97-L208), [triton_client.py:61-79](services/language-diarization-service/app/clients/triton_client.py#L61-L79). Applied per audio item in `request.audio`.

```
1. Audio resolution
  Input  : AudioInput { audioContent: Optional[str], audioUri: Optional[str] }
  Op     : if audioContent : audio_base64 = audioContent
           elif audioUri   : audio_base64 = base64.b64encode(
                                              requests.get(audioUri, timeout=300).content
                                            ).decode("utf-8")
           else            : audio_base64 = None
  Output : audio_base64 : Optional[str]

2. Size estimate (telemetry; not propagated to Triton)
  Input  : audio_base64 : str
  Op     : audio_bytes = len(base64.b64decode(audio_base64))
  Output : audio_bytes : int   →   span attr "audio_bytes_total"

3. Model resolution
  Input  : request.state
  Op     : model_name      = "lang_diarization"                # hardcoded constant
           target_language = ""                                # hardcoded
           triton_endpoint = request.state.triton_endpoint     # from Model Management
  Output : (model_name, target_language, triton_endpoint)

4. Triton tensor construction
  Input  : audio_base64 : str
           target_language : str
  Op     : AUDIO_DATA = _get_string_tensor_2d([[audio_base64]],    "AUDIO_DATA")
           LANGUAGE   = _get_string_tensor_2d([[target_language]], "LANGUAGE")
  Output : InferInput(name="AUDIO_DATA", shape=[1,1], datatype="BYTES",
                     data=[[audio_base64]])
           InferInput(name="LANGUAGE",   shape=[1,1], datatype="BYTES",
                     data=[[""]])
```

Per-item Triton call; no server-side batching across multiple audio inputs.

### 1.8 Post-processing (Triton output → API output)

Source: [triton_client.py:81-140](services/language-diarization-service/app/clients/triton_client.py#L81-L140), [service.py:259-348](services/language-diarization-service/app/services/language_diarization_service.py#L259-L348). Applied per Triton response.

```
1. Tensor extraction
  Input  : response : InferResult
  Op     : result = response.as_numpy("DIARIZATION_RESULT")
  Output : result : np.ndarray, shape=(1,1), dtype=object
           # Fallback {} if result is None or len(result) == 0

2. Byte decode
  Input  : result
  Op     : result_bytes = result[0][0]
           result_str   = result_bytes.decode("utf-8")
  Output : result_str : str  (JSON)

3. JSON parse
  Input  : result_str
  Op     : diarization_data = json.loads(result_str)
  Output : diarization_data : dict { segments: List[dict], target_language: str }
           # Fallback {} on JSONDecodeError

4. Segment normalization (per raw segment in diarization_data["segments"])
  Input  : seg : dict
  Op     : start_time = float(seg.get("start_time", 0.0))
           end_time   = float(seg.get("end_time",   0.0))
           duration   = float(seg.get("duration",   end_time - start_time))
           confidence = float(seg.get("confidence", 0.0))
           language   = seg.get("language", "")
  Output : LanguageSegment {
             start_time, end_time, duration, language, confidence
           }

5. Sort
  Input  : segments_list : List[LanguageSegment]
  Op     : segments_list.sort(key=lambda x: x.start_time)
  Output : segments_list  (ordered ascending by start_time)

6. Per-item output assembly
  Input  : segments_list, diarization_data["target_language"]
  Op     : total_segments = len(segments_list)
  Output : LanguageDiarizationOutput {
             total_segments  : int,
             segments        : List[LanguageSegment],
             target_language : str,
           }
           # Failed/skipped item → { total_segments: 0, segments: [], target_language: "" }

7. Response assembly
  Input  : output_list : List[LanguageDiarizationOutput]
           request.config.serviceId : str
  Output : LanguageDiarizationInferenceResponse {
             taskType : "language-diarization",
             output   : List[LanguageDiarizationOutput],
             config   : LanguageDiarizationResponseConfig { serviceId },
           }
```

---

## 2. Audio Language Detection Service

Classifies a complete audio clip to a single language. Returns the top language plus a score vector.

### 2.1 Service binding

| Property | Value | Source |
|---|---|---|
| FastAPI service port | `8096` | [env.template:7](services/audio-lang-detection-service/env.template#L7), [Dockerfile EXPOSE](services/audio-lang-detection-service/Dockerfile) |
| FastAPI HTTP path | `POST /api/v1/audio-lang-detection/inference` | [routes/inference.py:15,26](services/audio-lang-detection-service/app/routes/inference.py#L15-L26) |
| Triton server port | `8100` | Triton deployment (see §2.5 direct-Triton curl) |
| Triton model name | `ald` (resolved by Model Management from `config.serviceId`) | [dependencies/services.py:21,38-45](services/audio-lang-detection-service/app/dependencies/services.py#L21-L45) |
| Default serviceId | `ai4bharat/audio-lang-detection` | [env.template:41](services/audio-lang-detection-service/env.template#L41) |

> Key difference from language-diarization: this service does **not** hardcode the model name in code. The model name (`ald` in the current deployment) is resolved per-request by Model Management based on `config.serviceId`. If resolution fails, the service returns HTTP 500 ([dependencies/services.py:38-42](services/audio-lang-detection-service/app/dependencies/services.py#L38-L42)).

### 2.2 Direct-port CURL sample

ServiceId used throughout this section: `356b2b50747f44aa2abed17cae94327c`.
The base64 string below is the same 44-byte zero-sample WAV header as §1.2 — useful as a smoke test, not as real audio.

```bash
curl -X POST http://localhost:8096/api/v1/audio-lang-detection/inference \
  -H "Content-Type: application/json" \
  -H "Authorization: Bearer <JWT_OR_API_KEY>" \
  -d '{
    "controlConfig": {
      "dataTracking": true
    },
    "config": {
      "serviceId": "356b2b50747f44aa2abed17cae94327c"
    },
    "audio": [
      {
        "audioContent": "UklGRiQAAABXQVZFZm10IBAAAAABAAEAQB8AAEAfAAABAAgAZGF0YQAAAAA="
      }
    ]
  }'
```

URL-based form:

```bash
curl -X POST http://localhost:8096/api/v1/audio-lang-detection/inference \
  -H "Content-Type: application/json" \
  -H "Authorization: Bearer <JWT_OR_API_KEY>" \
  -d '{
    "config": { "serviceId": "356b2b50747f44aa2abed17cae94327c" },
    "audio":  [ { "audioUri": "https://example.com/sample.wav" } ]
  }'
```

### 2.3 API input format

Schema: `AudioLangDetectionInferenceRequest` ([schemas/inference.py:52-74](services/audio-lang-detection-service/app/schemas/inference.py#L52-L74)).

```jsonc
{
  "controlConfig": {                 // optional
    "dataTracking": true             // bool, default true
  },
  "config": {                        // required
    "serviceId": "<string>"          // required
  },
  "audio": [                         // required, min_items=1
    {
      "audioContent": "<base64>",    // optional ── one of these two is required
      "audioUri":     "<https url>"  // optional ──┘
    }
  ]
}
```

Identical input contract to language-diarization. Same validation rules.

**Concrete sample request:**

```json
{
  "controlConfig": {
    "dataTracking": true
  },
  "config": {
    "serviceId": "356b2b50747f44aa2abed17cae94327c"
  },
  "audio": [
    {
      "audioContent": "UklGRiQAAABXQVZFZm10IBAAAAABAAEAQB8AAEAfAAABAAgAZGF0YQAAAAA="
    }
  ]
}
```

### 2.4 API output format

Schema: `AudioLangDetectionInferenceResponse` ([schemas/inference.py:80-130](services/audio-lang-detection-service/app/schemas/inference.py#L80-L130)).

```jsonc
{
  "taskType": "audio-lang-detection",
  "output": [                            // one entry per audio input, preserving order
    {
      "language_code": "<code>: <name>",  // top language
      "confidence":    <float>,
      "all_scores": {
        "predicted_language": "<code>: <name>",
        "confidence":         <float>,
        "top_scores":        [<float>, ...]
      }
    }
  ],
  "config": {
    "serviceId": "<echoed from request>"
  }
}
```

**Concrete sample response** (illustrative — model output is deterministic for a given audio, but these numbers are representative, not guaranteed):

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
        "top_scores": [
          0.999923586845398,
          0.00006958437006687745,
          0.0000047704766075185034,
          0.0000021015366655774415,
          3.07008640731965e-8
        ]
      }
    }
  ],
  "config": {
    "serviceId": "356b2b50747f44aa2abed17cae94327c"
  }
}
```

Failed/missing items return an empty output:

```json
{
  "language_code": "",
  "confidence": 0.0,
  "all_scores": {
    "predicted_language": "",
    "confidence": 0.0,
    "top_scores": []
  }
}
```
([service.py:64-74,265-273](services/audio-lang-detection-service/app/services/audio_lang_detection_service.py#L64-L273))

### 2.5 Triton input format

One BYTES tensor.

| Tensor name | dtype | Shape | Contents |
|---|---|---|---|
| `AUDIO_DATA` | BYTES | `[1, 1]` (single base64 string wrapped by the shared `_get_string_tensor` helper) | Base64-encoded audio |

Built at [triton_client.py:67-73](services/audio-lang-detection-service/app/clients/triton_client.py#L67-L73):

```python
input_tensor = self._get_string_tensor([audio_base64], "AUDIO_DATA")
```

The helper used here is `_get_string_tensor` (inherited from `ai4icore_model_management.TritonClient` — base class lives in the external library). Comments downstream confirm Triton returns each result with shape `[1, 1]`, so the input tensor is similarly shaped.

> Note: unlike language-diarization, this service sends **only `AUDIO_DATA`** — no `LANGUAGE` tensor.

**Concrete Triton input values** (what the client sends for the §2.2 curl payload):

```python
audio_base64 = "UklGRiQAAABXQVZFZm10IBAAAAABAAEAQB8AAEAfAAABAAgAZGF0YQAAAAA="

# numpy representation — shape (1, 1), dtype object/BYTES:
# AUDIO_DATA:
#   [["UklGRiQAAABXQVZFZm10IBAAAAABAAEAQB8AAEAfAAABAAgAZGF0YQAAAAA="]]
```

Equivalent KServe v2 HTTP request body sent to Triton (`POST http://<triton-host>:8100/v2/models/ald/infer`):

```json
{
  "inputs": [
    {
      "name": "AUDIO_DATA",
      "shape": [1, 1],
      "datatype": "BYTES",
      "data": [["UklGRiQAAABXQVZFZm10IBAAAAABAAEAQB8AAEAfAAABAAgAZGF0YQAAAAA="]]
    }
  ],
  "outputs": [
    { "name": "LANGUAGE_CODE" },
    { "name": "CONFIDENCE" },
    { "name": "ALL_SCORES" }
  ]
}
```

**Direct-to-Triton curl** (bypasses the FastAPI wrapper — useful for debugging the model):

```bash
# First encode your audio file to base64
AUDIO_B64=$(base64 -w 0 /path/to/audio.wav)

# Then make the request
curl -X POST http://localhost:8100/v2/models/ald/infer \
  -H "Content-Type: application/json" \
  -d "{
    \"inputs\": [
      {
        \"name\": \"AUDIO_DATA\",
        \"shape\": [1, 1],
        \"datatype\": \"BYTES\",
        \"data\": [[\"$AUDIO_B64\"]]
      }
    ],
    \"outputs\": [
      {
        \"name\": \"LANGUAGE_CODE\"
      },
      {
        \"name\": \"CONFIDENCE\"
      },
      {
        \"name\": \"ALL_SCORES\"
      }
    ]
  }"
```

### 2.6 Triton output format

Three tensors are requested ([triton_client.py:68-72](services/audio-lang-detection-service/app/clients/triton_client.py#L68-L72)):

| Tensor name | dtype | Shape | Contents |
|---|---|---|---|
| `LANGUAGE_CODE` | BYTES | `[1, 1]` | UTF-8 string, e.g. `"ta: Tamil"` |
| `CONFIDENCE`    | numeric (treated as float; cast via `float(...)`) | `[1, 1]` | Top-language confidence |
| `ALL_SCORES`    | BYTES | `[1, 1]` | UTF-8 JSON string — see structure below |

`ALL_SCORES` JSON shape (parsed at [triton_client.py:145-155](services/audio-lang-detection-service/app/clients/triton_client.py#L145-L155)):

```jsonc
{
  "predicted_language": "ta: Tamil",
  "confidence":          0.9999236,
  "top_scores":         [0.9999236, 0.0000696, ...]
}
```

If `ALL_SCORES` is missing or unparseable, the client falls back to a synthesized object that reuses `language_code` and `confidence` and leaves `top_scores: []` ([triton_client.py:156-177](services/audio-lang-detection-service/app/clients/triton_client.py#L156-L177)).

**Concrete Triton output values** (what would come back for the §2.4 sample response above):

Equivalent KServe v2 HTTP response body from Triton:

```json
{
  "model_name": "ald",
  "model_version": "1",
  "outputs": [
    {
      "name": "LANGUAGE_CODE",
      "shape": [1, 1],
      "datatype": "BYTES",
      "data": [["ta: Tamil"]]
    },
    {
      "name": "CONFIDENCE",
      "shape": [1, 1],
      "datatype": "FP32",
      "data": [[0.999923586845398]]
    },
    {
      "name": "ALL_SCORES",
      "shape": [1, 1],
      "datatype": "BYTES",
      "data": [
        ["{\"predicted_language\":\"ta: Tamil\",\"confidence\":0.999923586845398,\"top_scores\":[0.999923586845398,0.00006958437006687745,0.0000047704766075185034,0.0000021015366655774415,3.07008640731965e-8]}"]
      ]
    }
  ]
}
```

> `CONFIDENCE` datatype `FP32` is inferred — the code only calls `float(...)` on `confidence_result[0][0]` and does not assert a Triton dtype. The model config is the ground truth; this could in principle be `FP64`.

What the Python client sees after `response.as_numpy(...)` for each output:

```python
# LANGUAGE_CODE — shape (1, 1), dtype object; element is bytes:
language_code_result = np.array([[b"ta: Tamil"]], dtype=object)
# After language_code_result[0][0].decode("utf-8"):
#   "ta: Tamil"

# CONFIDENCE — shape (1, 1), dtype float32 (or similar):
confidence_result = np.array([[0.999923586845398]], dtype=np.float32)
# After float(confidence_result[0][0]):
#   0.999923586845398

# ALL_SCORES — shape (1, 1), dtype object; element is bytes containing JSON:
all_scores_result = np.array(
    [[b'{"predicted_language":"ta: Tamil","confidence":0.999923586845398,"top_scores":[0.999923586845398,0.00006958437006687745,0.0000047704766075185034,0.0000021015366655774415,3.07008640731965e-8]}']],
    dtype=object,
)
# After all_scores_result[0][0].decode("utf-8") + json.loads(...):
{
    "predicted_language": "ta: Tamil",
    "confidence": 0.999923586845398,
    "top_scores": [
        0.999923586845398,
        0.00006958437006687745,
        0.0000047704766075185034,
        0.0000021015366655774415,
        3.07008640731965e-8
    ]
}
```

### 2.7 Pre-processing (API input → Triton input)

Source: [service.py:102-209](services/audio-lang-detection-service/app/services/audio_lang_detection_service.py#L102-L209), [triton_client.py:55-73](services/audio-lang-detection-service/app/clients/triton_client.py#L55-L73). Applied per audio item in `request.audio`.

```
1. Audio resolution
  Input  : AudioInput { audioContent: Optional[str], audioUri: Optional[str] }
  Op     : if audioContent : audio_base64 = audioContent
           elif audioUri   : audio_base64 = base64.b64encode(
                                              requests.get(audioUri, timeout=300).content
                                            ).decode("utf-8")
           else            : audio_base64 = None
  Output : audio_base64 : Optional[str]

2. Size estimate (telemetry; not propagated to Triton)
  Input  : audio_base64 : str
  Op     : audio_bytes = len(base64.b64decode(audio_base64))
  Output : audio_bytes : int   →   span attr "audio_bytes_total"

3. Model resolution
  Input  : request.state, request.config.serviceId
  Op     : model_name      = request.state.triton_model_name    # resolved by Model Management
           triton_endpoint = request.state.triton_endpoint
  Output : (model_name, triton_endpoint)
           # HTTP 500 if model_name in (None, "", "unknown")

4. Triton tensor construction
  Input  : audio_base64 : str
  Op     : AUDIO_DATA = _get_string_tensor([audio_base64], "AUDIO_DATA")
  Output : InferInput(name="AUDIO_DATA", shape=[1,1], datatype="BYTES",
                     data=[[audio_base64]])
```

Per-item Triton call; no server-side batching across multiple audio inputs.

### 2.8 Post-processing (Triton output → API output)

Source: [triton_client.py:75-177](services/audio-lang-detection-service/app/clients/triton_client.py#L75-L177), [service.py:258-322](services/audio-lang-detection-service/app/services/audio_lang_detection_service.py#L258-L322). Applied per Triton response.

```
1. Tensor extraction
  Input  : response : InferResult
  Op     : language_code_result = response.as_numpy("LANGUAGE_CODE")
           confidence_result    = response.as_numpy("CONFIDENCE")
           all_scores_result    = response.as_numpy("ALL_SCORES")
  Output : 3× np.ndarray, each shape=(1,1)
           # Empty result returned if any is None

2. LANGUAGE_CODE decode
  Input  : language_code_result
  Op     : language_code = language_code_result[0][0].decode("utf-8")
  Output : language_code : str
           # Default "" on extraction failure

3. CONFIDENCE cast
  Input  : confidence_result
  Op     : confidence = float(confidence_result[0][0])
  Output : confidence : float
           # Default 0.0 on extraction failure

4. ALL_SCORES decode + parse
  Input  : all_scores_result
  Op     : all_scores_str  = all_scores_result[0][0].decode("utf-8")
           all_scores_data = json.loads(all_scores_str)
  Output : all_scores_data : dict {
             predicted_language : str,
             confidence         : float,
             top_scores         : List[float],
           }
           # Fallback on JSONDecodeError:
           #   { predicted_language: language_code,
           #     confidence:         confidence,
           #     top_scores:         [] }

5. Per-item output assembly
  Input  : language_code, confidence, all_scores_data
  Output : AudioLangDetectionOutput {
             language_code : str,
             confidence    : float,
             all_scores    : AllScores {
               predicted_language : all_scores_data.get("predicted_language", ""),
               confidence         : all_scores_data.get("confidence",         0.0),
               top_scores         : all_scores_data.get("top_scores",         []),
             },
           }
           # Failed/skipped item → {
           #   language_code: "",
           #   confidence:    0.0,
           #   all_scores:    { predicted_language: "", confidence: 0.0, top_scores: [] }
           # }

6. Response assembly
  Input  : output_list : List[AudioLangDetectionOutput]
           request.config.serviceId : str
  Output : AudioLangDetectionInferenceResponse {
             taskType : "audio-lang-detection",
             output   : List[AudioLangDetectionOutput],
             config   : AudioLangDetectionResponseConfig { serviceId },
           }
```

---

## 3. Side-by-side comparison

| Dimension | Language Diarization | Audio Language Detection |
|---|---|---|
| Service port | 8090 | 8096 |
| HTTP path | `/api/v1/language-diarization/inference` | `/api/v1/audio-lang-detection/inference` |
| Request shape | identical | identical |
| Response per item | `total_segments`, `segments[]`, `target_language` | `language_code`, `confidence`, `all_scores{...}` |
| Triton model name | hardcoded `lang_diarization` | dynamic, resolved by Model Management per `serviceId` |
| Triton inputs | 2 BYTES tensors: `AUDIO_DATA`, `LANGUAGE` | 1 BYTES tensor: `AUDIO_DATA` |
| Triton input shape | `[1, 1]` (explicit 2D helper) | `[1, 1]` (default 1D-wrapping helper) |
| Triton outputs | 1 tensor: `DIARIZATION_RESULT` (JSON string) | 3 tensors: `LANGUAGE_CODE`, `CONFIDENCE`, `ALL_SCORES` (JSON string) |
| Granularity | Multiple time-bounded segments per audio | Single top-language classification per audio |
| Post-processing notable step | Sort segments by `start_time` ascending | Fallback synthesis when `ALL_SCORES` is unparseable |
| Per-item failure mode | Empty output `{0, [], ""}` | Empty output `{"", 0.0, {empty all_scores}}` |
| Batching to Triton | Per-item HTTP call inside a loop | Per-item HTTP call inside a loop |

---

## 4. File index

**Language Diarization**
- Routes: [services/language-diarization-service/app/routes/inference.py](services/language-diarization-service/app/routes/inference.py)
- Schemas: [services/language-diarization-service/app/schemas/inference.py](services/language-diarization-service/app/schemas/inference.py)
- Service logic: [services/language-diarization-service/app/services/language_diarization_service.py](services/language-diarization-service/app/services/language_diarization_service.py)
- Triton client: [services/language-diarization-service/app/clients/triton_client.py](services/language-diarization-service/app/clients/triton_client.py)
- DI: [services/language-diarization-service/app/dependencies/services.py](services/language-diarization-service/app/dependencies/services.py)
- Env: [services/language-diarization-service/env.template](services/language-diarization-service/env.template)

**Audio Language Detection**
- Routes: [services/audio-lang-detection-service/app/routes/inference.py](services/audio-lang-detection-service/app/routes/inference.py)
- Schemas: [services/audio-lang-detection-service/app/schemas/inference.py](services/audio-lang-detection-service/app/schemas/inference.py)
- Service logic: [services/audio-lang-detection-service/app/services/audio_lang_detection_service.py](services/audio-lang-detection-service/app/services/audio_lang_detection_service.py)
- Triton client: [services/audio-lang-detection-service/app/clients/triton_client.py](services/audio-lang-detection-service/app/clients/triton_client.py)
- DI: [services/audio-lang-detection-service/app/dependencies/services.py](services/audio-lang-detection-service/app/dependencies/services.py)
- Env: [services/audio-lang-detection-service/env.template](services/audio-lang-detection-service/env.template)
