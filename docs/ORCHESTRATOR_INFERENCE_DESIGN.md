# Multi-Service Inference Orchestrator Design

**Date**: April 29, 2026  
**Status**: Design Proposal  
**Target Services**: All micro-services with `/inference` endpoint calling Triton server  
**Design Patterns**: Factory Pattern + Strategy Pattern + Singleton Pattern

---

## 1. Executive Summary

This document proposes a unified, scalable architecture for handling inference requests across multiple micro-services. The design decouples service-specific logic from the orchestration layer, enabling:

- **Horizontal scalability**: Add new services without modifying orchestrator
- **Separation of concerns**: Each service handles its own preprocessing and postprocessing
- **Shared resources**: Singleton inference client across all services
- **Configuration-driven execution**: Chain multiple services dynamically
- **Testability**: Easy mocking and unit testing of individual components

---

## 2. Current Architecture Issues

### Problem Statement
Currently, each service implements its own `/inference` endpoint with redundant logic:
- Separate inference client initialization per service
- Duplicated request validation and error handling
- Service-specific processing scattered across multiple files
- No clear pattern for chaining multiple services
- Difficult to maintain consistency across services

### Example Current Issues
```python
# Transliteration service
async def run_inference(request_body, user_id, api_key_id, session_id):
    # Service-specific preprocessing
    # inference client initialization
    # Triton inference call
    # Service-specific postprocessing
    # Return response

# Same pattern repeated in NMT, NER, ASR, etc. services
```

---

## 3. Proposed Architecture

### 3.1 High-Level Design

```
┌─────────────────────────────────────────────────────────────┐
│                        API Gateway                          │
│                  /api/v1/{service}/inference                │
└────────────────────────┬────────────────────────────────────┘
                         │
                         ▼
┌─────────────────────────────────────────────────────────────┐
│              Inference Endpoint (FastAPI Router)            │
│              - Request Validation                           │
│              - Auth & Tenant Checks                         │
│              - Call Orchestrator                            │
└────────────────────────┬────────────────────────────────────┘
                         │
                         ▼
┌─────────────────────────────────────────────────────────────┐
│          Inference Orchestrator (Main Coordinator)          │
│  - Route request to inference factory                       │
│  - Manage service chaining (if configured)                  │
│  - Aggregate results                                        │
│  - Handle errors & logging                                  │
└────────────────────────┬────────────────────────────────────┘
                         │
                         ▼
┌─────────────────────────────────────────────────────────────┐
│          inference factory (Service Instantiation)          │
│  - Create/retrieve service instances                        │
│  - Maintain singleton services                              │
│  - Handle service registration                              │
└────────────────────────┬────────────────────────────────────┘
                         │
         ┌───────────────┼───────────────┐
         │               │               │
         ▼               ▼               ▼
    ┌─────────┐    ┌─────────┐    ┌─────────┐
    │  Trans. │    │   NMT   │    │   NER   │
    │ Service │    │ Service │    │ Service │
    └────┬────┘    └────┬────┘    └────┬────┘
         │               │               │
    (All implement InferenceService interface)
    - preProcess()
    - postProcess()
    - processData()
         │
         ▼
┌─────────────────────────────────────────────────────────────┐
│         inference client (Singleton - Shared Instance)      │
│  - Persistent connection to Triton server                   │
│  - execute(model_name, input_data) -> output                │
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
├── InferenceClient (Singleton)
│   └── execute(model_name, input_data) → Dict
│
├── ServiceFactory (Factory Pattern)
│   ├── get_service(service_id) → InferenceService
│   └── _services: Dict[str, InferenceService]
│
└── InferenceOrchestrator (Coordinator)
    └── execute(request, user_id, api_key_id, session_id) → Dict

Service Implementations
├── TransliterationServiceImpl(InferenceService)
├── NMTServiceImpl(InferenceService)
├── NERServiceImpl(InferenceService)
└── [Other services...]

Endpoints
└── FastAPI Router
    └── POST /inference → uses InferenceOrchestrator
```

---

## 4. Data Flow Diagrams

### 4.1 Single Service Execution Flow (with Smart Model Selection)

