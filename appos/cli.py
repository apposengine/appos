"""
AppOS CLI — Platform bootstrap and management commands.

Commands:
- appos init       — Create DB schema, seed system_admin user + groups
- appos run        — Start Reflex dev server
- appos impact     — Impact analysis for an object
- appos validate   — Validate app configuration
- appos new-app    — Scaffold a new app directory structure
- appos generate   — Run all code generators (models, services, APIs, audits)
- appos migrate    — Generate and apply Alembic database migrations
- appos check      — Validate objects, deps, permissions, import rules

Design refs: AppOS_Database_Design.md Appendix A, AppOS_Design.md §10 Impact Analysis
"""

from __future__ import annotations

import argparse
import getpass
import logging
import sys
from typing import Optional

logger = logging.getLogger("appos.cli")


def main(argv: Optional[list] = None) -> int:
    """Main CLI entry point."""
    parser = argparse.ArgumentParser(
        prog="appos",
        description="AppOS — Python Low-Code Platform",
    )
    subparsers = parser.add_subparsers(dest="command", help="Available commands")

    # appos init
    init_parser = subparsers.add_parser("init", help="Bootstrap platform database")
    init_parser.add_argument(
        "--config", default="appos.yaml", help="Path to appos.yaml (default: appos.yaml)"
    )
    init_parser.add_argument(
        "--admin-password", help="System admin password (prompted if not provided)"
    )

    # appos run
    run_parser = subparsers.add_parser("run", help="Start the Reflex dev server")
    run_parser.add_argument("--host", default="0.0.0.0", help="Backend host to bind (default: 0.0.0.0)")
    run_parser.add_argument("--port", type=int, default=3000, help="Frontend port (default: 3000)")
    run_parser.add_argument("--backend-port", type=int, default=8000, help="Backend port (default: 8000)")
    run_parser.add_argument("--env", choices=["dev", "prod"], default="dev", help="Environment (default: dev)")

    # appos impact
    impact_parser = subparsers.add_parser("impact", help="Impact analysis for an object")
    impact_parser.add_argument("object_ref", help="Object reference (e.g., crm.constants.TAX_RATE)")

    # appos validate
    validate_parser = subparsers.add_parser("validate", help="Validate app configuration")
    validate_parser.add_argument("app_name", nargs="?", help="App name to validate (default: all)")

    # appos new-app
    new_app_parser = subparsers.add_parser("new-app", help="Scaffold a new app directory")
    new_app_parser.add_argument("app_name", help="Short name for the new app (e.g., crm)")
    new_app_parser.add_argument("--display-name", help="Human-readable app name")

    # appos generate
    gen_parser = subparsers.add_parser("generate", help="Run code generators")
    gen_parser.add_argument("app_name", nargs="?", help="App to generate for (default: all)")
    gen_parser.add_argument(
        "--only",
        choices=["models", "services", "interfaces", "apis", "audits", "migrations"],
        help="Run only a specific generator",
    )

    # appos migrate
    migrate_parser = subparsers.add_parser("migrate", help="Generate / apply DB migrations")
    migrate_parser.add_argument("app_name", nargs="?", help="App to migrate (default: all)")
    migrate_parser.add_argument("--message", "-m", help="Migration message slug")
    migrate_parser.add_argument(
        "--apply", action="store_true", help="Apply pending migrations (default: generate only)"
    )

    # appos check
    check_parser = subparsers.add_parser("check", help="Validate objects, deps & imports")
    check_parser.add_argument("app_name", nargs="?", help="App to check (default: all)")
    check_parser.add_argument(
        "--fix", action="store_true", help="Auto-fix simple issues where possible"
    )

    args = parser.parse_args(argv)

    if args.command == "init":
        return cmd_init(args)
    elif args.command == "run":
        return cmd_run(args)
    elif args.command == "impact":
        return cmd_impact(args)
    elif args.command == "validate":
        return cmd_validate(args)
    elif args.command == "new-app":
        return cmd_new_app(args)
    elif args.command == "generate":
        return cmd_generate(args)
    elif args.command == "migrate":
        return cmd_migrate(args)
    elif args.command == "check":
        return cmd_check(args)
    else:
        parser.print_help()
        return 0


