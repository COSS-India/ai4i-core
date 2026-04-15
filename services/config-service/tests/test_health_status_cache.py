from utils.health_status_cache import compute_health_state


def test_compute_health_state_unknown_when_no_instances():
    assert compute_health_state(total_instances=0, healthy_instances=0) == "unknown"
    assert compute_health_state(total_instances=0, healthy_instances=1) == "unknown"


def test_compute_health_state_unhealthy_when_instances_exist_but_none_healthy():
    assert compute_health_state(total_instances=2, healthy_instances=0) == "unhealthy"


def test_compute_health_state_healthy_when_all_healthy():
    assert compute_health_state(total_instances=1, healthy_instances=1) == "healthy"
    assert compute_health_state(total_instances=3, healthy_instances=3) == "healthy"


def test_compute_health_state_degraded_when_some_healthy():
    assert compute_health_state(total_instances=3, healthy_instances=1) == "degraded"
    assert compute_health_state(total_instances=3, healthy_instances=2) == "degraded"

