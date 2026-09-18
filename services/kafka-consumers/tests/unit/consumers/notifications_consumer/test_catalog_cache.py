"""consumers/notifications_consumer/catalog_cache._parse_thresholds

config.thresholds has been stored in two shapes: the pre-migration dict
keyed by percent-as-string ({"70": false, ...}), and the current list of
{"percentage": int, "active": bool} bands. thresholds is unused by this
consumer's own handler today, but _refresh must not raise on an old-shape
row — that would take out the whole cache refresh, not just this field.
"""
from __future__ import annotations

from consumers.notifications_consumer.catalog_cache import _parse_thresholds


class TestParseThresholds:
    def test_new_list_shape_passes_through(self):
        raw = [{"percentage": 70, "active": True}, {"percentage": 90, "active": False}]
        assert _parse_thresholds(raw) == raw

    def test_old_dict_shape_is_normalised_to_the_list_shape(self):
        raw = {"70": True, "90": False}
        result = _parse_thresholds(raw)
        assert sorted(result, key=lambda b: b["percentage"]) == [
            {"percentage": 70, "active": True},
            {"percentage": 90, "active": False},
        ]

    def test_none_is_empty_list(self):
        assert _parse_thresholds(None) == []

    def test_empty_dict_is_empty_list(self):
        assert _parse_thresholds({}) == []

    def test_empty_list_is_empty_list(self):
        assert _parse_thresholds([]) == []