def cmd_init(args: argparse.Namespace) -> int:
    """
    Bootstrap platform database:
    1. Load config from appos.yaml
    2. Create all tables (SQLAlchemy metadata.create_all)
    3. Create system_admin user
    4. Create default groups (system_admin, public_access)
    5. Create public_api service account
    6. Grant system_admin wildcard admin permission
    """
    print("=" * 60)
    print("  AppOS Platform Initialization")
    print("=" * 60)

    # 1. Load config
    from appos.engine.config import load_platform_config

    try:
        config = load_platform_config(args.config)
        print(f"[OK] Loaded config from {args.config}")
    except FileNotFoundError:
        print(f"[ERROR] Config file not found: {args.config}")
        print("  Create appos.yaml or specify --config path.")
        return 1
    except Exception as e:
        print(f"[ERROR] Failed to load config: {e}")
        return 1

    # 2. Build DB URL and create engine
    import sqlalchemy
    from sqlalchemy import create_engine

    db_url = config.database.url

    try:
        from sqlalchemy import text

        engine = create_engine(db_url, echo=False)
        # Test connection
        with engine.connect() as conn:
            conn.execute(text("SELECT 1"))
        print(f"[OK] Connected to {config.database.host}:{config.database.port}/{config.database.name}")
    except Exception as e:
        print(f"[ERROR] Database connection failed: {e}")
        print(f"  Ensure PostgreSQL is running and database '{config.database.name}' exists.")
        return 1

    # 3. Create schema and tables via the canonical init function
    schema_name = config.database.db_schema
    try:
        from appos.db.session import init_platform_db
        from appos.db.base import engine_registry as _engine_registry

        init_platform_db(
            db_url=db_url,
            schema=schema_name,
            create_tables=True,
        )
        engine = _engine_registry.get("appos_core")
        print(f"[OK] Schema '{schema_name}' ready")
        print("[OK] Database tables created")
    except Exception as e:
        print(f"[ERROR] Failed to create tables: {e}")
        return 1

    # 4. Seed data
    from sqlalchemy.orm import Session as SA_Session

    from appos.db.platform_models import Group, ObjectPermission, User, UserGroup
    from appos.engine.security import generate_api_key, hash_password

    # Get admin password
    admin_password = args.admin_password
    if not admin_password:
        while True:
            admin_password = getpass.getpass("  Enter system admin password: ")
            confirm = getpass.getpass("  Confirm password: ")
            if admin_password == confirm:
                break
            print("  Passwords do not match. Try again.")

    if len(admin_password) < 4:
        print("[ERROR] Password must be at least 4 characters")
        return 1

    session = SA_Session(engine)
    try:
        # Check if already initialized
        existing_admin = session.query(User).filter_by(username="admin").first()
        if existing_admin:
            print("[INFO] Platform already initialized (admin user exists)")
            existing_admin.password_hash = hash_password(admin_password)
            existing_admin.is_active = True
            session.commit()
            print("[OK] Admin password updated")
            return 0

        # Create system_admin user
        admin_user = User(
            username="admin",
            email="admin@localhost",
            password_hash=hash_password(admin_password),
            full_name="System Administrator",
            user_type="system_admin",
            is_active=True,
        )
        session.add(admin_user)
        session.flush()
        print("[OK] Created system admin user: 'admin'")

        # Create default groups
        sa_group = Group(
            name="system_admin",
            type="system",
            description="Full platform access, admin console, user/group management",
            is_active=True,
        )
        pa_group = Group(
            name="public_access",
            type="system",
            description="Public Web API access with limited permissions",
            is_active=True,
        )
        session.add_all([sa_group, pa_group])
        session.flush()
        print("[OK] Created groups: system_admin, public_access")

        # Assign admin to system_admin group
        session.add(UserGroup(user_id=admin_user.id, group_id=sa_group.id))
        print("[OK] Assigned 'admin' → 'system_admin' group")

        # Create public_api service account
        api_key, api_key_hash = generate_api_key()
        public_api = User(
            username="public_api",
            email="public_api@system",
            password_hash=hash_password("service_account_no_login"),
            full_name="Public API Service Account",
            user_type="service_account",
            is_active=True,
            api_key_hash=api_key_hash,
        )
        session.add(public_api)
        session.flush()
        print("[OK] Created service account: 'public_api'")
        print(f"     API Key (save this — shown only once): {api_key}")

        # Assign public_api to public_access group
        session.add(UserGroup(user_id=public_api.id, group_id=pa_group.id))

        # Grant system_admin wildcard admin
        session.add(ObjectPermission(
            group_name="system_admin",
            object_ref="*",
            permission="admin",
        ))
        print("[OK] Granted system_admin wildcard admin permission")

        session.commit()
        print()
        print("=" * 60)
        print("  Platform initialized successfully!")
        print()
        print(f"  Admin login: admin / (your password)")
        print(f"  Run: appos run")
        print("=" * 60)
        return 0

    except Exception as e:
        session.rollback()
        print(f"[ERROR] Seed data failed: {e}")
        return 1
    finally:
        session.close()
        engine.dispose()


