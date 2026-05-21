# Service-Level Inference API Endpoint Design

**Date**: April 30, 2026  
**Status**: Design Proposal  
**Target Services**: All micro-services with `/inference` endpoint calling Triton server  
**Design Patterns**: Strategy Pattern + Singleton Pattern

---

## 1. Executive Summary

This document proposes a unified, scalable architecture for handling inference requests within individual micro-services. Each service implements its own `/inference` endpoint that directly handles requests using a shared interface pattern, enabling:

- **Direct routing**: Request endpoint → Service → Triton (no intermediary orchestrator)
- **Horizontal scalability**: Add new services without infrastructure changes
- **Separation of concerns**: Each service handles its own preprocessing and postprocessing
- **Shared resources**: Singleton Triton client and SmartRoutingModel across all services
- **Configuration-driven model selection**: Intelligent model routing per service
- **Testability**: Easy mocking and unit testing of individual service components

---

## 2. Current Architecture Issues

### Problem Statement
Currently, each service implements its own `/inference` endpoint with redundant logic:
- Separate Triton client initialization per service
- Duplicated request validation and error handling
- Service-specific processing scattered across multiple files
- No standardized pattern for model selection logic
- Difficult to maintain consistency across services

### Example Current Issues
```python
# Transliteration service
async def run_inference(request_body, user_id, api_key_id, session_id):
    # Service-specific preprocessing
    # Triton client initialization
    # Triton inference call
    # Service-specific postprocessing
    # Return response

# NER service (same pattern repeated)
async def run_inference(request_body, user_id, api_key_id, session_id):
    # Similar duplicate logic
```

---

## 3. Proposed Architecture

### 3.1 High-Level Design

```
┌─────────────────────────────────────────────────────────────┐
│                        API Gateway                          │
│              /api/v1/{service}/inference                    │
└────────────────────────┬────────────────────────────────────┘
                         │
         ┌───────────────┼───────────────┐
         │               │               │
         ▼               ▼               ▼
    ┌─────────┐    ┌─────────┐    ┌─────────┐
    │  Trans. │    │   NMT   │    │   NER   │
    │ Service │    │ Service │    │ Service │
    │Inference│    │Inference│    │Inference│
    │Endpoint │    │Endpoint │    │Endpoint │
    └────┬────┘    └────┬────┘    └────┬────┘
         │               │               │
    (All services implement InferenceService interface)
    - getModel() → Smart model selection
    - preProcess() → Input validation & formatting
    - postProcess() → Output formatting
    - processData() → Full pipeline orchestration
         │
         ▼
┌─────────────────────────────────────────────────────────────┐
│     SmartRoutingModel (Singleton - Model Selection)         │
│  - Intelligent model routing per service                    │
│  - Weighted scoring: Availability/Latency/Accuracy          │
└─────────────────────────────────────────────────────────────┘
         │
         ▼
┌─────────────────────────────────────────────────────────────┐
│         Triton Client (Singleton - Shared Instance)         │
│  - Persistent connection to Triton server                   │
│  - execute(model_name, input_data) → output                 │
└─────────────────────────────────────────────────────────────┘
         │
         ▼
┌─────────────────────────────────────────────────────────────┐
│              Triton Inference Server                         │
│              (Docker Container / Remote Host)               │
└─────────────────────────────────────────────────────────────┘
```

### 3.2 Component Hierarchy

```
Core Abstractions
├── InferenceService (Abstract Base Class)
│   ├── getModel(model_id) → str
│   ├── preProcess(input_data) → Dict
│   ├── postProcess(triton_output) → Dict
│   └── processData(request_data) → Dict
│
├── SmartRoutingModel (Intelligent Model Selection - Singleton)
│   ├── find_best_model(service_id, task_params) → str
│   └── get_default_model(service_id) → str
│
└── TritonClient (Singleton)
    └── execute(model_name, input_data) → Dict

Service Implementations
├── TransliterationService(InferenceService)
│   └── POST /inference → processData() → response
│
├── NMTService(InferenceService)
│   └── POST /inference → processData() → response
│
├── NERService(InferenceService)
│   └── POST /inference → processData() → response
│
└── [Other services...]
    └── POST /inference → processData() → response
```

---

## 4. Data Flow Diagrams

### 4.1 Service Inference Endpoint Flow (with Smart Model Selection)

