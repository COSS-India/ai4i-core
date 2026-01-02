from datetime import datetime
from typing import List, Optional
from uuid import UUID

import pydantic
from uuid import UUID

from cache.CacheBaseModel import CacheBaseModel, generate_cache_model
from pydantic import BaseModel


class _ServiceUsage(BaseModel):
    service_id: str
    usage: int = 0
    hits: int = 0


class ApiKey(BaseModel):
    name: str
    api_key: str
    masked_key: str
    active: bool
    user_id: UUID
    type: str
    created_timestamp: datetime
    usage: int = 0
    hits: int = 0
    data_tracking: bool
    services: List[_ServiceUsage] = []

    def revoke(self):
        self.active = False

    def activate(self):
        self.active = True

    def enable_tracking(self):
        self.data_tracking = True

    def disable_tracking(self):
        self.data_tracking = False


ApiKeyCache = pydantic.create_model(
    "ApiKeyCache",
    __base__=CacheBaseModel,
    **generate_cache_model(ApiKey, primary_key_field="api_key")
)