```
┌─────────────────────────────────────────────────┐
│   HTTP Request                                  │
│   {                                             │
│     service_id: "transliteration",              │
│     model_id: null  (or explicit model),        │
│     data: {...},                                │
│     config: { task_params: {...} }              │
│   }                                             │
└────────┬────────────────────────────────────────┘
         │
         ▼
┌─────────────────────────────────────────────────┐
│  FastAPI Endpoint (/inference)                  │
│  ✓ Request validation                           │
│  ✓ Auth check & Tenant check                    │
│  ✓ Extract user context                         │
└────────┬────────────────────────────────────────┘
         │
         ▼
┌─────────────────────────────────────────────────┐
│  InferenceOrchestrator.execute()                │
│  ✓ Extract service_id, model_id from request    │
│  ✓ Call ServiceFactory.get_service(service_id)  │
│  ✓ Pass model_id & task_params to service       │
└────────┬────────────────────────────────────────┘
         │
         ▼
┌──────────────────────────────────────────────────┐
│  ServiceFactory.get_service(service_id)         │
│  ✓ Look up singleton instance                   │
│  ✓ If not cached: create & cache                │
│  ✓ Return service instance                      │
└────────┬─────────────────────────────────────────┘
         │
         ▼
┌──────────────────────────────────────────────────┐
│ TransliterationServiceImpl.processData()         │
│ ✓ Extract: model_id, task_params from request   │
└────────┬─────────────────────────────────────────┘
         │
         ▼
┌──────────────────────────────────────────────────┐
│  getModel(model_id) - Smart Model Selection     │
│  ┌─────────────────────────────────────────┐    │
│  │ Decision Logic (3-level fallback):      │    │
│  │ 1. If model_id provided:                │    │
│  │    - Validate model                     │    │
│  │    - Return explicit model              │    │
│  │                                         │    │
│  │ 2. If model_id is None:                 │    │
│  │    - Use default model for service      │    │
│  └─────────────────────────────────────────┘    │
│  Output: selected_model_name                    │
└────────┬─────────────────────────────────────────┘
         │
         ▼
┌──────────────────────────────────────────────────┐
│  preProcess(input_data)                         │
│  ✓ Validate input                               │
│  ✓ Convert to Triton format                     │
│  Output: {input_text, language, ...}            │
└────────┬─────────────────────────────────────────┘
         │
         ▼
┌──────────────────────────────────────────────────┐
│  InferenceClient.execute()                      │
│  ✓ Model: selected_model_name                   │
│  ✓ Input: preprocessed data                     │
│  ✓ Call Triton Server                           │
└────────┬─────────────────────────────────────────┘
         │
         ▼
┌──────────────────────────────────────────────────┐
│  Triton Response                                │
│  {                                              │
│    "output": "nmst",                            │
│    "scores": [0.95, 0.89],                      │
│    "latency_ms": 12                             │
│  }                                              │
└────────┬─────────────────────────────────────────┘
         │
         ▼
┌──────────────────────────────────────────────────┐
│  postProcess(triton_output)                     │
│  ✓ Format output for response                   │
│  Output: {transliterated_text, confidence, ...} │
└────────┬─────────────────────────────────────────┘
         │
         ▼
┌──────────────────────────────────────────────────┐
│  Include Model Metadata in Response             │
│  {                                              │
│    "output": {...},                             │
│    "model_used": "transliteration-v2-fast",     │
│    "requested_model": null,                     │
│    "routing_strategy": "smart"                  │
│  }                                              │
└────────┬─────────────────────────────────────────┘
         │
         ▼
┌──────────────────────────────────────────────────┐
│  HTTP Response (200 OK)                         │
│  {                                              │
│    "results": {                                 │
│      "transliteration": {                       │
│        "transliterated_text": "nmst",           │
│        "model_used": "v2-fast",                 │
│        "routing_strategy": "smart"              │
│      }                                          │
│    },                                           │
│    "user_id": "user123",                        │
│    "session_id": "sess456"                      │
│  }                                              │
└──────────────────────────────────────────────────┘
```

### 4.2 Multi-Service Chaining Flow

