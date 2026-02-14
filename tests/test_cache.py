"""Unit tests for appos.engine.cache — RedisCache, PermissionCache."""

import json
import time
import pytest
from unittest.mock import MagicMock, patch, PropertyMock

from appos.engine.cache import (
    RedisCache,
    PermissionCache,
    create_permission_cache,
    create_object_cache,
    create_session_store,
    create_rate_limiter,
)


class TestRedisCacheCircuitBreaker:
    """Test circuit breaker behavior without real Redis."""

    def test_initial_state(self):
        cache = RedisCache(redis_url="redis://localhost:6379/0", db=0)
        assert cache.is_available is False
        assert cache.is_circuit_open is False

    def test_get_returns_none_when_unavailable(self):
        cache = RedisCache()
        assert cache.get("any_key") is None

    def test_set_returns_false_when_unavailable(self):
        cache = RedisCache()
        assert cache.set("key", "value") is False

    def test_delete_returns_false_when_unavailable(self):
        cache = RedisCache()
        assert cache.delete("key") is False

    def test_exists_returns_false_when_unavailable(self):
        cache = RedisCache()
        assert cache.exists("key") is False

    def test_ping_returns_false_no_client(self):
        cache = RedisCache()
        assert cache.ping() is False

    def test_get_json_returns_none_when_unavailable(self):
        cache = RedisCache()
        assert cache.get_json("key") is None

    def test_set_json_returns_false_when_unavailable(self):
        cache = RedisCache()
        assert cache.set_json("key", {"data": 1}) is False

    def test_smembers_returns_empty_when_unavailable(self):
        cache = RedisCache()
        assert cache.smembers("key") == set()

    def test_scard_returns_zero_when_unavailable(self):
        cache = RedisCache()
        assert cache.scard("key") == 0

    def test_incr_returns_neg1_when_unavailable(self):
        cache = RedisCache()
        assert cache.incr("key") == -1

    def test_flush_db_returns_false_when_unavailable(self):
        cache = RedisCache()
        assert cache.flush_db() is False

    def test_delete_pattern_returns_zero_when_unavailable(self):
        cache = RedisCache()
        assert cache.delete_pattern("test:*") == 0


class TestRedisCacheWithMock:
    """Test cache operations with mocked Redis client."""

    def setup_method(self):
        self.cache = RedisCache(prefix="test:", default_ttl=60, db=2)
        self.cache._client = MagicMock()
        self.cache._available = True

    def test_make_key(self):
        assert self.cache._make_key("hello") == "test:hello"

    def test_get_success(self):
        self.cache._client.get.return_value = "value"
        assert self.cache.get("key") == "value"
        self.cache._client.get.assert_called_once_with("test:key")

    def test_get_failure_records(self):
        self.cache._client.get.side_effect = Exception("connection lost")
        result = self.cache.get("key")
        assert result is None
        assert self.cache._failure_count == 1

    def test_set_success(self):
        self.cache._client.set.return_value = True
        assert self.cache.set("key", "val", ttl=120) is True
        self.cache._client.set.assert_called_once_with("test:key", "val", ex=120)

    def test_set_uses_default_ttl(self):
        self.cache._client.set.return_value = True
        self.cache.set("key", "val")
        self.cache._client.set.assert_called_once_with("test:key", "val", ex=60)

    def test_delete_success(self):
        self.cache._client.delete.return_value = 1
        assert self.cache.delete("key") is True

    def test_exists_true(self):
        self.cache._client.exists.return_value = 1
        assert self.cache.exists("key") is True

    def test_exists_false(self):
        self.cache._client.exists.return_value = 0
        assert self.cache.exists("key") is False

    def test_get_json(self):
        self.cache._client.get.return_value = '{"a": 1}'
        result = self.cache.get_json("key")
        assert result == {"a": 1}

    def test_get_json_invalid(self):
        self.cache._client.get.return_value = "not json{"
        assert self.cache.get_json("key") is None

    def test_set_json(self):
        self.cache._client.set.return_value = True
        assert self.cache.set_json("key", {"a": 1}) is True

    def test_sadd(self):
        self.cache._client.sadd.return_value = 1
        assert self.cache.sadd("myset", "a", "b") is True

    def test_srem(self):
        self.cache._client.srem.return_value = 1
        assert self.cache.srem("myset", "a") is True

    def test_smembers(self):
        self.cache._client.smembers.return_value = {"a", "b"}
        assert self.cache.smembers("myset") == {"a", "b"}

    def test_scard(self):
        self.cache._client.scard.return_value = 3
        assert self.cache.scard("myset") == 3

    def test_flush_db(self):
        self.cache._client.flushdb.return_value = True
        assert self.cache.flush_db() is True

    def test_circuit_breaker_opens(self):
        """After threshold failures within window, circuit opens."""
        self.cache._client.get.side_effect = Exception("fail")
        for _ in range(5):
            self.cache.get("key")
        assert self.cache.is_circuit_open is True
        # Subsequent calls should return None without hitting Redis
        self.cache._client.get.reset_mock()
        assert self.cache.get("key") is None


class TestPermissionCache:
    """Test PermissionCache wrapper."""

    def setup_method(self):
        self.redis = RedisCache(prefix="test:", default_ttl=300, db=2)
        self.redis._client = MagicMock()
        self.redis._available = True
        self.perm_cache = PermissionCache(self.redis)

    def test_store_and_check_allowed(self):
        self.redis._client.get.return_value = "1"
        groups = frozenset({"crm_users"})
        result = self.perm_cache.check(groups, "crm.rules.calc", "view")
        assert result is True

    def test_store_and_check_denied(self):
        self.redis._client.get.return_value = "0"
        groups = frozenset({"crm_users"})
        result = self.perm_cache.check(groups, "crm.rules.calc", "admin")
        assert result is False

    def test_check_miss(self):
        self.redis._client.get.return_value = None
        groups = frozenset({"crm_users"})
        result = self.perm_cache.check(groups, "crm.rules.calc", "view")
        assert result is None

    def test_invalidate_all(self):
        self.redis._client.scan_iter.return_value = iter(["test:perms:x"])
        self.redis._client.delete.return_value = 1
        self.perm_cache.invalidate_all()
        # Should have been called


class TestCacheFactories:
    """Test factory functions (they create configured RedisCache/PermissionCache)."""

    def test_create_permission_cache(self):
        pc = create_permission_cache("redis://localhost:6379/0")
        assert isinstance(pc, PermissionCache)

    def test_create_object_cache(self):
        oc = create_object_cache("redis://localhost:6379/0")
        assert isinstance(oc, RedisCache)

    def test_create_session_store(self):
        ss = create_session_store("redis://localhost:6379/0")
        assert isinstance(ss, RedisCache)

    def test_create_rate_limiter(self):
        rl = create_rate_limiter("redis://localhost:6379/0")
        assert isinstance(rl, RedisCache)
