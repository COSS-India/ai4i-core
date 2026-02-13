from pydantic import BaseModel, Field
from typing import Optional, Dict, Any


class ServicePolicyData(BaseModel):
    """Policy data structure for a service"""
    latency: Optional[str] = Field(None, description="Latency policy: low, medium, or high")
    cost: Optional[str] = Field(None, description="Cost policy: tier_1, tier_2, or tier_3")
    accuracy: Optional[str] = Field(None, description="Accuracy policy: sensitive or standard")
    
    class Config:
        json_schema_extra = {
            "example": {
                "latency": "low",
                "cost": "tier_3",
                "accuracy": "sensitive"
            }
        }


class ServicePolicyRequest(BaseModel):
    """Request to add or update policy for a service"""
    serviceId: str = Field(..., description="Service ID to add/update policy for")
    policy: ServicePolicyData = Field(..., description="Policy data (latency, cost, accuracy)")


class ServicePolicyUpdateRequest(BaseModel):
    """Request to add or update policy when service_id is in path (POST /services/{service_id}/policy)"""
    policy: ServicePolicyData = Field(..., description="Policy data (latency, cost, accuracy)")


class ServicePolicyResponse(BaseModel):
    """Response containing service policy information"""
    serviceId: str
    policy: Optional[Dict[str, Any]] = Field(None, description="Policy data as JSON object")
    
    class Config:
        json_schema_extra = {
            "example": {
                "serviceId": "abc123def456",
                "policy": {
                    "latency": "low",
                    "cost": "tier_3",
                    "accuracy": "sensitive"
                }
            }
        }


class ServicePolicyListResponse(BaseModel):
    """Response containing list of services with their policies"""
    services: list[ServicePolicyResponse] = Field(..., description="List of services with their policies")
    
    class Config:
        json_schema_extra = {
            "example": {
                "services": [
                    {
                        "serviceId": "abc123def456",
                        "policy": {
                            "latency": "low",
                            "cost": "tier_3",
                            "accuracy": "sensitive"
                        }
                    }
                ]
            }
        }
