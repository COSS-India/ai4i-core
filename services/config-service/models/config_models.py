from typing import List, Optional, Any, Dict
from pydantic import BaseModel, Field, field_validator, ConfigDict, model_serializer


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
    model_config = ConfigDict(exclude_none=True)
    
    id: Optional[int] = Field(None, description="Database ID (None for Vault-stored configs)", exclude=True)
    key: str
    value: str
    environment: str
    service_name: str
    is_encrypted: bool
    version: int
    created_at: str
    updated_at: str
    mask_value: bool = Field(default=False, exclude=True)  # Internal flag to mask encrypted values
    
    @model_serializer
    def serialize_model(self, mode='python') -> Dict[str, Any]:
        """Custom serialization that masks encrypted values and excludes id"""
        # Use model_fields_set to get actual values without recursion
        data = {}
        for field_name, field_info in self.model_fields.items():
            if field_name == 'mask_value':
                continue  # Skip internal field
            value = getattr(self, field_name, None)
            if value is not None or field_name != 'id':
                data[field_name] = value
        
        # Exclude id if it's None or 0
        if data.get("id") is None or data.get("id") == 0:
            data.pop("id", None)
        # Mask encrypted values if flag is set
        if data.get("is_encrypted", False) and self.mask_value:
            data["value"] = "***ENCRYPTED***"
        return data


class ConfigurationListResponse(BaseModel):
    items: List[ConfigurationResponse]
    total: int = Field(..., description="Total count of matching configurations")
    limit: int = Field(..., description="Page size")
    offset: int = Field(..., description="Page offset")


