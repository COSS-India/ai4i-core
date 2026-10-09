"""Jobs. One module per job, discovered by bootstrap.registry.

Each module defines ``async def run()``. Database sessions come from
``bootstrap.database`` (platform_core_session / auth_session), Redis from
``bootstrap.redis_client.get_redis``; platform-core's
internal API from ``bootstrap.platform_core.call_internal``. Schedules live in
the k8s CronJob manifests.
"""
