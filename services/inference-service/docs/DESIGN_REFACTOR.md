# Template Method Pattern Refactor

## Summary

Refactored `BaseTaskService` to implement the **Template Method pattern**, providing a unified `process()` method that orchestrates the inference pipeline. This improves maintainability and reduces code duplication across task services.

## Changes Made

### Before (Old Design)
```python
# Orchestrator managed the pipeline
async def route_inference(payload):
    # 1. Deserialize
    request = deserialize(payload)
    
    # 2. Get service
    service = factory.create_service(task_type)
    
    # 3. Call service methods in sequence
    await service.validate_request(request)
    await service.preprocess_input(request.input)
    response = await service.run_inference(request)  # Orchestrates everything
    
    # 4. Serialize
    return serialize(response)
```

**Problems:**
- `run_inference()` was doing too much (both orchestration and inference)
- Each service would need to re-implement orchestration logic
- Duplicate code across all 12 services
- Orchestrator tightly coupled to service implementation details

### After (New Design)
```python
# BaseTaskService.process() orchestrates the pipeline
async def process(request, user_id, api_key_id, session_id):
    # 1. Validate
    await self.validate_request(request)
    
    # 2. Preprocess
    input_data = extract_input_from_request(request)
    preprocessed = await self.preprocess_input(input_data)
    
    # 3. Run inference (implemented by subclass)
    response = await self.run_inference(request, user_id, api_key_id, session_id)
    
    return response
```

```python
# Orchestrator just calls process()
async def route_inference(payload):
    request = deserialize(payload)
    service = factory.create_service(task_type)
    
    # Single method call - all orchestration happens inside
    response = await service.process(request, user_id, api_key_id, session_id)
    
    return serialize(response)
```

**Benefits:**
- ✅ Single entry point (`process()`) instead of managing multiple method calls
- ✅ Consistent pipeline across all services
- ✅ Services only implement `run_inference()` - the actual inference logic
- ✅ Optional overrides for `validate_request()`, `preprocess_input()`, `postprocess_output()`
- ✅ Orchestrator simplified - no pipeline orchestration needed
- ✅ Follows Template Method pattern (GOF Design Patterns)

## Interface Changes

### `ITaskService` (interface)
- ✅ `validate_request(request)` - abstract (services can override)
- ✅ `preprocess_input(input_data)` - abstract (services can override)
- ✅ `run_inference(request, user_id, api_key_id, session_id)` - abstract (MUST implement)
- ✅ `postprocess_output(raw_triton_output)` - abstract (services can override)

### `BaseTaskService` (implementation)
- ✅ **NEW:** `process(request, user_id, api_key_id, session_id)` - Template Method
  - Orchestrates: validate → preprocess → run_inference → postprocess
  - Extract input from polymorphic request (input/audio/image)
  - Update request with preprocessed data
  - Delegate to `run_inference()`
  
- ✅ `validate_request(request)` - Default implementation (checks if not None)
  - Subclasses override for task-specific validation
  
- ✅ `preprocess_input(input_data)` - Default implementation (checks if not empty)
  - Subclasses override for task-specific preprocessing
  
- ✅ `run_inference(request, user_id, api_key_id, session_id)` - Abstract (MUST implement)
  - Subclasses implement actual inference: resolve → convert → call triton → return response
  
- ✅ `postprocess_output(raw_triton_output)` - Default implementation (checks if not empty)
  - Subclasses override for task-specific post-processing

## Pipeline Flow

```
Client Request
    ↓
POST /inference
    ↓
Orchestrator.route_inference(payload)
    ├─ Validate task_type is registered
    ├─ Deserialize to task-specific request
    ├─ Create task service instance
    └─ Call service.process(request, user_id, api_key_id, session_id)  ← NEW
            ↓
        BaseTaskService.process()  ← Template Method
            ├─ await validate_request()      [optional override]
            ├─ Extract input (input/audio/image)
            ├─ await preprocess_input()      [optional override]
            ├─ await run_inference()          [MUST override]
            │   └─ Implement actual inference logic
            ├─ await postprocess_output()    [optional override]
            └─ Return response
    
    └─ Serialize response
↓
Client Response
```