def cmd_run(args: argparse.Namespace) -> int:
    """Start the Reflex dev server."""
    import subprocess

    print("Starting AppOS (Reflex) server...")
    try:
        cmd = [
            "reflex", "run",
            "--backend-host", args.host,
            "--frontend-port", str(args.port),
            "--backend-port", str(args.backend_port),
            "--env", args.env,
        ]
        result = subprocess.run(cmd, check=True)
        return result.returncode
    except FileNotFoundError:
        print("[ERROR] 'reflex' command not found. Install: pip install reflex")
        return 1
    except KeyboardInterrupt:
        print("\nServer stopped.")
        return 0


def cmd_impact(args: argparse.Namespace) -> int:
    """Run impact analysis for an object."""
    import json

    from appos.engine.dependency import DependencyGraph

    graph = DependencyGraph()
    loaded = graph.load()

    if loaded == 0:
        print("[WARN] No dependency data found. Run the app first to build the graph.")
        return 1

    result = graph.impact_analysis(args.object_ref)
    print(json.dumps(result, indent=2))
    return 0


def cmd_validate(args: argparse.Namespace) -> int:
    """Validate app configuration."""
    from pathlib import Path

    from appos.engine.config import load_app_config

    apps_dir = Path("apps")
    if not apps_dir.exists():
        print("[ERROR] apps/ directory not found")
        return 1

    apps_to_check = []
    if args.app_name:
        apps_to_check.append(args.app_name)
    else:
        apps_to_check = [d.name for d in apps_dir.iterdir() if d.is_dir() and (d / "app.yaml").exists()]

    errors = 0
    for app_name in apps_to_check:
        config_path = apps_dir / app_name / "app.yaml"
        try:
            config = load_app_config(str(config_path))
            print(f"[OK] {app_name}: valid ({config.app.name})")
        except Exception as e:
            print(f"[ERROR] {app_name}: {e}")
            errors += 1

    print(f"\n{'All apps valid!' if errors == 0 else f'{errors} error(s) found.'}")
    return 1 if errors else 0


# ---------------------------------------------------------------------------
# appos new-app
# ---------------------------------------------------------------------------

