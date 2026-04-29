"""Tests for ai4icore_core.auth.permission_checker.PermissionChecker.

The class is the single platform-wide enforcement point for endpoint access.
ADMIN bypass behaviour is critical and must be covered.
"""
from __future__ import annotations

from ai4icore_core.auth.permission_checker import PermissionChecker


# ── check_endpoint_access — the central enforcement point ──

class TestCheckEndpointAccess:
    def test_no_required_permission_grants_access(self):
        """When required is None (public endpoint), any caller is allowed."""
        assert PermissionChecker.check_endpoint_access(
            required=None, user_permission_ids=[], user_roles=[]
        ) is True

    def test_user_with_matching_permission_id_granted(self):
        assert PermissionChecker.check_endpoint_access(
            required=5, user_permission_ids=[1, 5, 12], user_roles=["USER"]
        ) is True

    def test_user_without_matching_permission_id_denied(self):
        assert PermissionChecker.check_endpoint_access(
            required=99, user_permission_ids=[1, 5, 12], user_roles=["USER"]
        ) is False

    def test_admin_role_bypasses_permission_check(self):
        """Critical security invariant: ADMIN bypasses ID-based checks."""
        assert PermissionChecker.check_endpoint_access(
            required=99, user_permission_ids=[], user_roles=["ADMIN"]
        ) is True

    def test_admin_bypass_works_when_user_also_has_other_roles(self):
        assert PermissionChecker.check_endpoint_access(
            required=42, user_permission_ids=[], user_roles=["USER", "ADMIN"]
        ) is True

    def test_non_admin_role_does_not_bypass(self):
        """MODERATOR / GUEST / etc must NOT bypass permission checks."""
        for role in ("MODERATOR", "USER", "GUEST", "OPERATOR"):
            assert PermissionChecker.check_endpoint_access(
                required=99, user_permission_ids=[], user_roles=[role]
            ) is False, f"role={role!r} should not bypass"

    def test_permission_id_supplied_as_numeric_string_matches(self):
        """The verifier accepts string-form numeric IDs (legacy contract)."""
        assert PermissionChecker.check_endpoint_access(
            required="7", user_permission_ids=[7], user_roles=[]
        ) is True

    def test_none_user_inputs_treated_as_empty(self):
        assert PermissionChecker.check_endpoint_access(
            required=1, user_permission_ids=None, user_roles=None
        ) is False

    def test_admin_bypass_with_none_permission_ids(self):
        """ADMIN must still bypass even if permission_ids is None."""
        assert PermissionChecker.check_endpoint_access(
            required=1, user_permission_ids=None, user_roles=["ADMIN"]
        ) is True


# ── has_permission / has_permission_id / has_any_role helpers ──

def test_has_permission_grants_when_required_in_list():
    assert PermissionChecker.has_permission("asr.inference", ["asr.inference", "tts.read"]) is True


def test_has_permission_denies_when_required_not_in_list():
    assert PermissionChecker.has_permission("asr.inference", ["tts.read"]) is False


def test_has_permission_empty_required_grants():
    assert PermissionChecker.has_permission("", ["any"]) is True


def test_has_permission_id_grants_when_id_in_list():
    assert PermissionChecker.has_permission_id(5, [1, 5, 12]) is True


def test_has_permission_id_denies_when_id_not_in_list():
    assert PermissionChecker.has_permission_id(99, [1, 5, 12]) is False


def test_has_permission_id_zero_required_grants():
    """Falsy required_id (0) is treated as no requirement."""
    assert PermissionChecker.has_permission_id(0, []) is True


def test_has_any_role_grants_on_overlap():
    assert PermissionChecker.has_any_role(["ADMIN", "MODERATOR"], ["MODERATOR"]) is True


def test_has_any_role_denies_when_no_overlap():
    assert PermissionChecker.has_any_role(["ADMIN", "MODERATOR"], ["USER"]) is False


def test_has_any_role_empty_user_roles_denies():
    assert PermissionChecker.has_any_role(["ADMIN"], []) is False