## Task Service Implementation Template

### Before (Old Way)
```python
class NMTTaskService(BaseTaskService):
    async def validate_request(self, request):
        # Validation logic
        pass
    
    async def preprocess_input(self, input_data):
        # Preprocessing logic
        pass
    
    async def run_inference(self, request, user_id, api_key_id, session_id):
        # EVERYTHING had to be here:
        # - Additional validation
        # - Preprocess (duplicate)
        # - Resolve service/model
        # - Convert payload
        # - Call Triton
        # - Post-process
        # - Return response
        pass
    
    async def postprocess_output(self, raw_triton_output):
        pass
```

### After (New Way - Cleaner!)
```python
class NMTTaskService(BaseTaskService):
    async def validate_request(self, request):
        # Task-specific validation (optional)
        if request.config.language.source_language == request.config.language.target_language:
            raise ValueError("Source and target language cannot be the same")
    
    async def preprocess_input(self, input_data):
        # Task-specific preprocessing (optional)
        return [{"source": text.strip()} for text in input_data]
    
    async def run_inference(self, request, user_id, api_key_id, session_id):
        # ONLY actual inference logic - much cleaner!
        service_id = request.config.service_id or await self.smr.resolve(request)
        service_info = await resolver.resolve_service(service_id)
        
        model = NMTInferenceModel()
        triton_input = model.convert_payload_to_triton_format(request)
        triton_output = await triton_client.infer(service_info, triton_input)
        
        response_data = model.convert_triton_output_to_task_format(triton_output)
        return NMTInferenceResponse(**response_data)
```

## Impact on Implementation

### Orchestrator Changes (simplified)
```python
async def _execute_task_service(self, task_service, request, user_id, api_key_id, session_id):
    # Before: called multiple service methods
    # After: just one call!
    return await task_service.process(request, user_id, api_key_id, session_id)
```

### Service Changes (per task service)
- Implement `run_inference()` with only the inference logic
- Override `validate_request()`, `preprocess_input()`, `postprocess_output()` as needed
- NO need to orchestrate pipeline - `process()` handles it

## Benefits Summary

| Aspect | Before | After |
|--------|--------|-------|
| **Code Duplication** | High - each service re-implements orchestration | Low - orchestration in `process()` |
| **Service Entry Point** | Multiple methods to call | Single `process()` method |
| **Pipeline Consistency** | Manual ordering per service | Automatic via template method |
| **Testability** | Hard to test individual steps | Easy - each method independent |
| **Maintenance** | Changes to pipeline require updating all services | Single place to update |
| **Orchestrator Complexity** | High - manages pipeline | Low - just calls `process()` |
| **Lines per Service** | More | Less |

## Backward Compatibility

⚠️ **Breaking Change:** Services must update their `run_inference()` implementation:
- Old: Takes only `request`, does everything
- New: Takes `request`, `user_id`, `api_key_id`, `session_id`, does only inference

Update each of the 12 services to implement `run_inference()` with the new signature.

## Files Changed

1. **`interfaces/task_service.py`**
   - Added `process()` method to `BaseTaskService`
   - Updated `run_inference()` docstring to clarify it's for inference only
   - All other methods now have clear override contract

2. **`orchestrator/orchestrator.py`**
   - Updated `_execute_task_service()` docstring to show it calls `process()`
   - Implementation remains `pass` (no implementation in this step)

## Next Steps

1. Update all 12 TaskService implementations to implement `run_inference()` with new signature
2. Update Orchestrator's `_execute_task_service()` to call `task_service.process()`
3. Each service now only focuses on inference logic, not orchestration
