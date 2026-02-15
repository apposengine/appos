"""
AppOS Admin Console — Active Sessions Page

Route: /admin/sessions
Purpose: View active user sessions, kill sessions, flush Redis cache.
Design ref: AppOS_Design.md §13 (Admin Console → Active Sessions)
"""

import reflex as rx

from appos.admin.components.layout import admin_layout
from appos.admin.state import AdminState


class SessionsState(rx.State):
    """State for the active sessions management page."""

    # Active sessions from Redis
    sessions: list[dict] = []
    total_sessions: int = 0

    # Cache stats
    cache_keys: int = 0
    cache_memory: str = "—"

    # Feedback
    action_message: str = ""

    def load_sessions(self) -> None:
        """Load active sessions from Redis session store."""
        try:
            from appos.admin.state import _get_runtime

            runtime = _get_runtime()
            if runtime is None:
                return

            if runtime.session_store is None:
                self.sessions = []
                return

            import json

            # Scan Redis for session keys (session:*)
            store = runtime.session_store
            session_keys = store.scan_keys("session:*")
            active = []
            for key in session_keys:
                data = store.get(key)
                if data:
                    try:
                        info = json.loads(data) if isinstance(data, str) else data
                        active.append({
                            "session_id": key.replace("session:", ""),
                            "username": info.get("username", "—"),
                            "user_type": info.get("user_type", "—"),
                            "created_at": info.get("created_at", "—"),
                            "ip_address": info.get("ip_address", "—"),
                            "last_activity": info.get("last_activity", "—"),
                        })
                    except Exception:
                        pass

            self.sessions = active
            self.total_sessions = len(active)

            # Cache stats
            try:
                stats = store.info()
                self.cache_keys = stats.get("db0", {}).get("keys", 0) if isinstance(stats.get("db0"), dict) else 0
                self.cache_memory = stats.get("used_memory_human", "—")
            except Exception:
                pass

        except Exception:
            self.sessions = []

    def kill_session(self, session_id: str) -> None:
        """Terminate a specific user session."""
        try:
            from appos.admin.state import _get_runtime

            runtime = _get_runtime()
            if runtime is None:
                return

            if runtime.session_store:
                runtime.session_store.delete(f"session:{session_id}")
                self.action_message = f"Session {session_id[:8]}… terminated"

            self.load_sessions()
        except Exception as e:
            self.action_message = f"Error: {e}"

    def kill_all_sessions(self) -> None:
        """Terminate all active sessions (except current admin session)."""
        try:
            from appos.admin.state import _get_runtime

            runtime = _get_runtime()
            if runtime is None:
                return

            if runtime.session_store:
                session_keys = runtime.session_store.scan_keys("session:*")
                admin_session = AdminState.session_id
                killed = 0
                for key in session_keys:
                    sid = key.replace("session:", "")
                    if sid != admin_session:
                        runtime.session_store.delete(key)
                        killed += 1
                self.action_message = f"Terminated {killed} session(s)"

            self.load_sessions()
        except Exception as e:
            self.action_message = f"Error: {e}"

    def flush_permission_cache(self) -> None:
        """Flush the permission cache in Redis."""
        try:
            from appos.admin.state import _get_runtime

            runtime = _get_runtime()
            if runtime is None:
                return

            if runtime.permission_cache:
                runtime.permission_cache.flush()
                self.action_message = "Permission cache flushed"
            else:
                self.action_message = "No permission cache configured"
        except Exception as e:
            self.action_message = f"Error: {e}"

    def flush_object_cache(self) -> None:
        """Flush the object/constant cache in Redis."""
        try:
            from appos.admin.state import _get_runtime

            runtime = _get_runtime()
            if runtime is None:
                return

            if runtime.object_cache:
                runtime.object_cache.flush()
                self.action_message = "Object cache flushed"
            else:
                self.action_message = "No object cache configured"
        except Exception as e:
            self.action_message = f"Error: {e}"


def sessions_page() -> rx.Component:
    """Active sessions management page."""
    return admin_layout(
        rx.vstack(
            rx.hstack(
                rx.heading("Active Sessions", size="6"),
                rx.spacer(),
                rx.button(
                    "Kill All Sessions",
                    size="2",
                    color_scheme="red",
                    variant="outline",
                    on_click=SessionsState.kill_all_sessions,
                ),
                width="100%",
                align="center",
            ),
            rx.divider(),
            # Stats cards
            rx.grid(
                _stat_card("Active Sessions", SessionsState.total_sessions),
                _stat_card("Cache Keys", SessionsState.cache_keys),
                _stat_card("Memory", SessionsState.cache_memory),
                columns="3",
                spacing="4",
                width="100%",
            ),
            # Cache actions
            rx.hstack(
                rx.button(
                    "Flush Permission Cache",
                    size="2",
                    variant="outline",
                    on_click=SessionsState.flush_permission_cache,
                ),
                rx.button(
                    "Flush Object Cache",
                    size="2",
                    variant="outline",
                    on_click=SessionsState.flush_object_cache,
                ),
                spacing="3",
            ),
            # Action message
            rx.cond(
                SessionsState.action_message,
                rx.callout(
                    SessionsState.action_message,
                    icon="info",
                    color_scheme="blue",
                    size="1",
                ),
            ),
            rx.divider(),
            # Sessions table
            rx.table.root(
                rx.table.header(
                    rx.table.row(
                        rx.table.column_header_cell("Session ID"),
                        rx.table.column_header_cell("Username"),
                        rx.table.column_header_cell("Type"),
                        rx.table.column_header_cell("IP Address"),
                        rx.table.column_header_cell("Created"),
                        rx.table.column_header_cell("Last Activity"),
                        rx.table.column_header_cell("Actions"),
                    ),
                ),
                rx.table.body(
                    rx.foreach(
                        SessionsState.sessions,
                        _session_row,
                    ),
                ),
                width="100%",
            ),
            spacing="5",
            width="100%",
            padding="6",
            on_mount=SessionsState.load_sessions,
        ),
    )


def _session_row(session: dict) -> rx.Component:
    """Render a single session row."""
    return rx.table.row(
        rx.table.cell(
            rx.code(session["session_id"].to(str)[:12] + "…", size="1"),
        ),
        rx.table.cell(rx.text(session["username"], weight="bold")),
        rx.table.cell(rx.badge(session["user_type"])),
        rx.table.cell(rx.text(session["ip_address"], size="1")),
        rx.table.cell(rx.text(session["created_at"], size="1", color="gray")),
        rx.table.cell(rx.text(session["last_activity"], size="1", color="gray")),
        rx.table.cell(
            rx.button(
                "Kill",
                size="1",
                color_scheme="red",
                variant="outline",
                on_click=SessionsState.kill_session(session["session_id"]),
            ),
        ),
    )


def _stat_card(title: str, value) -> rx.Component:
    """Render a stats card."""
    return rx.card(
        rx.vstack(
            rx.text(title, size="2", color="gray"),
            rx.heading(value, size="5"),
            spacing="1",
            align="center",
        ),
    )