```
┌─────────────────────────────────────────────────────────────┐
│   HTTP Request                                              │
│   POST /api/v1/transliteration/inference                    │
│   {                                                         │
│     "data": {                                               │
│       "text": "namaste",                                    │
│       "source_language": "hi",                              │
│       "target_language": "en"                               │
│     },                                                      │
│     "model_id": null,  # Optional explicit model            │
│     "config": {                                             │
│       "task_params": {                                      │
│         "latency_budget_ms": 50,                            │
│         "accuracy_threshold": 85.0                          │
│       }                                                     │
│     }                                                       │
│   }                                                         │
└────────┬────────────────────────────────────────────────────┘
         │
         ▼
┌─────────────────────────────────────────────────────────────┐
│  FastAPI Endpoint (/inference)                              │
│  ✓ Request validation & schema parsing                      │
│  ✓ Auth check & Tenant check (via middleware)               │
│  ✓ Extract user context                                     │
│  ✓ Call service.processData(request)                        │
└────────┬────────────────────────────────────────────────────┘
         │
         ▼
┌──────────────────────────────────────────────────────────┐
│ TransliterationService.processData()                     │
│ Full pipeline orchestration (inherited from base class)  │
└────────┬─────────────────────────────────────────────────┘
         │
         ▼
┌──────────────────────────────────────────────────────────┐
│  Stage 1: Extract request components                     │
│  ✓ model_id from request (optional)                      │
│  ✓ task_params from config                               │
│  ✓ Store in current_task_params                          │
└────────┬─────────────────────────────────────────────────┘
         │
         ▼
┌──────────────────────────────────────────────────────────┐
│  Stage 2: Smart Model Selection (getModel)              │
│  ┌────────────────────────────────────────────────────┐ │
│  │ 3-Level Fallback Strategy:                         │ │
│  │                                                    │ │
│  │ LEVEL 1: EXPLICIT MODEL                            │ │
│  │ If model_id provided:                              │ │
│  │   ✓ Validate model exists                          │ │
│  │   ✓ Return explicit model                          │ │
│  │   ✓ routing_strategy = "explicit"                  │ │
│  │                    ↓ (model_id is None)            │ │
│  │ LEVEL 2: SMART ROUTING                             │ │
│  │ Call SmartRoutingModel.find_best_model():          │ │
│  │   ✓ Extract task parameters                        │ │
│  │   ✓ Score all available models                     │ │
│  │   ✓ Return best model matching constraints         │ │
│  │   ✓ routing_strategy = "smart"                     │ │
│  │                    ↓ (SmartRouting returns None)   │ │
│  │ LEVEL 3: DEFAULT FALLBACK                          │ │
│  │ Use service default model:                         │ │
│  │   ✓ Guaranteed availability                        │ │
│  │   ✓ routing_strategy = "default"                   │ │
│  └────────────────────────────────────────────────────┘ │
│  Output: selected_model_name                             │
└────────┬─────────────────────────────────────────────────┘
         │
         ▼
┌──────────────────────────────────────────────────────────┐
│  Stage 3: Preprocess Input (preProcess)                 │
│  ✓ Validate input data                                   │
│  ✓ Convert to Triton format                              │
│  ✓ Handle service-specific preprocessing                 │
│  Output: {input_text, language, ...}                     │
└────────┬─────────────────────────────────────────────────┘
         │
         ▼
┌──────────────────────────────────────────────────────────┐
│  Stage 4: Execute Inference (Triton)                    │
│  ✓ Model: selected_model_name                            │
│  ✓ Input: preprocessed data                              │
│  ✓ Call TritonClient.execute() (singleton)               │
│  Output:                                                 │
│  {                                                       │
│    "output": "nmst",                                     │
│    "scores": [0.95, 0.89],                               │
│    "latency_ms": 12                                      │
│  }                                                       │
└────────┬─────────────────────────────────────────────────┘
         │
         ▼
┌──────────────────────────────────────────────────────────┐
│  Stage 5: Postprocess Output (postProcess)              │
│  ✓ Format output for API response                        │
│  ✓ Extract confidence/scores                             │
│  ✓ Apply service-specific formatting                     │
│  Output: {transliterated_text, confidence, ...}          │
└────────┬─────────────────────────────────────────────────┘
         │
         ▼
┌──────────────────────────────────────────────────────────┐
│  Stage 6: Add Model Metadata                             │
│  {                                                       │
│    "output": {...},                                      │
│    "model_used": "transliteration-v2-fast",              │
│    "requested_model": null,                              │
│    "routing_strategy": "smart"                           │
│  }                                                       │
└────────┬─────────────────────────────────────────────────┘
         │
         ▼
┌──────────────────────────────────────────────────────────┐
│  HTTP Response (200 OK)                                  │
│  {                                                       │
│    "data": {                                             │
│      "transliterated_text": "nmst",                       │
│      "confidence": 0.95                                  │
│    },                                                    │
│    "model_info": {                                       │
│      "model_used": "transliteration-v2-fast",            │
│      "requested_model": null,                            │
│      "routing_strategy": "smart",                        │
│      "triton_latency_ms": 12                             │
│    },                                                    │
│    "user_id": "user123",                                 │
│    "session_id": "sess456"                               │
│  }                                                       │
└──────────────────────────────────────────────────────────┘
```

---

## 5. Component Specifications

### 5.1 InferenceService Interface