```
┌──────────────────────────────────────────┐
│   HTTP Request (Multi-Service Config)    │
│   {                                      │
│     data: {...},                         │
│     config: {                            │
│       services: [                        │
│         "transliteration",               │
│         "language-detection",            │
│         "ner"                            │
│       ]                                  │
│     }                                    │
│   }                                      │
└────────┬─────────────────────────────────┘
         │
         ▼
┌────────────────────────────────────────────┐
│   InferenceOrchestrator.execute()          │
│   ✓ Parse config.services list             │
│   ✓ Initialize results dictionary          │
└────────┬───────────────────────────────────┘
         │
    ┌────┴────┬──────────┬──────────┐
    │ Service │ Service  │ Service  │
    │    1    │    2     │    3     │
    │ "xlit"  │ "langdet"│  "ner"   │
    ▼         ▼          ▼
┌──────────────────────────────────────────┐
│  For each service in config.services:    │
│  1. Get service instance from factory    │
│  2. Call service.processData()           │
│  3. Store result in results dict         │
│  4. Handle exceptions (log & continue)   │
└────────┬───────────────────────────────────┘
         │
         ▼
┌────────────────────────────────────────────┐
│  Aggregated Results                        │
│  {                                         │
│    "results": {                            │
│      "transliteration": {...},             │
│      "language_detection": {...},          │
│      "ner": {...}                          │
│    },                                      │
│    "user_id": "user123",                   │
│    "session_id": "sess456"                 │
│  }                                         │
└────────┬───────────────────────────────────┘
         │
         ▼
┌────────────────────────────────────────────┐
│  HTTP Response (200 OK)                    │
└────────────────────────────────────────────┘
```

---

## 5. Component Specifications

### 5.1 InferenceService Interface

```python
from abc import ABC, abstractmethod
from typing import Any, Dict, Optional

class InferenceService(ABC):
    """
    Abstract base class for all inference services.
    All services MUST implement these methods to handle inference.
    """
    
    def __init__(self, service_id: str, default_model: str):
        """
        Initialize the service with its ID and default model.
        
        Args:
            service_id: Unique identifier (e.g., 'transliteration', 'ner', 'asr')
            default_model: Fallback model name if inference fails
        """
        self.service_id = service_id
        self.default_model = default_model
        self.inference_client = InferenceClient()  # Singleton instance
    
    async def getModel(self, model_id: Optional[str] = None) -> str:
        """
        Get model for inference.
        
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
        │ LEVEL 2: DEFAULT FALLBACK                       │
        │ ─────────────────────────────────────────────   │
        │ If model_id is None:                            │
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
        
        # Level 2: Default fallback
        return self.default_model
    
    def _is_valid_model(self, model_id: str) -> bool:
        """Check if model is supported by this service."""
        return model_id in self._get_supported_models()
    
    def _get_supported_models(self) -> list:
        """Return list of supported models for this service."""
        # Override in subclass
        return [self.default_model]
    
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
            
        Example:
            Input:  {"text": "namaste", "language": "hi"}
            Output: {"input_text": "namaste", "language": "hi"}
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
            
        Example:
            Input:  {"output": "nmst", "scores": [0.95]}
            Output: {"transliterated_text": "nmst", "confidence": 0.95}
        """
        pass
    
    async def processData(self, request_data: Any) -> Dict[str, Any]:
        """
        Orchestrate full inference pipeline.
        
        Pipeline Stages:
        1. Extract model_id from request
        2. Call getModel() to select model
        3. Preprocess the input data
        4. Execute inference on Triton with selected model
        5. Postprocess the Triton output
        6. Add model metadata to response
        
        Args:
            request_data: Full request payload with:
                - data: actual input data
                - model_id: optional explicit model selection
            
        Returns:
            Dictionary with inference results and model tracking metadata
            
        Example:
            Input Request:
            {
                "data": {"text": "namaste", "language": "hi"},
                "model_id": null
            }
            
            Output Response:
            {
                "output": {
                    "transliterated_text": "nmst",
                    "confidence": 0.95
                },
                "model_used": "transliteration-v2-fast",
                "requested_model": null,
                "triton_latency_ms": 12
            }
        """
        # Stage 1: Extract model_id from request
        model_id = request_data.get("model_id")
        requested_model = model_id  # Store original request for response
        
        # Stage 2: Get model to use
        selected_model = await self.getModel(model_id)
        
        # Stage 3: Preprocess input
        preprocessed = await self.preProcess(request_data.get("data", {}))
        
        # Stage 4: Execute on Triton with selected model
        triton_output = await self.inference_client.execute(
            model_name=selected_model,
            input_data=preprocessed
        )
        
        # Stage 5: Postprocess output
        output = await self.postProcess(triton_output)
        
        # Stage 6: Add model metadata
        return {
            "output": output,
            "model_used": selected_model,
            "requested_model": requested_model,
            "triton_latency_ms": triton_output.get("latency_ms", 0)
        }
```

