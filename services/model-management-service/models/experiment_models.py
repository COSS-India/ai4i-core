"""
Pydantic models for A/B Experiment API requests and responses.
"""
from pydantic import BaseModel, Field, field_validator
from typing import Optional
from datetime import datetime
from enum import Enum


class ExperimentStatus(str, Enum):
    """Status of an A/B experiment"""
    DRAFT = "DRAFT"
    RUNNING = "RUNNING"
    STOPPED = "STOPPED"


# ---- Request Models ----

class ExperimentCreateRequest(BaseModel):
    """Request to create a new A/B experiment"""
    name: str = Field(..., min_length=1, max_length=255, description="Unique experiment name")
    description: Optional[str] = Field(None, description="Description of what this experiment tests")
    task_type: str = Field(..., description="Task type: asr, nmt, tts, ocr, ner, etc.")
    control_service_id: str = Field(..., description="Service ID of the control (baseline) model")
    treatment_service_id: str = Field(..., description="Service ID of the treatment (new) model")
    treatment_percentage: int = Field(50, ge=0, le=100, description="Percentage of traffic to treatment (0-100)")

    @field_validator("name")
    def validate_name(cls, v):
        """Validate experiment name format"""
        if not v or not v.strip():
            raise ValueError("Experiment name cannot be empty")
        return v.strip()

    @field_validator("task_type")
    def validate_task_type(cls, v):
        """Validate task type is a known type"""
        valid_types = ["asr", "nmt", "tts", "ocr", "ner", "transliteration", 
                       "language-detection", "speaker-diarization", "language-diarization",
                       "audio-lang-detection", "llm", "pipeline"]
        if v.lower() not in valid_types:
            raise ValueError(f"Invalid task_type. Must be one of: {', '.join(valid_types)}")
        return v.lower()


class ExperimentUpdateRequest(BaseModel):
    """Request to update an experiment (only treatment_percentage can be updated while running)"""
    description: Optional[str] = None
    treatment_percentage: Optional[int] = Field(None, ge=0, le=100)


# ---- Response Models ----

class ExperimentResponse(BaseModel):
    """Full experiment details response"""
    id: str
    name: str
    description: Optional[str]
    task_type: str
    control_service_id: str
    treatment_service_id: str
    treatment_percentage: int
    status: ExperimentStatus
    created_by: Optional[str]
    updated_by: Optional[str]
    created_at: datetime
    updated_at: Optional[datetime]
    started_at: Optional[datetime]
    stopped_at: Optional[datetime]

    model_config = {
        "from_attributes": True
    }


class ExperimentSummary(BaseModel):
    """Summary view for listing experiments"""
    id: str
    name: str
    task_type: str
    status: ExperimentStatus
    treatment_percentage: int
    created_at: datetime
    started_at: Optional[datetime]

    model_config = {
        "from_attributes": True
    }


class VariantResolution(BaseModel):
    """
    Response from variant resolution endpoint.
    Used by inference services to determine which service to route to.
    """
    service_id: str = Field(..., description="The service_id to use for this request")
    variant: str = Field(..., description="Which variant: 'control', 'treatment', or 'default'")
    experiment_name: Optional[str] = Field(None, description="Name of the active experiment, if any")
    experiment_id: Optional[str] = Field(None, description="ID of the active experiment, if any")


class ExperimentStartStopResponse(BaseModel):
    """Response for start/stop operations"""
    id: str
    name: str
    status: ExperimentStatus
    message: str