```python
from abc import ABC, abstractmethod
from typing import Any, Dict, Optional
from datetime import datetime

class InferenceService(ABC):
    """
    Abstract base class for all inference services.
    Each service implements this interface for its /inference endpoint.
    """
    
    def __init__(self, service_id: str, default_model: str):
        """
        Initialize the service with its ID and default model.
        
        Args:
            service_id: Unique identifier (e.g., 'transliteration', 'ner', 'asr')
            default_model: Fallback model name if smart routing fails
        """
        self.service_id = service_id
        self.default_model = default_model
        self.triton_client = TritonClient()  # Singleton instance
        self.smart_routing = SmartRoutingModel()  # Singleton instance
        self.current_task_params = {}
        self.logger = logging.getLogger(__name__)
    
    async def getModel(self, model_id: Optional[str] = None) -> str:
        """
        Smart model selection with 3-level fallback strategy.
        
        Decision Logic:
        ┌─────────────────────────────────────────────────┐
        │ LEVEL 1: EXPLICIT MODEL                         │
        │ ─────────────────────────────────────────────   │
        │ If model_id is provided in request:             │
        │   • Validate that model exists                  │
        │   • Return the explicitly requested model       │
        │   • Tracking: routing_strategy = "explicit"     │
        └─────────────────────────────────────────────────┘
                           ↓ (model_id is None)
        ┌─────────────────────────────────────────────────┐
        │ LEVEL 2: SMART MODEL ROUTING                    │
        │ ─────────────────────────────────────────────   │
        │ If model_id is None:                            │
        │   • Extract task parameters                     │
        │   • Call SmartRoutingModel.find_best_model()    │
        │   • Algorithm: Weighted scoring                 │
        │     - Availability: 50% weight                  │
        │     - Latency: 30% weight                       │
        │     - Accuracy: 20% weight                      │
        │   • If best model found:                        │
        │     - Return selected model                     │
        │     - Tracking: routing_strategy = "smart"      │
        └─────────────────────────────────────────────────┘
                    ↓ (SmartRouting returns None)
        ┌─────────────────────────────────────────────────┐
        │ LEVEL 3: DEFAULT FALLBACK                       │
        │ ─────────────────────────────────────────────   │
        │ If SmartRouting returns None:                   │
        │   • Use service's pre-configured default model  │
        │   • Guaranteed availability                     │
        │   • Tracking: routing_strategy = "default"      │
        └─────────────────────────────────────────────────┘
        
        Args:
            model_id: Optional explicit model ID from request
            
        Returns:
            Selected model name to use for inference
            
        Raises:
            ValueError: If explicit model_id is invalid
        """
        # Level 1: Explicit model selection
        if model_id is not None:
            if not self._is_valid_model(model_id):
                raise ValueError(
                    f"Model '{model_id}' not supported by {self.service_id}. "
                    f"Valid models: {self._get_supported_models()}"
                )
            return model_id
        
        # Level 2: Smart model routing
        task_params = self._extract_task_params()
        routed_model = await self.smart_routing.find_best_model(
            service_id=self.service_id,
            task_params=task_params
        )
        
        if routed_model is not None:
            return routed_model
        
        # Level 3: Default fallback
        return self.default_model
    
    def _is_valid_model(self, model_id: str) -> bool:
        """Check if model is supported by this service."""
        return model_id in self._get_supported_models()
    
    def _get_supported_models(self) -> list:
        """Return list of supported models for this service."""
        # Override in subclass
        return [self.default_model]
    
    def _extract_task_params(self) -> Dict[str, Any]:
        """Extract task parameters from current request context."""
        # Override in subclass to provide context-specific parameters
        return self.current_task_params
    
    @abstractmethod
    async def preProcess(self, input_data: Any) -> Dict[str, Any]:
        """
        Convert raw request payload to Triton-compatible format.
        
        Args:
            input_data: Raw input from request
            
        Returns:
            Dictionary with Triton-compatible format
            
        Raises:
            ValueError: If input validation fails
        """
        pass
    
    @abstractmethod
    async def postProcess(self, triton_output: Dict[str, Any]) -> Dict[str, Any]:
        """
        Convert Triton response to service-specific format.
        
        Args:
            triton_output: Raw output from Triton server
            
        Returns:
            Formatted output specific to this service
            
        Raises:
            ValueError: If output transformation fails
        """
        pass
    
    async def processData(self, request_data: Any) -> Dict[str, Any]:
        """
        Orchestrate full inference pipeline with smart model selection.
        
        Pipeline Stages:
        1. Extract model_id and task parameters from request
        2. Call getModel() for smart model selection
        3. Preprocess the input data
        4. Execute inference on Triton with selected model
        5. Postprocess the Triton output
        6. Add model metadata to response
        
        Args:
            request_data: Full request payload with:
                - data: actual input data
                - model_id: optional explicit model selection
                - config: task configuration with task_params
            
        Returns:
            Dictionary with inference results and model tracking metadata
        """
        try:
            # Stage 1: Extract model_id and task parameters
            model_id = request_data.get("model_id")
            self.current_task_params = request_data.get("config", {}).get("task_params", {})
            requested_model = model_id
            
            self.logger.info(
                f"Processing inference for {self.service_id}. "
                f"Model requested: {model_id}, Task params: {self.current_task_params}"
            )
            
            # Stage 2: Smart model selection (with 3-level fallback)
            selected_model = await self.getModel(model_id)
            
            # Determine routing strategy for response tracking
            if model_id is not None:
                routing_strategy = "explicit"
            else:
                # Check if smart routing found a model
                smart_result = await self.smart_routing.find_best_model(
                    self.service_id,
                    self.current_task_params
                )
                routing_strategy = "smart" if smart_result else "default"
            
            self.logger.info(
                f"Selected model: {selected_model} (strategy: {routing_strategy})"
            )
            
            # Stage 3: Preprocess input
            preprocessed = await self.preProcess(request_data.get("data", {}))
            self.logger.debug(f"Preprocessed data: {preprocessed}")
            
            # Stage 4: Execute on Triton with selected model
            triton_output = await self.triton_client.execute(
                model_name=selected_model,
                input_data=preprocessed
            )
            
            self.logger.info(
                f"Triton inference completed. Latency: {triton_output.get('latency_ms')}ms"
            )
            
            # Stage 5: Postprocess output
            output = await self.postProcess(triton_output)
            
            # Stage 6: Add model metadata
            result = {
                "data": output,
                "model_info": {
                    "model_used": selected_model,
                    "requested_model": requested_model,
                    "routing_strategy": routing_strategy,
                    "triton_latency_ms": triton_output.get("latency_ms", 0)
                }
            }
            
            self.logger.info(f"Inference completed successfully for {self.service_id}")
            return result
            
        except Exception as e:
            self.logger.error(f"Inference failed for {self.service_id}: {str(e)}")
            raise
```

### 5.2 SmartRoutingModel (Singleton)

