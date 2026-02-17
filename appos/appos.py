"""
AppOS — Main Reflex application entry point.

Registers all admin routes and app routes.
Single-port, multi-app routing.

Boot sequence:
    1. _init_platform()  — config, DB engine, runtime.startup()
    2. _discover_apps()  — import app modules so decorators register objects
    3. _sync_apps_to_db() — ensure apps listed in appos.yaml exist in the DB
    4. Create rx.App() and register admin routes
    5. _register_app_routes() — use AppOSReflexApp to bind app pages + APIs
"""

import importlib
import logging
from pathlib import Path

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
_runtime_ref = None  # keep reference for app route registration
_session_factory_ref = None  # keep reference for DB sync
_platform_config_ref = None  # keep reference for app discovery


# ---------------------------------------------------------------------------
# Platform runtime initialization
# ---------------------------------------------------------------------------

def _init_platform() -> None:
    """Load config, create DB session factory, start CentralizedRuntime."""
    global _platform_initialized, _runtime_ref, _session_factory_ref, _platform_config_ref
    if _platform_initialized:
        return
    _platform_initialized = True

    try:
        from appos.engine.config import load_platform_config
        from appos.engine.runtime import init_runtime

        config = load_platform_config("appos.yaml")
        _platform_config_ref = config

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
        _session_factory_ref = session_factory

        # Create and start the runtime
        runtime = init_runtime(
            log_dir=config.logging.directory,
            redis_url=config.redis.url,
            db_session_factory=session_factory,
        )
        runtime.startup()
        _runtime_ref = runtime

        # Register with admin state so the admin console can use it
        from appos.admin.state import set_runtime
        set_runtime(runtime)

        logger.info("AppOS platform runtime initialized successfully")

    except Exception as e:
        logger.error(f"Failed to initialize platform runtime: {e}", exc_info=True)


# ---------------------------------------------------------------------------
# App auto-discovery — import app modules to trigger decorator registration
# ---------------------------------------------------------------------------

def _discover_apps() -> None:
    """
    Import all app modules listed in appos.yaml so that @record, @rule,
    @process, @page, etc. decorators fire and register objects in the
    global ObjectRegistryManager.
    """
    config = _platform_config_ref
    if not config or not config.apps:
        logger.info("No apps listed in appos.yaml — skipping discovery")
        return

    from appos.engine.config import get_project_root

    project_root = get_project_root()
    apps_dir = project_root / "apps"

    for app_name in config.apps:
        app_path = apps_dir / app_name
        if not app_path.is_dir():
            logger.warning(f"App directory not found: {app_path}")
            continue

        logger.info(f"Discovering app: {app_name}")
        _import_app_modules(app_name, app_path)


def _import_app_modules(app_name: str, app_path: Path) -> None:
    """
    Import all Python modules in an app directory tree.

    Imports __init__.py for each sub-package (records/, rules/, etc.)
    which in turn re-exports the individual object modules, triggering
    decorator registration.
    """
    # Sub-packages to discover (in dependency order)
    sub_packages = [
        "constants",
        "translation_sets",
        "records",
        "rules",
        "connected_systems",
        "integrations",
        "web_apis",
        "processes",
        "interfaces",
        "pages",
        "sites",
    ]

    # First import the app's own __init__.py
    app_module = f"apps.{app_name}"
    try:
        importlib.import_module(app_module)
        logger.debug(f"  Imported {app_module}")
    except Exception as e:
        logger.warning(f"  Failed to import {app_module}: {e}")

    # Then import each sub-package
    for sub_pkg in sub_packages:
        sub_dir = app_path / sub_pkg
        if not sub_dir.is_dir():
            continue

        module_path = f"apps.{app_name}.{sub_pkg}"
        try:
            importlib.import_module(module_path)
            logger.debug(f"  Imported {module_path}")
        except Exception as e:
            logger.warning(f"  Failed to import {module_path}: {e}")


# ---------------------------------------------------------------------------
# Sync apps to DB — ensure apps in appos.yaml exist in the App table
# ---------------------------------------------------------------------------

def _sync_apps_to_db() -> None:
    """
    For each app listed in appos.yaml, ensure a corresponding row exists
    in the 'apps' DB table.  Reads app.yaml for metadata.
    """
    config = _platform_config_ref
    sf = _session_factory_ref
    if not config or not sf or not config.apps:
        return

    from appos.engine.config import load_app_config

    try:
        from appos.db.platform_models import App

        session = sf()
        try:
            for app_name in config.apps:
                existing = session.query(App).filter_by(short_name=app_name).first()
                if existing:
                    logger.debug(f"App '{app_name}' already in DB")
                    continue

                # Load app.yaml for metadata
                try:
                    app_cfg = load_app_config(app_name)
                    display_name = app_cfg.name
                    description = app_cfg.description
                    version = app_cfg.version
                except Exception:
                    display_name = app_name.title()
                    description = ""
                    version = "1.0.0"

                new_app = App(
                    name=display_name,
                    short_name=app_name,
                    description=description,
                    version=version,
                    is_active=True,
                )
                session.add(new_app)
                logger.info(f"Registered app '{app_name}' in DB")

            session.commit()
        except Exception as e:
            session.rollback()
            logger.warning(f"Failed to sync apps to DB: {e}")
        finally:
            session.close()
    except Exception as e:
        logger.warning(f"App DB sync skipped (tables may not exist yet): {e}")


# ---------------------------------------------------------------------------
# App route registration via Reflex Bridge
# ---------------------------------------------------------------------------

def _register_app_routes(reflex_app) -> None:
    """
    Use AppOSReflexApp to bind all discovered @page and @web_api objects
    to the Reflex application instance.
    """
    runtime = _runtime_ref
    if not runtime:
        logger.warning("Runtime not available — skipping app route registration")
        return

    try:
        from appos.ui.reflex_bridge import AppOSReflexApp

        bridge = AppOSReflexApp(registry=runtime.registry, runtime=runtime)
        bridge.register_all(reflex_app)
    except Exception as e:
        logger.error(f"Failed to register app routes: {e}", exc_info=True)


# ---------------------------------------------------------------------------
# Boot sequence
# ---------------------------------------------------------------------------

# 1. Initialize platform (config, DB, runtime)
_init_platform()

# 2. Discover and import app modules
_discover_apps()

# 3. Sync apps to the DB
_sync_apps_to_db()

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

# 4. Register app page/API routes via the Reflex bridge
_register_app_routes(app)
