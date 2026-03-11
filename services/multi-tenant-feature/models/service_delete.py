from pydantic import BaseModel , Field


class ServiceDeleteRequest(BaseModel):
    """Request model for deleting a service configuration."""

    service_id: int = Field(..., description="Service identifier in tenant DB")


class ServiceDeleteResponse(BaseModel):
    """Response model for service deletion."""

    service_id: int = Field(..., description="Deleted service identifier")
    message: str = Field(..., description="Deletion message")