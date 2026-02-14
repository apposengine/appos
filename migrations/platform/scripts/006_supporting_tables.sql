-- ============================================================================
-- AppOS Platform Database — 006: Supporting Tables
-- ============================================================================
-- Purpose:  Create dependency_changes, object_registry, platform_config,
--           scheduled_tasks
-- Source:   AppOS_Database_Design.md v1.0, §2.11, §2.12, §2.13, §2.14
-- Depends:  002_core_tables.sql
-- Idempotent: Yes (IF NOT EXISTS)
-- ============================================================================

SET search_path TO "appOS", public;

-- ---------------------------------------------------------------------------
-- 1. dependency_changes — Dependency graph change audit
-- ---------------------------------------------------------------------------
CREATE TABLE IF NOT EXISTS "appOS".dependency_changes (
    id          SERIAL PRIMARY KEY,
    object_ref  VARCHAR(255) NOT NULL,                  -- "crm.rules.calculate_discount"
    change_type VARCHAR(20)  NOT NULL
                CHECK (change_type IN ('added', 'removed', 'modified')),
    old_hash    VARCHAR(64),                            -- SHA-256 hash of previous version
    new_hash    VARCHAR(64),                            -- SHA-256 hash of current version
    details     JSONB,                                  -- {"field_added": "loyalty_points", ...}
    changed_at  TIMESTAMP WITH TIME ZONE NOT NULL DEFAULT NOW(),
    changed_by  VARCHAR(100)                            -- user or "system" for auto-detection
);

COMMENT ON TABLE "appOS".dependency_changes IS 'Tracks dependency graph changes over time for audit and AI querying.';
COMMENT ON COLUMN "appOS".dependency_changes.object_ref IS 'Fully qualified object reference (e.g., crm.rules.calculate_discount)';
COMMENT ON COLUMN "appOS".dependency_changes.old_hash IS 'SHA-256 of previous source file version';
COMMENT ON COLUMN "appOS".dependency_changes.new_hash IS 'SHA-256 of current source file version';

-- ---------------------------------------------------------------------------
-- 2. object_registry — Runtime registry of all discovered objects
-- ---------------------------------------------------------------------------
CREATE TABLE IF NOT EXISTS "appOS".object_registry (
    id            SERIAL PRIMARY KEY,
    object_ref    VARCHAR(255) NOT NULL UNIQUE,          -- "crm.rules.calculate_discount"
    object_type   VARCHAR(30)  NOT NULL
                  CHECK (object_type IN (
                      'record', 'expression_rule', 'constant', 'process', 'step',
                      'integration', 'web_api', 'interface', 'page', 'site',
                      'document', 'folder', 'translation_set', 'connected_system'
                  )),
    app_name      VARCHAR(50),                           -- NULL for platform/global objects
    module_path   VARCHAR(500) NOT NULL,                 -- Python module path
    file_path     VARCHAR(500) NOT NULL,                 -- Filesystem path
    source_hash   VARCHAR(64)  NOT NULL,                 -- SHA-256 of source file
    metadata      JSONB        NOT NULL DEFAULT '{}',
    -- For records:       {table_name, audit, soft_delete, display_field, search_fields, connected_system}
    -- For rules:         {inputs, outputs, depends_on, cacheable, cache_ttl}
    -- For processes:     {inputs, triggers, display_name, timeout}
    -- For web_apis:      {method, path, version, auth, rate_limit}
    -- For constants:     {type, has_env_overrides}
    -- For integrations:  {connected_system, method, path, log_payload}
    -- For pages:         {route, title, interface, on_load}
    -- For sites:         {pages, default_page, auth_required}

    is_active     BOOLEAN      NOT NULL DEFAULT TRUE,
    discovered_at TIMESTAMP WITH TIME ZONE NOT NULL DEFAULT NOW(),
    updated_at    TIMESTAMP WITH TIME ZONE NOT NULL DEFAULT NOW()
);

COMMENT ON TABLE "appOS".object_registry IS 'Runtime registry of all discovered objects across all apps. Populated on startup by scanning app directories.';
COMMENT ON COLUMN "appOS".object_registry.object_ref IS 'Fully qualified: app.type_plural.name (e.g., crm.rules.calculate_discount)';
COMMENT ON COLUMN "appOS".object_registry.source_hash IS 'SHA-256 of source file — used for change detection';

-- ---------------------------------------------------------------------------
-- 3. platform_config — Runtime-editable platform configuration
-- ---------------------------------------------------------------------------
CREATE TABLE IF NOT EXISTS "appOS".platform_config (
    id         SERIAL PRIMARY KEY,
    key        VARCHAR(100) NOT NULL UNIQUE,             -- "security.session_timeout", "logging.level"
    value      JSONB        NOT NULL,                    -- JSON value (string, number, object)
    category   VARCHAR(50)  NOT NULL,                    -- "security", "logging", "celery", "ui"
    updated_at TIMESTAMP WITH TIME ZONE NOT NULL DEFAULT NOW(),
    updated_by INTEGER      REFERENCES "appOS".users(id)
);

COMMENT ON TABLE "appOS".platform_config IS 'Runtime-editable platform configuration (supplements appos.yaml). Admin console manages these values.';

-- ---------------------------------------------------------------------------
-- 4. scheduled_tasks — Celery Beat schedule (DB-backed)
-- ---------------------------------------------------------------------------
CREATE TABLE IF NOT EXISTS "appOS".scheduled_tasks (
    id            SERIAL PRIMARY KEY,
    task_name     VARCHAR(200) NOT NULL UNIQUE,          -- "crm.processes.daily_report"
    schedule      VARCHAR(100) NOT NULL,                 -- cron expression: "0 8 * * *"
    timezone      VARCHAR(50)  NOT NULL DEFAULT 'UTC',
    app_name      VARCHAR(50)  NOT NULL,
    process_name  VARCHAR(100) NOT NULL,
    inputs        JSONB        NOT NULL DEFAULT '{}',
    is_active     BOOLEAN      NOT NULL DEFAULT TRUE,
    last_run_at   TIMESTAMP WITH TIME ZONE,
    next_run_at   TIMESTAMP WITH TIME ZONE,
    created_at    TIMESTAMP WITH TIME ZONE NOT NULL DEFAULT NOW(),
    updated_at    TIMESTAMP WITH TIME ZONE NOT NULL DEFAULT NOW()
);

COMMENT ON TABLE "appOS".scheduled_tasks IS 'Registered scheduled processes — Celery Beat schedule stored in DB for admin visibility.';
COMMENT ON COLUMN "appOS".scheduled_tasks.schedule IS 'Cron expression (e.g., "0 8 * * *" = daily at 8am)';
