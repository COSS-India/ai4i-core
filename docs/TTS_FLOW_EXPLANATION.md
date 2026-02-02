# TTS Service Flow: From UI Button Click to Audio Generation

## Complete Flow Diagram

```
User clicks "Generate Audio" button
    ↓
Frontend (React/Next.js)
    ↓
API Client (apiClient.post)
    ↓
API Gateway (Port 8080)
    ↓
TTS Service (Port 8088)
    ↓
Triton Inference Server
    ↓
Audio Response (Base64)
    ↓
Frontend displays/plays audio
```

## Step-by-Step Code Flow

### 1. **UI Button Click** (`frontend/simple-ui/src/pages/tts.tsx`)

**File:** `tts.tsx` (Line 218-228)
```tsx
<Button
  onClick={handleGenerate}  // ← Button click handler
  isLoading={fetching}
>
  Generate Audio
</Button>
```

**Handler Function** (Line 79-91):
```tsx
const handleGenerate = () => {
  if (!inputText.trim()) {
    toast({ title: "Input Required", ... });
    return;
  }
  performInference(inputText);  // ← Calls hook function
};
```

### 2. **React Hook** (`frontend/simple-ui/src/hooks/useTTS.ts`)

**File:** `useTTS.ts` (Line 111-155)

The `performInference` function:
```tsx
const performInference = useCallback(async (text: string) => {
  setFetching(true);
  setRequestWordCount(getWordCount(text));
  await ttsMutation.mutateAsync(text);  // ← Triggers mutation
}, [ttsMutation, toast, serviceId, language]);
```

**Mutation Function** (Line 49-62):
```tsx
const ttsMutation = useMutation({
  mutationFn: async (text: string) => {
    const config = {
      language: { sourceLanguage: language },
      serviceId: effectiveServiceId,
      gender,
      samplingRate,
      audioFormat,
    };
    return performTTSInference(text, config);  // ← Calls service
  },
  onSuccess: (response) => {
    // Process audio response
    const audioContent = response.data.audio[0]?.audioContent;
    const dataUrl = `data:audio/wav;base64,${audioContent}`;
    setAudio(dataUrl);  // ← Sets audio for playback
  }
});
```

### 3. **API Service Call** (`frontend/simple-ui/src/services/ttsService.ts`)

**File:** `ttsService.ts` (Line 91-120)

```tsx
export const performTTSInference = async (
  text: string,
  config: TTSInferenceRequest['config']
) => {
  const payload: TTSInferenceRequest = {
    input: [{ source: text }],
    config,
    controlConfig: { dataTracking: false },
  };

  // ← Makes HTTP POST request to API Gateway
  const response = await apiClient.post<TTSInferenceResponse>(
    apiEndpoints.tts.inference,  // "/api/v1/tts/inference"
    payload
  );

  return {
    data: response.data,
    responseTime: parseInt(response.headers['request-duration'] || '0')
  };
};
```

### 4. **API Client Configuration** (`frontend/simple-ui/src/services/api.ts`)

**File:** `api.ts`

```tsx
// API Base URL from environment variable
const API_BASE_URL = process.env.NEXT_PUBLIC_API_URL;  // "http://localhost:8080"

// Axios instance configured with base URL
const apiClient = axios.create({
  baseURL: API_BASE_URL,
  timeout: 300000,  // 5 minutes
  headers: {
    'Content-Type': 'application/json',
  },
});

// Endpoint definition
export const apiEndpoints = {
  tts: {
    inference: '/api/v1/tts/inference',  // ← Full path: http://localhost:8080/api/v1/tts/inference
  }
};
```

### 5. **API Gateway Route** (`services/api-gateway-service/main.py`)

**File:** `main.py` (Line 3325-3339)

**Route Mapping** (Line 1596):
```python
self.routes = {
    '/api/v1/tts': 'tts-service',  # ← Maps /api/v1/tts/* to tts-service
    ...
}
```

**TTS Inference Endpoint** (Line 3325):
```python
@app.post("/api/v1/tts/inference", response_model=TTSInferenceResponse, tags=["TTS"])
async def tts_inference(
    payload: TTSInferenceRequest,
    request: Request,
    credentials: Optional[HTTPAuthorizationCredentials] = Security(bearer_scheme),
    api_key: Optional[str] = Security(api_key_scheme)
):
    """Perform batch TTS inference on text inputs"""
    await ensure_authenticated_for_request(request, credentials, api_key)
    
    # Convert Pydantic model to JSON
    body = json.dumps(payload.dict()).encode()
    
    # Build auth headers
    headers = build_auth_headers(request, credentials, api_key)
    
    # ← Proxy request to TTS service
    return await proxy_to_service(
        None, 
        "/api/v1/tts/inference", 
        "tts-service",  # ← Service name
        method="POST", 
        body=body, 
        headers=headers
    )
```

**Service Discovery** (Line 1564):
```python
async def select_instance(self, service_name: str) -> Optional[Tuple[str, str]]:
    # Gets service URL from service registry
    # Returns: ("http://tts-service:8088", instance_id)
```

### 6. **TTS Service Endpoint** (`services/tts-service/routers/inference_router.py`)

**File:** `inference_router.py` (Line 171-200)

```python
@inference_router.post(
    "/inference",
    response_model=TTSInferenceResponse,
    summary="Perform batch TTS inference"
)
async def run_inference(
    request: TTSInferenceRequest,
    http_request: Request,
    tts_service: TTSService = Depends(get_tts_service)
) -> TTSInferenceResponse:
    """Run TTS inference on the given request."""
    
    # Extract auth context
    user_id = getattr(http_request.state, "user_id", None)
    api_key_id = getattr(http_request.state, "api_key_id", None)
    
    # ← Calls TTS service to process request
    response = await tts_service.run_inference(
        request=request,
        user_id=user_id,
        api_key_id=api_key_id,
        session_id=session_id
    )
    
    return response
```

### 7. **TTS Service Processing** (`services/tts-service/services/tts_service.py`)

The TTS service:
1. Validates the request
2. Calls Triton Inference Server
3. Processes audio response
4. Returns base64-encoded audio

### 8. **Response Flow Back**

```
TTS Service → API Gateway → Frontend
    ↓
Response contains:
{
  "output": [{
    "audioContent": "base64EncodedAudioData..."
  }],
  "config": {...}
}
    ↓
Frontend converts to data URL:
data:audio/wav;base64,{audioContent}
    ↓
Audio element created and played
```

## Key Configuration Points

### Environment Variables

**Frontend** (`.env`):
```bash
NEXT_PUBLIC_API_URL=http://localhost:8080  # API Gateway URL
```

**API Gateway** (`docker-compose.yml`):
```yaml
TTS_SERVICE_URL=http://tts-service:8088
```

**TTS Service** (`docker-compose.yml`):
```yaml
TRITON_ENDPOINT=http://13.200.133.97:9000
```

## Network Flow

1. **Browser** → `http://localhost:8080/api/v1/tts/inference` (API Gateway)
2. **API Gateway** → `http://tts-service:8088/api/v1/tts/inference` (TTS Service)
3. **TTS Service** → `http://13.200.133.97:9000/v2/models/tts/infer` (Triton)
4. **Response flows back** through the same path

## Authentication Flow

1. Frontend sends API key in `Authorization` header
2. API Gateway validates API key with Auth Service
3. API Gateway forwards auth headers to TTS Service
4. TTS Service validates permissions
5. Request proceeds if authenticated

## Error Handling

- **Frontend**: Shows toast notifications for errors
- **API Gateway**: Returns HTTP error codes
- **TTS Service**: Returns detailed error messages
- **Triton**: Returns model-specific errors