```python
import asyncio
from typing import Dict, Any, Optional
from dataclasses import dataclass
from datetime import datetime
import logging
import threading

@dataclass
class ModelMetrics:
    """Model performance metrics for scoring."""
    availability_pct: float  # 0-100
    avg_latency_ms: float    # milliseconds
    accuracy_score: float    # 0-100
    domain: str              # e.g., "transliteration", "ner", "asr"
    language_pair: Optional[str] = None
    last_updated: Optional[datetime] = None

class SmartRoutingModel:
    """
    Intelligent model selection singleton using weighted scoring.
    
    Selects the best model based on:
    1. Task parameters (latency_budget_ms, accuracy_threshold, etc.)
    2. Model availability and health metrics
    3. Weighted scoring algorithm (Availability: 50%, Latency: 30%, Accuracy: 20%)
    
    Fallback: Returns None if no model meets constraints
    (Service will then use default model)
    """
    
    _instance = None
    _lock = threading.Lock()
    
    def __new__(cls):
        if cls._instance is None:
            with cls._lock:
                if cls._instance is None:
                    cls._instance = super().__new__(cls)
                    cls._instance._initialize()
        return cls._instance
    
    def _initialize(self):
        """Initialize metrics storage and logger."""
        self.logger = logging.getLogger(__name__)
        self.model_metrics: Dict[str, ModelMetrics] = {}
        self._load_model_metrics()
    
    def _load_model_metrics(self):
        """Load model metrics from config or metrics service."""
        # Load from configuration/database
        # Example metrics (per service):
        self.model_metrics = {
            # Transliteration models
            "transliteration-v1": ModelMetrics(
                availability_pct=99.5,
                avg_latency_ms=25,
                accuracy_score=92.0,
                domain="transliteration"
            ),
            "transliteration-v2-fast": ModelMetrics(
                availability_pct=99.8,
                avg_latency_ms=12,
                accuracy_score=89.5,
                domain="transliteration"
            ),
            "transliteration-v2-accurate": ModelMetrics(
                availability_pct=98.9,
                avg_latency_ms=45,
                accuracy_score=95.2,
                domain="transliteration"
            ),
            # NER models
            "ner-v1": ModelMetrics(
                availability_pct=99.2,
                avg_latency_ms=35,
                accuracy_score=91.5,
                domain="ner"
            ),
            # NMT models
            "nmt-en-hi": ModelMetrics(
                availability_pct=98.5,
                avg_latency_ms=50,
                accuracy_score=88.0,
                domain="nmt"
            ),
        }
    
    async def find_best_model(
        self,
        service_id: str,
        task_params: Dict[str, Any]
    ) -> Optional[str]:
        """
        Find best model for given service and task constraints.
        
        Scoring Algorithm:
        ─────────────────
        For each available model:
            1. Check hard constraints:
               - latency_budget_ms: model.avg_latency_ms <= budget
               - accuracy_threshold: model.accuracy_score >= threshold
               - availability_pct >= 95% (minimum health threshold)
            
            2. If constraints satisfied:
               Calculate score = (
                   Availability(50%) * (availability_pct / 100)
                   + Latency(30%) * ((100 - latency_score) / 100)
                   + Accuracy(20%) * (accuracy_score / 100)
               )
        
        3. Return model with highest score
        
        Args:
            service_id: Service ID (e.g., 'transliteration', 'ner')
            task_params: Task constraints:
                - latency_budget_ms: max acceptable latency (optional)
                - accuracy_threshold: min acceptable accuracy (optional)
        
        Returns:
            Best model name satisfying constraints, or None
        """
        candidate_models = self._get_candidate_models(service_id)
        
        if not candidate_models:
            self.logger.warning(f"No candidate models for service: {service_id}")
            return None
        
        # Extract constraints
        latency_budget_ms = task_params.get("latency_budget_ms")
        accuracy_threshold = task_params.get("accuracy_threshold", 0)
        min_availability = 95.0
        
        # Score models
        scored_models = []
        for model_name in candidate_models:
            metrics = self.model_metrics.get(model_name)
            if not metrics:
                continue
            
            # Check hard constraints
            if metrics.availability_pct < min_availability:
                self.logger.debug(
                    f"Model {model_name} below availability threshold"
                )
                continue
            
            if latency_budget_ms and metrics.avg_latency_ms > latency_budget_ms:
                self.logger.debug(
                    f"Model {model_name} exceeds latency budget"
                )
                continue
            
            if metrics.accuracy_score < accuracy_threshold:
                self.logger.debug(
                    f"Model {model_name} below accuracy threshold"
                )
                continue
            
            # Calculate weighted score
            score = self._calculate_score(metrics)
            scored_models.append((model_name, score))
        
        if not scored_models:
            self.logger.info(
                f"No models satisfy constraints for {service_id}"
            )
            return None
        
        best_model = sorted(scored_models, key=lambda x: x[1], reverse=True)[0][0]
        self.logger.info(f"Selected model '{best_model}' for {service_id}")
        return best_model
    
    def _calculate_score(self, metrics: ModelMetrics) -> float:
        """
        Calculate weighted score for model.
        
        Weights:
        - Availability: 50% (reliability is paramount)
        - Latency: 30% (performance matters)
        - Accuracy: 20% (quality matters but constrained by task params)
        """
        latency_score = max(0, 100 - metrics.avg_latency_ms)
        
        final_score = (
            0.50 * (metrics.availability_pct / 100)
            + 0.30 * (latency_score / 100)
            + 0.20 * (metrics.accuracy_score / 100)
        )
        
        return final_score
    
    def _get_candidate_models(self, service_id: str) -> list:
        """Get list of models available for service."""
        return [
            model for model, metrics in self.model_metrics.items()
            if metrics.domain == service_id
        ]
    
    def get_default_model(self, service_id: str) -> str:
        """Get default/fallback model for service."""
        candidates = self._get_candidate_models(service_id)
        if not candidates:
            raise ValueError(f"No models configured for service: {service_id}")
        
        sorted_models = sorted(
            candidates,
            key=lambda m: self.model_metrics[m].availability_pct,
            reverse=True
        )
        return sorted_models[0]
    
    async def update_metrics(self, model_name: str, metrics: ModelMetrics):
        """Update metrics for model (called by monitoring service)."""
        self.model_metrics[model_name] = metrics
        self.logger.debug(f"Updated metrics for model: {model_name}")
```

