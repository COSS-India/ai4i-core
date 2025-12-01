from pydantic import create_model
from models.model_create import ModelCreateRequest
from models.service_create import ServiceCreateRequest
from cache.CacheBaseModel import CacheBaseModel, generate_cache_model

ModelCache = create_model(
    "ModelCache",
    __base__=CacheBaseModel,
    **generate_cache_model(ModelCreateRequest, primary_key_field="modelId"),
)

ServiceCache = create_model(
    "ServiceCache",
    __base__=CacheBaseModel,
    **generate_cache_model(ServiceCreateRequest, primary_key_field="serviceId")
)