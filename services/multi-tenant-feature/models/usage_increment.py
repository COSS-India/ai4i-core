from pydantic import BaseModel, Field, field_validator


class UsageIncrementRequest(BaseModel):
    """Request model for incrementing tenant usage"""
    tenant_id: str = Field(..., description="Tenant identifier")
    characters_length: int = Field(0, ge=0, description="Characters to add to usage")
    audio_length_in_min: float = Field(0, ge=0, description="Audio minutes to add to usage (supports fractional minutes, rounded to 2 decimals)")
    
    @field_validator('audio_length_in_min', mode='before')
    @classmethod
    def round_audio_length(cls, v):
        """Round audio length to 2 decimal places"""
        if v is not None and isinstance(v, (int, float)):
            return round(float(v), 2)
        return v


class UsageIncrementResponse(BaseModel):
    """Response model for usage increment"""
    tenant_id: str
    message: str
    updated_usage: dict
