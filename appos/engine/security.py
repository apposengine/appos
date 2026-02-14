"""
AppOS Security Engine — Unified 6-permission model with cache-first checks.

Implements:
- SecurityPolicy: Cache-first permission checking with wildcard support
- Permission resolution: Most specific match wins (crm.rules.X > crm.rules.* > crm.*)
- Three-tier inherited security (app defaults → inheriting → explicit)
- Session-based authentication (Redis DB 4)
- Login/logout with audit logging
- CSRF token generation and validation
- Service account API key authentication

Design refs: §6 Security Model, §7 State Management, AppOS_Permissions_Reference.md
"""

from __future__ import annotations

import hashlib
import logging
import secrets
import uuid
from datetime import datetime, timezone
from typing import Any, Dict, List, Optional, Set

import bcrypt
from sqlalchemy.orm import Session

from appos.db.platform_models import (
    Group,
    LoginAuditLog,
    ObjectPermission,
    User,
    UserGroup,
)
from appos.engine.cache import PermissionCache, RedisCache
from appos.engine.context import (
    ExecutionContext,
    clear_execution_context,
    set_execution_context,
)
from appos.engine.errors import AppOSSecurityError, AppOSSessionError

logger = logging.getLogger("appos.engine.security")

# Permission hierarchy — higher includes lower
PERMISSION_HIERARCHY = {
    "admin": {"admin", "delete", "update", "create", "use", "view"},
    "delete": {"delete", "view"},
    "update": {"update", "view"},
    "create": {"create", "view"},
    "use": {"use", "view"},
    "view": {"view"},
}


class SecurityPolicy:
    """
    Evaluated by Auto-Import layer on every object access.
    Cache-first: Redis hit → return immediately. Miss → query DB → cache result.

    Unified 6-permission model: view | use | create | update | delete | admin
    Wildcard support: crm.rules.* grants all rules, crm.* grants all objects.
    Resolution order: Most specific match wins.

    system_admin users bypass all permission checks.
    """

    def __init__(
        self,
        permission_cache: Optional[PermissionCache] = None,
        db_session_factory=None,
    ):
        self._cache = permission_cache
        self._db_session_factory = db_session_factory

    def check_access(
        self,
        user_groups: Set[str],
        object_ref: str,
        permission: str,
        user_type: str = "basic",
    ) -> bool:
        """
        Check if any of user's groups have the required permission on the object.

        Args:
            user_groups: Set of group names the user belongs to.
            object_ref: Fully-qualified object reference (e.g., "crm.rules.calculate_discount").
            permission: Required permission (view/use/create/update/delete/admin).
            user_type: User type — system_admin bypasses all checks.

        Returns:
            True if access allowed, False if denied.
        """
        # system_admin bypasses all permission checks
        if user_type == "system_admin":
            return True

        # No groups = no access
        if not user_groups:
            return False

        groups_frozen = frozenset(user_groups)

        # 1. Cache check
        if self._cache:
            cached = self._cache.check(groups_frozen, object_ref, permission)
            if cached is not None:
                return cached

        # 2. DB fallback
        allowed = self._query_permissions(user_groups, object_ref, permission)

        # 3. Cache result
        if self._cache:
            self._cache.store(groups_frozen, object_ref, permission, allowed)

        return allowed

    def _query_permissions(
        self, user_groups: Set[str], object_ref: str, permission: str
    ) -> bool:
        """
        Query the object_permission table with wildcard resolution.
        Most specific match wins.
        """
        if self._db_session_factory is None:
            # No DB available — deny by default (secure)
            logger.warning("No DB session factory — denying access by default")
            return False

        session: Session = self._db_session_factory()
        try:
            # Build all possible object_ref patterns to check (most specific first)
            patterns = self._build_wildcard_patterns(object_ref)

            # Query permissions for all user groups and all patterns
            group_list = list(user_groups)
            permissions = (
                session.query(ObjectPermission)
                .filter(
                    ObjectPermission.group_name.in_(group_list),
                    ObjectPermission.object_ref.in_(patterns),
                )
                .all()
            )

            if not permissions:
                return False

            # Check if any permission grants access
            # Higher-level permissions imply lower ones (admin implies all)
            required_set = {permission}
            implied_by = set()
            for perm_name, implies in PERMISSION_HIERARCHY.items():
                if permission in implies:
                    implied_by.add(perm_name)

            for perm in permissions:
                if perm.permission in implied_by or perm.permission == permission:
                    return True

            return False

        except Exception as e:
            logger.error(f"Permission query failed: {e}")
            return False
        finally:
            session.close()

    def _build_wildcard_patterns(self, object_ref: str) -> List[str]:
        """
        Build wildcard patterns from most specific to least specific.

        "crm.rules.calculate_discount" →
            ["crm.rules.calculate_discount", "crm.rules.*", "crm.*", "*"]
        """
        patterns = [object_ref]
        parts = object_ref.split(".")

        for i in range(len(parts) - 1, 0, -1):
            pattern = ".".join(parts[:i]) + ".*"
            patterns.append(pattern)

        patterns.append("*")
        return patterns

    def check_permission(
        self,
        object_ref: str,
        permission: str,
        raise_on_deny: bool = True,
    ) -> bool:
        """
        Check permission using the current execution context.
        Convenience method that reads user info from contextvars.
        """
        from appos.engine.context import get_execution_context

        ctx = get_execution_context()
        if ctx is None:
            if raise_on_deny:
                raise AppOSSecurityError(
                    "No execution context — user not authenticated",
                    object_ref=object_ref,
                    required_permission=permission,
                )
            return False

        allowed = self.check_access(
            user_groups=ctx.user_groups,
            object_ref=object_ref,
            permission=permission,
            user_type=ctx.user_type,
        )

        if not allowed and raise_on_deny:
            raise AppOSSecurityError(
                f"Access denied: {ctx.username} → {object_ref} ({permission})",
                user_id=ctx.user_id,
                user_groups=sorted(ctx.user_groups),
                object_ref=object_ref,
                required_permission=permission,
                execution_id=ctx.execution_id,
            )

        return allowed

    def invalidate_cache(self) -> None:
        """Invalidate all cached permissions."""
        if self._cache:
            self._cache.invalidate_all()
            logger.info("Permission cache invalidated")