### 5.2 InferenceClient (Singleton)

```python
from typing import Dict, Any
from concurrent.futures import ThreadPoolExecutor

class InferenceClient:
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
        self.grpc_client = grpcclient.InferenceServerClient(self.triton_url)
        self.logger = logging.getLogger(__name__)
    
    async def execute(
        self, 
        model_name: str, 
        input_data: Dict[str, Any],
        timeout: float = 30.0
    ) -> Dict[str, Any]:
        """
        Execute inference on Triton server.
        
        Args:
            model_name: Name of model deployed on Triton
            input_data: Preprocessed input data
            timeout: Request timeout in seconds
            
        Returns:
            Triton server response
            
        Raises:
            TimeoutError: If request exceeds timeout
            ConnectionError: If cannot connect to Triton
            RuntimeError: If Triton inference fails
        """
        try:
            # Build Triton input tensors from input_data
            # Call Triton server
            # Parse response
            # Return output
            pass
        except Exception as e:
            self.logger.error(f"Triton execution failed: {str(e)}")
            raise
```

### 5.3 ServiceFactory

```python
from typing import Dict
from app.services.base_service import InferenceService

class ServiceFactory:
    """
    Factory pattern implementation for creating service instances.
    Maintains singleton instances per service type.
    Registry-based for extensibility.
    """
    
    _services: Dict[str, InferenceService] = {}
    _registry: Dict[str, type] = {}
    
    @classmethod
    def register(cls, service_id: str, service_class: type):
        """
        Register a service class.
        
        Args:
            service_id: Unique identifier for service
            service_class: Class implementing InferenceService
            
        Example:
            ServiceFactory.register("transliteration", TransliterationServiceImpl)
        """
        cls._registry[service_id] = service_class
    
    @classmethod
    def get_service(cls, service_id: str) -> InferenceService:
        """
        Get or create service instance (singleton per service type).
        
        Args:
            service_id: Service identifier
            
        Returns:
            Service instance
            
        Raises:
            ValueError: If service not registered
        """
        if service_id not in cls._services:
            if service_id not in cls._registry:
                raise ValueError(f"Service '{service_id}' not registered")
            
            service_class = cls._registry[service_id]
            cls._services[service_id] = service_class()
        
        return cls._services[service_id]
    
    @classmethod
    def clear_cache(cls):
        """Clear singleton instances (for testing)."""
        cls._services.clear()
```

### 5.4 InferenceOrchestrator

```python
from typing import List, Dict, Any
from app.factory.service_factory import ServiceFactory

class InferenceOrchestrator:
    """
    Main coordinator for inference requests.
    Routes requests to appropriate services.
    Handles service chaining and result aggregation.
    """
    
    def __init__(self):
        self.logger = logging.getLogger(__name__)
    
    async def execute(
        self, 
        request: InferenceRequest,
    ) -> Dict[str, Any]:
        """
        Execute inference orchestration.
        
        Args:
            request: Full inference request
            
        Returns:
            Aggregated results from all services
            
        Process:
            1. Extract service list from request.config
            2. For each service:
               a. Get service instance from factory
               b. Call service.processData()
               c. Catch and log exceptions
               d. Store result
            3. Return aggregated results
        """
        results = {}
        services_config = request.config.get("services", [])
        
        if not services_config:
            services_config = [request.service_id]  # Default single service
        
        for service_id in services_config:
            try:
                service = ServiceFactory.get_service(service_id)
                self.logger.info(f"Executing service: {service_id}")
                
                result = await service.processData(request.data)
                results[service_id] = result
                
                self.logger.info(f"Service {service_id} completed successfully")
                
            except Exception as e:
                self.logger.error(f"Service {service_id} failed: {str(e)}")
                results[service_id] = {
                    "error": str(e),
                    "status": "failed"
                }
        
        return {
            "results": results,
            "timestamp": datetime.utcnow().isoformat(),
        }
```

