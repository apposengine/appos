"""Unit tests for appos.engine.security — SecurityPolicy, password utils, RowSecurityPolicy."""

import pytest
from unittest.mock import MagicMock, patch

from appos.engine.security import (
    PERMISSION_HIERARCHY,
    SecurityPolicy,
    RowSecurityPolicy,
    hash_password,
    verify_password,
    generate_api_key,
)


class TestPermissionHierarchy:
    """Test permission hierarchy mappings."""

    def test_admin_includes_all(self):
        assert PERMISSION_HIERARCHY["admin"] == {"admin", "delete", "update", "create", "use", "view"}

    def test_view_is_minimal(self):
        assert PERMISSION_HIERARCHY["view"] == {"view"}

    def test_delete_includes_view(self):
        assert "view" in PERMISSION_HIERARCHY["delete"]

    def test_create_includes_view(self):
        assert "view" in PERMISSION_HIERARCHY["create"]

    def test_use_includes_view(self):
        assert "view" in PERMISSION_HIERARCHY["use"]

    def test_all_six_permissions_present(self):
        assert set(PERMISSION_HIERARCHY.keys()) == {"admin", "delete", "update", "create", "use", "view"}


class TestSecurityPolicy:
    """Test SecurityPolicy.check_access()."""

    def setup_method(self):
        self.policy = SecurityPolicy(
            permission_cache=None,
            db_session_factory=None,
        )

    def test_system_admin_bypasses(self):
        """system_admin should always have access."""
        result = self.policy.check_access(
            user_groups=set(),
            object_ref="crm.rules.calc",
            permission="admin",
            user_type="system_admin",
        )
        assert result is True

    def test_no_groups_denied(self):
        """User with no groups should be denied."""
        result = self.policy.check_access(
            user_groups=set(),
            object_ref="crm.rules.calc",
            permission="view",
            user_type="basic",
        )
        assert result is False


class TestPasswordUtils:
    """Test password hashing and verification."""

    def test_hash_and_verify(self):
        password = "MySecret123!"
        hashed = hash_password(password)
        assert hashed != password
        assert verify_password(password, hashed) is True

    def test_wrong_password_fails(self):
        hashed = hash_password("correct")
        assert verify_password("wrong", hashed) is False

    def test_hash_is_bcrypt(self):
        hashed = hash_password("test")
        assert hashed.startswith("$2b$") or hashed.startswith("$2a$")

    def test_different_hashes_for_same_password(self):
        """bcrypt uses salt, so same password produces different hashes."""
        h1 = hash_password("same")
        h2 = hash_password("same")
        assert h1 != h2
        assert verify_password("same", h1) is True
        assert verify_password("same", h2) is True


class TestGenerateApiKey:
    """Test API key generation."""

    def test_generates_tuple(self):
        result = generate_api_key()
        assert isinstance(result, tuple)
        assert len(result) == 2

    def test_prefix_and_hash(self):
        key, key_hash = generate_api_key()
        assert isinstance(key, str)
        assert isinstance(key_hash, str)
        assert len(key) > 20  # Should be a substantial key

    def test_unique_keys(self):
        k1, _ = generate_api_key()
        k2, _ = generate_api_key()
        assert k1 != k2


class TestRowSecurityPolicy:
    """Test RowSecurityPolicy placeholder."""

    def setup_method(self):
        self.rsp = RowSecurityPolicy()

    def test_register_policy(self):
        filter_fn = lambda query, ctx: query
        self.rsp.register_policy("customer", filter_fn)
        assert self.rsp.has_policy("customer") is True

    def test_has_policy_false(self):
        assert self.rsp.has_policy("nonexistent") is False

    def test_registered_policies(self):
        self.rsp.register_policy("customer", lambda q, c: q)
        self.rsp.register_policy("order", lambda q, c: q)
        policies = self.rsp.registered_policies
        assert "customer" in policies
        assert "order" in policies

    def test_apply_filter(self):
        filter_fn = MagicMock(return_value="filtered_query")
        self.rsp.register_policy("customer", filter_fn)
        result = self.rsp.apply_filter("customer", "base_query", "ctx")
        assert result == "filtered_query"
        filter_fn.assert_called_once_with("base_query", "ctx")

    def test_apply_filter_no_policy(self):
        """apply_filter returns query unchanged when no policy registered."""
        result = self.rsp.apply_filter("unknown", "base_query", "ctx")
        assert result == "base_query"
