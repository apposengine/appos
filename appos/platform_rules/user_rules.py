"""
AppOS Platform Rules — Prebuilt expression rules for user/group management.

Available globally via `platform.rules` namespace. No import needed.

Security:
- get_current_user() — any authenticated user
- change_password() — self only (user_id must match ctx.user_id)
- All others — system_admin required

Design refs: AppOS_Design.md §8 Prebuilt Platform Rules, AppOS_PlatformRules_Reference.md
"""

from __future__ import annotations

import logging
from datetime import datetime, timezone
from typing import Any, Dict, List, Optional

from appos.engine.context import get_execution_context
from appos.engine.errors import AppOSSecurityError, AppOSValidationError
from appos.engine.security import hash_password, verify_password

logger = logging.getLogger("appos.platform_rules")


def _require_admin() -> None:
    """Raise if current user is not system_admin."""
    ctx = get_execution_context()
    if ctx is None or ctx.user_type != "system_admin":
        raise AppOSSecurityError(
            "system_admin access required",
            user_id=getattr(ctx, "user_id", None),
        )


def _get_session():
    """Get a platform DB session. Caller must close."""
    from appos.db.session import get_platform_session
    return get_platform_session()


# ---------------------------------------------------------------------------
# User rules
# ---------------------------------------------------------------------------

def get_current_user() -> Dict[str, Any]:
    """Returns current user details. Any authenticated user."""
    ctx = get_execution_context()
    if ctx is None:
        raise AppOSSecurityError("Not authenticated")

    from appos.db.platform_models import User

    session = _get_session()
    try:
        user = session.query(User).get(ctx.user_id)
        if user is None:
            return {}
        return {
            "id": user.id,
            "username": user.username,
            "email": user.email,
            "full_name": user.full_name,
            "user_type": user.user_type,
            "preferred_language": user.preferred_language,
            "timezone": user.timezone,
            "groups": [g.name for g in user.groups],
        }
    finally:
        session.close()


def get_user(user_id: int) -> Dict[str, Any]:
    """Returns user by ID. system_admin required."""
    _require_admin()

    from appos.db.platform_models import User

    session = _get_session()
    try:
        user = session.query(User).get(user_id)
        if user is None:
            return {}
        return {
            "id": user.id,
            "username": user.username,
            "email": user.email,
            "full_name": user.full_name,
            "user_type": user.user_type,
            "is_active": user.is_active,
            "preferred_language": user.preferred_language,
            "timezone": user.timezone,
            "last_login": user.last_login.isoformat() if user.last_login else None,
            "groups": [g.name for g in user.groups],
        }
    finally:
        session.close()


def get_user_groups(user_id: int) -> List[str]:
    """Returns list of group names for a user. system_admin required."""
    _require_admin()

    from appos.db.platform_models import User

    session = _get_session()
    try:
        user = session.query(User).get(user_id)
        return [g.name for g in user.groups] if user else []
    finally:
        session.close()


def get_group_members(group_name: str) -> List[Dict[str, Any]]:
    """Returns list of users in a group. system_admin required."""
    _require_admin()

    from appos.db.platform_models import Group

    session = _get_session()
    try:
        group = session.query(Group).filter_by(name=group_name).first()
        if group is None:
            return []
        return [
            {
                "id": u.id,
                "username": u.username,
                "full_name": u.full_name,
                "user_type": u.user_type,
            }
            for u in group.users
            if u.is_active
        ]
    finally:
        session.close()


def create_user(
    username: str,
    email: str,
    full_name: str,
    password: str,
    user_type: str = "basic",
    groups: Optional[List[str]] = None,
) -> Dict[str, Any]:
    """Create a new user. system_admin required."""
    _require_admin()

    from appos.db.platform_models import Group, User, UserGroup

    if user_type not in ("basic", "system_admin", "service_account"):
        raise AppOSValidationError(f"Invalid user_type: {user_type}")

    session = _get_session()
    try:
        # Check uniqueness
        existing = session.query(User).filter(
            (User.username == username) | (User.email == email)
        ).first()
        if existing:
            raise AppOSValidationError(
                f"User already exists with username '{username}' or email '{email}'"
            )

        user = User(
            username=username,
            email=email,
            full_name=full_name,
            password_hash=hash_password(password),
            user_type=user_type,
            is_active=True,
        )
        session.add(user)
        session.flush()

        # Assign groups
        if groups:
            for gname in groups:
                g = session.query(Group).filter_by(name=gname).first()
                if g:
                    session.add(UserGroup(user_id=user.id, group_id=g.id))

        session.commit()
        logger.info(f"Created user: {username} (type: {user_type})")

        return {"id": user.id, "username": user.username}

    except Exception:
        session.rollback()
        raise
    finally:
        session.close()


