from typing import List, Optional

from .model_create import Task
from .service_view import ServiceResponse


class ServiceListResponse(ServiceResponse):
    task: Task
    languages: List[dict]
    modelVersion: Optional[str] = None
    versionStatus: Optional[str] = None