### 5.3 TritonClient (Singleton)

```python
from typing import Dict, Any
import logging
import threading
import os

class TritonClient:
    """
    Singleton Triton inference client.
    Maintains persistent connection to Triton server.
    Shared across all services.
    """
    
    _instance = None
    _lock = threading.Lock()
    
    def __new__(cls):
        if cls._instance is None:
            with cls._lock:
                if cls._instance is None:
                    cls._instance = super().__new__(cls)
                    cls._instance._initialize()
        return cls._instance
    
    def _initialize(self):
        """Initialize Triton connection on first instantiation."""
        self.triton_url = os.getenv("TRITON_URL", "localhost:8000")
        self.triton_timeout = int(os.getenv("TRITON_TIMEOUT", "30"))
        # Initialize gRPC or HTTP client
        # self.client = grpcclient.InferenceServerClient(self.triton_url)
        self.logger = logging.getLogger(__name__)
        self.logger.info(f"TritonClient initialized with URL: {self.triton_url}")
    
    async def execute(
        self,
        model_name: str,
        input_data: Dict[str, Any],
        timeout: float = None
    ) -> Dict[str, Any]:
        """
        Execute inference on Triton server.
        
        Args:
            model_name: Name of model deployed on Triton
            input_data: Preprocessed input data (service-specific format)
            timeout: Request timeout in seconds (defaults to TRITON_TIMEOUT)
            
        Returns:
            Dictionary with Triton response including:
            - output: Model output data
            - latency_ms: Inference latency
            
        Raises:
            TimeoutError: If request exceeds timeout
            ConnectionError: If cannot connect to Triton
            RuntimeError: If Triton inference fails
        """
        if timeout is None:
            timeout = self.triton_timeout
        
        try:
            self.logger.info(
                f"Executing Triton inference for model: {model_name}"
            )
            
            # Build Triton input tensors from input_data
            # Call Triton server
            # Parse response and measure latency
            # Return output
            
            # TODO: Implement actual Triton client call
            pass
            
        except Exception as e:
            self.logger.error(f"Triton execution failed: {str(e)}")
            raise
```

---

## 6. Implementation Example: Transliteration Service

```python
# services/transliteration-service/app/services/transliteration_service.py
from app.core.base_service import InferenceService
from app.core.triton_client import TritonClient
from typing import Any, Dict, Optional
import logging

class TransliterationService(InferenceService):
    """
    Transliteration service implementation with smart model routing.
    
    Demonstrates full integration of getModel() with SmartRoutingModel
    for intelligent model selection and direct endpoint routing.
    
    Endpoint: POST /api/v1/transliteration/inference
    """
    
    def __init__(self):
        super().__init__(
            service_id="transliteration",
            default_model="transliteration-v2-fast"
        )
        self.supported_languages = ["en", "hi", "ta", "te", "kn", "ml", "bn", "gu"]
        self.supported_models = [
            "transliteration-v1",
            "transliteration-v2-fast",
            "transliteration-v2-accurate"
        ]
        self.logger = logging.getLogger(__name__)
    
    def _is_valid_model(self, model_id: str) -> bool:
        """Validate model exists in supported list."""
        return model_id in self.supported_models
    
    def _get_supported_models(self) -> list:
        """Return models available for this service."""
        return self.supported_models
    
    def _extract_task_params(self) -> Dict[str, Any]:
        """
        Extract task parameters for smart routing decision.
        
        Example params:
        - latency_budget_ms: real-time inference needs fast response
        - accuracy_threshold: batch processing needs accurate results
        """
        params = self.current_task_params.copy()
        
        # Provide service defaults if not specified
        if "latency_budget_ms" not in params:
            params["latency_budget_ms"] = 50
        
        if "accuracy_threshold" not in params:
            params["accuracy_threshold"] = 85.0
        
        return params
    
    async def preProcess(self, input_data: Any) -> Dict[str, Any]:
        """
        Convert raw input to Triton format.
        
        Input format:
        {
            "text": "namaste",
            "source_language": "hi",
            "target_language": "en"
        }
        """
        text = input_data.get("text", "")
        source_lang = input_data.get("source_language", "en")
        target_lang = input_data.get("target_language", "hi")
        
        if not text:
            raise ValueError("Text input is required")
        
        if source_lang not in self.supported_languages:
            raise ValueError(f"Unsupported source language: {source_lang}")
        
        if target_lang not in self.supported_languages:
            raise ValueError(f"Unsupported target language: {target_lang}")
        
        self.logger.debug(
            f"Preprocessed: '{text}' ({source_lang} → {target_lang})"
        )
        
        return {
            "input_text": text,
            "source_language": source_lang,
            "target_language": target_lang,
        }
    
    async def postProcess(self, triton_output: Dict[str, Any]) -> Dict[str, Any]:
        """
        Format Triton output to service response format.
        
        Triton output format:
        {
            "output": "nmst",
            "scores": [0.95, 0.89],
            "latency_ms": 12
        }
        
        Service response format:
        {
            "transliterated_text": "nmst",
            "confidence_scores": [0.95, 0.89]
        }
        """
        output = {
            "transliterated_text": triton_output.get("output", ""),
            "confidence_scores": triton_output.get("scores", [])
        }
        
        self.logger.debug(f"Postprocessed output: {output}")
        return output
```

