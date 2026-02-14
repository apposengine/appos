"""
AppOS Admin Console — Reflex State for authentication and session management.

Provides:
- AdminState: Login/logout state, session management
- Middleware hook for auth checks on admin routes
"""

from __future__ import annotations

import logging
from typing import Any, Dict, List, Optional

import reflex as rx

logger = logging.getLogger("appos.admin.state")


class AdminState(rx.State):
    """
    Main admin console state.

    Manages:
    - Authentication (login/logout)
    - Session info (username, user_type, groups)
    - Navigation state
    """

    # Auth state
    is_authenticated: bool = False
    username: str = ""
    full_name: str = ""
    user_type: str = ""
    user_groups: list[str] = []
    session_id: str = ""
    csrf_token: str = ""

    # UI state
    login_error: str = ""
    is_loading: bool = False

    # Data holders for admin pages
    users: list[dict] = []
    groups: list[dict] = []
    apps: list[dict] = []

    def login(self, form_data: dict) -> rx.event.EventSpec | None:
        """Handle login form submission."""
        self.is_loading = True
        self.login_error = ""

        username = form_data.get("username", "").strip()
        password = form_data.get("password", "")

        if not username or not password:
            self.login_error = "Username and password are required"
            self.is_loading = False
            return None

        try:
            from appos.engine.runtime import CentralizedRuntime

            # Get runtime (needs to be initialized at app startup)
            runtime = _get_runtime()
            if runtime is None or runtime.auth is None:
                self.login_error = "Platform not initialized. Run: appos init"
                self.is_loading = False
                return None

            result = runtime.auth.authenticate(
                username=username,
                password=password,
            )

            # Must be system_admin for admin console
            if result["user_type"] != "system_admin":
                self.login_error = "Admin console requires system_admin access"
                self.is_loading = False
                return None

            # Set state
            self.is_authenticated = True
            self.username = result["username"]
            self.full_name = result.get("full_name", "")
            self.user_type = result["user_type"]
            self.user_groups = result.get("groups", [])
            self.session_id = result["session_id"]
            self.csrf_token = result["csrf_token"]
            self.login_error = ""
            self.is_loading = False

            return rx.redirect("/admin/dashboard")

        except Exception as e:
            self.login_error = str(e)
            self.is_loading = False
            return None

    def logout(self) -> rx.event.EventSpec:
        """Handle logout."""
        try:
            runtime = _get_runtime()
            if runtime and runtime.auth and self.session_id:
                runtime.auth.logout(self.session_id)
        except Exception:
            pass

        self.is_authenticated = False
        self.username = ""
        self.full_name = ""
        self.user_type = ""
        self.user_groups = []
        self.session_id = ""
        self.csrf_token = ""

        return rx.redirect("/admin/login")

    def check_auth(self) -> rx.event.EventSpec | None:
        """Check if user is authenticated. Redirect to login if not."""
        if not self.is_authenticated:
            return rx.redirect("/admin/login")
        return None

    def load_users(self) -> None:
        """Load users list for admin UI."""
        try:
            runtime = _get_runtime()
            if runtime is None:
                return

            from appos.db.platform_models import User

            session = runtime._db_session_factory()
            try:
                users = session.query(User).order_by(User.username).all()
                self.users = [
                    {
                        "id": u.id,
                        "username": u.username,
                        "email": u.email,
                        "full_name": u.full_name,
                        "user_type": u.user_type,
                        "is_active": u.is_active,
                        "last_login": u.last_login.isoformat() if u.last_login else None,
                    }
                    for u in users
                ]
            finally:
                session.close()
        except Exception as e:
            logger.error(f"Failed to load users: {e}")

    def load_groups(self) -> None:
        """Load groups list for admin UI."""
        try:
            runtime = _get_runtime()
            if runtime is None:
                return

            from appos.db.platform_models import Group

            session = runtime._db_session_factory()
            try:
                groups = session.query(Group).order_by(Group.name).all()
                self.groups = [
                    {
                        "id": g.id,
                        "name": g.name,
                        "type": g.type,
                        "description": g.description,
                        "is_active": g.is_active,
                    }
                    for g in groups
                ]
            finally:
                session.close()
        except Exception as e:
            logger.error(f"Failed to load groups: {e}")

    def load_apps(self) -> None:
        """Load apps list for admin UI."""
        try:
            runtime = _get_runtime()
            if runtime is None:
                return

            from appos.db.platform_models import App

            session = runtime._db_session_factory()
            try:
                apps = session.query(App).order_by(App.short_name).all()
                self.apps = [
                    {
                        "id": a.id,
                        "name": a.name,
                        "short_name": a.short_name,
                        "version": a.version,
                        "is_active": a.is_active,
                    }
                    for a in apps
                ]
            finally:
                session.close()
        except Exception as e:
            logger.error(f"Failed to load apps: {e}")

    def create_app(self, form_data: dict) -> None:
        """Create a new app from the registration form."""
        name = form_data.get("name", "").strip()
        short_name = form_data.get("short_name", "").strip().lower()
        version = form_data.get("version", "1.0.0").strip()
        description = form_data.get("description", "").strip()

        if not name or not short_name:
            return

        try:
            runtime = _get_runtime()
            if runtime is None:
                return

            from appos.db.platform_models import App

            session = runtime._db_session_factory()
            try:
                app = App(
                    name=name,
                    short_name=short_name,
                    version=version,
                    description=description,
                    is_active=True,
                )
                session.add(app)
                session.commit()
            finally:
                session.close()

            # Reload apps list
            self.load_apps()
        except Exception as e:
            logger.error(f"Failed to create app: {e}")


# ---------------------------------------------------------------------------
# Runtime singleton accessor
# ---------------------------------------------------------------------------

_runtime_instance = None


def set_runtime(runtime: Any) -> None:
    """Set the global runtime reference for admin state."""
    global _runtime_instance
    _runtime_instance = runtime


def _get_runtime() -> Any:
    """Get the global runtime instance."""
    return _runtime_instance