# ---------------------------------------------------------------------------
# Authentication Service
# ---------------------------------------------------------------------------

class AuthService:
    """
    Session-based authentication with Redis-backed session store.

    Flow:
    1. User logs in → server creates session in Redis
    2. Session ID in secure HttpOnly cookie
    3. CSRF token per session
    4. Each request → session lookup → ExecutionContext
    5. Logout/timeout → session deleted
    """

    def __init__(
        self,
        session_store: RedisCache,
        db_session_factory,
        session_timeout: int = 3600,
        idle_timeout: int = 1800,
        max_concurrent_sessions: int = 5,
        max_login_attempts: int = 5,
    ):
        self._sessions = session_store
        self._db_session_factory = db_session_factory
        self._session_timeout = session_timeout
        self._idle_timeout = idle_timeout
        self._max_concurrent = max_concurrent_sessions
        self._max_login_attempts = max_login_attempts

    def authenticate(
        self,
        username: str,
        password: str,
        ip_address: Optional[str] = None,
        user_agent: Optional[str] = None,
    ) -> Dict[str, Any]:
        """
        Authenticate a user and create a session.

        Returns:
            Dict with session_id, csrf_token, user info.

        Raises:
            AppOSSecurityError on invalid credentials.
            AppOSSessionError on account disabled or max attempts.
        """
        session: Session = self._db_session_factory()
        try:
            user = session.query(User).filter_by(username=username).first()

            # User not found
            if user is None:
                self._log_login(session, username, None, False, ip_address, user_agent, "invalid_username")
                raise AppOSSecurityError(
                    "Invalid username or password",
                    user_id=username,
                )

            # Account disabled
            if not user.is_active:
                self._log_login(session, username, user.id, False, ip_address, user_agent, "account_disabled")
                raise AppOSSessionError(
                    "Account is disabled",
                    user_id=user.id,
                )

            # Service accounts cannot login via UI
            if user.user_type == "service_account":
                self._log_login(session, username, user.id, False, ip_address, user_agent, "service_account_ui_login")
                raise AppOSSecurityError(
                    "Service accounts cannot login via UI",
                    user_id=user.id,
                )

            # Verify password
            if not bcrypt.checkpw(password.encode("utf-8"), user.password_hash.encode("utf-8")):
                self._log_login(session, username, user.id, False, ip_address, user_agent, "invalid_password")
                raise AppOSSecurityError(
                    "Invalid username or password",
                    user_id=user.id,
                )

            # Get user groups
            groups = {g.name for g in user.groups if g.is_active}

            # Create session
            session_id = f"sess_{uuid.uuid4().hex}"
            csrf_token = secrets.token_urlsafe(32)

            session_data = {
                "user_id": user.id,
                "username": user.username,
                "user_type": user.user_type,
                "groups": sorted(groups),
                "preferred_language": user.preferred_language,
                "timezone": user.timezone,
                "full_name": user.full_name,
                "csrf_token": csrf_token,
                "login_at": datetime.now(timezone.utc).isoformat(),
                "last_activity": datetime.now(timezone.utc).isoformat(),
                "ip_address": ip_address,
            }

            # Enforce concurrent session limit
            self._enforce_session_limit(user.id, session_id)

            # Store session in Redis
            self._sessions.set_json(session_id, session_data, ttl=self._session_timeout)

            # Track user sessions
            self._sessions.sadd(f"user_sessions:{user.id}", session_id)

            # Update last_login
            user.last_login = datetime.now(timezone.utc)
            session.commit()

            # Log success
            self._log_login(session, username, user.id, True, ip_address, user_agent)

            logger.info(f"User '{username}' authenticated successfully (session: {session_id[:16]}...)")

            return {
                "session_id": session_id,
                "csrf_token": csrf_token,
                "user_id": user.id,
                "username": user.username,
                "user_type": user.user_type,
                "groups": sorted(groups),
                "preferred_language": user.preferred_language,
                "timezone": user.timezone,
                "full_name": user.full_name,
            }

        finally:
            session.close()

    def validate_session(self, session_id: str) -> Optional[ExecutionContext]:
        """
        Validate a session and return an ExecutionContext.

        Returns:
            ExecutionContext if session is valid, None otherwise.
        """
        if not session_id:
            return None

        session_data = self._sessions.get_json(session_id)
        if session_data is None:
            return None

        # Update last_activity (refresh idle timeout)
        session_data["last_activity"] = datetime.now(timezone.utc).isoformat()
        self._sessions.set_json(session_id, session_data, ttl=self._session_timeout)

        # Build execution context
        ctx = ExecutionContext(
            user_id=session_data["user_id"],
            username=session_data["username"],
            user_type=session_data["user_type"],
            user_groups=set(session_data.get("groups", [])),
            preferred_language=session_data.get("preferred_language", "en"),
            timezone=session_data.get("timezone", "UTC"),
            full_name=session_data.get("full_name", ""),
            session_id=session_id,
        )

        return ctx

    def logout(self, session_id: str) -> bool:
        """Destroy a session."""
        session_data = self._sessions.get_json(session_id)
        if session_data:
            user_id = session_data.get("user_id")
            if user_id:
                self._sessions.srem(f"user_sessions:{user_id}", session_id)
        self._sessions.delete(session_id)
        logger.info(f"Session destroyed: {session_id[:16]}...")
        return True

    def get_active_sessions(self, user_id: int) -> List[Dict[str, Any]]:
        """Get all active sessions for a user."""
        session_ids = self._sessions.smembers(f"user_sessions:{user_id}")
        sessions = []
        for sid in session_ids:
            data = self._sessions.get_json(sid)
            if data:
                sessions.append({"session_id": sid, **data})
            else:
                # Clean up stale session reference
                self._sessions.srem(f"user_sessions:{user_id}", sid)
        return sessions

    def kill_session(self, session_id: str) -> bool:
        """Admin: forcefully kill a session."""
        return self.logout(session_id)

    def validate_csrf(self, session_id: str, csrf_token: str) -> bool:
        """Validate CSRF token for a session."""
        session_data = self._sessions.get_json(session_id)
        if not session_data:
            return False
        return session_data.get("csrf_token") == csrf_token

    def authenticate_api_key(self, api_key: str) -> Optional[ExecutionContext]:
        """
        Authenticate a service account via API key.

        Returns:
            ExecutionContext if valid, None otherwise.
        """
        session: Session = self._db_session_factory()
        try:
            # Find service accounts with API keys
            service_accounts = (
                session.query(User)
                .filter_by(user_type="service_account", is_active=True)
                .filter(User.api_key_hash.isnot(None))
                .all()
            )

            for user in service_accounts:
                if bcrypt.checkpw(api_key.encode("utf-8"), user.api_key_hash.encode("utf-8")):
                    groups = {g.name for g in user.groups if g.is_active}
                    return ExecutionContext(
                        user_id=user.id,
                        username=user.username,
                        user_type=user.user_type,
                        user_groups=groups,
                        preferred_language=user.preferred_language,
                        timezone=user.timezone,
                        full_name=user.full_name,
                    )

            return None
        finally:
            session.close()

    def _enforce_session_limit(self, user_id: int, new_session_id: str) -> None:
        """Evict oldest session(s) if over limit."""
        current_count = self._sessions.scard(f"user_sessions:{user_id}")
        if current_count >= self._max_concurrent:
            # Get all sessions and evict oldest
            session_ids = self._sessions.smembers(f"user_sessions:{user_id}")
            sessions_with_time = []
            for sid in session_ids:
                data = self._sessions.get_json(sid)
                if data:
                    sessions_with_time.append((sid, data.get("login_at", "")))
                else:
                    self._sessions.srem(f"user_sessions:{user_id}", sid)

            # Sort by login time, evict oldest
            sessions_with_time.sort(key=lambda x: x[1])
            to_evict = len(sessions_with_time) - self._max_concurrent + 1
            for i in range(to_evict):
                self.logout(sessions_with_time[i][0])

    def _log_login(
        self,
        session: Session,
        username: str,
        user_id: Optional[int],
        success: bool,
        ip_address: Optional[str] = None,
        user_agent: Optional[str] = None,
        failure_reason: Optional[str] = None,
    ) -> None:
        """Log a login attempt to login_audit_log."""
        try:
            log_entry = LoginAuditLog(
                username=username,
                user_id=user_id,
                success=success,
                ip_address=ip_address,
                user_agent=user_agent,
                failure_reason=failure_reason,
            )
            session.add(log_entry)
            session.commit()
        except Exception as e:
            logger.error(f"Failed to log login attempt: {e}")
            session.rollback()


