from typing import List, Optional

from .model_create import TaskResponse
from .service_view import ServiceResponse


class ServiceListResponse(ServiceResponse):
    task: TaskResponse  # Use TaskResponse to allow invalid task types from DB
    languages: List[dict]
    modelVersion: Optional[str] = None
    versionStatus: Optional[str] = None