---

## 6. Implementation Example: Transliteration Service

```python
# app/services/transliteration_service_impl.py
from app.services.base_service import InferenceService
from app.services.inference_client import InferenceClient

class TransliterationServiceImpl(InferenceService):
    """
    Transliteration service implementation.
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
    
    def _is_valid_model(self, model_id: str) -> bool:
        """Validate model exists in supported list."""
        return model_id in self.supported_models
    
    def _get_supported_models(self) -> list:
        """Return models available for this service."""
        return self.supported_models
    
    async def preProcess(self, input_data: Any) -> Dict[str, Any]:
        """Convert to Triton format."""
        text = input_data.get("text", "")
        source_lang = input_data.get("source_language", "en")
        target_lang = input_data.get("target_language", "hi")
        
        if not text:
            raise ValueError("Text input is required")
        
        if source_lang not in self.supported_languages:
            raise ValueError(f"Unsupported language: {source_lang}")
        
        return {
            "input_text": text,
            "source_language": source_lang,
            "target_language": target_lang,
        }
    
    async def postProcess(self, triton_output: Dict[str, Any]) -> Dict[str, Any]:
        """Format Triton output."""
        return {
            "transliterated_text": triton_output.get("output", ""),
            "confidence_scores": triton_output.get("scores", []),
            "latency_ms": triton_output.get("latency_ms"),
        }
    
    # Note: processData() is inherited from InferenceService base class
    # It implements the full pipeline with smart model selection:
    # 1. Extract model_id and task_params
    # 2. Call getModel(model_id) → 3-level fallback
    # 3. Preprocess input
    # 4. Execute on Triton with selected model
    # 5. Postprocess output
    # 6. Return with model metadata (model_used, routing_strategy, etc.)
```
```

---

## 7. API Integration

### 7.1 Updated FastAPI Endpoint (with Smart Model Selection)

```python
# app/routes/inference.py
from app.orchestrator.inference_orchestrator import InferenceOrchestrator
from fastapi import APIRouter, Request
from typing import Optional

orchestrator = InferenceOrchestrator()
router = APIRouter()

@router.post("/inference", response_model=InferenceResponse)
async def run_inference(
    request_body: InferenceRequest,
) -> InferenceResponse:
    """
    Universal inference endpoint with smart model selection.
    
    Note: Authentication and authorization checks are handled at APISIX level.
    
    Flow:
    1. Endpoint receives request with optional model_id
    2. Passes to InferenceOrchestrator.execute()
    3. Orchestrator routes to ServiceFactory.get_service(service_id)
    4. Service.processData() called with model_id
    5. Service.getModel(model_id) performs fallback:
       - Level 1: Use explicit model_id if provided
       - Level 2: Use default model if not provided
    6. Triton inference executed with selected model
    7. Response includes model tracking metadata
    
    Query Parameters:
    - model_id (optional): Explicit model name
      Example: ?model_id=transliteration-v2-accurate
    
    Request Body:
    {
        "service_id": "transliteration",
        "data": {
            "text": "namaste",
            "source_language": "hi",
            "target_language": "en"
        },
        "model_id": null
    }
    
    Response Body:
    {
        "results": {
            "transliteration": {
                "transliterated_text": "nmst",
                "model_used": "transliteration-v2-fast",
                "requested_model": null,
                "triton_latency_ms": 12
            }
        },
        "timestamp": "2026-04-30T10:30:45Z"
    }
    """
    result = await orchestrator.execute(request_body)
    
    return InferenceResponse(**result)
```

### 7.2 Request/Response Schemas (with Model Tracking)

```python
# app/schemas/inference.py
from pydantic import BaseModel, Field
from typing import Any, Dict, Optional, List
from datetime import datetime

class InferenceRequest(BaseModel):
    """Universal inference request."""
    service_id: str = Field(
        ...,
        description="Primary service ID (transliteration, ner, asr, etc.)"
    )
    data: Dict[str, Any] = Field(
        ...,
        description="Service-specific input data"
    )
    model_id: Optional[str] = Field(
        None,
        description="Optional explicit model. If None, uses default model."
    )