### 6.1 Service FastAPI Endpoint

```python
# services/transliteration-service/app/routes/inference.py
from fastapi import APIRouter, Depends, HTTPException
from app.services.transliteration_service import TransliterationService
from app.schemas.inference import InferenceRequest, InferenceResponse
from app.dependencies.auth import get_current_user
from app.dependencies.tenant import get_tenant_id
import logging

router = APIRouter(prefix="/inference", tags=["inference"])
logger = logging.getLogger(__name__)

# Service instance (can also be initialized globally)
transliteration_service = TransliterationService()

@router.post(
    "",
    response_model=InferenceResponse,
    summary="Transliteration Inference",
    description="Execute transliteration inference with smart model selection"
)
async def run_inference(
    request: InferenceRequest
) -> InferenceResponse:
    """
    Transliteration inference endpoint with smart model selection.
    
    This endpoint:
    1. Validates request format
    2. Calls TransliterationService.processData()
    3. Service performs 3-level model selection:
       - Level 1: Use explicit model_id if provided
       - Level 2: Call SmartRoutingModel if model_id is None
       - Level 3: Use default model if SmartRouting returns None
    4. Returns response with model tracking metadata
    
    Query Parameters:
    - model_id (optional): Explicit model name
      Example: ?model_id=transliteration-v2-accurate
    
    Request Body:
    {
        "data": {
            "text": "namaste",
            "source_language": "hi",
            "target_language": "en"
        },
        "model_id": null,  # Optional explicit model
        "config": {
            "task_params": {
                "latency_budget_ms": 50,
                "accuracy_threshold": 0.85
            }
        }
    }
    
    Response Body:
    {
        "data": {
            "transliterated_text": "nmst",
            "confidence_scores": [0.95]
        },
        "model_info": {
            "model_used": "transliteration-v2-fast",
            "requested_model": null,
            "routing_strategy": "smart",
            "triton_latency_ms": 12
        },
        "user_id": "user123",
        "tenant_id": "tenant456",
        "timestamp": "2026-04-30T10:30:45Z"
    }
    """
    try:
        logger.info(
            f"Transliteration inference request with model_id={request.model_id}"
        )
        
        # Call service's processData() method (inherited from base class)
        # This orchestrates the full pipeline with smart model selection
        result = await transliteration_service.processData(request.dict())
        
        # Create response
        response = InferenceResponse(**result)
        
        logger.info(
            f"Transliteration inference completed. "
            f"Model used: {result['model_info']['model_used']}, "
            f"Latency: {result['model_info']['triton_latency_ms']}ms"
        )
        
        return response
        
    except ValueError as e:
        logger.error(f"Validation error: {str(e)}")
        raise HTTPException(status_code=400, detail=str(e))
    
    except Exception as e:
        logger.error(f"Inference failed: {str(e)}", exc_info=True)
        raise HTTPException(status_code=500, detail="Inference failed")
```

---

## 7. Request/Response Schemas

```python
# app/schemas/inference.py
from pydantic import BaseModel, Field
from typing import Any, Dict, Optional
from datetime import datetime

class TaskParams(BaseModel):
    """Task parameters for smart routing decision."""
    latency_budget_ms: Optional[int] = Field(
        None,
        description="Maximum acceptable latency in milliseconds"
    )
    accuracy_threshold: Optional[float] = Field(
        None,
        description="Minimum acceptable accuracy (0-100)"
    )
    language_pair: Optional[str] = Field(
        None,
        description="Language pair specification"
    )

class InferenceConfig(BaseModel):
    """Inference configuration."""
    task_params: Optional[Dict[str, Any]] = Field(
        default_factory=dict,
        description="Task parameters for smart routing"
    )
    timeout: float = Field(
        30.0,
        description="Request timeout in seconds"
    )

class InferenceRequest(BaseModel):
    """Service-level inference request with model selection."""
    data: Dict[str, Any] = Field(
        ...,
        description="Service-specific input data"
    )
    model_id: Optional[str] = Field(
        None,
        description="Optional explicit model. If None, SmartRouting decides."
    )
    config: Optional[InferenceConfig] = Field(
        default_factory=InferenceConfig,
        description="Configuration including task parameters"
    )

class ModelInfo(BaseModel):
    """Model selection tracking information."""
    model_used: str = Field(
        ...,
        description="Actual model used for inference"
    )
    requested_model: Optional[str] = Field(
        None,
        description="Model requested by user (if explicit)"
    )
    routing_strategy: str = Field(
        ...,
        description="Strategy used: explicit, smart, or default"
    )
    triton_latency_ms: int = Field(
        ...,
        description="Latency of Triton inference in milliseconds"
    )

class InferenceResponse(BaseModel):
    """Service-level inference response with model tracking."""
    data: Dict[str, Any] = Field(
        ...,
        description="Service-specific inference output"
    )
    model_info: ModelInfo = Field(
        ...,
        description="Model selection and execution tracking"
    )
    timestamp: str = Field(
        default_factory=lambda: datetime.utcnow().isoformat(),
        description="Response timestamp"
    )

# Example Request:
# {
#     "data": {
#         "text": "namaste",
#         "source_language": "hi",
#         "target_language": "en"
#     },
#     "model_id": null,
#     "config": {
#         "task_params": {
#             "latency_budget_ms": 50,
#             "accuracy_threshold": 85.0
#         }
#     }
# }

# Example Response:
# {
#     "data": {
#         "transliterated_text": "nmst",
#         "confidence_scores": [0.95]
#     },
#     "model_info": {
#         "model_used": "transliteration-v2-fast",
#         "requested_model": null,
#         "routing_strategy": "smart",
#         "triton_latency_ms": 12
#     },
#     "timestamp": "2026-04-30T10:30:45.123456"
# }
```

