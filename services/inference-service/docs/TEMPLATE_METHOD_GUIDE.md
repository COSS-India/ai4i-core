# Template Method Pattern Implementation Guide

## Refactor Complete ✅

The `BaseTaskService` has been refactored to use the **Template Method pattern**. All 12 task services now need to update their implementation.

## Quick Reference

### Method Responsibilities

| Method | Responsibility | Override? | Notes |
|--------|---|---|---|
| `process()` | **Orchestrate pipeline** | ❌ No | Template Method - handles validate → preprocess → infer |
| `validate_request()` | Validate task-specific request | ✅ Optional | Base checks `request is not None` |
| `preprocess_input()` | Preprocess input array | ✅ Optional | Base checks `input is not empty` |
| `run_inference()` | **Execute actual inference** | ✅ **MUST** | Only place services implement business logic |
| `postprocess_output()` | Post-process Triton output | ✅ Optional | Base checks `output is not empty` |

## For Each Task Service

### Current Signature (Must Update)
```python
# Each service extends BaseTaskService
class ASRTaskService(BaseTaskService):
    async def run_inference(self, request):
        # OLD: Does everything (validation, preprocessing, inference, postprocessing)
        pass
```

### New Signature (After Refactor)
```python
# Each service extends BaseTaskService
class ASRTaskService(BaseTaskService):
    async def run_inference(self, request, user_id=None, api_key_id=None, session_id=None):
        # NEW: Only inference logic
        # 1. Resolve service
        # 2. Convert payload to Triton format
        # 3. Call Triton
        # 4. Convert output back to task format
        # 5. Return response
        pass
```

## Practical Example: ASRTaskService

### Before Refactor
```python
class ASRTaskService(BaseTaskService):
    
    async def validate_request(self, request):
        # Validate language code format
        if not request.config.language_code:
            raise ValueError("language_code required")
    
    async def preprocess_input(self, input_data):
        # Resample audio to 16kHz
        return [resample_audio(item['audio_content']) for item in input_data]
    
    async def run_inference(self, request):
        # TODO: This method had to do everything!
        # 1. Validate (duplicate)
        # 2. Preprocess (duplicate)
        # 3. Actually do inference
        # ... lots of code
        pass
    
    async def postprocess_output(self, raw_triton_output):
        # Format as ASR response
        pass
```

### After Refactor
```python
class ASRTaskService(BaseTaskService):
    
    async def validate_request(self, request):
        """Validate ASR-specific request."""
        if not request.config.language_code:
            raise ValueError("language_code required")
    
    async def preprocess_input(self, input_data):
        """Preprocess: Resample audio to 16kHz."""
        return [resample_audio(item['audio_content']) for item in input_data]
    
    async def run_inference(self, request, user_id=None, api_key_id=None, session_id=None):
        """Execute ASR inference - this is the ONLY place service logic goes."""
        
        # 1. Resolve service/model
        service_id = request.config.service_id or await self._smr.resolve(request)
        service_info = await self._resolver.resolve_service(service_id)
        
        # 2. Convert to Triton format
        model = ASRInferenceModel()
        triton_input = model.convert_payload_to_triton_format(request)
        
        # 3. Call Triton
        triton_client = await self._get_triton_client(service_info)
        triton_output = await triton_client.infer(service_info.model_name, triton_input)
        
        # 4. Convert back to task format
        response_data = model.convert_triton_output_to_task_format(triton_output)
        
        # 5. Return response
        return ASRInferenceResponse(**response_data)
    
    async def postprocess_output(self, raw_triton_output):
        """Post-process Triton output."""
        # Format output if needed
        pass
```

## Implementation Steps for 12 Services

For each service (NMT, ASR, OCR, NER, LLM, LanguageDetection, TTS, Transliteration, LanguageDiarization, SpeakerDiarization, AudioLanguageDetection, PII):

1. **Update `run_inference()` signature:**
   ```python
   async def run_inference(
       self, 
       request: TaskSpecificRequest,
       user_id: Optional[int] = None,
       api_key_id: Optional[int] = None,
       session_id: Optional[str] = None,
   ) -> TaskSpecificResponse:
   ```

2. **Move all inference logic into `run_inference()`:**
   - Resolve service via `InferenceServerResolver`
   - Create InferenceModel converter
   - Convert payload to Triton format
   - Call Triton inference server
   - Convert Triton output to task format
   - Return response

