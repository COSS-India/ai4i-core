from typing import List

from .model_create import Task
from .service_view import ServiceResponse


class ServiceListResponse(ServiceResponse):
    task: Task
    languages: List[dict]