---

## 8. Core Module Structure

```
services/transliteration-service/app/
├── main.py                              # FastAPI app initialization
├── core/
│   ├── base_service.py                  # InferenceService interface (SHARED)
│   ├── triton_client.py                 # TritonClient singleton (SHARED)
│   └── smart_routing.py                 # SmartRoutingModel singleton (SHARED)
├── services/
│   └── transliteration_service.py       # TransliterationService implementation
├── routes/
│   └── inference.py                     # FastAPI /inference endpoint
├── schemas/
│   └── inference.py                     # Request/Response schemas
└── dependencies/
    ├── auth.py                          # Authentication dependency
    └── tenant.py                        # Tenant dependency

# Same structure for all other services:
# services/nmt-service/app/
# services/ner-service/app/
# services/asr-service/app/
# etc.

# SHARED CORE LIBRARIES (optional, can be in libs/)
libs/
└── ai4icore_inference/
    ├── base_service.py                  # InferenceService interface
    ├── triton_client.py                 # TritonClient singleton
    ├── smart_routing.py                 # SmartRoutingModel singleton
    └── schemas.py                       # Common schemas
```

---

## 9. Testing Strategy

### 9.1 Unit Tests

```python
# services/transliteration-service/tests/unit/test_transliteration_service.py
import pytest
from app.services.transliteration_service import TransliterationService
from app.core.triton_client import TritonClient
from app.core.smart_routing import SmartRoutingModel
from unittest.mock import AsyncMock, patch, MagicMock

@pytest.fixture
def service():
    return TransliterationService()

@pytest.mark.asyncio
async def test_preprocess_valid_input(service):
    """Test preprocessing with valid input."""
    input_data = {
        "text": "namaste",
        "source_language": "hi",
        "target_language": "en"
    }
    result = await service.preProcess(input_data)
    
    assert result["input_text"] == "namaste"
    assert result["source_language"] == "hi"
    assert result["target_language"] == "en"

@pytest.mark.asyncio
async def test_preprocess_invalid_language(service):
    """Test preprocessing with unsupported language."""
    input_data = {
        "text": "test",
        "source_language": "xyz",
        "target_language": "en"
    }
    
    with pytest.raises(ValueError, match="Unsupported source language"):
        await service.preProcess(input_data)

@pytest.mark.asyncio
async def test_postprocess(service):
    """Test postprocessing Triton output."""
    triton_output = {
        "output": "nmst",
        "scores": [0.95, 0.89],
        "latency_ms": 12
    }
    result = await service.postProcess(triton_output)
    
    assert result["transliterated_text"] == "nmst"
    assert result["confidence_scores"] == [0.95, 0.89]

@pytest.mark.asyncio
async def test_get_model_explicit(service):
    """Test model selection with explicit model_id."""
    model = await service.getModel("transliteration-v2-accurate")
    assert model == "transliteration-v2-accurate"

@pytest.mark.asyncio
async def test_get_model_invalid(service):
    """Test model selection with invalid model_id."""
    with pytest.raises(ValueError, match="not supported"):
        await service.getModel("invalid-model")

@pytest.mark.asyncio
async def test_get_model_smart_routing(service):
    """Test model selection with smart routing."""
    with patch.object(
        service.smart_routing,
        'find_best_model',
        new_callable=AsyncMock
    ) as mock_smart:
        mock_smart.return_value = "transliteration-v2-fast"
        
        model = await service.getModel(None)
        assert model == "transliteration-v2-fast"
        mock_smart.assert_called_once()

@pytest.mark.asyncio
async def test_get_model_default_fallback(service):
    """Test model selection with default fallback."""
    with patch.object(
        service.smart_routing,
        'find_best_model',
        new_callable=AsyncMock
    ) as mock_smart:
        mock_smart.return_value = None
        
        model = await service.getModel(None)
        assert model == "transliteration-v2-fast"  # default_model

@pytest.mark.asyncio
async def test_processdata_full_pipeline(service):
    """Test full inference pipeline."""
    request_data = {
        "data": {
            "text": "namaste",
            "source_language": "hi",
            "target_language": "en"
        },
        "model_id": None,
        "config": {
            "task_params": {
                "latency_budget_ms": 50,
                "accuracy_threshold": 85.0
            }
        }
    }
    
    with patch.object(
        service.triton_client,
        'execute',
        new_callable=AsyncMock
    ) as mock_triton:
        mock_triton.return_value = {
            "output": "nmst",
            "scores": [0.95],
            "latency_ms": 12
        }
        
        result = await service.processData(request_data)
        
        assert "data" in result
        assert "model_info" in result
        assert result["data"]["transliterated_text"] == "nmst"
        assert result["model_info"]["model_used"] == "transliteration-v2-fast"
        mock_triton.assert_called_once()
```

### 9.2 Integration Tests