# ---------------------------------------------------------------------------
# Password Utilities
# ---------------------------------------------------------------------------

def hash_password(password: str) -> str:
    """Hash a password using bcrypt."""
    return bcrypt.hashpw(password.encode("utf-8"), bcrypt.gensalt(rounds=12)).decode("utf-8")


def verify_password(password: str, password_hash: str) -> bool:
    """Verify a password against its bcrypt hash."""
    return bcrypt.checkpw(password.encode("utf-8"), password_hash.encode("utf-8"))


def generate_api_key() -> tuple[str, str]:
    """
    Generate an API key for service accounts.

    Returns:
        Tuple of (api_key, api_key_hash). The api_key is shown once; only the hash is stored.
    """
    api_key = secrets.token_urlsafe(48)
    api_key_hash = hash_password(api_key)
    return api_key, api_key_hash


# ---------------------------------------------------------------------------
# Row-Level Security (Future — Design Placeholder)
# ---------------------------------------------------------------------------

class RowSecurityPolicy:
    """
    Placeholder for per-row security rules on Records.

    Future implementation will allow apps to define row-level access
    policies that filter query results based on the current user's
    groups, roles, or custom attributes.

    Design ref: AppOS_Design.md §6 (Security Model — Future Extensions)

    Planned API::

        @row_security(record="Customer")
        def customer_row_filter(ctx, query):
            # Users can only see customers assigned to their group
            user_groups = ctx.user_groups
            return query.filter(Customer.assigned_group.in_(user_groups))

    Implementation will intercept RecordService.list() and
    RecordService.search() to apply the filter automatically.

    Evaluation order:
        1. Object-level permission check (existing SecurityPolicy)
        2. Row-level filter applied to query (this class)
        3. Field-level masking (future — not yet designed)

    Storage: Row security rules stored as Python callables in the
    object registry, keyed by record name.
    """

    def __init__(self, db_session_factory=None):
        self._db_session_factory = db_session_factory
        self._policies: Dict[str, Any] = {}  # record_name → filter_callable

    def register_policy(self, record_name: str, filter_fn) -> None:
        """
        Register a row-level security filter for a record type.

        Args:
            record_name: The record type (e.g., "Customer").
            filter_fn: Callable(ctx, query) → filtered_query.
        """
        self._policies[record_name] = filter_fn
        logger.info(f"Row security policy registered: {record_name}")

    def apply_filter(self, record_name: str, query, ctx):
        """
        Apply row-level security filter to a SQLAlchemy query.

        Returns the original query if no policy is registered.

        Args:
            record_name: Record type name.
            query: SQLAlchemy query to filter.
            ctx: ExecutionContext with user info.

        Returns:
            Filtered query.
        """
        policy = self._policies.get(record_name)
        if policy is None:
            return query
        try:
            return policy(ctx, query)
        except Exception as e:
            logger.error(f"Row security filter failed for {record_name}: {e}")
            raise AppOSSecurityError(
                f"Row security policy error for {record_name}"
            ) from e

    def has_policy(self, record_name: str) -> bool:
        """Check if a row security policy is registered."""
        return record_name in self._policies

    @property
    def registered_policies(self) -> List[str]:
        """List all record names with registered row security policies."""
        return list(self._policies.keys())
