from typing import List, Optional
from pydantic import BaseModel, Field, field_validator


class ConfigurationCreate(BaseModel):
    key: str = Field(..., description="Configuration key", min_length=1, max_length=255)
    value: str = Field(..., description="Configuration value")
    environment: str = Field(..., description="Environment name (development|staging|production)")
    service_name: str = Field(..., description="Service name", min_length=1, max_length=100)
    is_encrypted: bool = Field(False, description="Whether the value is encrypted")

    @field_validator("environment")
    @classmethod
    def validate_environment(cls, v: str) -> str:
        allowed = {"development", "staging", "production"}
        if v not in allowed:
            raise ValueError("environment must be one of development, staging, production")
        return v


class ConfigurationUpdate(BaseModel):
    value: str = Field(..., description="New configuration value")
    is_encrypted: Optional[bool] = Field(None, description="Whether the value is encrypted")


class ConfigurationQuery(BaseModel):
    environment: Optional[str] = Field(None, description="Environment filter")
    service_name: Optional[str] = Field(None, description="Service name filter")
    keys: Optional[List[str]] = Field(None, description="List of keys to filter")


class ConfigurationResponse(BaseModel):
    id: int
    key: str
    value: str
    environment: str
    service_name: str
    is_encrypted: bool
    version: int
    created_at: str
    updated_at: str


class ConfigurationListResponse(BaseModel):
    items: List[ConfigurationResponse]
    total: int = Field(..., description="Total count of matching configurations")
    limit: int = Field(..., description="Page size")
    offset: int = Field(..., description="Page offset")


