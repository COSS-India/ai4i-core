from pydantic import BaseModel, Field, field_validator
from typing import List, Optional, Dict, Any, Union
from datetime import datetime
import time
from .type_enum import TaskTypeEnum


class ExperimentVariantRequest(BaseModel):
    """Request model for creating/updating an experiment variant"""
    variant_name: str = Field(..., description="Name of the variant (e.g., 'control', 'variant-a')")
    service_id: str = Field(..., description="Service ID to use for this variant")
    traffic_percentage: int = Field(..., ge=0, le=100, description="Traffic percentage (0-100)")
    description: Optional[str] = Field(None, description="Optional description of the variant")

    @field_validator("variant_name")
    def validate_variant_name(cls, v):
        if not v or not v.strip():
            raise ValueError("Variant name cannot be empty")
        return v.strip()


class ExperimentVariantResponse(BaseModel):
    """Response model for experiment variant"""
    id: str
    variant_name: str
    service_id: str
    traffic_percentage: int
    description: Optional[str] = None
    created_at: Union[datetime, str]
    updated_at: Union[datetime, str]

    class Config:
        from_attributes = True
        json_encoders = {
            datetime: lambda v: v.isoformat() if isinstance(v, datetime) else v
        }


class ExperimentCreateRequest(BaseModel):
    """Request model for creating an experiment"""
    name: str = Field(..., min_length=1, max_length=255, description="Experiment name")
    description: Optional[str] = Field(None, description="Experiment description")
    
    # Filters
    task_type: Optional[List[str]] = Field(None, description="List of task types to filter (e.g., ['asr', 'tts'])")
    languages: Optional[List[str]] = Field(None, description="List of language codes to filter (e.g., ['hi', 'en'])")
    
    # Duration
    start_date: Optional[datetime] = Field(None, description="Experiment start date (optional, defaults to now)")
    end_date: Optional[datetime] = Field(None, description="Experiment end date (optional)")
    
    # Variants
    variants: List[ExperimentVariantRequest] = Field(..., min_items=2, description="At least 2 variants required")

    @field_validator("name")
    def validate_name(cls, v):
        if not v or not v.strip():
            raise ValueError("Experiment name cannot be empty")
        return v.strip()

    @field_validator("variants")
    def validate_variants(cls, v):
        if len(v) < 2:
            raise ValueError("At least 2 variants are required for A/B testing")
        
        # Validate traffic percentages sum to 100
        total_percentage = sum(variant.traffic_percentage for variant in v)
        if total_percentage != 100:
            raise ValueError(f"Traffic percentages must sum to 100. Current sum: {total_percentage}")
        
        # Validate unique variant names
        variant_names = [variant.variant_name for variant in v]
        if len(variant_names) != len(set(variant_names)):
            raise ValueError("Variant names must be unique")
        
        return v

    @field_validator("task_type")
    def validate_task_type(cls, v):
        if v is not None:
            valid_tasks = [task.value for task in TaskTypeEnum]
            for task in v:
                if task not in valid_tasks:
                    raise ValueError(f"Invalid task type: {task}. Valid types: {valid_tasks}")
        return v

    @field_validator("end_date")
    def validate_end_date(cls, v, info):
        if v is not None and 'start_date' in info.data and info.data['start_date'] is not None:
            if v <= info.data['start_date']:
                raise ValueError("End date must be after start date")
        return v


class ExperimentUpdateRequest(BaseModel):
    """Request model for updating an experiment"""
    name: Optional[str] = Field(None, min_length=1, max_length=255)
    description: Optional[str] = None
    task_type: Optional[List[str]] = None
    languages: Optional[List[str]] = None
    start_date: Optional[datetime] = None
    end_date: Optional[datetime] = None
    variants: Optional[List[ExperimentVariantRequest]] = None

    @field_validator("variants")
    def validate_variants(cls, v):
        if v is not None:
            if len(v) < 2:
                raise ValueError("At least 2 variants are required for A/B testing")
            
            total_percentage = sum(variant.traffic_percentage for variant in v)
            if total_percentage != 100:
                raise ValueError(f"Traffic percentages must sum to 100. Current sum: {total_percentage}")
            
            variant_names = [variant.variant_name for variant in v]
            if len(variant_names) != len(set(variant_names)):
                raise ValueError("Variant names must be unique")
        
        return v