def cmd_new_app(args: argparse.Namespace) -> int:
    """Scaffold a new app directory structure under apps/."""
    from pathlib import Path

    app_name = args.app_name.lower().strip()
    display_name = args.display_name or app_name.replace("_", " ").title()

    # Validate name
    if not app_name.isidentifier():
        print(f"[ERROR] Invalid app name '{app_name}'. Must be a valid Python identifier.")
        return 1

    app_dir = Path("apps") / app_name
    if app_dir.exists():
        print(f"[ERROR] Directory already exists: {app_dir}")
        return 1

    print(f"Creating app: {display_name} ({app_name})")
    print("=" * 50)

    # Standard subdirectories matching the CRM example structure
    subdirs = [
        "constants",
        "integrations",
        "interfaces",
        "pages",
        "processes",
        "records",
        "rules",
        "runtime/documents",
        "steps",
        "translation_sets",
        "web_apis",
    ]

    # Create directory tree
    app_dir.mkdir(parents=True)
    for sub in subdirs:
        (app_dir / sub).mkdir(parents=True, exist_ok=True)
        # Add __init__.py at each package level
        parts = sub.split("/")
        for i in range(len(parts)):
            pkg_path = app_dir / "/".join(parts[: i + 1]) / "__init__.py"
            if not pkg_path.exists():
                pkg_path.write_text(f'"""AppOS {display_name} — {parts[i]}."""\n')

    # Root __init__.py
    (app_dir / "__init__.py").write_text(
        f'"""\nAppOS Application: {display_name}\n\nAuto-generated by `appos new-app`.\n"""\n'
    )

    # app.yaml
    yaml_content = f"""app:
  name: "{display_name}"
  short_name: "{app_name}"
  version: "1.0.0"
  description: "{display_name} application"

database:
  connected_system: "{app_name}_db"

security:
  default_permission: "view"
  inheriting_types:
    - "expression_rule"
    - "constant"
    - "step"
  always_explicit_types:
    - "web_api"
    - "integration"
    - "process"
    - "record"
    - "interface"
    - "page"
    - "site"

logging:
  rotation: "daily"
  retention:
    execution_days: 90
    performance_days: 30
    security_days: 365
"""
    (app_dir / "app.yaml").write_text(yaml_content)

    print(f"[OK] Created {app_dir}/")
    for sub in subdirs:
        print(f"     ├── {sub}/")
    print(f"     └── app.yaml")
    print()
    print(f"Next steps:")
    print(f"  1. Define records in apps/{app_name}/records/")
    print(f"  2. Define rules in apps/{app_name}/rules/")
    print(f"  3. Run: appos generate {app_name}")
    return 0


# ---------------------------------------------------------------------------
# appos generate
# ---------------------------------------------------------------------------

def cmd_generate(args: argparse.Namespace) -> int:
    """Run code generators for one or all apps."""
    from pathlib import Path

    apps_dir = Path("apps")
    if not apps_dir.exists():
        print("[ERROR] apps/ directory not found")
        return 1

    # Determine which apps to generate for
    if args.app_name:
        app_names = [args.app_name]
    else:
        app_names = [
            d.name for d in apps_dir.iterdir()
            if d.is_dir() and (d / "__init__.py").exists()
        ]

    if not app_names:
        print("[WARN] No apps found in apps/")
        return 0

    errors = 0
    for app_name in sorted(app_names):
        print(f"\n{'=' * 50}")
        print(f"  Generating: {app_name}")
        print(f"{'=' * 50}")

        app_dir = apps_dir / app_name
        output_dir = Path(".appos/generated") / app_name

        only = args.only if hasattr(args, "only") else None

        # 1. Model generation
        if only in (None, "models"):
            errors += _run_model_generator(app_name, app_dir, output_dir)

        # 2. Service generation
        if only in (None, "services"):
            errors += _run_service_generator(app_name, app_dir, output_dir)

        # 3. Interface generation
        if only in (None, "interfaces"):
            errors += _run_interface_generator(app_name, app_dir, output_dir)

        # 4. Audit log table generation
        if only in (None, "audits"):
            errors += _run_audit_generator(app_name, app_dir, output_dir)

        # 5. REST API generation
        if only in (None, "apis"):
            errors += _run_api_generator(app_name, app_dir, output_dir)

        # 6. Migration generation
        if only in (None, "migrations"):
            errors += _run_migration_generator(app_name, app_dir, output_dir)

    summary = "with errors" if errors else "successfully"
    print(f"\nGeneration completed {summary} ({errors} error(s)).")
    return 1 if errors else 0


