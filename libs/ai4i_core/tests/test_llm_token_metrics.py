"""MetricsCollector.track_llm_tokens: one telemetry_obsv_llm_tokens_processed
series per token_type, cached_input included when there was a cache hit."""
from unittest.mock import MagicMock

from ai4i_core.observability.metrics import MetricsCollector


def _collector() -> MetricsCollector:
    collector = MetricsCollector.__new__(MetricsCollector)   # skip registry setup
    collector.enterprise_llm_tokens_processed = MagicMock()
    return collector


def _observed(collector) -> dict:
    histogram = collector.enterprise_llm_tokens_processed
    return {
        call.kwargs["token_type"]: histogram.labels.return_value.observe.call_args_list[i].args[0]
        for i, call in enumerate(histogram.labels.call_args_list)
    }


def test_cached_input_series_when_cache_hit():
    collector = _collector()
    collector.track_llm_tokens(
        model="gemma", prompt_tokens=1200, completion_tokens=150, total_tokens=1350,
        cached_input_tokens=1024,
    )
    assert _observed(collector) == {"prompt": 1200, "completion": 150, "total": 1350, "cached_input": 1024}


def test_no_cached_input_series_without_cache_hit():
    collector = _collector()
    collector.track_llm_tokens(model="gemma", prompt_tokens=23, completion_tokens=9, total_tokens=32)
    assert "cached_input" not in _observed(collector)
