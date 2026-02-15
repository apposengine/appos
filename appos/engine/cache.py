"""
AppOS Redis Cache Layer — Permission cache, object cache, session store, rate limiting.

Redis DB allocation (from AppOS_Database_Design.md §4):
  DB 0: Celery broker
  DB 1: Celery results
  DB 2: Permission cache (TTL=5min)
  DB 3: Object cache (TTL=10min)
  DB 4: Session store (TTL=session_timeout)
  DB 5: Rate limiting counters

All Redis data is ephemeral and reconstructible from PostgreSQL.
"""

from __future__ import annotations

import json
import logging
import time
from typing import Any, Dict, List, Optional, Set

logger = logging.getLogger("appos.engine.cache")


class RedisCache:
    """
    Redis cache wrapper with typed operations and circuit breaker.

    Supports:
    - Permission caching (DB 2)
    - Object metadata caching (DB 3)
    - Session store (DB 4)
    - Rate limiting (DB 5)

    Falls back to DB-only mode on Redis failure (circuit breaker pattern).
    """

    def __init__(
        self,
        redis_url: str = "redis://localhost:6379/0",
        prefix: str = "appos:",
        default_ttl: int = 300,
        db: int = 0,
    ):
        self._redis_url = redis_url
        self._prefix = prefix
        self._default_ttl = default_ttl
        self._db = db
        self._client = None
        self._available = False

        # Circuit breaker state
        self._failure_count = 0
        self._failure_threshold = 5
        self._failure_window = 30  # seconds
        self._first_failure_time = 0.0
        self._circuit_open = False

    def connect(self) -> bool:
        """Initialize Redis connection."""
        try:
            import redis
            # Parse base URL and override DB
            self._client = redis.Redis.from_url(
                self._redis_url,
                db=self._db,
                decode_responses=True,
                socket_timeout=5,
                socket_connect_timeout=5,
                retry_on_timeout=True,
            )
            self._client.ping()
            self._available = True
            self._circuit_open = False
            self._failure_count = 0
            logger.info(f"Redis connected: DB {self._db} ({self._prefix})")
            return True
        except Exception as e:
            logger.warning(f"Redis connection failed (DB {self._db}): {e}")
            self._available = False
            return False

    def _check_circuit(self) -> bool:
        """Check circuit breaker state."""
        if self._circuit_open:
            # Try to recover after window
            if time.time() - self._first_failure_time > self._failure_window:
                self._circuit_open = False
                self._failure_count = 0
                return self.connect()
            return False
        return self._available

    def _record_failure(self) -> None:
        """Record a Redis failure for circuit breaker."""
        now = time.time()
        if self._failure_count == 0:
            self._first_failure_time = now

        self._failure_count += 1

        if self._failure_count >= self._failure_threshold:
            elapsed = now - self._first_failure_time
            if elapsed <= self._failure_window:
                self._circuit_open = True
                logger.error(
                    f"Redis circuit breaker OPEN: {self._failure_count} failures in {elapsed:.1f}s"
                )

    def _make_key(self, key: str) -> str:
        """Build prefixed key."""
        return f"{self._prefix}{key}"

    # ── Core Operations ──

    def get(self, key: str) -> Optional[str]:
        """Get a value from cache. Returns None on miss or failure."""
        if not self._check_circuit():
            return None
        try:
            result = self._client.get(self._make_key(key))
            return result
        except Exception as e:
            self._record_failure()
            logger.debug(f"Redis GET failed: {e}")
            return None

    def set(self, key: str, value: str, ttl: Optional[int] = None) -> bool:
        """Set a value with optional TTL. Returns False on failure."""
        if not self._check_circuit():
            return False
        try:
            self._client.set(
                self._make_key(key),
                value,
                ex=ttl or self._default_ttl,
            )
            return True
        except Exception as e:
            self._record_failure()
            logger.debug(f"Redis SET failed: {e}")
            return False

    def delete(self, key: str) -> bool:
        """Delete a key."""
        if not self._check_circuit():
            return False
        try:
            self._client.delete(self._make_key(key))
            return True
        except Exception as e:
            self._record_failure()
            return False

    def delete_pattern(self, pattern: str) -> int:
        """Delete all keys matching a pattern. Returns count deleted."""
        if not self._check_circuit():
            return 0
        try:
            full_pattern = self._make_key(pattern)
            keys = list(self._client.scan_iter(match=full_pattern, count=1000))
            if keys:
                return self._client.delete(*keys)
            return 0
        except Exception as e:
            self._record_failure()
            return 0

    def exists(self, key: str) -> bool:
        """Check if a key exists."""
        if not self._check_circuit():
            return False
        try:
            return bool(self._client.exists(self._make_key(key)))
        except Exception:
            self._record_failure()
            return False

    # ── JSON Operations ──

    def get_json(self, key: str) -> Optional[Any]:
        """Get and deserialize a JSON value."""
        raw = self.get(key)
        if raw is None:
            return None
        try:
            return json.loads(raw)
        except json.JSONDecodeError:
            return None

    def set_json(self, key: str, value: Any, ttl: Optional[int] = None) -> bool:
        """Serialize and set a JSON value."""
        try:
            return self.set(key, json.dumps(value, default=str), ttl=ttl)
        except (TypeError, ValueError):
            return False

    # ── Set Operations (for session tracking) ──

    def sadd(self, key: str, *values: str) -> bool:
        """Add member(s) to a set."""
        if not self._check_circuit():
            return False
        try:
            self._client.sadd(self._make_key(key), *values)
            return True
        except Exception:
            self._record_failure()
            return False

    def srem(self, key: str, *values: str) -> bool:
        """Remove member(s) from a set."""
        if not self._check_circuit():
            return False
        try:
            self._client.srem(self._make_key(key), *values)
            return True
        except Exception:
            self._record_failure()
            return False

    def smembers(self, key: str) -> Set[str]:
        """Get all set members."""
        if not self._check_circuit():
            return set()
        try:
            return self._client.smembers(self._make_key(key))
        except Exception:
            self._record_failure()
            return set()

    def scard(self, key: str) -> int:
        """Get set cardinality."""
        if not self._check_circuit():
            return 0
        try:
            return self._client.scard(self._make_key(key))
        except Exception:
            self._record_failure()
            return 0

    # ── Counter Operations (for rate limiting) ──

    def incr(self, key: str, ttl: Optional[int] = None) -> int:
        """Increment a counter. Returns new value or -1 on failure."""
        if not self._check_circuit():
            return -1
        try:
            full_key = self._make_key(key)
            pipe = self._client.pipeline()
            pipe.incr(full_key)
            if ttl:
                pipe.expire(full_key, ttl)
            results = pipe.execute()
            return results[0]
        except Exception:
            self._record_failure()
            return -1

    # ── Health & Management ──

    def ping(self) -> bool:
        """Health check."""
        if not self._client:
            return False
        try:
            return self._client.ping()
        except Exception:
            return False

    def flush_db(self) -> bool:
        """Flush the current database."""
        if not self._check_circuit():
            return False
        try:
            self._client.flushdb()
            return True
        except Exception:
            self._record_failure()
            return False

    def close(self) -> None:
        """Close the Redis connection and release resources."""
        if self._client is not None:
            try:
                self._client.close()
            except Exception:
                pass
            self._client = None
        self._available = False
        self._circuit_open = False
        self._failure_count = 0

    @property
    def is_available(self) -> bool:
        return self._available and not self._circuit_open

    @property
    def is_circuit_open(self) -> bool:
        return self._circuit_open