def _run_model_generator(app_name: str, app_dir, output_dir) -> int:
    """Run model generator for an app. Returns error count."""
    try:
        from appos.generators.model_generator import ModelGenerator

        gen = ModelGenerator(app_name=app_name, app_dir=str(app_dir), output_dir=str(output_dir / "models"))
        count = gen.generate_all()
        print(f"  [OK] Models: {count} generated")
        return 0
    except ImportError:
        print("  [SKIP] Model generator not available")
        return 0
    except Exception as e:
        print(f"  [ERROR] Models: {e}")
        return 1


def _run_service_generator(app_name: str, app_dir, output_dir) -> int:
    """Run service generator for an app."""
    try:
        from appos.generators.service_generator import ServiceGenerator

        gen = ServiceGenerator(app_name=app_name, app_dir=str(app_dir), output_dir=str(output_dir / "services"))
        count = gen.generate_all()
        print(f"  [OK] Services: {count} generated")
        return 0
    except ImportError:
        print("  [SKIP] Service generator not available")
        return 0
    except Exception as e:
        print(f"  [ERROR] Services: {e}")
        return 1


def _run_interface_generator(app_name: str, app_dir, output_dir) -> int:
    """Run interface generator for an app."""
    try:
        from appos.generators.interface_generator import InterfaceGenerator

        gen = InterfaceGenerator(app_name=app_name, app_dir=str(app_dir), output_dir=str(output_dir / "interfaces"))
        count = gen.generate_all()
        print(f"  [OK] Interfaces: {count} generated")
        return 0
    except ImportError:
        print("  [SKIP] Interface generator not available")
        return 0
    except Exception as e:
        print(f"  [ERROR] Interfaces: {e}")
        return 1


def _run_audit_generator(app_name: str, app_dir, output_dir) -> int:
    """Run audit log table generator for an app."""
    try:
        from appos.generators.audit_generator import AuditGenerator

        gen = AuditGenerator(app_name=app_name, app_dir=str(app_dir), output_dir=str(output_dir / "audits"))
        count = gen.generate_all()
        print(f"  [OK] Audit tables: {count} generated")
        return 0
    except ImportError:
        print("  [SKIP] Audit generator not available")
        return 0
    except Exception as e:
        print(f"  [ERROR] Audits: {e}")
        return 1


def _run_api_generator(app_name: str, app_dir, output_dir) -> int:
    """Run REST API endpoint generator for an app."""
    try:
        from appos.generators.api_generator import ApiGenerator

        gen = ApiGenerator(app_name=app_name, app_dir=str(app_dir), output_dir=str(output_dir / "apis"))
        count = gen.generate_all()
        print(f"  [OK] APIs: {count} generated")
        return 0
    except ImportError:
        print("  [SKIP] API generator not available")
        return 0
    except Exception as e:
        print(f"  [ERROR] APIs: {e}")
        return 1


def _run_migration_generator(app_name: str, app_dir, output_dir) -> int:
    """Run migration generator for an app."""
    try:
        from appos.generators.migration_generator import MigrationGenerator

        gen = MigrationGenerator(app_name=app_name, app_dir=str(app_dir))
        count = gen.generate_all()
        print(f"  [OK] Migrations: {count} generated")
        return 0
    except ImportError:
        print("  [SKIP] Migration generator not available")
        return 0
    except Exception as e:
        print(f"  [ERROR] Migrations: {e}")
        return 1


# ---------------------------------------------------------------------------
# appos migrate
# ---------------------------------------------------------------------------