class ServiceResult(BaseModel):
    """Result from a service."""
    output: Dict[str, Any] = Field(
        ...,
        description="Service-specific output"
    )
    model_used: str = Field(
        ...,
        description="Model used for inference"
    )
    requested_model: Optional[str] = Field(
        None,
        description="Model requested by user (if explicit)"
    )
    triton_latency_ms: int = Field(
        ...,
        description="Latency of Triton inference"
    )

class InferenceResponse(BaseModel):
    """Universal inference response."""
    results: Dict[str, ServiceResult] = Field(
        ...,
        description="Results from each service"
    )
    timestamp: str = Field(
        default_factory=lambda: datetime.utcnow().isoformat(),
        description="Response timestamp"
    )

# Example Usage:
# {
#     "results": {
#         "transliteration": {
#             "output": {
#                 "transliterated_text": "nmst",
#                 "confidence_scores": [0.95, 0.89]
#             },
#             "model_used": "transliteration-v2-fast",
#             "requested_model": null,
#             "triton_latency_ms": 12
#         }
#     },
#     "timestamp": "2026-04-30T10:30:45.123456"
# }
```

---

## 8. Service Registration

```python
# app/main.py or app/services/__init__.py
from app.factory.service_factory import ServiceFactory
from app.services.transliteration_service_impl import TransliterationServiceImpl
from app.services.nmt_service_impl import NMTServiceImpl
from app.services.ner_service_impl import NERServiceImpl

def register_services():
    """Register all available services with factory."""
    ServiceFactory.register("transliteration", TransliterationServiceImpl)
    ServiceFactory.register("xlit", TransliterationServiceImpl)  # Alias
    ServiceFactory.register("nmt", NMTServiceImpl)
    ServiceFactory.register("ner", NERServiceImpl)

# Call during application startup
register_services()
```

---

## 9. Testing Strategy

### 9.1 Unit Tests

```python
# tests/unit/test_transliteration_service.py
import pytest
from app.services.transliteration_service_impl import TransliterationServiceImpl
from unittest.mock import AsyncMock, patch

@pytest.mark.asyncio
async def test_preprocess():
    service = TransliterationServiceImpl()
    input_data = {"text": "namaste", "source_language": "hi"}
    result = await service.preProcess(input_data)
    assert result["input_text"] == "namaste"

@pytest.mark.asyncio
async def test_postprocess():
    service = TransliterationServiceImpl()
    triton_output = {"output": "nmst", "scores": [0.95]}
    result = await service.postProcess(triton_output)
    assert result["transliterated_text"] == "nmst"

@pytest.mark.asyncio
async def test_processdata_full_pipeline():
    service = TransliterationServiceImpl()
    
    with patch.object(service.inference_client, 'execute', new_callable=AsyncMock) as mock_triton:
        mock_triton.return_value = {"output": "nmst", "scores": [0.95]}
        
        result = await service.processData(
            {"text": "namaste", "source_language": "hi"}
        )
        
        assert result["transliterated_text"] == "nmst"
        mock_triton.assert_called_once()
```

### 9.2 Integration Tests

```python
# tests/integration/test_orchestrator.py
@pytest.mark.asyncio
async def test_single_service_orchestration():
    request = InferenceRequest(
        service_id="transliteration",
        data={"text": "namaste", "source_language": "hi"}
    )
    
    result = await orchestrator.execute(request)
    
    assert "results" in result
    assert "transliteration" in result["results"]

@pytest.mark.asyncio
async def test_multi_service_orchestration():
    request = InferenceRequest(
        service_id="transliteration",
        data={"text": "namaste"},
        config={"services": ["transliteration", "language_detection"]}
    )
    
    result = await orchestrator.execute(request)
    
    assert "transliteration" in result["results"]
    assert "language_detection" in result["results"]