class ExperimentStatusUpdateRequest(BaseModel):
    """Request model for updating experiment status"""
    action: str = Field(..., description="Action to perform: 'start', 'stop', 'pause', 'resume', or 'cancel'")

    @field_validator("action")
    def validate_action(cls, v):
        valid_actions = ["start", "stop", "pause", "resume", "cancel"]
        if v.lower() not in valid_actions:
            raise ValueError(f"Invalid action '{v}'. Valid actions: {', '.join(valid_actions)}")
        return v.lower()


class ExperimentResponse(BaseModel):
    """Response model for experiment"""
    id: str
    name: str
    description: Optional[str] = None
    status: str
    task_type: Optional[List[str]] = None
    languages: Optional[List[str]] = None
    start_date: Optional[Union[datetime, str]] = None
    end_date: Optional[Union[datetime, str]] = None
    created_by: Optional[str] = None
    updated_by: Optional[str] = None
    created_at: Union[datetime, str]
    updated_at: Union[datetime, str]
    started_at: Optional[Union[datetime, str]] = None
    completed_at: Optional[Union[datetime, str]] = None
    variants: List[ExperimentVariantResponse] = []

    class Config:
        from_attributes = True
        json_encoders = {
            datetime: lambda v: v.isoformat() if isinstance(v, datetime) else v
        }


class ExperimentListResponse(BaseModel):
    """Response model for listing experiments"""
    id: str
    name: str
    description: Optional[str] = None
    status: str
    task_type: Optional[List[str]] = None
    languages: Optional[List[str]] = None
    start_date: Optional[Union[datetime, str]] = None
    end_date: Optional[Union[datetime, str]] = None
    created_at: Union[datetime, str]
    updated_at: Union[datetime, str]
    variant_count: int = 0

    class Config:
        from_attributes = True
        json_encoders = {
            datetime: lambda v: v.isoformat() if isinstance(v, datetime) else v
        }


class ExperimentDeleteDetail(BaseModel):
    """Detail payload for experiment delete success (matches error response shape)."""
    message: str = Field(..., description="Success message")
    code: str = Field(..., description="Response code (e.g. DELETED)")
    timestamp: float = Field(default_factory=time.time, description="Response timestamp")
    experiment_id: str = Field(..., description="ID of the deleted experiment")


class ExperimentDeleteResponse(BaseModel):
    """Standard response for experiment delete (detail.message, detail.code, detail.timestamp)."""
    detail: ExperimentDeleteDetail


class ExperimentMetricItem(BaseModel):
    """Single variant metric (per day) - no experiment_id to avoid repetition."""
    variant_id: str
    variant_name: str
    request_count: int
    success_count: int
    error_count: int
    success_rate: float
    avg_latency_ms: Optional[int] = None
    custom_metrics: Optional[Dict[str, Any]] = None
    metric_date: datetime


class ExperimentMetricsResponse(BaseModel):
    """Standard response for GET experiment metrics: experiment_id once + metrics array."""
    experiment_id: str
    metrics: List[ExperimentMetricItem]


class ExperimentMetricTrackRequest(BaseModel):
    """Request model for tracking a single experiment metric (from services)"""
    experiment_id: str = Field(..., description="Experiment UUID")
    variant_id: str = Field(..., description="Variant UUID")
    success: bool = Field(..., description="Whether the request succeeded")
    latency_ms: int = Field(..., ge=0, description="Request latency in milliseconds")
    custom_metrics: Optional[Dict[str, Any]] = Field(default_factory=dict, description="Optional service-specific metrics")


class ExperimentVariantSelectionRequest(BaseModel):
    """Request model for selecting a variant for a given request"""
    task_type: str = Field(..., description="Task type (e.g., 'asr', 'tts')")
    language: Optional[str] = Field(None, description="Language code (e.g., 'hi', 'en')")
    request_id: Optional[str] = Field(None, description="Optional request ID for consistent routing")
    user_id: Optional[str] = Field(None, description="Optional user ID so same user gets same variant")
    service_id: Optional[str] = Field(
        None,
        description="Optional service ID from the request; when set, only experiments that include this service as a variant are considered"
    )


class ExperimentVariantSelectionResponse(BaseModel):
    """Response model for variant selection (api_key and endpoint omitted for security)"""
    experiment_id: Optional[str] = None
    variant_id: Optional[str] = None
    variant_name: Optional[str] = None
    service_id: Optional[str] = None
    model_id: Optional[str] = None
    model_version: Optional[str] = None
    is_experiment: bool = False