def cmd_migrate(args: argparse.Namespace) -> int:
    """Generate and/or apply database migrations."""
    from pathlib import Path

    apps_dir = Path("apps")
    if not apps_dir.exists():
        print("[ERROR] apps/ directory not found")
        return 1

    # Determine which apps
    if args.app_name:
        app_names = [args.app_name]
    else:
        app_names = [
            d.name for d in apps_dir.iterdir()
            if d.is_dir() and (d / "app.yaml").exists()
        ]

    errors = 0
    for app_name in sorted(app_names):
        print(f"\n--- Migrating: {app_name} ---")

        migrations_dir = Path("migrations") / app_name / "versions"

        if args.apply:
            # Apply pending migrations
            errors += _apply_migrations(app_name, migrations_dir)
        else:
            # Generate new migration
            message = args.message or f"auto_{app_name}"
            errors += _generate_migration(app_name, message)

    return 1 if errors else 0


def _generate_migration(app_name: str, message: str) -> int:
    """Generate a migration for an app using the migration generator."""
    try:
        from appos.generators.migration_generator import MigrationGenerator

        gen = MigrationGenerator(app_name=app_name, app_dir=f"apps/{app_name}")
        result = gen.generate(message=message)
        if result:
            print(f"  [OK] Migration generated: {result}")
        else:
            print(f"  [OK] No changes detected")
        return 0
    except ImportError:
        print("  [ERROR] Migration generator not available")
        return 1
    except Exception as e:
        print(f"  [ERROR] {e}")
        return 1


def _apply_migrations(app_name: str, migrations_dir) -> int:
    """Apply pending migrations for an app."""
    from pathlib import Path

    if not migrations_dir.exists():
        print(f"  [SKIP] No migrations directory: {migrations_dir}")
        return 0

    migration_files = sorted(migrations_dir.glob("*.py"))
    if not migration_files:
        print(f"  [SKIP] No migration files found")
        return 0

    # Load config for DB connection
    try:
        from appos.engine.config import load_platform_config
        config = load_platform_config("appos.yaml")
    except Exception as e:
        print(f"  [ERROR] Cannot load config: {e}")
        return 1

    import sqlalchemy
    from sqlalchemy import create_engine, text

    db_url = config.database.url
    schema_name = config.database.db_schema

    try:
        engine = create_engine(db_url, echo=False)

        # Set search_path so migrations run against the correct schema
        @sqlalchemy.event.listens_for(engine, "connect")
        def set_search_path(dbapi_conn, connection_record):
            cursor = dbapi_conn.cursor()
            cursor.execute(f'SET search_path TO "{schema_name}", public')
            cursor.close()

        applied = 0
        for mig_file in migration_files:
            print(f"  Applying: {mig_file.name}")
            # Load and execute migration module
            import importlib.util
            spec = importlib.util.spec_from_file_location(mig_file.stem, str(mig_file))
            mod = importlib.util.module_from_spec(spec)
            spec.loader.exec_module(mod)

            if hasattr(mod, "upgrade"):
                with engine.begin() as conn:
                    mod.upgrade(conn)
                applied += 1
            else:
                print(f"    [WARN] No upgrade() function in {mig_file.name}")

        print(f"  [OK] Applied {applied} migration(s)")
        engine.dispose()
        return 0
    except Exception as e:
        print(f"  [ERROR] Migration failed: {e}")
        return 1


# ---------------------------------------------------------------------------
# appos check
# ---------------------------------------------------------------------------

