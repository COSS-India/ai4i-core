"""
Tests for the response envelope helpers.
"""

from app.core.responses import error_response, success_response


class TestResponses:
    def test_success_response(self):
        resp = success_response(data={"id": 1})
        assert resp["success"] is True
        assert resp["data"]["id"] == 1
        assert "error" not in resp

    def test_success_with_meta(self):
        resp = success_response(data=[], meta={"total": 50})
        assert resp["meta"]["total"] == 50

    def test_error_response(self):
        resp = error_response("NOT_FOUND", "User not found.")
        assert resp["success"] is False
        assert resp["error"]["code"] == "NOT_FOUND"
        assert resp["error"]["message"] == "User not found."

    def test_error_with_details(self):
        resp = error_response("VALIDATION_ERROR", "Bad input.", details={"field": "email"})
        assert resp["error"]["details"]["field"] == "email"
