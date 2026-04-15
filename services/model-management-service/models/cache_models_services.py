from pydantic import create_model
from models.model_create import ModelCreateRequest
from models.service_create import ServiceCreateRequest
from cache.CacheBaseModel import CacheBaseModel, generate_cache_model
from redis_om import Field as RedisField

# Generate cache model fields from ModelCreateRequest
# Note: modelId is no longer in ModelCreateRequest, so we need to add it manually as primary key
cache_fields = generate_cache_model(ModelCreateRequest, primary_key_field="modelId")

cache_fields["modelId"] = (str, RedisField(..., primary_key=True))

# redis-om 1.x: HashModel.save() calls key(), which requires index=True on the class
# (see RedisModel.key). Pass via metaclass kwargs, not only model_config.
ModelCache = create_model(
    "ModelCache",
    __base__=CacheBaseModel,
    __cls_kwargs__={"index": True},
    **cache_fields,
)

# serviceId is generated server-side (not on ServiceCreateRequest), so
# generate_cache_model(..., primary_key_field="serviceId") would never attach
# primary_key=True. Mirror ModelCache: declare serviceId explicitly so inserts
# can cache by business id and default redis_om `pk` is not used.
_service_cache_fields = dict(
    generate_cache_model(ServiceCreateRequest, primary_key_field="serviceId")
)
_service_cache_fields["serviceId"] = (str, RedisField(..., primary_key=True))

ServiceCache = create_model(
    "ServiceCache",
    __base__=CacheBaseModel,
    __cls_kwargs__={"index": True},
    **_service_cache_fields,
)