# ---------------------------------------------------------------------------
# Permission Cache — Specialized wrapper for permission checks
# ---------------------------------------------------------------------------

class PermissionCache:
    """
    Permission-specific cache operations using Redis DB 2.

    Key format: appos:perms:{groups_hash}:{object_ref}:{permission}
    Value: "1" (allowed) | "0" (denied)
    TTL: 300s (5 minutes)
    """

    def __init__(self, cache: RedisCache):
        self._cache = cache

    def _make_perm_key(self, groups: frozenset, object_ref: str, permission: str) -> str:
        """Build permission cache key."""
        groups_hash = hash(groups) & 0xFFFFFFFF  # Positive 32-bit hash
        return f"perms:{groups_hash:08x}:{object_ref}:{permission}"

    def check(self, groups: frozenset, object_ref: str, permission: str) -> Optional[bool]:
        """
        Check cached permission. Returns True/False from cache, or None on miss.
        """
        key = self._make_perm_key(groups, object_ref, permission)
        result = self._cache.get(key)
        if result is None:
            return None
        return result == "1"

    def store(self, groups: frozenset, object_ref: str, permission: str, allowed: bool) -> None:
        """Cache a permission check result."""
        key = self._make_perm_key(groups, object_ref, permission)
        self._cache.set(key, "1" if allowed else "0")

    def invalidate_all(self) -> int:
        """Invalidate all permission cache entries."""
        return self._cache.delete_pattern("perms:*")

    def invalidate_for_group(self, group_name: str) -> int:
        """Invalidate all permissions for any group set containing this group."""
        # Since group_name is hashed into the key, we must flush all
        return self.invalidate_all()

    def invalidate_for_object(self, object_ref: str) -> int:
        """Invalidate all permissions for a specific object."""
        return self._cache.delete_pattern(f"perms:*:{object_ref}:*")


# ---------------------------------------------------------------------------
# Factory functions for creating cache instances per Redis DB
# ---------------------------------------------------------------------------

def create_permission_cache(redis_url: str, ttl: int = 300) -> PermissionCache:
    """Create permission cache (Redis DB 2)."""
    cache = RedisCache(redis_url=redis_url, prefix="appos:", default_ttl=ttl, db=2)
    cache.connect()
    return PermissionCache(cache)


def create_object_cache(redis_url: str, ttl: int = 600) -> RedisCache:
    """Create object cache (Redis DB 3)."""
    cache = RedisCache(redis_url=redis_url, prefix="appos:obj:", default_ttl=ttl, db=3)
    cache.connect()
    return cache


def create_session_store(redis_url: str, ttl: int = 3600) -> RedisCache:
    """Create session store (Redis DB 4)."""
    cache = RedisCache(redis_url=redis_url, prefix="appos:session:", default_ttl=ttl, db=4)
    cache.connect()
    return cache


def create_rate_limiter(redis_url: str) -> RedisCache:
    """Create rate limiting cache (Redis DB 5)."""
    cache = RedisCache(redis_url=redis_url, prefix="appos:rate:", default_ttl=60, db=5)
    cache.connect()
    return cache