3. **Optionally override `validate_request()`, `preprocess_input()`, `postprocess_output()`:**
   - Only if task-specific logic is needed
   - Base class has safe defaults

4. **Delete any orchestration code:**
   - Don't manually call `validate_request()`, `preprocess_input()`, etc.
   - The `process()` method handles that

## Updated Flow (for developers)

### User's Perspective (Unchanged)
```
POST /api/v1/inference
Request: GenericInferenceRequest
Response: GenericInferenceResponse
```

### Implementation Flow (Simplified)

```
Orchestrator.route_inference(payload)
  ├─ Deserialize payload to task-specific request
  ├─ Create service instance via TaskFactory
  └─ Call service.process(request, user_id, api_key_id, session_id)
        ↓
     BaseTaskService.process()  ← Template Method
       ├─ await validate_request()            [optional override]
       ├─ Extract input (input/audio/image)
       ├─ await preprocess_input()            [optional override]
       ├─ await run_inference(...)             [MUST override]
       │   └─ YOUR INFERENCE LOGIC HERE
       ├─ await postprocess_output()          [optional override]
       └─ Return response
        ↓
  Serialize response to JSON
  ↓
Response back to client
```

## Testing the Refactor

### Test 1: Verify process() exists
```python
from services.asr_service import ASRTaskService

service = ASRTaskService()
assert hasattr(service, 'process')
assert hasattr(service, 'validate_request')
assert hasattr(service, 'preprocess_input')
assert hasattr(service, 'run_inference')
```

### Test 2: Verify pipeline execution
```python
request = ASRInferenceRequest(...)
response = await service.process(request, user_id=123)

# process() should have:
# 1. Called validate_request()
# 2. Called preprocess_input()
# 3. Called run_inference()
# 4. Returned response
```

### Test 3: Unit test individual methods
```python
# Test validation
try:
    await service.validate_request(invalid_request)
    assert False, "Should raise"
except ValueError:
    pass

# Test preprocessing
preprocessed = await service.preprocess_input(raw_input)
assert preprocessed != raw_input

# Test inference
response = await service.run_inference(valid_request)
assert isinstance(response, ASRInferenceResponse)
```

## Files to Update

### Services (12 files)
- [ ] `services/nmt_service.py` - Update `run_inference()`
- [ ] `services/asr_service.py` - Update `run_inference()`
- [ ] `services/ocr_service.py` - Update `run_inference()`
- [ ] `services/ner_service.py` - Update `run_inference()`
- [ ] `services/llm_service.py` - Update `run_inference()`
- [ ] `services/language_detection_service.py` - Update `run_inference()`
- [ ] `services/tts_service.py` - Update `run_inference()`
- [ ] `services/transliteration_service.py` - Update `run_inference()`
- [ ] `services/language_diarization_service.py` - Update `run_inference()`
- [ ] `services/speaker_diarization_service.py` - Update `run_inference()`
- [ ] `services/audio_language_detection_service.py` - Update `run_inference()`
- [ ] `services/pii_service.py` - Update `run_inference()`

### Orchestrator (1 file)
- [ ] `orchestrator/orchestrator.py` - Update `_execute_task_service()` to call `process()`

## Key Benefits After Implementation

✅ **Cleaner Services** — Each service focuses only on inference logic
✅ **Consistent Pipeline** — All services follow same orchestration pattern
✅ **Easier Maintenance** — Changes to pipeline happen in one place
✅ **Better Testability** — Each method independently testable
✅ **Less Duplication** — No repeated orchestration code

## Common Pitfalls to Avoid

❌ **Don't:** Manually call other methods in `run_inference()`
```python
async def run_inference(self, request, ...):
    # WRONG!
    await self.validate_request(request)
    await self.preprocess_input(request.input)
    ...
```

✅ **Do:** Only implement inference logic
```python
async def run_inference(self, request, ...):
    # Resolve, convert, call Triton, convert back, return
    ...
```

❌ **Don't:** Override `process()` method
```python
# WRONG!
async def process(self, request, ...):
    # Custom orchestration
```

✅ **Do:** Only override the step methods you need
```python
# RIGHT!
async def validate_request(self, request):
    # Custom validation for this service
    pass

async def preprocess_input(self, input_data):
    # Custom preprocessing for this service
    pass
```

## Questions?

Refer to:
- `interfaces/task_service.py` — Full interface with docstrings
- `DESIGN_REFACTOR.md` — Detailed before/after explanation
- `ARCHITECTURE.md` — Overall architecture overview