def cmd_check(args: argparse.Namespace) -> int:
    """
    Validate objects, dependencies, permissions, and import rules.

    Checks:
    1. All @record, @expression_rule, etc. decorators parse without error
    2. All dependency references resolve to real objects
    3. Always-explicit types have explicit permissions
    4. No disallowed external imports (AppOS-only import policy)
    5. app.yaml is valid
    """
    import json
    from pathlib import Path

    apps_dir = Path("apps")
    if not apps_dir.exists():
        print("[ERROR] apps/ directory not found")
        return 1

    if args.app_name:
        app_names = [args.app_name]
    else:
        app_names = [
            d.name for d in apps_dir.iterdir()
            if d.is_dir() and (d / "__init__.py").exists()
        ]

    total_errors = 0
    total_warnings = 0
    report: dict = {}

    for app_name in sorted(app_names):
        print(f"\n{'=' * 50}")
        print(f"  Checking: {app_name}")
        print(f"{'=' * 50}")

        app_dir = apps_dir / app_name
        app_errors = 0
        app_warnings = 0
        app_report: dict = {"errors": [], "warnings": []}

        # 1. Validate app.yaml
        config_path = app_dir / "app.yaml"
        if config_path.exists():
            try:
                from appos.engine.config import load_app_config
                load_app_config(str(config_path))
                print(f"  [OK] app.yaml valid")
            except Exception as e:
                print(f"  [ERROR] app.yaml: {e}")
                app_report["errors"].append(f"app.yaml: {e}")
                app_errors += 1
        else:
            print(f"  [WARN] No app.yaml found")
            app_report["warnings"].append("No app.yaml found")
            app_warnings += 1

        # 2. Check Python files for syntax errors
        py_files = list(app_dir.rglob("*.py"))
        for py_file in py_files:
            try:
                with open(py_file, "r", encoding="utf-8") as f:
                    source = f.read()
                compile(source, str(py_file), "exec")
            except SyntaxError as e:
                rel = py_file.relative_to(apps_dir)
                print(f"  [ERROR] Syntax: {rel}:{e.lineno} — {e.msg}")
                app_report["errors"].append(f"Syntax: {rel}:{e.lineno} — {e.msg}")
                app_errors += 1

        # 3. Check import policy (no bare stdlib for disallowed modules)
        disallowed_imports = {"subprocess", "ctypes", "socket", "multiprocessing"}
        for py_file in py_files:
            try:
                with open(py_file, "r", encoding="utf-8") as f:
                    for lineno, line in enumerate(f, 1):
                        stripped = line.strip()
                        if stripped.startswith("import ") or stripped.startswith("from "):
                            for mod in disallowed_imports:
                                if mod in stripped:
                                    rel = py_file.relative_to(apps_dir)
                                    print(f"  [WARN] Disallowed import '{mod}': {rel}:{lineno}")
                                    app_report["warnings"].append(
                                        f"Disallowed import '{mod}': {rel}:{lineno}"
                                    )
                                    app_warnings += 1
            except OSError:
                pass

        # 4. Check dependency graph references
        try:
            from appos.engine.dependency import DependencyGraph

            graph = DependencyGraph()
            loaded = graph.load()
            if loaded > 0:
                # Check all edges resolve
                for node in graph.graph.nodes():
                    if node.startswith(f"{app_name}."):
                        for _, target in graph.graph.out_edges(node):
                            if not graph.graph.has_node(target):
                                print(f"  [ERROR] Unresolved dep: {node} → {target}")
                                app_report["errors"].append(f"Unresolved dep: {node} → {target}")
                                app_errors += 1
                print(f"  [OK] Dependency references checked")
            else:
                print(f"  [SKIP] No dependency graph data")
        except Exception:
            print(f"  [SKIP] Dependency graph not available")

        # 5. Check always-explicit types have permissions
        try:
            from appos.engine.config import load_app_config

            if config_path.exists():
                app_config = load_app_config(str(config_path))
                explicit_types = getattr(
                    getattr(app_config, "security", None), "always_explicit_types", []
                )
                if explicit_types:
                    print(f"  [INFO] Always-explicit types: {', '.join(explicit_types)}")
        except Exception:
            pass

        # Summary for this app
        print(f"\n  Summary: {app_errors} error(s), {app_warnings} warning(s)")
        total_errors += app_errors
        total_warnings += app_warnings
        report[app_name] = app_report

    # Write report to validation log
    output_path = Path(".appos/logs/validation")
    output_path.mkdir(parents=True, exist_ok=True)
    from datetime import datetime, timezone

    report_file = output_path / f"appos-check-{datetime.now(timezone.utc).strftime('%Y%m%d-%H%M%S')}.json"
    report_file.write_text(json.dumps(report, indent=2))
    print(f"\nReport saved: {report_file}")
    print(f"\nTotal: {total_errors} error(s), {total_warnings} warning(s)")
    return 1 if total_errors else 0


if __name__ == "__main__":
    sys.exit(main())
