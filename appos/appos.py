"""
AppOS — Main Reflex application entry point.

Registers all admin routes and app routes.
Single-port, multi-app routing.
"""

import logging

import reflex as rx

from appos.admin.pages.dashboard import dashboard_page
from appos.admin.pages.groups import groups_page
from appos.admin.pages.login import login_page
from appos.admin.pages.users import users_page
from appos.admin.pages.apps import apps_page
from appos.admin.pages.connections import connections_page
from appos.admin.pages.logs import logs_page
from appos.admin.pages.metrics import metrics_page
from appos.admin.pages.object_browser import object_browser_page
from appos.admin.pages.processes import processes_page
from appos.admin.pages.records_browser import records_browser_page
from appos.admin.pages.sessions import sessions_page
from appos.admin.pages.settings import settings_page
from appos.admin.pages.themes import themes_page
from appos.admin.pages.workers import workers_page

logger = logging.getLogger("appos.startup")

# Guard: only initialize once, even if the module is re-imported
_platform_initialized = False


# ---------------------------------------------------------------------------
# Platform runtime initialization
# ---------------------------------------------------------------------------

def _init_platform() -> None:
    """Load config, create DB session factory, start CentralizedRuntime."""
    global _platform_initialized
    if _platform_initialized:
        return
    _platform_initialized = True

    try:
        from appos.engine.config import load_platform_config
        from appos.engine.runtime import init_runtime

        config = load_platform_config("appos.yaml")

        # Build a session factory from the platform DB config
        import sqlalchemy
        from sqlalchemy import create_engine
        from sqlalchemy.orm import sessionmaker

        engine = create_engine(
            config.database.url,
            pool_size=config.database.pool_size,
            max_overflow=config.database.max_overflow,
            pool_timeout=config.database.pool_timeout,
            pool_recycle=config.database.pool_recycle,
            pool_pre_ping=config.database.pool_pre_ping,
        )

        # Set search_path for the configured schema
        schema = config.database.db_schema
        if schema:
            @sqlalchemy.event.listens_for(engine, "connect")
            def set_search_path(dbapi_conn, connection_record):
                cursor = dbapi_conn.cursor()
                cursor.execute(f'SET search_path TO "{schema}", public')
                cursor.close()

        session_factory = sessionmaker(bind=engine)

        # Create and start the runtime
        runtime = init_runtime(
            log_dir=config.logging.directory,
            redis_url=config.redis.url,
            db_session_factory=session_factory,
        )
        runtime.startup()

        # Register with admin state so the admin console can use it
        from appos.admin.state import set_runtime
        set_runtime(runtime)

        logger.info("AppOS platform runtime initialized successfully")

    except Exception as e:
        logger.error(f"Failed to initialize platform runtime: {e}", exc_info=True)


# Initialize on module load (when Reflex imports appos.appos)
_init_platform()

# Create the Reflex app
app = rx.App()

# Admin console routes
app.add_page(login_page, route="/admin/login", title="AppOS Admin — Login")
app.add_page(dashboard_page, route="/admin/dashboard", title="AppOS Admin — Dashboard")
app.add_page(users_page, route="/admin/users", title="AppOS Admin — Users")
app.add_page(groups_page, route="/admin/groups", title="AppOS Admin — Groups")
app.add_page(apps_page, route="/admin/apps", title="AppOS Admin — Apps")
app.add_page(connections_page, route="/admin/connections", title="AppOS Admin — Connections")
app.add_page(logs_page, route="/admin/logs", title="AppOS Admin — Logs")
app.add_page(metrics_page, route="/admin/metrics", title="AppOS Admin — Metrics")
app.add_page(object_browser_page, route="/admin/objects", title="AppOS Admin — Object Browser")
app.add_page(processes_page, route="/admin/processes", title="AppOS Admin — Processes")
app.add_page(records_browser_page, route="/admin/records", title="AppOS Admin — Records Browser")
app.add_page(sessions_page, route="/admin/sessions", title="AppOS Admin — Sessions")
app.add_page(settings_page, route="/admin/settings", title="AppOS Admin — Settings")
app.add_page(themes_page, route="/admin/themes", title="AppOS Admin — Themes")
app.add_page(workers_page, route="/admin/workers", title="AppOS Admin — Workers")

# Redirect /admin → /admin/dashboard
app.add_page(lambda: rx.fragment(), route="/admin", on_load=rx.redirect("/admin/dashboard"))
