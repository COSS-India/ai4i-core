from pydantic import create_model
from models.model_create import ModelCreateRequest
from models.service_create import ServiceCreateRequest
from cache.CacheBaseModel import CacheBaseModel, generate_cache_model
from redis_om import Field as RedisField

# Generate cache model fields from ModelCreateRequest
# Note: modelId is no longer in ModelCreateRequest, so we need to add it manually as primary key
cache_fields = generate_cache_model(ModelCreateRequest, primary_key_field="modelId")

cache_fields["modelId"] = (str, RedisField(..., primary_key=True))

ModelCache = create_model(
    "ModelCache",
    __base__=CacheBaseModel,
    **cache_fields,
)

ServiceCache = create_model(
    "ServiceCache",
    __base__=CacheBaseModel,
    **generate_cache_model(ServiceCreateRequest, primary_key_field="serviceId")
)