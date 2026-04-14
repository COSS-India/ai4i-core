import json


def _cache_key(service_id: str) -> str:
    return f"internal:health-status:{service_id}"


def test_internal_health_status_cache_read(test_client, redis_client, monkeypatch):
    import main as app_main

    # Ensure the router reads from our test Redis instance.
    monkeypatch.setattr(app_main, "redis_client", redis_client, raising=False)

    service_id = "asr-service"
    payload = {
        "service_id": service_id,
        "state": "degraded",
        "last_check": "2026-04-14T00:00:00+00:00",
        "total_instances": 2,
        "healthy_instances": 1,
    }

    import asyncio

    asyncio.get_event_loop().run_until_complete(
        redis_client.set(_cache_key(service_id), json.dumps(payload), ex=60)
    )

    resp = test_client.get("/internal/health-status", params={"service_id": service_id})
    assert resp.status_code == 200
    body = resp.json()
    assert body["service_id"] == service_id
    assert body["state"] == "degraded"
    assert body["last_check"] == payload["last_check"]


def test_internal_health_status_404_when_missing(test_client, redis_client, monkeypatch):
    import main as app_main

    monkeypatch.setattr(app_main, "redis_client", redis_client, raising=False)

    resp = test_client.get("/internal/health-status", params={"service_id": "missing-service"})
    assert resp.status_code == 404

