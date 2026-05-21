# Smart Model Routing - Design Addon

**Date**: April 30, 2026  
**Status**: Addon to ORCHESTRATOR_INFERENCE_DESIGN.md  
**Purpose**: Add intelligent model selection capability to InferenceService

---

## 1. Summary of Changes

This addon extends the `InferenceService` interface with a new `getModel(modelId)` method that enables intelligent model selection:

- **Explicit Model Selection**: If `model_id` is specified in request → use that model
- **Smart Routing**: If `model_id` is None → SmartRoutingModel finds the best model based on task parameters
- **Fallback**: If SmartRoutingModel returns None → use default model

---

## 2. Updated InferenceService Interface

### Add this method to InferenceService (before preProcess)

```python
from abc import ABC, abstractmethod
from typing import Any, Dict, Optional

class InferenceService(ABC):
    """
    Abstract base class for all inference services.
    All services MUST implement these four methods.
    """
    
    @abstractmethod
    async def getModel(self, model_id: Optional[str] = None) -> str:
        """
        Determine which model to use for inference.
        
        **Decision Logic (Decision Tree)**:
        
        1. **If model_id is explicitly provided** (not None):
           - Validate the model_id
           - If valid → Return the provided model_id
           - If invalid → Raise ValueError with reason
        
        2. **If model_id is None**:
           - Call SmartRoutingModel.find_best_model(service_id, task_params)
           - SmartRoutingModel scores all available models based on:
             * Model availability (is it loaded in Triton?)
             * Latency constraints (can it meet latency budget?)
             * Accuracy requirements (does it meet accuracy threshold?)
             * Resource utilization (GPU/CPU availability)
           - If SmartRoutingModel returns a model → Return it
        
        3. **If SmartRoutingModel returns None**:
           - Fall back to default model for this service
           - Return the default model
        
        Args:
            model_id: Optional model identifier from request payload
                      - If provided: must be a valid model name
                      - If None: SmartRoutingModel will select
            
        Returns:
            str: Model name/identifier to use for Triton inference
            
        Raises:
            ValueError: If provided model_id is invalid/not found
            RuntimeError: If no model can be determined (emergency case)
            
        Examples:
            ```python
            # Case 1: Explicit model selection
            model = await service.getModel(\"transliteration-v2-accurate\")
            # Returns: \"transliteration-v2-accurate\" (after validation)
            
            # Case 2: Smart routing with task parameters
            model = await service.getModel(None)
            # SmartRoutingModel analyzes:
            # - Available models: [v1, v2-fast, v2-accurate]
            # - Current load: medium
            # - Latency budget: 100ms
            # - Accuracy threshold: 0.85
            # Returns: \"v2-fast\" (lowest latency meeting accuracy)
            
            # Case 3: Fallback to default
            model = await service.getModel(None)
            # SmartRoutingModel returns None (all models unavailable)
            # Returns: \"transliteration-v1\" (default model)
            
            # Case 4: Invalid model
            model = await service.getModel(\"unknown-model-xyz\")
            # Raises: ValueError(\"Model 'unknown-model-xyz' not found for service\")
            ```
        """
        pass
    
    # Existing methods (keep as is)
    @abstractmethod
    async def preProcess(self, input_data: Any) -> Dict[str, Any]:
        # ... existing docstring ...
        pass
    
    @abstractmethod
    async def postProcess(self, triton_output: Dict[str, Any]) -> Dict[str, Any]:
        # ... existing docstring ...
        pass
    
    @abstractmethod
    async def processData(self, request_data: Any) -> Dict[str, Any]:
        # ... existing docstring ...
        pass
```

---

## 3. SmartRoutingModel Implementation

### New File: `app/services/smart_routing_model.py`

```python
import logging
from typing import Dict, Optional, List, Any
from enum import Enum

class RoutingStrategy(Enum):
    """How the model was selected."""
    EXPLICIT = "explicit"       # User specified model_id
    SMART_ROUTING = "smart"     # SmartRoutingModel selected
    DEFAULT_FALLBACK = "default"  # Fallback to default


class SmartRoutingModel:
    """
    Intelligent model selection for each service.
    
    Determines the best model based on:
    - Task parameters (latency, accuracy requirements)
    - Historical performance metrics
    - Model availability
    - Resource constraints
    
    **Singleton Pattern**: Single instance shared across all services
    """
    
    _instance = None
    
    def __new__(cls):
        if cls._instance is None:
            cls._instance = super().__new__(cls)
            cls._instance._initialize()
        return cls._instance
    
    def _initialize(self):
        """Initialize routing engine."""
        self.logger = logging.getLogger(__name__)
        self.routing_config = self._load_routing_config()
        self.metrics_cache = {}
    
    def find_best_model(
        self,
        service_id: str,
        task_params: Optional[Dict[str, Any]] = None
    ) -> Optional[str]:
        """
        Find the best model for the given service and task.
        
        **Scoring Algorithm**:
        Each model is scored (0-1) based on:
        
        1. **Availability Score** (50% weight):
           - Is model loaded in Triton? Is it healthy?
           - Score: 1.0 (available) or 0.5 (degraded) or 0 (unavailable)
        
        2. **Latency Score** (30% weight):
           - Can model meet latency_budget_ms constraint?
           - Score: 1.0 (meets) or 0.3 (too slow) or 1.0 (no constraint)
        
        3. **Accuracy Score** (20% weight):
           - Does model meet accuracy_threshold?
           - Score: 1.0 (meets) or 0.1 (below threshold) or 1.0 (no constraint)
        
        **Final Score** = (Availability * 0.5) + (Latency * 0.3) + (Accuracy * 0.2)
        
        Args:
            service_id: Service name (\"transliteration\", \"nmt\", etc.)
            task_params: Optional task constraints:
                ```python
                {
                    \"latency_budget_ms\": 100,      # Max response time
                    \"accuracy_threshold\": 0.85,    # Min accuracy (0-1)
                    \"language_pair\": \"hi-en\",     # For NMT: source-target
                    \"domain\": \"general\",         # Domain type
                    \"user_tier\": \"premium\"       # User tier (premium gets better models)
                }
                ```
            
        Returns:
            str: Best model name or None if no suitable model found
            
        Example:
            ```python
            routing = SmartRoutingModel()
            
            # Find fast model for real-time inference
            model = routing.find_best_model(\n                \"transliteration\",\n                {\n                    \"latency_budget_ms\": 50,\n                    \"accuracy_threshold\": 0.80\n                }\n            )\n            # Returns: \"transliteration-v2-fast\" (lowest latency meeting threshold)\n            \n            # Find accurate model (no latency constraint)\n            model = routing.find_best_model(\n                \"transliteration\",\n                {\"accuracy_threshold\": 0.90}\n            )\n            # Returns: \"transliteration-v2-accurate\" (highest accuracy)\n            ```\n        \"\"\"\n        if service_id not in self.routing_config:\n            self.logger.warning(f\"No routing config for service: {service_id}\")\n            return None\n        \n        # Get available models for this service\n        available_models = self.routing_config[service_id].get(\"models\", [])\n        if not available_models:\n            self.logger.warning(f\"No models available for: {service_id}\")\n            return None\n        \n        # Score each model\n        scored_models = self._score_models(\n            service_id,\n            available_models,\n            task_params or {}\n        )\n        \n        if not scored_models:\n            return None\n        \n        # Sort by score (descending) and return best\n        best_model = max(scored_models, key=lambda x: x[\"score\"])\n        \n        self.logger.info(\n            f\"SmartRouting: service={service_id}, \"\n            f\"selected_model={best_model['name']}, \"\n            f\"score={best_model['score']:.3f}\"\n        )\n        \n        return best_model[\"name\"]\n    \n    def _score_models(\n        self,\n        service_id: str,\n        models: List[str],\n        task_params: Dict[str, Any]\n    ) -> List[Dict[str, Any]]:\n        \"\"\"Score each model against task requirements.\"\"\"\n        scored_models = []\n        \n        for model_name in models:\n            score = self._calculate_model_score(model_name, task_params)\n            scored_models.append({\n                \"name\": model_name,\n                \"score\": score\n            })\n        \n        return scored_models\n    \n    def _calculate_model_score(\n        self,\n        model_name: str,\n        task_params: Dict[str, Any]\n    ) -> float:\n        \"\"\"Calculate composite score for model.\"\"\"\n        # Component scores\n        availability_score = self._availability_score(model_name)\n        latency_score = self._latency_score(model_name, task_params)\n        accuracy_score = self._accuracy_score(model_name, task_params)\n        \n        # Weighted composite\n        final_score = (\n            availability_score * 0.5 +\n            latency_score * 0.3 +\n            accuracy_score * 0.2\n        )\n        \n        return final_score\n    \n    def _availability_score(self, model_name: str) -> float:\n        \"\"\"Score based on model availability in Triton.\"\"\"\n        is_available = self._is_model_available(model_name)\n        return 1.0 if is_available else 0.5\n    \n    def _latency_score(self, model_name: str, task_params: Dict[str, Any]) -> float:\n        \"\"\"Score based on latency constraints.\"\"\"\n        if \"latency_budget_ms\" not in task_params:\n            return 1.0  # No constraint\n        \n        budget = task_params[\"latency_budget_ms\"]\n        actual_latency = self._get_model_latency(model_name)\n        \n        if actual_latency <= budget:\n            return 1.0  # Meets budget\n        else:\n            return 0.3  # Penalize slow models\n    \n    def _accuracy_score(self, model_name: str, task_params: Dict[str, Any]) -> float:\n        \"\"\"Score based on accuracy constraints.\"\"\"\n        if \"accuracy_threshold\" not in task_params:\n            return 1.0  # No constraint\n        \n        threshold = task_params[\"accuracy_threshold\"]\n        actual_accuracy = self._get_model_accuracy(model_name)\n        \n        if actual_accuracy >= threshold:\n            return 1.0  # Meets threshold\n        else:\n            return 0.1  # Strong penalty for inaccurate models\n    \n    def _is_model_available(self, model_name: str) -> bool:\n        \"\"\"Check if model is loaded and healthy in Triton.\"\"\"\n        # Query Triton server\n        # For now: stub implementation\n        return True\n    \n    def _get_model_latency(self, model_name: str) -> float:\n        \"\"\"Get average latency (ms) from metrics server.\"\"\"\n        # Query metrics/monitoring system\n        # For now: stub implementation\n        model_latencies = {\n            \"transliteration-v1\": 45.0,\n            \"transliteration-v2-fast\": 20.0,\n            \"transliteration-v2-accurate\": 80.0,\n        }\n        return model_latencies.get(model_name, 50.0)\n    \n    def _get_model_accuracy(self, model_name: str) -> float:\n        \"\"\"Get accuracy score (0-1) from model metadata.\"\"\"\n        # Query model repository or metrics\n        # For now: stub implementation\n        model_accuracy = {\n            \"transliteration-v1\": 0.88,\n            \"transliteration-v2-fast\": 0.85,\n            \"transliteration-v2-accurate\": 0.92,\n        }\n        return model_accuracy.get(model_name, 0.85)\n    \n    def _load_routing_config(self) -> Dict[str, Any]:\n        \"\"\"Load model routing configuration.\"\"\"\n        return {\n            \"transliteration\": {\n                \"default_model\": \"transliteration-v1\",\n                \"models\": [\n                    \"transliteration-v1\",\n                    \"transliteration-v2-fast\",\n                    \"transliteration-v2-accurate\"\n                ]\n            },\n            \"nmt\": {\n                \"default_model\": \"nmt-v1\",\n                \"models\": [\n                    \"nmt-v1\",\n                    \"nmt-v2-fast\",\n                    \"nmt-v2-accurate\"\n                ]\n            }\n        }\n    \n    def get_default_model(self, service_id: str) -> Optional[str]:\n        \"\"\"Get the default model for a service.\"\"\"\n        return self.routing_config.get(\n            service_id, {}\n        ).get(\"default_model\")\n```

---

## 4. Updated TransliterationServiceImpl

Replace the `processData` implementation:

```python
# app/services/transliteration_service_impl.py
from app.services.base_service import InferenceService
from app.services.triton_client import TritonClient
from app.services.smart_routing_model import SmartRoutingModel, RoutingStrategy
from typing import Optional, Any, Dict

class TransliterationServiceImpl(InferenceService):
    \"\"\"Transliteration service with intelligent model selection.\"\"\"
    
    def __init__(self):
        self.triton_client = TritonClient()
        self.smart_routing = SmartRoutingModel()
        self.service_id = \"transliteration\"
        self.default_model = \"transliteration-v1\"
    
    async def getModel(self, model_id: Optional[str] = None) -> str:
        \"\"\"
        Intelligent model selection with three-level fallback.
        \"\"\"
        # Case 1: Explicit model_id provided by user
        if model_id is not None:
            if not self._is_valid_model(model_id):
                raise ValueError(f\"Unknown model: {model_id}\")
            return model_id
        
        # Case 2: Let SmartRoutingModel find best model
        # (Use task params from somewhere - e.g., config or request)
        task_params = {
            \"accuracy_threshold\": 0.85,
            \"latency_budget_ms\": 100\n        }\n        routed_model = self.smart_routing.find_best_model(\n            self.service_id,\n            task_params\n        )\n        \n        # Case 3: Fall back to default if SmartRouting returns None\n        return routed_model or self.default_model\n    \n    def _is_valid_model(self, model_id: str) -> bool:\n        \"\"\"Validate model exists in this service's registry.\"\"\"\n        valid_models = [\n            \"transliteration-v1\",\n            \"transliteration-v2-fast\",\n            \"transliteration-v2-accurate\"\n        ]\n        return model_id in valid_models\n    \n    async def preProcess(self, input_data: Any) -> Dict[str, Any]:\n        \"\"\"Existing implementation - no changes.\"\"\"\n        # ... existing code ...\n        pass\n    \n    async def postProcess(self, triton_output: Dict[str, Any]) -> Dict[str, Any]:\n        \"\"\"Existing implementation - no changes.\"\"\"\n        # ... existing code ...\n        pass\n    \n    async def processData(self, request_data: Any) -> Dict[str, Any]:\n        \"\"\"\n        Updated pipeline that uses getModel() for model selection.\n        \n        Flow:\n        1. Extract model_id from request (optional)\n        2. Call getModel() → returns selected model\n        3. Preprocess input\n        4. Execute Triton with selected model\n        5. Postprocess output\n        6. Track which model was used and how it was selected\n        \"\"\"\n        try:\n            # Step 1: Get optional model_id from request\n            model_id = request_data.get(\"model_id\")\n            \n            # Step 2: Determine model using getModel()\n            model_to_use = await self.getModel(model_id)\n            \n            # Step 3: Preprocess\n            preprocessed = await self.preProcess(request_data)\n            \n            # Step 4: Execute inference\n            triton_response = await self.triton_client.execute(\n                model_name=model_to_use,\n                input_data=preprocessed\n            )\n            \n            # Step 5: Postprocess\n            result = await self.postProcess(triton_response)\n            \n            # Step 6: Add model tracking info\n            result[\"model_used\"] = model_to_use\n            result[\"requested_model\"] = model_id\n            \n            # Determine routing strategy\n            if model_id is not None:\n                strategy = RoutingStrategy.EXPLICIT.value\n            elif model_id is None and model_to_use != self.default_model:\n                strategy = RoutingStrategy.SMART_ROUTING.value\n            else:\n                strategy = RoutingStrategy.DEFAULT_FALLBACK.value\n            \n            result[\"routing_strategy\"] = strategy\n            \n            return result\n            \n        except ValueError as e:\n            raise ValueError(f\"Model selection failed: {str(e)}\")\n        except Exception as e:\n            raise RuntimeError(f\"Inference failed: {str(e)}\")\n```

---

## 5. Model Selection Decision Flow

```
┌─────────────────────────┐\n│  User Request           │\n│  {                      │\n│    model_id: ??         │ ← Can be null or explicit\n│    data: {...}          │\n│  }                      │\n└──────────┬──────────────┘\n           │\n           ▼\n    ┌──────────────────┐\n    │  getModel(?)     │\n    └─────┬────────┬───┘\n      null│        │explicit\n         ▼         ▼\n   ┌────────────┐ ┌──────────────┐\n   │SmartRouting│ │Validate Model│\n   │.find_best()│ └──────┬────┬──┘\n   └────┬───────┘    valid│    │invalid\n       │              ┌───┘    └───┐\n       │              ▼            ▼\n       │         ┌────────┐  ┌──────────┐\n       │         │  Use   │  │ Raise    │\n       │         │ given  │  │ Error    │\n       │         │ model  │  └──────────┘\n       │         └───┬────┘\n       ▼─────────────┘\n   ┌────────────────────┐\n   │ Model returned?    │\n   │ (from SmartRouting)│\n   └────┬───────────┬───┘\n     yes│           │no\n        ▼           ▼\n   ┌─────────┐  ┌────────────┐\n   │Use Smart│  │Use Default │\n   │Model    │  │Model       │\n   └────┬────┘  └──────┬─────┘\n        │               │\n        └───────┬───────┘\n                ▼\n        ┌──────────────────┐\n        │ Execute with     │\n        │ Selected Model   │\n        └──────────────────┘\n```

---

## 6. Request/Response Schema Updates

### Update InferenceRequest

```python
class InferenceRequest(BaseModel):\n    \"\"\"Request with optional explicit model selection.\"\"\"\n    service_id: str\n    model_id: Optional[str] = None  # NEW: explicit model or null for smart routing\n    data: Dict[str, Any]\n    config: Optional[Dict[str, Any]] = {\n        \"services\": [],\n        \"timeout\": 30.0,\n        \"task_params\": {  # NEW: parameters for SmartRoutingModel\n            \"latency_budget_ms\": 100,\n            \"accuracy_threshold\": 0.85,\n            \"language_pair\": None,\n            \"domain\": \"general\"\n        }\n    }\n```\n\n### Update Service Result\n\n```python\nclass ServiceResult(BaseModel):\n    \"\"\"Single service result with model tracking.\"\"\"\n    status: str  # success/failed\n    output: Optional[Dict[str, Any]]\n    model_info: Optional[Dict[str, Any]] = {  # NEW: model selection tracking\n        \"model_used\": str,          # Actual model used\n        \"requested_model\": Optional[str],  # What user asked for\n        \"routing_strategy\": str  # explicit/smart/default\n    }\n    error: Optional[str] = None\n```\n\n---\n\n## 7. Integration Checklist\n\n- [ ] Add `getModel()` method to `InferenceService` interface\n- [ ] Create `SmartRoutingModel` singleton class\n- [ ] Implement `getModel()` in `TransliterationServiceImpl`\n- [ ] Update `processData()` to call `getModel()`\n- [ ] Update request schema with `model_id` field\n- [ ] Update response schema with model tracking\n- [ ] Create unit tests for `getModel()`\n- [ ] Create unit tests for `SmartRoutingModel`\n- [ ] Add integration tests for model selection flow\n- [ ] Document model routing configuration\n- [ ] Add metrics for model selection decisions\n\n---\n\n## 8. Test Examples\n\n```python\n# Unit test: Explicit model\n@pytest.mark.asyncio\nasync def test_getmodel_explicit():\n    service = TransliterationServiceImpl()\n    model = await service.getModel(\"transliteration-v2-accurate\")\n    assert model == \"transliteration-v2-accurate\"\n\n# Unit test: Invalid model\n@pytest.mark.asyncio\nasync def test_getmodel_invalid():\n    service = TransliterationServiceImpl()\n    with pytest.raises(ValueError):\n        await service.getModel(\"unknown-model\")\n\n# Unit test: Smart routing\n@pytest.mark.asyncio\nasync def test_getmodel_smart_routing():\n    service = TransliterationServiceImpl()\n    model = await service.getModel(None)  # Smart routing\n    assert model in [\"transliteration-v1\", \"transliteration-v2-fast\", \"transliteration-v2-accurate\"]\n\n# Integration test: Full pipeline\n@pytest.mark.asyncio\nasync def test_processdata_with_model_selection():\n    service = TransliterationServiceImpl()\n    result = await service.processData({\n        \"text\": \"namaste\",\n        \"source_language\": \"hi\",\n        \"model_id\": None  # Smart routing\n    })\n    assert \"model_used\" in result\n    assert \"routing_strategy\" in result\n```\n\n---\n\n**Addon Document Prepared**: April 30, 2026\n