```

---

## 10. Deployment & Configuration

### 10.1 Environment Variables

```bash
# .env
TRITON_URL=localhost:8000
TRITON_TIMEOUT=30
SERVICE_CACHE_TTL=3600
LOG_LEVEL=INFO
```

### 10.2 Service Configuration

```yaml
# config/services.yaml
services:
  transliteration:
    class: TransliterationServiceImpl
    triton_model: "transliteration"
    enabled: true
  
  nmt:
    class: NMTServiceImpl
    triton_model: "nmt"
    enabled: true
  
  ner:
    class: NERServiceImpl
    triton_model: "ner"
    enabled: true
```

---

## 11. Benefits Analysis

| Benefit | Current | Proposed |
|---------|---------|----------|
| **Code Reuse** | ~50% duplication | ~0% duplication |
| **Service Addition Time** | 2-3 hours | 30 minutes |
| **Triton Connections** | N clients | 1 singleton |
| **Testability** | Difficult | Easy (mocked interfaces) |
| **Service Chaining** | Manual | Automatic via config |
| **Maintenance** | High | Low |
| **Scaling** | Per-service | Shared resources |

---

## 12. Migration Plan

### Phase 1: Foundation (Week 1)
- [ ] Create base classes and interfaces
- [ ] Implement TritonClient singleton
- [ ] Implement ServiceFactory
- [ ] Implement InferenceOrchestrator
- [ ] Write unit tests

### Phase 2: Pilot Service (Week 2)
- [ ] Migrate Transliteration service
- [ ] Integration tests
- [ ] Load testing
- [ ] Documentation

### Phase 3: Rollout (Weeks 3-4)
- [ ] Migrate NMT service
- [ ] Migrate NER service
- [ ] Migrate remaining services
- [ ] Monitor performance
- [ ] Decommission old endpoints

### Phase 4: Optimization (Week 5)
- [ ] Performance tuning
- [ ] Caching optimization
- [ ] Circuit breaker implementation
- [ ] Metrics & monitoring

---

## 13. Risk Mitigation

| Risk | Mitigation |
|------|-----------|
| Shared inference client bottleneck | Use connection pooling, add async queuing |
| Service dependency failures | Implement circuit breaker, graceful degradation |
| Backward compatibility | Version endpoints, gradual rollout |
| Performance regression | Baseline metrics, load testing before deploy |

---

## 14. Monitoring & Observability

```python
# Metrics to track
- Service latency (per service)
- Triton server response time
- Error rates (per service)
- Service cache hits/misses
- Memory usage (connection pooling)
```

---

## 15. Future Enhancements

1. **Async Service Parallel Execution**: Execute multiple services in parallel instead of sequential
2. **Result Caching**: Cache Triton responses for repeated inputs
3. **Circuit Breaker Pattern**: Handle Triton server failures gracefully
4. **Service Versioning**: Support multiple versions of same service
5. **Dynamic Service Loading**: Load services from configuration
6. **Result Streaming**: Stream results for long-running services

---

## 16. Decision Points for Architect Review

1. **Parallel vs Sequential Execution**: Should multi-service requests execute services in parallel or sequentially?
2. **Error Handling Strategy**: Should one service failure stop the entire request or continue with others?
3. **Response Format**: Should each service result be isolated or merged into a single response?
4. **Service Discovery**: Should services be registered statically or dynamically?
5. **Triton Connection**: Should we use HTTP or gRPC client? Connection pooling strategy?

---

## Appendix: File Structure

```
services/transliteration-service/app/
├── main.py                              # FastAPI app initialization
├── routes/
│   └── inference.py                     # FastAPI endpoints (updated)
├── services/
│   ├── base_service.py                  # InferenceService interface (NEW)
│   ├── inference_client.py              # InferenceClient singleton (NEW)
│   └── transliteration_service_impl.py  # Implementation (updated)
├── factory/
│   └── service_factory.py               # ServiceFactory (NEW)
├── orchestrator/
│   └── inference_orchestrator.py        # InferenceOrchestrator (NEW)
├── schemas/
│   └── inference.py                     # Request/Response schemas (updated)
└── dependencies/
    └── services.py                      # Service dependencies

tests/
├── unit/
│   ├── test_base_service.py             # (NEW)
│   ├── test_service_factory.py          # (NEW)
│   └── test_transliteration_service.py  # (updated)
└── integration/
    └── test_orchestrator.py             # (NEW)
```

---

**Document prepared for architectural review and discussion.**  
**Last updated**: April 29, 2026