def update_user(user_id: int, fields: Dict[str, Any]) -> Dict[str, Any]:
    """Update user fields. system_admin required."""
    _require_admin()

    from appos.db.platform_models import User

    ALLOWED = {"email", "full_name", "is_active", "user_type", "preferred_language", "timezone"}

    session = _get_session()
    try:
        user = session.query(User).get(user_id)
        if user is None:
            raise AppOSValidationError(f"User {user_id} not found")

        for key, value in fields.items():
            if key in ALLOWED:
                setattr(user, key, value)

        session.commit()
        return {"id": user.id, "username": user.username, "updated": list(fields.keys())}

    except Exception:
        session.rollback()
        raise
    finally:
        session.close()


def add_user_to_group(user_id: int, group_name: str) -> bool:
    """Add a user to a group. system_admin required."""
    _require_admin()

    from appos.db.platform_models import Group, UserGroup

    session = _get_session()
    try:
        group = session.query(Group).filter_by(name=group_name).first()
        if group is None:
            raise AppOSValidationError(f"Group not found: {group_name}")

        existing = session.query(UserGroup).filter_by(
            user_id=user_id, group_id=group.id
        ).first()
        if existing:
            return True  # Already a member

        session.add(UserGroup(user_id=user_id, group_id=group.id))
        session.commit()
        return True

    except Exception:
        session.rollback()
        raise
    finally:
        session.close()


def remove_user_from_group(user_id: int, group_name: str) -> bool:
    """Remove a user from a group. system_admin required."""
    _require_admin()

    from appos.db.platform_models import Group, UserGroup

    session = _get_session()
    try:
        group = session.query(Group).filter_by(name=group_name).first()
        if group is None:
            raise AppOSValidationError(f"Group not found: {group_name}")

        membership = session.query(UserGroup).filter_by(
            user_id=user_id, group_id=group.id
        ).first()
        if membership:
            session.delete(membership)
            session.commit()

        return True

    except Exception:
        session.rollback()
        raise
    finally:
        session.close()


def change_password(user_id: int, old_password: str, new_password: str) -> bool:
    """
    Change a user's password.
    Self only — user_id must match ctx.user_id (unless system_admin).
    """
    ctx = get_execution_context()
    if ctx is None:
        raise AppOSSecurityError("Not authenticated")

    # Self-change or admin
    if ctx.user_id != user_id and ctx.user_type != "system_admin":
        raise AppOSSecurityError(
            "Can only change your own password",
            user_id=ctx.user_id,
        )

    from appos.db.platform_models import User

    session = _get_session()
    try:
        user = session.query(User).get(user_id)
        if user is None:
            raise AppOSValidationError(f"User {user_id} not found")

        # Verify old password (not required for admin)
        if ctx.user_type != "system_admin":
            if not verify_password(old_password, user.password_hash):
                raise AppOSSecurityError("Current password is incorrect")

        if len(new_password) < 8:
            raise AppOSValidationError("Password must be at least 8 characters")

        user.password_hash = hash_password(new_password)
        session.commit()
        return True

    except Exception:
        session.rollback()
        raise
    finally:
        session.close()


# ---------------------------------------------------------------------------
# Group rules
# ---------------------------------------------------------------------------

def create_group(
    name: str,
    description: str = "",
    group_type: str = "security",
    apps: Optional[List[str]] = None,
    users: Optional[List[int]] = None,
) -> Dict[str, Any]:
    """Create a new group. system_admin required."""
    _require_admin()

    from appos.db.platform_models import App, Group, GroupApp, UserGroup

    session = _get_session()
    try:
        existing = session.query(Group).filter_by(name=name).first()
        if existing:
            raise AppOSValidationError(f"Group already exists: {name}")

        group = Group(
            name=name,
            type=group_type,
            description=description,
            is_active=True,
        )
        session.add(group)
        session.flush()

        # Assign apps
        if apps:
            for app_name in apps:
                app = session.query(App).filter_by(short_name=app_name).first()
                if app:
                    session.add(GroupApp(group_id=group.id, app_id=app.id))

        # Assign users
        if users:
            for uid in users:
                session.add(UserGroup(user_id=uid, group_id=group.id))

        session.commit()
        return {"id": group.id, "name": group.name}

    except Exception:
        session.rollback()
        raise
    finally:
        session.close()