```python
# tests/integration/test_transliteration_endpoint.py
import pytest
from fastapi.testclient import TestClient
from app.main import app

@pytest.fixture
def client():
    return TestClient(app)

def test_inference_endpoint_success(client):
    """Test successful inference endpoint call."""
    response = client.post(
        "/api/v1/transliteration/inference",
        json={
            "data": {
                "text": "namaste",
                "source_language": "hi",
                "target_language": "en"
            },
            "model_id": None
        }
    )
    
    assert response.status_code == 200
    data = response.json()
    assert "data" in data
    assert "model_info" in data
    assert data["model_info"]["routing_strategy"] in ["explicit", "smart", "default"]

def test_inference_endpoint_validation_error(client):
    """Test inference endpoint with invalid input."""
    response = client.post(
        "/api/v1/transliteration/inference",
        json={"data": {}}
    )
    
    assert response.status_code == 400

def test_inference_endpoint_explicit_model(client):
    """Test inference endpoint with explicit model selection."""
    response = client.post(
        "/api/v1/transliteration/inference",
        json={
            "data": {"text": "namaste"},
            "model_id": "transliteration-v2-accurate"
        }
    )
    
    assert response.status_code == 200
    data = response.json()
    assert data["model_info"]["model_used"] == "transliteration-v2-accurate"
    assert data["model_info"]["routing_strategy"] == "explicit"
```

---

## 10. Deployment & Configuration

### 10.1 Environment Variables

```bash
# .env (per service)
TRITON_URL=localhost:8000
TRITON_TIMEOUT=30
SERVICE_NAME=transliteration
DEFAULT_MODEL=transliteration-v2-fast
LOG_LEVEL=INFO
```

### 10.2 Service Configuration

```yaml
# config/models.yaml
models:
  transliteration:
    default: "transliteration-v2-fast"
    available:
      - "transliteration-v1"
      - "transliteration-v2-fast"
      - "transliteration-v2-accurate"
  
  ner:
    default: "ner-v1"
    available:
      - "ner-v1"
  
  nmt:
    default: "nmt-en-hi"
    available:
      - "nmt-en-hi"
      - "nmt-hi-en"
```

---

## 11. Benefits Analysis

| Benefit | Current | Proposed |
|---------|---------|----------|
| **Code Reuse** | ~50% duplication | ~0% duplication |
| **Inference Endpoint Time** | 2-3 hours per service | 30 minutes per service |
| **Triton Connections** | N clients (one per service) | 1 singleton |
| **Model Selection Logic** | Scattered | Centralized in getModel() |
| **Testability** | Difficult | Easy (mocked interfaces) |
| **Maintenance** | High | Low |
| **Scaling** | Per-service | Shared singleton resources |
| **Smart Routing** | Manual per-service | Automatic via SmartRoutingModel |

---

## 12. Migration Plan

### Phase 1: Foundation (Week 1)
- [ ] Create shared core libraries (base_service, triton_client, smart_routing)
- [ ] Write unit tests for shared components
- [ ] Documentation for service developers

### Phase 2: Pilot Service (Week 2)
- [ ] Migrate Transliteration service
- [ ] Integration tests
- [ ] Load testing with smart routing
- [ ] Documentation

### Phase 3: Rollout (Weeks 3-4)
- [ ] Migrate NMT service
- [ ] Migrate NER service
- [ ] Migrate remaining services
- [ ] Monitor performance

### Phase 4: Optimization (Week 5)
- [ ] Performance tuning
- [ ] Circuit breaker implementation
- [ ] Metrics & monitoring
- [ ] Service versioning strategy

---

## 13. Key Differences from Orchestrator Design

| Aspect | Orchestrator Design | Service-Level Design |
|--------|---------------------|----------------------|
| **Routing** | Orchestrator routes to ServiceFactory | Direct endpoint routing to service |
| **Request Flow** | Endpoint → Orchestrator → ServiceFactory → Service | Endpoint → Service |
| **Complexity** | More layers, more flexibility | Simpler, more direct |
| **Multi-service chaining** | Built into orchestrator | Per-service responsibility |
| **Configuration** | Orchestrator owns config | Each service owns config |
| **Shared Resources** | Orchestrator manages | Services access directly (singletons) |

---

## 14. Future Enhancements

1. **Result Caching**: Cache Triton responses for repeated inputs across all services
2. **Circuit Breaker Pattern**: Handle Triton server failures gracefully
3. **Service Versioning**: Support multiple versions of same service
4. **Custom Model Metrics**: Per-service custom scoring algorithms
5. **A/B Testing**: Route requests to different models for comparison
6. **Performance Monitoring**: Per-endpoint metrics and SLOs

---

## 15. Example Service Implementations

### NER Service Example

```python
# services/ner-service/app/services/ner_service.py
from app.core.base_service import InferenceService

class NERService(InferenceService):
    """Named Entity Recognition service implementation."""
    
    def __init__(self):
        super().__init__(
            service_id="ner",
            default_model="ner-v1"
        )
        self.supported_languages = ["en", "hi"]
        self.supported_models = ["ner-v1", "ner-multilingual"]
    
    async def preProcess(self, input_data: Any) -> Dict[str, Any]:
        text = input_data.get("text", "")
        language = input_data.get("language", "en")
        
        if not text:
            raise ValueError("Text input is required")
        
        return {
            "input_text": text,
            "language": language
        }
    
    async def postProcess(self, triton_output: Dict[str, Any]) -> Dict[str, Any]:
        return {
            "entities": triton_output.get("entities", []),
            "confidence_scores": triton_output.get("scores", [])
        }
```

---

## Appendix: Shared Libraries Implementation

```python
# libs/ai4icore_inference/__init__.py
from .base_service import InferenceService
from .triton_client import TritonClient
from .smart_routing import SmartRoutingModel
from .schemas import InferenceRequest, InferenceResponse

__all__ = [
    "InferenceService",
    "TritonClient",
    "SmartRoutingModel",
    "InferenceRequest",
    "InferenceResponse"
]
```

---

**Document prepared for architectural review and discussion.**  
**Last updated**: April 30, 2026
