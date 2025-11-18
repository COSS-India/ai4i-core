from pydantic import create_model
from models.model_create import ModelCreateRequest
from cache.CacheBaseModel import CacheBaseModel, generate_cache_model

ModelCache = create_model(
    "ModelCache",
    __base__=CacheBaseModel,
    **generate_cache_model(ModelCreateRequest, primary_key_field="modelId"),
)