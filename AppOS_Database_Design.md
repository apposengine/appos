# AppOS — Database Design Document

> **Version:** 1.0  
> **Date:** February 13, 2026  
> **Source:** Derived from `AppOS_Design.md` v2.1, `AppOS_TaskPlan.md`, all Reference Docs  
> **Goal:** Define the complete end-to-end database schema required to implement the AppOS platform engine — covering platform tables, per-app auto-generated tables, Redis data model, partitioning strategy, and migration approach.

---

## Table of Contents

1. [Database Architecture Overview](#1-database-architecture-overview)
2. [Platform Database Schema (appos_core)](#2-platform-database-schema-appos_core)
3. [Per-App Auto-Generated Tables](#3-per-app-auto-generated-tables)
4. [Redis Data Model](#4-redis-data-model)
5. [Entity Relationship Diagrams](#5-entity-relationship-diagrams)
6. [Partitioning & Archival Strategy](#6-partitioning--archival-strategy)
7. [Indexing Strategy](#7-indexing-strategy)
8. [Data Migration & Alembic](#8-data-migration--alembic)
9. [Security & Encryption](#9-security--encryption)
10. [Backup & Recovery](#10-backup--recovery)
11. [Table Summary Matrix](#11-table-summary-matrix)

---

## 1. Database Architecture Overview

### Multi-Database Topology

AppOS uses a **multi-database architecture** where the platform core and each application can have dedicated databases:

```
┌──────────────────────────────────────────────────────────────────────┐
│                       DATABASE TOPOLOGY                              │
├──────────────────────────────────────────────────────────────────────┤
│                                                                      │
│  ┌─────────────────────────────────────┐                            │
│  │  PostgreSQL: appos_core             │  ← Platform database       │
│  │  ───────────────────────            │                            │
│  │  • users, groups, apps              │                            │
│  │  • object_permission                │                            │
│  │  • connected_systems                │                            │
│  │  • process_instances (partitioned)  │                            │
│  │  • process_step_log  (partitioned)  │                            │
│  │  • dependency_changes               │                            │
│  └─────────────────────────────────────┘                            │
│                                                                      │
│  ┌─────────────────────────────────────┐                            │
│  │  PostgreSQL: crm_db                 │  ← Per Connected System    │
│  │  ───────────────────────            │                            │
│  │  • customers, orders, order_items   │  ← Auto-generated from    │
│  │  • crm_customers_audit_log         │     @record definitions    │
│  │  • documents, document_versions     │                            │
│  │  • folders                          │                            │
│  │  • crm_event_log                    │                            │
│  └─────────────────────────────────────┘                            │
│                                                                      │
│  ┌─────────────────────────────────────┐                            │
│  │  PostgreSQL: finance_db             │  ← Another app database    │
│  │  ───────────────────────            │                            │
│  │  • invoices, payments, accounts     │                            │
│  │  • fin_invoices_audit_log           │                            │
│  │  • documents, document_versions     │                            │
│  │  • folders                          │                            │
│  │  • finance_event_log               │                            │
│  └─────────────────────────────────────┘                            │
│                                                                      │
│  ┌─────────────────────────────────────┐                            │
│  │  Redis (6 logical databases)        │  ← In-memory data         │
│  │  ───────────────────────            │                            │
│  │  DB 0: Celery broker                │                            │
│  │  DB 1: Celery results               │                            │
│  │  DB 2: Permission cache             │                            │
│  │  DB 3: Object cache                 │                            │
│  │  DB 4: Session store                │                            │
│  │  DB 5: Rate limiting counters       │                            │
│  └─────────────────────────────────────┘                            │
│                                                                      │
└──────────────────────────────────────────────────────────────────────┘
```

### SQLAlchemy Multi-Engine Registry

Each Connected System of `type="database"` registers its own SQLAlchemy engine. The platform manages engine lifecycle (creation, pool config, disposal, health checks) centrally via `db_connected_system` in each `app.yaml`.

```
Engine Registry:
  "appos_core"      → Engine(postgresql://...appos_core)     ← always present
  "crm_database"    → Engine(postgresql://...crm_db)         ← from Connected System
  "finance_database" → Engine(postgresql://...finance_db)    ← from Connected System
```

### Design Principles

| Principle | Implementation |
|-----------|---------------|
| **Platform tables are fixed** | Schema defined here, managed via Alembic |
| **App tables are auto-generated** | From `@record` Pydantic models → SQLAlchemy → Alembic |
| **Audit tables are conditional** | Only generated when `Meta.audit = True` |
| **Soft deletes preferred** | `is_deleted` + `deleted_at` + `deleted_by` (SoftDeleteMixin) |
| **No hard deletes for users/groups** | Deactivation via `is_active = False` |
| **Encrypted credentials** | Connected System credentials encrypted at rest (Fernet/AES) |
| **Partitioned high-volume tables** | `process_instances`, `process_step_log` — monthly by `started_at` |
| **File-based system logs** | NOT in database — see `AppOS_Logging_Reference.md` |

---

## 2. Platform Database Schema (appos_core)

All platform tables live in the `appos_core` PostgreSQL database. This is the only database whose schema is fully defined by the platform (not auto-generated from developer `@record` definitions).

### 2.1 users

Stores all user accounts — basic users, system admins, and service accounts.

```sql
CREATE TABLE users (
    id              SERIAL PRIMARY KEY,
    username        VARCHAR(100)  NOT NULL UNIQUE,
    email           VARCHAR(255)  NOT NULL UNIQUE,
    password_hash   VARCHAR(255)  NOT NULL,             -- bcrypt
    full_name       VARCHAR(200)  NOT NULL,
    is_active       BOOLEAN       NOT NULL DEFAULT TRUE,
    user_type       VARCHAR(20)   NOT NULL DEFAULT 'basic'
                    CHECK (user_type IN ('basic', 'system_admin', 'service_account')),
    preferred_language VARCHAR(10) NOT NULL DEFAULT 'en',
    timezone        VARCHAR(50)   NOT NULL DEFAULT 'UTC',
    last_login      TIMESTAMP WITH TIME ZONE,
    api_key_hash    VARCHAR(255),                        -- for service_account auth
    created_at      TIMESTAMP WITH TIME ZONE NOT NULL DEFAULT NOW(),
    updated_at      TIMESTAMP WITH TIME ZONE NOT NULL DEFAULT NOW(),
    created_by      INTEGER       REFERENCES users(id),
    updated_by      INTEGER       REFERENCES users(id)
);

-- Indexes
CREATE INDEX idx_users_username      ON users(username);
CREATE INDEX idx_users_email         ON users(email);
CREATE INDEX idx_users_user_type     ON users(user_type);
CREATE INDEX idx_users_is_active     ON users(is_active);
CREATE INDEX idx_users_last_login    ON users(last_login);
```

**Notes:**
- `user_type` replaces the old `is_admin` boolean (extensible enum).
- `service_account` users cannot log in via UI — they authenticate via API key or OAuth.
- `api_key_hash` stores bcrypt hash of API key for service accounts.
- No hard deletes — deactivation sets `is_active = FALSE`.
- `password_hash` uses bcrypt (via `passlib` or `bcrypt` library).

---

### 2.2 groups

Access control groups — the core unit of the permission system.

```sql
CREATE TABLE groups (
    id              SERIAL PRIMARY KEY,
    name            VARCHAR(100) NOT NULL UNIQUE,
    type            VARCHAR(20)  NOT NULL DEFAULT 'security'
                    CHECK (type IN ('security', 'team', 'app', 'system')),
    description     TEXT,
    is_active       BOOLEAN      NOT NULL DEFAULT TRUE,
    created_at      TIMESTAMP WITH TIME ZONE NOT NULL DEFAULT NOW(),
    updated_at      TIMESTAMP WITH TIME ZONE NOT NULL DEFAULT NOW(),
    created_by      INTEGER      REFERENCES users(id),
    updated_by      INTEGER      REFERENCES users(id)
);

-- Indexes
CREATE INDEX idx_groups_name        ON groups(name);
CREATE INDEX idx_groups_type        ON groups(type);
CREATE INDEX idx_groups_is_active   ON groups(is_active);
```

**Bootstrap groups** (created by `appos init`):

| Name | Type | Purpose |
|------|------|---------|
| `system_admin` | system | Full platform access, admin console |
| `public_access` | system | Public Web API access (limited permissions) |

---

### 2.3 user_groups (Junction)

Many-to-many relationship between users and groups.

```sql
CREATE TABLE user_groups (
    id         SERIAL PRIMARY KEY,
    user_id    INTEGER NOT NULL REFERENCES users(id) ON DELETE CASCADE,
    group_id   INTEGER NOT NULL REFERENCES groups(id) ON DELETE CASCADE,
    added_at   TIMESTAMP WITH TIME ZONE NOT NULL DEFAULT NOW(),
    added_by   INTEGER REFERENCES users(id),
    UNIQUE (user_id, group_id)
);

-- Indexes
CREATE INDEX idx_ug_user_id  ON user_groups(user_id);
CREATE INDEX idx_ug_group_id ON user_groups(group_id);
```

---

### 2.4 apps

Registry of all applications in the platform.

```sql
CREATE TABLE apps (
    id                  SERIAL PRIMARY KEY,
    name                VARCHAR(200) NOT NULL,
    short_name          VARCHAR(50)  NOT NULL UNIQUE,       -- URL prefix: "crm", "finance"
    description         TEXT,
    version             VARCHAR(20)  NOT NULL DEFAULT '1.0.0',
    is_active           BOOLEAN      NOT NULL DEFAULT TRUE,
    environment         VARCHAR(20)  NOT NULL DEFAULT 'dev'
                        CHECK (environment IN ('dev', 'staging', 'prod')),
    db_connected_system VARCHAR(100),                        -- FK to connected_systems.name
    theme               JSONB        NOT NULL DEFAULT '{}',  -- {primary_color, font_family, ...}
    security_defaults   JSONB        NOT NULL DEFAULT '{}',  -- {logic: {groups: [...]}, ui: {groups: [...]}}
    config              JSONB        NOT NULL DEFAULT '{}',  -- full app.yaml parsed config
    created_at          TIMESTAMP WITH TIME ZONE NOT NULL DEFAULT NOW(),
    updated_at          TIMESTAMP WITH TIME ZONE NOT NULL DEFAULT NOW()
);

-- Indexes
CREATE INDEX idx_apps_short_name  ON apps(short_name);
CREATE INDEX idx_apps_is_active   ON apps(is_active);
CREATE INDEX idx_apps_environment ON apps(environment);
```

---

### 2.5 group_apps (Junction)

Which groups have access to which apps.

```sql
CREATE TABLE group_apps (
    id        SERIAL PRIMARY KEY,
    group_id  INTEGER     NOT NULL REFERENCES groups(id) ON DELETE CASCADE,
    app_id    INTEGER     NOT NULL REFERENCES apps(id) ON DELETE CASCADE,
    added_at  TIMESTAMP WITH TIME ZONE NOT NULL DEFAULT NOW(),
    UNIQUE (group_id, app_id)
);

-- Indexes
CREATE INDEX idx_ga_group_id ON group_apps(group_id);
CREATE INDEX idx_ga_app_id   ON group_apps(app_id);
```

---

### 2.6 object_permission

Unified 6-permission model with wildcard support. This is the heart of the security system.

```sql
CREATE TABLE object_permission (
    id          SERIAL PRIMARY KEY,
    group_name  VARCHAR(100) NOT NULL,
    object_ref  VARCHAR(255) NOT NULL,   -- e.g., "crm.rules.*", "crm.records.customer", "crm.*"
    permission  VARCHAR(20)  NOT NULL
                CHECK (permission IN ('view', 'use', 'create', 'update', 'delete', 'admin')),
    created_at  TIMESTAMP WITH TIME ZONE NOT NULL DEFAULT NOW(),
    created_by  INTEGER      REFERENCES users(id),
    UNIQUE (group_name, object_ref, permission)
);

-- Indexes
CREATE INDEX idx_perm_group      ON object_permission(group_name);
CREATE INDEX idx_perm_obj        ON object_permission(object_ref);
CREATE INDEX idx_perm_group_obj  ON object_permission(group_name, object_ref);
CREATE INDEX idx_perm_permission ON object_permission(permission);
```

**Permission applicability by object type:**

| Object Type | view | use | create | update | delete | admin |
|---|---|---|---|---|---|---|
| Expression Rule | ✓ | ✓ | — | — | — | ✓ |
| Constant | ✓ | ✓ | — | — | — | ✓ |
| Process | ✓ | ✓ | — | — | — | ✓ |
| Integration | ✓ | ✓ | — | — | — | ✓ |
| Web API | ✓ | ✓ | — | — | — | ✓ |
| Interface | ✓ | ✓ | — | — | — | ✓ |
| Page | ✓ | ✓ | — | — | — | ✓ |
| Translation Set | ✓ | ✓ | — | — | — | ✓ |
| Record | ✓ | ✓ | ✓ | ✓ | ✓ | ✓ |
| Document | ✓ | ✓ | ✓ | ✓ | ✓ | ✓ |
| Connected System | ✓ | ✓ | — | — | — | ✓ |

**Wildcard resolution order:** Most specific match wins:
`crm.rules.calculate_discount` > `crm.rules.*` > `crm.*`

**Example data:**

```sql
INSERT INTO object_permission (group_name, object_ref, permission) VALUES
    ('sales',       'crm.rules.*',            'use'),
    ('sales',       'crm.constants.*',        'use'),
    ('sales',       'crm.records.customer',   'view'),
    ('sales',       'crm.records.customer',   'create'),
    ('sales',       'crm.records.customer',   'update'),
    ('crm_admins',  'crm.*',                  'admin'),
    ('api_consumers', 'crm.web_apis.*',       'use');
```

---

### 2.7 connected_systems

Global external connections — database, REST API, FTP, SMTP, IMAP. **Not app-bound** — shared across all apps, secured via groups.

```sql
CREATE TABLE connected_systems (
    id                    SERIAL PRIMARY KEY,
    name                  VARCHAR(100) NOT NULL UNIQUE,   -- "crm_database", "stripe_api"
    type                  VARCHAR(20)  NOT NULL
                          CHECK (type IN ('database', 'rest_api', 'ftp', 'smtp', 'imap', 'custom')),
    description           TEXT,
    is_active             BOOLEAN      NOT NULL DEFAULT TRUE,
    connection_details    JSONB        NOT NULL DEFAULT '{}',
    -- For database: {driver, host, port, database, pool_size, max_overflow, pool_timeout,
    --               pool_recycle, pool_pre_ping, pool_reset_on_return}
    -- For rest_api: {base_url, timeout}
    -- For ftp:      {host, port, passive, encoding}
    -- For smtp:     {host, port, use_tls}
    -- For imap:     {host, port, use_ssl, mailbox}

    auth_type             VARCHAR(20)  NOT NULL DEFAULT 'none'
                          CHECK (auth_type IN ('none', 'basic', 'oauth2', 'api_key', 'certificate')),
    credentials_encrypted BYTEA,                          -- Fernet-encrypted JSON blob:
    -- {username, password, api_key, client_id, client_secret, tenant_id, certificate_path, ...}

    environment_overrides JSONB        NOT NULL DEFAULT '{}',
    -- {"staging": {"host": "staging-db"}, "prod": {"host": "prod-db", "pool_size": 50}}

    health_check          JSONB        NOT NULL DEFAULT '{}',
    -- {"enabled": true, "interval_seconds": 60, "endpoint": "/health", "timeout": 10}

    is_sensitive          BOOLEAN      NOT NULL DEFAULT FALSE,  -- if true, payloads encrypted in logs
    created_at            TIMESTAMP WITH TIME ZONE NOT NULL DEFAULT NOW(),
    updated_at            TIMESTAMP WITH TIME ZONE NOT NULL DEFAULT NOW(),
    created_by            INTEGER      REFERENCES users(id),
    updated_by            INTEGER      REFERENCES users(id)
);

-- Indexes
CREATE INDEX idx_cs_name      ON connected_systems(name);
CREATE INDEX idx_cs_type      ON connected_systems(type);
CREATE INDEX idx_cs_is_active ON connected_systems(is_active);
```

---

### 2.8 connected_system_groups (Junction)

Which groups can access which connected systems.

```sql
CREATE TABLE connected_system_groups (
    id                  SERIAL PRIMARY KEY,
    connected_system_id INTEGER     NOT NULL REFERENCES connected_systems(id) ON DELETE CASCADE,
    group_id            INTEGER     NOT NULL REFERENCES groups(id) ON DELETE CASCADE,
    added_at            TIMESTAMP WITH TIME ZONE NOT NULL DEFAULT NOW(),
    UNIQUE (connected_system_id, group_id)
);

-- Indexes
CREATE INDEX idx_csg_cs_id    ON connected_system_groups(connected_system_id);
CREATE INDEX idx_csg_group_id ON connected_system_groups(group_id);
```

---

### 2.9 process_instances (Partitioned)

Tracks every process execution. **Partitioned monthly** by `started_at` for performance at scale.

```sql
CREATE TABLE process_instances (
    id                   SERIAL,
    instance_id          VARCHAR(50)  NOT NULL UNIQUE,     -- "proc_abc123" (human-readable)
    process_name         VARCHAR(100) NOT NULL,             -- "onboard_customer"
    app_name             VARCHAR(50)  NOT NULL,             -- "crm"
    display_name         VARCHAR(255),                      -- "Onboard: Acme Corp" (from template)
    status               VARCHAR(20)  NOT NULL DEFAULT 'pending'
                         CHECK (status IN ('pending', 'running', 'paused',
                                           'completed', 'failed', 'cancelled', 'interrupted')),
    current_step         VARCHAR(100),
    inputs               JSONB        NOT NULL DEFAULT '{}', -- initial process inputs
    variables            JSONB        NOT NULL DEFAULT '{}', -- ctx.var values (runtime state)
    variable_visibility  JSONB        NOT NULL DEFAULT '{}', -- {"var_name": "logged"|"hidden"|"sensitive"}
    outputs              JSONB,                              -- final outputs on completion
    error_info           JSONB,                              -- AppOSError JSON on failure

    started_at           TIMESTAMP WITH TIME ZONE NOT NULL DEFAULT NOW(),
    completed_at         TIMESTAMP WITH TIME ZONE,
    started_by           INTEGER      NOT NULL REFERENCES users(id),
    parent_instance_id   INTEGER,                            -- FK for sub-processes
    triggered_by         VARCHAR(255),                       -- "web_api:crm.web_apis.submit_order"
                                                             -- or "event:records.customer.on_create"
                                                             -- or "schedule:0 9 * * *"
                                                             -- or "manual:user_456"

    -- Audit fields
    created_at           TIMESTAMP WITH TIME ZONE NOT NULL DEFAULT NOW(),
    updated_at           TIMESTAMP WITH TIME ZONE NOT NULL DEFAULT NOW(),

    PRIMARY KEY (id, started_at)                             -- required for partitioning
) PARTITION BY RANGE (started_at);

-- Monthly partitions (auto-created by platform)
CREATE TABLE process_instances_2026_01 PARTITION OF process_instances
    FOR VALUES FROM ('2026-01-01') TO ('2026-02-01');
CREATE TABLE process_instances_2026_02 PARTITION OF process_instances
    FOR VALUES FROM ('2026-02-01') TO ('2026-03-01');
-- ... continued monthly

-- Indexes (on parent table — inherited by partitions)
CREATE INDEX idx_pi_instance_id   ON process_instances(instance_id);
CREATE INDEX idx_pi_process_name  ON process_instances(process_name);
CREATE INDEX idx_pi_app_name      ON process_instances(app_name);
CREATE INDEX idx_pi_status        ON process_instances(status);
CREATE INDEX idx_pi_started_at    ON process_instances(started_at);
CREATE INDEX idx_pi_started_by    ON process_instances(started_by);
CREATE INDEX idx_pi_parent        ON process_instances(parent_instance_id);
CREATE INDEX idx_pi_app_status    ON process_instances(app_name, status);
```

**Variable visibility flags:**

| Flag | In Logs | In Admin UI | In `variables` Column | In AI Queries |
|------|---------|-------------|------------------------|---------------|
| `logged=True` (default) | ✓ | ✓ | Plaintext | ✓ |
| `logged=False` | ✗ | ✗ | Hashed (SHA-256) | ✗ |
| `sensitive=True` | ✗ | ✗ | Encrypted (Fernet) | ✗ |

---

### 2.10 process_step_log (Partitioned)

Separate table for step execution history — one row per step execution attempt. **Not a JSON array** inside `process_instances`.

```sql
CREATE TABLE process_step_log (
    id                    SERIAL,
    process_instance_id   INTEGER      NOT NULL,
    step_name             VARCHAR(100) NOT NULL,
    rule_ref              VARCHAR(200) NOT NULL,           -- "crm.rules.validate_customer"
    status                VARCHAR(30)  NOT NULL
                          CHECK (status IN ('pending', 'running', 'completed', 'failed',
                                            'skipped', 'async_dispatched', 'interrupted')),
    started_at            TIMESTAMP WITH TIME ZONE NOT NULL DEFAULT NOW(),
    completed_at          TIMESTAMP WITH TIME ZONE,
    duration_ms           NUMERIC(12,3),
    inputs                JSONB,                            -- step inputs (opt-in via logging config)
    outputs               JSONB,                            -- step outputs (opt-in)
    error_info            JSONB,                            -- AppOSError JSON if failed:
    -- {"error_type": "AppOSTimeoutError", "message": "...", "execution_id": "...",
    --  "object_ref": "...", "stack_trace": "..."}

    attempt               INTEGER      NOT NULL DEFAULT 1,  -- retry attempt number
    is_fire_and_forget    BOOLEAN      NOT NULL DEFAULT FALSE,
    is_parallel           BOOLEAN      NOT NULL DEFAULT FALSE,

    PRIMARY KEY (id, started_at)
) PARTITION BY RANGE (started_at);

-- Monthly partitions (same strategy as process_instances)
CREATE TABLE process_step_log_2026_01 PARTITION OF process_step_log
    FOR VALUES FROM ('2026-01-01') TO ('2026-02-01');
CREATE TABLE process_step_log_2026_02 PARTITION OF process_step_log
    FOR VALUES FROM ('2026-02-01') TO ('2026-03-01');

-- Indexes
CREATE INDEX idx_psl_instance_id   ON process_step_log(process_instance_id);
CREATE INDEX idx_psl_step_name     ON process_step_log(step_name);
CREATE INDEX idx_psl_status        ON process_step_log(status);
CREATE INDEX idx_psl_started_at    ON process_step_log(started_at);
CREATE INDEX idx_psl_instance_step ON process_step_log(process_instance_id, step_name, started_at);
```

**Status values:**

| Status | Meaning |
|--------|---------|
| `pending` | Queued, not yet started |
| `running` | Currently executing |
| `completed` | Finished successfully |
| `failed` | Execution failed (see `error_info`) |
| `skipped` | Condition evaluated to false |
| `async_dispatched` | `fire_and_forget=True` — dispatched, running independently |
| `interrupted` | Platform shutdown interrupted this step |

---

### 2.11 dependency_changes

Tracks dependency graph changes over time for audit and AI querying.

```sql
CREATE TABLE dependency_changes (
    id          SERIAL PRIMARY KEY,
    object_ref  VARCHAR(255) NOT NULL,       -- "crm.rules.calculate_discount"
    change_type VARCHAR(20)  NOT NULL
                CHECK (change_type IN ('added', 'removed', 'modified')),
    old_hash    VARCHAR(64),                  -- SHA-256 hash of previous version
    new_hash    VARCHAR(64),                  -- SHA-256 hash of current version
    details     JSONB,                        -- {"field_added": "loyalty_points", ...}
    changed_at  TIMESTAMP WITH TIME ZONE NOT NULL DEFAULT NOW(),
    changed_by  VARCHAR(100)                  -- user or "system" for auto-detection
);

-- Indexes
CREATE INDEX idx_depchange_obj  ON dependency_changes(object_ref);
CREATE INDEX idx_depchange_time ON dependency_changes(changed_at);
CREATE INDEX idx_depchange_type ON dependency_changes(change_type);
```

---

### 2.12 object_registry

Runtime registry of all discovered objects across all apps. Populated on startup by scanning app directories.

```sql
CREATE TABLE object_registry (
    id            SERIAL PRIMARY KEY,
    object_ref    VARCHAR(255) NOT NULL UNIQUE,  -- "crm.rules.calculate_discount"
    object_type   VARCHAR(30)  NOT NULL
                  CHECK (object_type IN (
                      'record', 'expression_rule', 'constant', 'process', 'step',
                      'integration', 'web_api', 'interface', 'page', 'site',
                      'document', 'folder', 'translation_set', 'connected_system'
                  )),
    app_name      VARCHAR(50),                    -- NULL for platform / global objects
    module_path   VARCHAR(500) NOT NULL,          -- Python module path
    file_path     VARCHAR(500) NOT NULL,          -- Filesystem path
    source_hash   VARCHAR(64)  NOT NULL,          -- SHA-256 of source file
    metadata      JSONB        NOT NULL DEFAULT '{}',
    -- For records: {table_name, audit, soft_delete, display_field, search_fields, connected_system}
    -- For rules:   {inputs, outputs, depends_on, cacheable, cache_ttl}
    -- For processes: {inputs, triggers, display_name, timeout}
    -- For web_apis: {method, path, version, auth, rate_limit}
    -- For constants: {type, has_env_overrides}
    -- For integrations: {connected_system, method, path, log_payload}
    -- For pages: {route, title, interface, on_load}
    -- For sites: {pages, default_page, auth_required}

    is_active     BOOLEAN      NOT NULL DEFAULT TRUE,
    discovered_at TIMESTAMP WITH TIME ZONE NOT NULL DEFAULT NOW(),
    updated_at    TIMESTAMP WITH TIME ZONE NOT NULL DEFAULT NOW()
);

-- Indexes
CREATE INDEX idx_or_type      ON object_registry(object_type);
CREATE INDEX idx_or_app       ON object_registry(app_name);
CREATE INDEX idx_or_type_app  ON object_registry(object_type, app_name);
```

---

### 2.13 platform_config

Stores runtime-editable platform configuration (supplement to `appos.yaml`).

```sql
CREATE TABLE platform_config (
    id         SERIAL PRIMARY KEY,
    key        VARCHAR(100) NOT NULL UNIQUE,   -- "security.session_timeout", "logging.level"
    value      JSONB        NOT NULL,           -- JSON value (string, number, object)
    category   VARCHAR(50)  NOT NULL,           -- "security", "logging", "celery", "ui"
    updated_at TIMESTAMP WITH TIME ZONE NOT NULL DEFAULT NOW(),
    updated_by INTEGER      REFERENCES users(id)
);

-- Indexes
CREATE INDEX idx_pc_key      ON platform_config(key);
CREATE INDEX idx_pc_category ON platform_config(category);
```

**Example rows:**

```sql
INSERT INTO platform_config (key, value, category) VALUES
    ('security.session_timeout',        '3600',           'security'),
    ('security.idle_timeout',           '1800',           'security'),
    ('security.max_concurrent_sessions','5',              'security'),
    ('security.permission_cache_ttl',   '300',            'security'),
    ('security.max_login_attempts',     '5',              'security'),
    ('logging.level',                   '"INFO"',         'logging'),
    ('logging.retention.execution_days','90',             'logging'),
    ('logging.retention.performance_days','30',           'logging'),
    ('logging.retention.security_days', '365',            'logging'),
    ('process_instances.archive_after_days','90',         'process'),
    ('documents.max_upload_size_mb',    '50',             'documents');
```

---

### 2.14 scheduled_tasks

Registered scheduled processes (Celery Beat schedule stored in DB for admin visibility).

```sql
CREATE TABLE scheduled_tasks (
    id            SERIAL PRIMARY KEY,
    task_name     VARCHAR(200) NOT NULL UNIQUE,   -- "crm.processes.daily_report"
    schedule      VARCHAR(100) NOT NULL,           -- cron expression: "0 8 * * *"
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

-- Indexes
CREATE INDEX idx_st_app       ON scheduled_tasks(app_name);
CREATE INDEX idx_st_is_active ON scheduled_tasks(is_active);
CREATE INDEX idx_st_next_run  ON scheduled_tasks(next_run_at);
```

---

### 2.15 login_audit_log

Tracks login attempts for security compliance.

```sql
CREATE TABLE login_audit_log (
    id           SERIAL PRIMARY KEY,
    username     VARCHAR(100) NOT NULL,
    user_id      INTEGER      REFERENCES users(id),
    success      BOOLEAN      NOT NULL,
    ip_address   INET,
    user_agent   TEXT,
    failure_reason VARCHAR(100),     -- "invalid_password", "account_disabled", "max_attempts"
    timestamp    TIMESTAMP WITH TIME ZONE NOT NULL DEFAULT NOW()
);

-- Indexes
CREATE INDEX idx_lal_username  ON login_audit_log(username);
CREATE INDEX idx_lal_user_id   ON login_audit_log(user_id);
CREATE INDEX idx_lal_success   ON login_audit_log(success);
CREATE INDEX idx_lal_timestamp ON login_audit_log(timestamp);
```

---

## 3. Per-App Auto-Generated Tables

These tables are **auto-generated** from developer `@record` definitions via the Pydantic → SQLAlchemy → Alembic pipeline. The platform creates them in the app's Connected System database (not in `appos_core`).

### 3.1 Record Tables (Auto-Generated from @record)

For each `@record` class, the platform generates:

```python
# Developer writes:
@record
class Customer(BaseModel):
    name: str = Field(max_length=100)
    email: str = Field(max_length=255, pattern=r"...")
    phone: Optional[str] = Field(default=None, max_length=20)
    tier: str = Field(default="bronze", json_schema_extra={"choices": [...]})
    credit_limit: float = Field(default=0.0, ge=0, decimal_places=2)
    is_active: bool = Field(default=True)
    created_at: datetime = Field(default_factory=datetime.utcnow)
    orders: List["Order"] = has_many("Order", back_ref="customer")
    primary_address: Optional["Address"] = has_one("Address")
    class Meta:
        table_name = "customers"
        audit = True
        soft_delete = True
```

**Generated SQL:**

```sql
-- Auto-generated from @record Customer
CREATE TABLE customers (
    -- Primary key (always auto-generated)
    id              SERIAL PRIMARY KEY,

    -- Fields from Pydantic model
    name            VARCHAR(100) NOT NULL,
    email           VARCHAR(255) NOT NULL UNIQUE,
    phone           VARCHAR(20),
    tier            VARCHAR(20)  NOT NULL DEFAULT 'bronze'
                    CHECK (tier IN ('bronze', 'silver', 'gold', 'platinum')),
    credit_limit    NUMERIC(10,2) NOT NULL DEFAULT 0.00
                    CHECK (credit_limit >= 0),
    is_active       BOOLEAN      NOT NULL DEFAULT TRUE,

    -- AuditMixin (always added)
    created_at      TIMESTAMP WITH TIME ZONE NOT NULL DEFAULT NOW(),
    updated_at      TIMESTAMP WITH TIME ZONE NOT NULL DEFAULT NOW(),
    created_by      INTEGER,       -- user ID who created
    updated_by      INTEGER,       -- user ID who last updated

    -- SoftDeleteMixin (when Meta.soft_delete = True)
    is_deleted      BOOLEAN      NOT NULL DEFAULT FALSE,
    deleted_at      TIMESTAMP WITH TIME ZONE,
    deleted_by      INTEGER
);

-- Auto-generated indexes
CREATE INDEX idx_customers_is_active  ON customers(is_active);
CREATE INDEX idx_customers_tier      ON customers(tier);
CREATE INDEX idx_customers_is_deleted ON customers(is_deleted);
-- Search fields indexes (from Meta.search_fields)
CREATE INDEX idx_customers_name  ON customers(name);
CREATE INDEX idx_customers_email ON customers(email);
CREATE INDEX idx_customers_phone ON customers(phone);
```

### Pydantic → SQL Type Mapping

| Pydantic Type | SQLAlchemy Column | PostgreSQL Type |
|---|---|---|
| `str` | `String(max_length)` | `VARCHAR(n)` |
| `str` (no max) | `Text` | `TEXT` |
| `int` | `Integer` | `INTEGER` |
| `float` | `Numeric(precision, scale)` | `NUMERIC(p,s)` |
| `bool` | `Boolean` | `BOOLEAN` |
| `datetime` | `DateTime(timezone=True)` | `TIMESTAMP WITH TIME ZONE` |
| `date` | `Date` | `DATE` |
| `Optional[T]` | `Column(T, nullable=True)` | `T NULL` |
| `List[str]` | `ARRAY(String)` or `JSON` | `TEXT[]` or `JSONB` |
| `dict` | `JSON` | `JSONB` |
| Field with `choices` | `String` + CHECK | `VARCHAR + CHECK IN (...)` |
| Field with `pattern` | `String` | `VARCHAR` (validation in app layer) |
| Field with `ge`/`le` | Column + CHECK | `CHECK (field >= n)` |
| `has_many(...)` | `relationship(...)` | FK on child table |
| `belongs_to(...)` | `Column(Integer, ForeignKey)` | `INTEGER REFERENCES ...` |
| `has_one(...)` | `relationship(uselist=False)` | FK on child table, unique |

### 3.2 Audit Log Tables (Conditional)

Generated **only** when `Meta.audit = True` on a Record. One audit table per record.

```sql
-- Auto-generated: {app}_{table}_audit_log
-- Example: crm_customers_audit_log
CREATE TABLE crm_customers_audit_log (
    id          SERIAL PRIMARY KEY,
    record_id   INTEGER      NOT NULL,           -- FK to customers.id
    field_name  VARCHAR(100) NOT NULL,
    old_value   TEXT,                              -- JSON-serialized old value
    new_value   TEXT,                              -- JSON-serialized new value
    operation   VARCHAR(20)  NOT NULL              -- 'create', 'update', 'delete'
                CHECK (operation IN ('create', 'update', 'delete')),
    changed_by  INTEGER      NOT NULL,             -- user ID
    changed_at  TIMESTAMP WITH TIME ZONE NOT NULL DEFAULT NOW(),
    execution_id VARCHAR(50),                      -- correlation ID for tracing
    process_instance_id VARCHAR(50)                -- if within a process
);

-- Indexes
CREATE INDEX idx_cust_audit_record   ON crm_customers_audit_log(record_id);
CREATE INDEX idx_cust_audit_field    ON crm_customers_audit_log(field_name);
CREATE INDEX idx_cust_audit_changed  ON crm_customers_audit_log(changed_at);
CREATE INDEX idx_cust_audit_user     ON crm_customers_audit_log(changed_by);
CREATE INDEX idx_cust_audit_op       ON crm_customers_audit_log(operation);
```

**Trigger pattern:** The CRUD service hooks into `after_create`, `after_update`, `after_delete` to write audit rows:

- **Create:** One row per field with `old_value=NULL`, `new_value=<value>`, `operation='create'`
- **Update:** One row per changed field with `old_value=<old>`, `new_value=<new>`, `operation='update'`
- **Delete:** One row with `field_name='_record'`, `old_value=<full record JSON>`, `operation='delete'`

---

### 3.3 Documents Table

Per-app document metadata. Physical files stored on filesystem at `apps/{app}/runtime/documents/{folder}/`.

```sql
CREATE TABLE documents (
    id              SERIAL PRIMARY KEY,
    name            VARCHAR(255) NOT NULL,
    file_path       VARCHAR(500) NOT NULL,
    folder_id       INTEGER      REFERENCES folders(id),
    mime_type       VARCHAR(100) NOT NULL,
    size_bytes      BIGINT       NOT NULL CHECK (size_bytes >= 0),
    version         INTEGER      NOT NULL DEFAULT 1,
    tags            JSONB        NOT NULL DEFAULT '[]',     -- ["invoice", "2026"]
    owner_id        INTEGER      NOT NULL,                   -- user ID
    is_archived     BOOLEAN      NOT NULL DEFAULT FALSE,
    parent_record_type VARCHAR(100),                          -- "customers" (for security inheritance)
    parent_record_id   INTEGER,                               -- FK to parent record

    -- AuditMixin
    created_at      TIMESTAMP WITH TIME ZONE NOT NULL DEFAULT NOW(),
    updated_at      TIMESTAMP WITH TIME ZONE NOT NULL DEFAULT NOW(),
    created_by      INTEGER,
    updated_by      INTEGER,

    -- SoftDeleteMixin
    is_deleted      BOOLEAN      NOT NULL DEFAULT FALSE,
    deleted_at      TIMESTAMP WITH TIME ZONE,
    deleted_by      INTEGER
);

-- Indexes
CREATE INDEX idx_doc_folder       ON documents(folder_id);
CREATE INDEX idx_doc_owner        ON documents(owner_id);
CREATE INDEX idx_doc_mime          ON documents(mime_type);
CREATE INDEX idx_doc_parent       ON documents(parent_record_type, parent_record_id);
CREATE INDEX idx_doc_is_deleted   ON documents(is_deleted);
CREATE INDEX idx_doc_tags         ON documents USING GIN(tags);
```

---

### 3.4 Document Versions Table

Tracks version history for each document.

```sql
CREATE TABLE document_versions (
    id            SERIAL PRIMARY KEY,
    document_id   INTEGER      NOT NULL REFERENCES documents(id) ON DELETE CASCADE,
    version       INTEGER      NOT NULL,
    file_path     VARCHAR(500) NOT NULL,
    size_bytes    BIGINT       NOT NULL CHECK (size_bytes >= 0),
    uploaded_by   INTEGER      NOT NULL,                   -- user ID
    uploaded_at   TIMESTAMP WITH TIME ZONE NOT NULL DEFAULT NOW(),
    change_note   VARCHAR(500),

    UNIQUE (document_id, version)
);

-- Indexes
CREATE INDEX idx_dv_document   ON document_versions(document_id);
CREATE INDEX idx_dv_version    ON document_versions(document_id, version);
CREATE INDEX idx_dv_uploaded   ON document_versions(uploaded_at);
```

---

### 3.5 Folders Table

Folder configuration — drives physical directory creation and MIME validation.

```sql
CREATE TABLE folders (
    id              SERIAL PRIMARY KEY,
    name            VARCHAR(100) NOT NULL,
    path            VARCHAR(500) NOT NULL,               -- relative: "invoices", "contracts/2026"
    purpose         VARCHAR(200),
    app_id          INTEGER      NOT NULL,                -- FK to apps table (in appos_core)
    document_types  JSONB        NOT NULL DEFAULT '["*/*"]',  -- allowed MIME types
    max_size_mb     INTEGER      NOT NULL DEFAULT 1000,
    auto_cleanup    JSONB,                                -- {"retention_days": 365, "archive_first": true}
    is_active       BOOLEAN      NOT NULL DEFAULT TRUE,

    -- AuditMixin
    created_at      TIMESTAMP WITH TIME ZONE NOT NULL DEFAULT NOW(),
    updated_at      TIMESTAMP WITH TIME ZONE NOT NULL DEFAULT NOW(),
    created_by      INTEGER,
    updated_by      INTEGER,

    UNIQUE (app_id, path)
);

-- Indexes
CREATE INDEX idx_folder_app       ON folders(app_id);
CREATE INDEX idx_folder_is_active ON folders(is_active);
CREATE INDEX idx_folder_path      ON folders(path);
```

---

### 3.6 Event Log Table (Per-App)

Custom business event logging — app-level audit trail beyond record changes.

```sql
-- {app}_event_log — one per app
-- Example: crm_event_log
CREATE TABLE crm_event_log (
    id              SERIAL PRIMARY KEY,
    event_type      VARCHAR(100) NOT NULL,           -- "customer_tier_upgraded", "order_cancelled"
    event_source    VARCHAR(255) NOT NULL,           -- "crm.rules.upgrade_tier"
    object_ref      VARCHAR(255),                     -- "crm.records.customer:123"
    user_id         INTEGER      NOT NULL,
    execution_id    VARCHAR(50),
    process_instance_id VARCHAR(50),
    data            JSONB        NOT NULL DEFAULT '{}',  -- event-specific payload
    timestamp       TIMESTAMP WITH TIME ZONE NOT NULL DEFAULT NOW()
);

-- Indexes
CREATE INDEX idx_cev_event_type   ON crm_event_log(event_type);
CREATE INDEX idx_cev_source       ON crm_event_log(event_source);
CREATE INDEX idx_cev_user         ON crm_event_log(user_id);
CREATE INDEX idx_cev_timestamp    ON crm_event_log(timestamp);
CREATE INDEX idx_cev_object       ON crm_event_log(object_ref);
```

---

### 3.7 Translation Storage Table (Optional — Per-App)

Translation sets are primarily defined in Python files, but may optionally be cached/overridden in DB for admin console editing.

```sql
CREATE TABLE translation_entries (
    id                  SERIAL PRIMARY KEY,
    translation_set     VARCHAR(100) NOT NULL,       -- "crm_labels"
    app_name            VARCHAR(50)  NOT NULL,       -- "crm"
    key                 VARCHAR(200) NOT NULL,       -- "customer_name"
    language            VARCHAR(10)  NOT NULL,       -- "en", "fr", "es"
    value               TEXT         NOT NULL,       -- "Customer Name"
    is_override         BOOLEAN      NOT NULL DEFAULT FALSE,  -- admin override of file-defined value
    updated_at          TIMESTAMP WITH TIME ZONE NOT NULL DEFAULT NOW(),
    updated_by          INTEGER      REFERENCES users(id),

    UNIQUE (translation_set, key, language)
);

-- Indexes
CREATE INDEX idx_te_set       ON translation_entries(translation_set);
CREATE INDEX idx_te_app       ON translation_entries(app_name);
CREATE INDEX idx_te_key       ON translation_entries(translation_set, key);
CREATE INDEX idx_te_language  ON translation_entries(language);
```

---

## 4. Redis Data Model

Redis stores ephemeral, high-frequency-access data. **Not backed up** — all data is reconstructible from PostgreSQL or regenerated at runtime.

### 4.1 Database Allocation

| DB | Purpose | Key Pattern | TTL | Recovery |
|----|---------|-------------|-----|----------|
| 0 | Celery broker | Celery internal | — | Tasks re-queued on restart |
| 1 | Celery results | Celery internal | Per-task | Regenerated on completion |
| 2 | Permission cache | `appos:perms:{hash}` | 300s (5min) | Auto-populated from DB on miss |
| 3 | Object cache | `appos:obj:{object_ref}` | 600s (10min) | Auto-populated from filesystem |
| 4 | Session store | `appos:session:{session_id}` | session_timeout | Users re-login after flush |
| 5 | Rate limiting | `appos:rate:{endpoint}:{ip}` | window (60s) | Auto-reset |

### 4.2 Permission Cache (DB 2)

```
Key:    appos:perms:{groups_hash}:{object_ref}:{permission}
Value:  "1" (allowed) | "0" (denied)
TTL:    300 seconds (5 minutes)

Example:
  Key:   appos:perms:abc123:crm.rules.calculate_discount:use
  Value: "1"
  TTL:   300s
```

**Invalidation:** On permission change (admin console) → delete keys matching `appos:perms:*`.

### 4.3 Session Store (DB 4)

```
Key:    appos:session:{session_id}
Value:  JSON hash:
        {
            "user_id": 42,
            "username": "john_doe",
            "user_type": "basic",
            "groups": ["sales", "support"],
            "preferred_language": "en",
            "timezone": "America/New_York",
            "csrf_token": "random_token_here",
            "login_at": "2026-02-13T10:00:00Z",
            "last_activity": "2026-02-13T10:30:00Z",
            "ip_address": "192.168.1.100"
        }
TTL:    session_timeout (default 3600s)

Idle tracking:
  Key:   appos:session:{session_id}:idle
  Value: timestamp of last activity
  TTL:   idle_timeout (default 1800s)
```

**Concurrent session tracking:**

```
Key:    appos:user_sessions:{user_id}
Value:  SET of session_ids
TTL:    session_timeout
```

When `SET.length > max_concurrent_sessions`, oldest session is evicted.

### 4.4 Object Cache (DB 3)

```
Key:    appos:obj:{object_ref}
Value:  JSON serialized object metadata
TTL:    600 seconds (10 minutes)

Example:
  Key:   appos:obj:crm.rules.calculate_discount
  Value: {"type": "expression_rule", "app": "crm", "inputs": [...], ...}
```

### 4.5 Rate Limiting (DB 5)

```
Key:    appos:rate:{app}:{endpoint}:{client_id}
Value:  Counter (INCR)
TTL:    window seconds (e.g., 60)

Example:
  Key:   appos:rate:crm:get_customer_info:api_key_abc
  Value: 47
  TTL:   60s
```

---

## 5. Entity Relationship Diagrams

### 5.1 Platform Core ER Diagram

```
┌──────────────┐     ┌──────────────┐     ┌──────────────┐
│    users     │     │  user_groups  │     │    groups     │
├──────────────┤     ├──────────────┤     ├──────────────┤
│ PK id        │──┐  │ PK id        │  ┌──│ PK id        │
│    username  │  └──│ FK user_id   │  │  │    name      │
│    email     │     │ FK group_id  │──┘  │    type      │
│    pass_hash │     │    added_at  │     │    is_active  │
│    full_name │     └──────────────┘     └──────┬───────┘
│    is_active │                                  │
│    user_type │     ┌──────────────┐     ┌──────┴───────┐
│    pref_lang │     │  group_apps  │     │              │
│    timezone  │     ├──────────────┤     │              │
│    last_login│     │ PK id        │     │              │
│    api_key_h │     │ FK group_id  │─────┘              │
│    created_at│     │ FK app_id    │──┐                  │
│    updated_at│     └──────────────┘  │                  │
└──────────────┘                       │                  │
                                       │                  │
                      ┌────────────────┴──┐               │
                      │       apps        │               │
                      ├───────────────────┤               │
                      │ PK id             │               │
                      │    name           │               │
                      │    short_name     │               │
                      │    is_active      │               │
                      │    environment    │               │
                      │    db_conn_sys    │               │
                      │    theme (JSONB)  │               │
                      │    security_defs  │               │
                      └───────────────────┘               │
                                                          │
┌───────────────────────┐     ┌───────────────────────┐   │
│  object_permission    │     │  connected_systems    │   │
├───────────────────────┤     ├───────────────────────┤   │
│ PK id                 │     │ PK id                 │   │
│    group_name ────────┼─────│    name               │   │
│    object_ref         │     │    type               │   │
│    permission         │     │    is_active          │   │
│    created_at         │     │    conn_details(JSONB)│   │
└───────────────────────┘     │    auth_type          │   │
                              │    creds_encrypted    │   │
                              │    env_overrides(JSONB│   │
                              │    health_check(JSONB)│   │
                              └───────────┬───────────┘   │
                                          │               │
                              ┌───────────┴───────────┐   │
                              │ connected_system_grps │   │
                              ├───────────────────────┤   │
                              │ PK id                 │   │
                              │ FK connected_system_id│   │
                              │ FK group_id ──────────┼───┘
                              └───────────────────────┘
```

### 5.2 Process Engine ER Diagram

```
┌───────────────────────────┐
│    process_instances      │
│    (PARTITIONED monthly)  │
├───────────────────────────┤
│ PK id + started_at       │
│    instance_id (UNIQUE)   │
│    process_name           │
│    app_name               │
│    display_name           │
│    status                 │
│    current_step           │
│    inputs (JSONB)         │
│    variables (JSONB)      │
│    variable_visibility    │
│    outputs (JSONB)        │
│    error_info (JSONB)     │
│    started_at             │
│    completed_at           │
│ FK started_by → users    │
│    parent_instance_id     │───── self-reference (sub-processes)
│    triggered_by           │
└────────────┬──────────────┘
             │ 1:N
┌────────────┴──────────────┐
│    process_step_log       │
│    (PARTITIONED monthly)  │
├───────────────────────────┤
│ PK id + started_at       │
│ FK process_instance_id   │
│    step_name              │
│    rule_ref               │
│    status                 │
│    started_at             │
│    completed_at           │
│    duration_ms            │
│    inputs (JSONB)         │
│    outputs (JSONB)        │
│    error_info (JSONB)     │
│    attempt                │
│    is_fire_and_forget     │
│    is_parallel            │
└───────────────────────────┘
```

### 5.3 Per-App Data ER Diagram (Example: CRM)

```
┌───────────────┐    1:N    ┌───────────────┐    1:N    ┌───────────────┐
│   customers   │──────────│    orders      │──────────│  order_items   │
├───────────────┤          ├───────────────┤          ├───────────────┤
│ PK id         │          │ PK id         │          │ PK id         │
│    name       │          │ FK customer_id│          │ FK order_id   │
│    email      │          │    order_number│         │    product_id │
│    phone      │          │    status     │          │    quantity   │
│    tier       │          │    total_amount│         │    unit_price │
│    credit_lim │          │    order_date │          └───────────────┘
│    is_active  │          │ -- audit --   │
│ -- audit --   │          │ -- soft_del --│
│ -- soft_del --│          └───────────────┘
└───────┬───────┘
        │
        │ 1:N                ┌─────────────────────────┐
        │                    │ crm_customers_audit_log │
        └───────────────────│  (conditional: audit=T) │
                            ├─────────────────────────┤
                            │ PK id                   │
                            │    record_id → customers│
                            │    field_name           │
                            │    old_value            │
                            │    new_value            │
                            │    operation            │
                            │    changed_by           │
                            │    changed_at           │
                            └─────────────────────────┘

┌───────────────┐    1:N    ┌───────────────────┐
│    folders    │──────────│     documents      │
├───────────────┤          ├───────────────────┤
│ PK id         │          │ PK id             │
│    name       │          │ FK folder_id      │
│    path       │          │    name           │
│    purpose    │          │    file_path      │
│    app_id     │          │    mime_type      │
│    doc_types  │          │    size_bytes     │
│    max_size_mb│          │    version        │
│    auto_clean │          │    tags (JSONB)   │
└───────────────┘          │    owner_id       │
                           │    parent_record_*│
                           └────────┬──────────┘
                                    │ 1:N
                           ┌────────┴──────────┐
                           │ document_versions │
                           ├───────────────────┤
                           │ PK id             │
                           │ FK document_id    │
                           │    version        │
                           │    file_path      │
                           │    size_bytes     │
                           │    uploaded_by    │
                           │    uploaded_at    │
                           │    change_note    │
                           └───────────────────┘
```

---

## 6. Partitioning & Archival Strategy

### 6.1 Partitioned Tables

Two tables require partitioning due to high volume:

| Table | Partition Key | Range | Rationale |
|-------|--------------|-------|-----------|
| `process_instances` | `started_at` | Monthly | Thousands of process executions per day |
| `process_step_log` | `started_at` | Monthly | 5-10x more rows than process_instances |

### 6.2 Partition Management

```sql
-- Auto-partition creation (run monthly via scheduled task or pg_partman)
-- Platform creates next month's partition on the 1st of each month

-- Example: Create partition for March 2026
CREATE TABLE process_instances_2026_03 PARTITION OF process_instances
    FOR VALUES FROM ('2026-03-01') TO ('2026-04-01');

CREATE TABLE process_step_log_2026_03 PARTITION OF process_step_log
    FOR VALUES FROM ('2026-03-01') TO ('2026-04-01');
```

### 6.3 Archival Policy

Configured in `appos.yaml`:

```yaml
process_instances:
  archive_after_days: 90      # move completed instances to archive
  partition_range: monthly
```

**Archival process:**

```sql
-- 1. Create archive table (flat, non-partitioned)
CREATE TABLE process_instances_archive (
    LIKE process_instances INCLUDING ALL
);

CREATE TABLE process_step_log_archive (
    LIKE process_step_log INCLUDING ALL
);

-- 2. Scheduled platform process moves old completed data:
-- Move completed instances older than 90 days
INSERT INTO process_instances_archive
SELECT * FROM process_instances
WHERE status IN ('completed', 'failed', 'cancelled')
  AND completed_at < NOW() - INTERVAL '90 days';

DELETE FROM process_instances
WHERE status IN ('completed', 'failed', 'cancelled')
  AND completed_at < NOW() - INTERVAL '90 days';

-- 3. Drop empty old partitions
DROP TABLE process_instances_2025_09;  -- after all data archived
```

### 6.4 Partition for Audit Logs (Future)

For apps with very high record change rates, audit log tables can also be partitioned:

```sql
-- Only if {app}_{record}_audit_log exceeds ~10M rows
CREATE TABLE crm_customers_audit_log (
    ...
) PARTITION BY RANGE (changed_at);
```

---

## 7. Indexing Strategy

### 7.1 Platform Table Indexes Summary

| Table | Index | Columns | Type | Purpose |
|-------|-------|---------|------|---------|
| users | idx_users_username | username | B-tree (unique) | Login lookup |
| users | idx_users_email | email | B-tree (unique) | Email lookup |
| users | idx_users_user_type | user_type | B-tree | Filter by type |
| users | idx_users_is_active | is_active | B-tree | Active user filter |
| groups | idx_groups_name | name | B-tree (unique) | Group lookup |
| groups | idx_groups_type | type | B-tree | Filter by type |
| object_permission | idx_perm_group_obj | group_name, object_ref | B-tree (composite) | Permission check (hot path) |
| object_permission | idx_perm_group | group_name | B-tree | Group permission listing |
| object_permission | idx_perm_obj | object_ref | B-tree | Object permission listing |
| connected_systems | idx_cs_name | name | B-tree (unique) | Connection lookup |
| process_instances | idx_pi_instance_id | instance_id | B-tree (unique) | Instance lookup |
| process_instances | idx_pi_app_status | app_name, status | B-tree (composite) | Admin console filter |
| process_instances | idx_pi_started_at | started_at | B-tree | Time-based queries |
| process_step_log | idx_psl_instance_step | process_instance_id, step_name, started_at | B-tree (composite) | Step history lookup |
| dependency_changes | idx_depchange_obj | object_ref | B-tree | Impact analysis |
| dependency_changes | idx_depchange_time | changed_at | B-tree | Change timeline |

### 7.2 Per-App Table Index Guidelines

Auto-generated indexes for every `@record`:

1. **Primary key** (always): `id`
2. **Unique fields**: Any field with `unique=True` in Pydantic
3. **Foreign keys**: All `belongs_to` relationships
4. **Search fields**: All fields in `Meta.search_fields`
5. **Soft delete**: `is_deleted` (when `Meta.soft_delete = True`)
6. **JSONB columns**: GIN index for array/object search (tags, etc.)
7. **Choice fields**: B-tree for enum-like filtering

### 7.3 Index Naming Convention

```
idx_{table}_{column}           -- single column
idx_{table}_{col1}_{col2}      -- composite
idx_{table}_{column}_unique    -- unique constraint
idx_{table}_{column}_gin       -- GIN (JSONB/array)
```

---

## 8. Data Migration & Alembic

### 8.1 Migration Strategy

```
┌──────────────────────────────────────────────────────────────────┐
│                    MIGRATION FLOW                                │
├──────────────────────────────────────────────────────────────────┤
│                                                                  │
│  Developer defines @record                                       │
│       │                                                          │
│       ▼                                                          │
│  `appos generate`                                                │
│       │                                                          │
│       ├── Pydantic → SQLAlchemy model (.appos/generated/models/) │
│       │                                                          │
│       ├── Diff current model vs DB schema                        │
│       │                                                          │
│       └── Generate Alembic migration (migrations/versions/)      │
│                                                                  │
│  `appos migrate`                                                 │
│       │                                                          │
│       └── Run Alembic upgrade head                               │
│                                                                  │
│  `appos check`                                                   │
│       │                                                          │
│       └── Validate schema matches models                         │
│                                                                  │
└──────────────────────────────────────────────────────────────────┘
```

### 8.2 Two Migration Tracks

| Track | Database | Location | Generated By |
|-------|----------|----------|-------------|
| **Platform** | `appos_core` | `migrations/platform/versions/` | Platform developers (manual) |
| **App** | App DB (per Connected System) | `migrations/{app}/versions/` | `appos generate` (auto from @record) |

### 8.3 Platform Schema Versioning

Platform tables (§2) are version-controlled and migrated on `appos migrate`:

```python
# migrations/platform/env.py
from appos.db.platform_models import Base as PlatformBase

target_metadata = PlatformBase.metadata

# Only runs against appos_core database
```

### 8.4 App Schema Versioning

App tables (§3) are auto-generated on `appos generate`:

```python
# migrations/{app}/env.py
# Connects to the app's Connected System database
# Compares generated SQLAlchemy models against current DB state
# Produces migration script
```

---

## 9. Security & Encryption

### 9.1 Credential Encryption

Connected System credentials are encrypted at rest using Fernet symmetric encryption:

```
┌──────────────────────────────────────────────────────────────────┐
│                  CREDENTIAL STORAGE                              │
├──────────────────────────────────────────────────────────────────┤
│                                                                  │
│  connected_systems.credentials_encrypted column:                 │
│                                                                  │
│  1. Admin enters credentials via Admin Console                  │
│  2. Platform serializes to JSON:                                │
│     {"username": "admin", "password": "secret123",              │
│      "api_key": "sk_live_xxx..."}                               │
│  3. Encrypt with Fernet (AES-128-CBC + HMAC-SHA256):            │
│     key = derive_key(APPOS_ENCRYPTION_KEY env var)              │
│     encrypted = Fernet(key).encrypt(json_bytes)                 │
│  4. Store as BYTEA in connected_systems.credentials_encrypted   │
│                                                                  │
│  Decryption:                                                     │
│  1. Engine reads BYTEA from DB                                  │
│  2. Decrypt with same Fernet key                                │
│  3. Parse JSON → use for connection                             │
│  4. Never log decrypted credentials                             │
│                                                                  │
│  Key management:                                                 │
│  - APPOS_ENCRYPTION_KEY set as environment variable              │
│  - Different key per environment (dev/staging/prod)              │
│  - Key rotation: re-encrypt all credentials with new key        │
│                                                                  │
└──────────────────────────────────────────────────────────────────┘
```

### 9.2 Process Variable Encryption

| Visibility | Storage in `process_instances.variables` |
|---|---|
| `logged=True` (default) | Plaintext JSON |
| `logged=False` | SHA-256 hash: `{"temp_token": "sha256:a1b2c3..."}` |
| `sensitive=True` | Fernet encrypted: `{"internal_key": "enc:gAAAAA..."}` |

### 9.3 Password Storage

User passwords stored as bcrypt hashes:

```python
# Writing
password_hash = bcrypt.hashpw(password.encode(), bcrypt.gensalt(rounds=12))

# Verifying
bcrypt.checkpw(password.encode(), stored_hash)
```

### 9.4 API Key Storage

Service account API keys stored as bcrypt hashes in `users.api_key_hash`:

```python
# On service account creation, generate random API key
api_key = secrets.token_urlsafe(48)  # 64 chars
api_key_hash = bcrypt.hashpw(api_key.encode(), bcrypt.gensalt(rounds=12))
# Return api_key to admin (shown once), store api_key_hash in DB
```

### 9.5 Session Security

```
Cookie:     appos_session={session_id}
Flags:      HttpOnly, Secure (in prod), SameSite=Lax
CSRF:       X-CSRF-Token header (validated on state-changing requests)
```

---

## 10. Backup & Recovery

### 10.1 Backup Scope

| Component | Method | Frequency | Location |
|-----------|--------|-----------|----------|
| `appos_core` DB | `pg_dump -Fc` | Daily + pre-migration | `/backup/db/` |
| App databases | `pg_dump -Fc` per DB | Daily | `/backup/db/` |
| Uploaded documents | `rsync` or file copy | Daily | `/backup/documents/` |
| Dependency graphs | File copy | After `appos check` | `/backup/dependencies/` |
| Config files | Git (version control) | Every commit | Git repo |
| Redis | **NOT backed up** | — | Ephemeral, auto-recoverable |
| Generated code | **NOT backed up** | — | Regenerated from source |
| Log files | Optional archive | Weekly | `/backup/logs/` |

### 10.2 Recovery Procedure

```
1. Restore PostgreSQL databases
   pg_restore -d appos_core backup.dump

2. Restore app databases
   pg_restore -d crm_db crm_backup.dump

3. Run pending migrations
   appos migrate

4. Regenerate code
   appos generate

5. Validate
   appos check

6. Flush Redis caches
   Admin Console → Settings → Flush Cache
   (or: redis-cli -n 2 FLUSHDB; redis-cli -n 3 FLUSHDB)

7. Verify health
   curl http://localhost:3000/ready
```

### 10.3 Redis Recovery

Redis data is fully reconstructible:

| DB | Content | Recovery |
|----|---------|----------|
| 0 | Celery broker queue | Tasks re-queued on restart |
| 1 | Celery results | Regenerated on task completion |
| 2 | Permission cache | Auto-populated from `object_permission` table on cache miss |
| 3 | Object cache | Auto-populated from filesystem scan on cache miss |
| 4 | Sessions | Users re-login (sessions lost) |
| 5 | Rate limiting | Counters reset (acceptable) |

---

## 11. Table Summary Matrix

### Platform Tables (appos_core)

| # | Table | Purpose | Estimated Rows | Partitioned | Audit |
|---|-------|---------|----------------|-------------|-------|
| 1 | `users` | User accounts | 100s-10Ks | No | No (login_audit_log instead) |
| 2 | `groups` | Access control groups | 10s-100s | No | No |
| 3 | `user_groups` | User ↔ Group junction | 100s-10Ks | No | No |
| 4 | `apps` | Application registry | 1s-10s | No | No |
| 5 | `group_apps` | Group ↔ App junction | 10s-100s | No | No |
| 6 | `object_permission` | Permission rules (wildcard) | 100s-1Ks | No | No |
| 7 | `connected_systems` | External connections | 10s | No | No |
| 8 | `connected_system_groups` | ConnSys ↔ Group junction | 10s-100s | No | No |
| 9 | `process_instances` | Process execution tracking | 10Ks-1Ms/year | **Monthly** | Yes (built-in) |
| 10 | `process_step_log` | Step execution history | 100Ks-10Ms/year | **Monthly** | No |
| 11 | `dependency_changes` | Dependency graph history | 1Ks-10Ks | No | No |
| 12 | `object_registry` | Discovered object catalog | 100s-1Ks | No | No |
| 13 | `platform_config` | Runtime settings | 10s-100s | No | No |
| 14 | `scheduled_tasks` | Celery Beat schedule | 10s-100s | No | No |
| 15 | `login_audit_log` | Login attempts | 10Ks-100Ks/year | No (consider if high) | No |

### Per-App Tables (Auto-Generated)

| # | Table Pattern | Purpose | Generated When |
|---|---|---|---|
| 1 | `{record_table}` | Developer-defined data model | Every `@record` class |
| 2 | `{app}_{table}_audit_log` | Field-level change tracking | `@record` with `Meta.audit = True` |
| 3 | `documents` | File metadata | Every app with document support |
| 4 | `document_versions` | File version history | Every app with document support |
| 5 | `folders` | Folder configuration | Every app with document support |
| 6 | `{app}_event_log` | Custom business events | Every app (optional) |
| 7 | `translation_entries` | i18n overrides (optional) | Apps using `@translation_set` |

### Total Table Count Estimate

```
Platform tables:       15
Per-app tables:        ~5-7 fixed + N record tables + N audit tables per app
Example (CRM + Finance with 10 records each, 5 with audit):
  Platform:  15
  CRM:       10 records + 5 audit + 3 document + 1 event + 1 translation = 20
  Finance:   10 records + 5 audit + 3 document + 1 event + 1 translation = 20
  Total:     ~55 tables
```

---

## Appendix A: Bootstrap SQL (appos init)

The `appos init` command bootstraps the platform database with required seed data:

```sql
-- 1. Create initial system_admin user
INSERT INTO users (username, email, password_hash, full_name, user_type)
VALUES ('admin', 'admin@localhost', '$2b$12$...', 'System Administrator', 'system_admin');

-- 2. Create default groups
INSERT INTO groups (name, type, description) VALUES
    ('system_admin', 'system', 'Full platform access, admin console, user/group management'),
    ('public_access', 'system', 'Public Web API access with limited permissions');

-- 3. Assign admin user to system_admin group
INSERT INTO user_groups (user_id, group_id)
SELECT u.id, g.id FROM users u, groups g
WHERE u.username = 'admin' AND g.name = 'system_admin';

-- 4. Create public_access service account
INSERT INTO users (username, email, password_hash, full_name, user_type)
VALUES ('public_api', 'public_api@system', '$2b$12$...', 'Public API Service Account', 'service_account');

-- 5. Assign public_api to public_access group
INSERT INTO user_groups (user_id, group_id)
SELECT u.id, g.id FROM users u, groups g
WHERE u.username = 'public_api' AND g.name = 'public_access';

-- 6. Grant system_admin full permissions
INSERT INTO object_permission (group_name, object_ref, permission) VALUES
    ('system_admin', '*', 'admin');
```

---

## Appendix B: Connection Pool Configuration Reference

For Connected Systems of `type="database"`:

| Parameter | Default | Description |
|-----------|---------|-------------|
| `pool_size` | 10 | Number of persistent connections |
| `max_overflow` | 20 | Extra connections beyond pool_size |
| `pool_timeout` | 30 | Seconds to wait for a connection from pool |
| `pool_recycle` | 1800 | Seconds before connection is recycled (30 min) |
| `pool_pre_ping` | true | Verify connection is alive before use |
| `pool_reset_on_return` | "rollback" | Rollback uncommitted work on return to pool |

Platform DB (`appos_core`) uses the same parameters configured in `appos.yaml → database`.

---

## Appendix C: JSONB Column Schemas

### connected_systems.connection_details

```jsonc
// type="database"
{
    "driver": "postgresql",
    "host": "localhost",
    "port": 5432,
    "database": "crm_db",
    "pool_size": 10,
    "max_overflow": 20,
    "pool_timeout": 30,
    "pool_recycle": 1800,
    "pool_pre_ping": true,
    "pool_reset_on_return": "rollback"
}

// type="rest_api"
{
    "base_url": "https://api.stripe.com/v1",
    "timeout": 30
}

// type="smtp"
{
    "host": "smtp.office365.com",
    "port": 587,
    "use_tls": true
}

// type="imap"
{
    "host": "outlook.office365.com",
    "port": 993,
    "use_ssl": true,
    "mailbox": "INBOX"
}

// type="ftp"
{
    "host": "ftp.example.com",
    "port": 21,
    "passive": true,
    "encoding": "utf-8"
}
```

### connected_systems.environment_overrides

```jsonc
{
    "staging": {
        "host": "staging-db.internal",
        "database": "crm_staging"
    },
    "prod": {
        "host": "prod-db.internal",
        "database": "crm_prod",
        "pool_size": 50
    }
}
```

### connected_systems.health_check

```jsonc
{
    "enabled": true,
    "interval_seconds": 60,
    "endpoint": "/health",    // for rest_api type
    "timeout": 10
}
```

### process_instances.error_info

```jsonc
{
    "error_type": "AppOSTimeoutError",
    "message": "Step 'charge_payment' exceeded timeout of 30s",
    "execution_id": "exec_abc123",
    "object_ref": "crm.rules.charge_payment",
    "object_type": "expression_rule",
    "step_name": "charge",
    "stack_trace": "Traceback (most recent call last):...",
    "dependency_chain": ["crm.processes.process_order → crm.rules.charge_payment"]
}
```

### apps.security_defaults

```jsonc
{
    "logic": {
        "groups": ["sales", "support", "crm_admins"]
    },
    "ui": {
        "groups": ["sales", "support", "crm_admins"]
    }
}
```

### apps.theme

```jsonc
{
    "primary_color": "#3B82F6",
    "secondary_color": "#1E40AF",
    "accent_color": "#DBEAFE",
    "font_family": "Inter",
    "border_radius": "8px"
}
```

---

## Appendix D: SQLAlchemy Model Definitions (Platform)

Reference SQLAlchemy models for the platform tables, matching the DDL in Section 2:

```python
# appos/db/platform_models.py

from sqlalchemy import (
    Column, Integer, String, Boolean, DateTime, Text, ForeignKey,
    JSON, LargeBinary, Numeric, CheckConstraint, UniqueConstraint, Index
)
from sqlalchemy.orm import relationship, DeclarativeBase
from datetime import datetime, timezone


class Base(DeclarativeBase):
    pass


class AuditMixin:
    """Adds created_at, updated_at, created_by, updated_by."""
    created_at = Column(DateTime(timezone=True), default=lambda: datetime.now(timezone.utc), nullable=False)
    updated_at = Column(DateTime(timezone=True), default=lambda: datetime.now(timezone.utc),
                        onupdate=lambda: datetime.now(timezone.utc), nullable=False)
    created_by = Column(Integer, ForeignKey('users.id'))
    updated_by = Column(Integer, ForeignKey('users.id'))


class SoftDeleteMixin:
    """Adds is_deleted, deleted_at, deleted_by."""
    is_deleted = Column(Boolean, default=False, nullable=False)
    deleted_at = Column(DateTime(timezone=True))
    deleted_by = Column(Integer)


class User(Base, AuditMixin):
    __tablename__ = 'users'

    id = Column(Integer, primary_key=True, autoincrement=True)
    username = Column(String(100), unique=True, nullable=False)
    email = Column(String(255), unique=True, nullable=False)
    password_hash = Column(String(255), nullable=False)
    full_name = Column(String(200), nullable=False)
    is_active = Column(Boolean, default=True, nullable=False)
    user_type = Column(String(20), default='basic', nullable=False)
    preferred_language = Column(String(10), default='en', nullable=False)
    timezone = Column(String(50), default='UTC', nullable=False)
    last_login = Column(DateTime(timezone=True))
    api_key_hash = Column(String(255))

    groups = relationship('Group', secondary='user_groups', back_populates='users')

    __table_args__ = (
        CheckConstraint("user_type IN ('basic', 'system_admin', 'service_account')"),
    )


class Group(Base, AuditMixin):
    __tablename__ = 'groups'

    id = Column(Integer, primary_key=True, autoincrement=True)
    name = Column(String(100), unique=True, nullable=False)
    type = Column(String(20), default='security', nullable=False)
    description = Column(Text)
    is_active = Column(Boolean, default=True, nullable=False)

    users = relationship('User', secondary='user_groups', back_populates='groups')
    apps = relationship('App', secondary='group_apps', back_populates='groups')

    __table_args__ = (
        CheckConstraint("type IN ('security', 'team', 'app', 'system')"),
    )


class UserGroup(Base):
    __tablename__ = 'user_groups'

    id = Column(Integer, primary_key=True, autoincrement=True)
    user_id = Column(Integer, ForeignKey('users.id', ondelete='CASCADE'), nullable=False)
    group_id = Column(Integer, ForeignKey('groups.id', ondelete='CASCADE'), nullable=False)
    added_at = Column(DateTime(timezone=True), default=lambda: datetime.now(timezone.utc), nullable=False)
    added_by = Column(Integer, ForeignKey('users.id'))

    __table_args__ = (UniqueConstraint('user_id', 'group_id'),)


class App(Base, AuditMixin):
    __tablename__ = 'apps'

    id = Column(Integer, primary_key=True, autoincrement=True)
    name = Column(String(200), nullable=False)
    short_name = Column(String(50), unique=True, nullable=False)
    description = Column(Text)
    version = Column(String(20), default='1.0.0', nullable=False)
    is_active = Column(Boolean, default=True, nullable=False)
    environment = Column(String(20), default='dev', nullable=False)
    db_connected_system = Column(String(100))
    theme = Column(JSON, default=dict, nullable=False)
    security_defaults = Column(JSON, default=dict, nullable=False)
    config = Column(JSON, default=dict, nullable=False)

    groups = relationship('Group', secondary='group_apps', back_populates='apps')

    __table_args__ = (
        CheckConstraint("environment IN ('dev', 'staging', 'prod')"),
    )


class GroupApp(Base):
    __tablename__ = 'group_apps'

    id = Column(Integer, primary_key=True, autoincrement=True)
    group_id = Column(Integer, ForeignKey('groups.id', ondelete='CASCADE'), nullable=False)
    app_id = Column(Integer, ForeignKey('apps.id', ondelete='CASCADE'), nullable=False)
    added_at = Column(DateTime(timezone=True), default=lambda: datetime.now(timezone.utc), nullable=False)

    __table_args__ = (UniqueConstraint('group_id', 'app_id'),)


class ObjectPermission(Base):
    __tablename__ = 'object_permission'

    id = Column(Integer, primary_key=True, autoincrement=True)
    group_name = Column(String(100), nullable=False)
    object_ref = Column(String(255), nullable=False)
    permission = Column(String(20), nullable=False)
    created_at = Column(DateTime(timezone=True), default=lambda: datetime.now(timezone.utc), nullable=False)
    created_by = Column(Integer, ForeignKey('users.id'))

    __table_args__ = (
        UniqueConstraint('group_name', 'object_ref', 'permission'),
        CheckConstraint("permission IN ('view', 'use', 'create', 'update', 'delete', 'admin')"),
    )


class ConnectedSystem(Base, AuditMixin):
    __tablename__ = 'connected_systems'

    id = Column(Integer, primary_key=True, autoincrement=True)
    name = Column(String(100), unique=True, nullable=False)
    type = Column(String(20), nullable=False)
    description = Column(Text)
    is_active = Column(Boolean, default=True, nullable=False)
    connection_details = Column(JSON, default=dict, nullable=False)
    auth_type = Column(String(20), default='none', nullable=False)
    credentials_encrypted = Column(LargeBinary)
    environment_overrides = Column(JSON, default=dict, nullable=False)
    health_check = Column(JSON, default=dict, nullable=False)
    is_sensitive = Column(Boolean, default=False, nullable=False)

    __table_args__ = (
        CheckConstraint("type IN ('database', 'rest_api', 'ftp', 'smtp', 'imap', 'custom')"),
        CheckConstraint("auth_type IN ('none', 'basic', 'oauth2', 'api_key', 'certificate')"),
    )


class ConnectedSystemGroup(Base):
    __tablename__ = 'connected_system_groups'

    id = Column(Integer, primary_key=True, autoincrement=True)
    connected_system_id = Column(Integer, ForeignKey('connected_systems.id', ondelete='CASCADE'), nullable=False)
    group_id = Column(Integer, ForeignKey('groups.id', ondelete='CASCADE'), nullable=False)
    added_at = Column(DateTime(timezone=True), default=lambda: datetime.now(timezone.utc), nullable=False)

    __table_args__ = (UniqueConstraint('connected_system_id', 'group_id'),)


class ProcessInstance(Base):
    __tablename__ = 'process_instances'

    id = Column(Integer, primary_key=True, autoincrement=True)
    instance_id = Column(String(50), unique=True, nullable=False)
    process_name = Column(String(100), nullable=False)
    app_name = Column(String(50), nullable=False)
    display_name = Column(String(255))
    status = Column(String(20), default='pending', nullable=False)
    current_step = Column(String(100))
    inputs = Column(JSON, default=dict, nullable=False)
    variables = Column(JSON, default=dict, nullable=False)
    variable_visibility = Column(JSON, default=dict, nullable=False)
    outputs = Column(JSON)
    error_info = Column(JSON)
    started_at = Column(DateTime(timezone=True), default=lambda: datetime.now(timezone.utc), nullable=False)
    completed_at = Column(DateTime(timezone=True))
    started_by = Column(Integer, ForeignKey('users.id'), nullable=False)
    parent_instance_id = Column(Integer)
    triggered_by = Column(String(255))

    __table_args__ = (
        CheckConstraint("status IN ('pending','running','paused','completed','failed','cancelled','interrupted')"),
        # Note: Partitioning handled via raw DDL, not SQLAlchemy
    )


class ProcessStepLog(Base):
    __tablename__ = 'process_step_log'

    id = Column(Integer, primary_key=True, autoincrement=True)
    process_instance_id = Column(Integer, nullable=False)
    step_name = Column(String(100), nullable=False)
    rule_ref = Column(String(200), nullable=False)
    status = Column(String(30), nullable=False)
    started_at = Column(DateTime(timezone=True), default=lambda: datetime.now(timezone.utc), nullable=False)
    completed_at = Column(DateTime(timezone=True))
    duration_ms = Column(Numeric(12, 3))
    inputs = Column(JSON)
    outputs = Column(JSON)
    error_info = Column(JSON)
    attempt = Column(Integer, default=1, nullable=False)
    is_fire_and_forget = Column(Boolean, default=False, nullable=False)
    is_parallel = Column(Boolean, default=False, nullable=False)

    __table_args__ = (
        CheckConstraint(
            "status IN ('pending','running','completed','failed','skipped','async_dispatched','interrupted')"
        ),
    )


class DependencyChange(Base):
    __tablename__ = 'dependency_changes'

    id = Column(Integer, primary_key=True, autoincrement=True)
    object_ref = Column(String(255), nullable=False)
    change_type = Column(String(20), nullable=False)
    old_hash = Column(String(64))
    new_hash = Column(String(64))
    details = Column(JSON)
    changed_at = Column(DateTime(timezone=True), default=lambda: datetime.now(timezone.utc), nullable=False)
    changed_by = Column(String(100))

    __table_args__ = (
        CheckConstraint("change_type IN ('added', 'removed', 'modified')"),
    )


class ObjectRegistry(Base):
    __tablename__ = 'object_registry'

    id = Column(Integer, primary_key=True, autoincrement=True)
    object_ref = Column(String(255), unique=True, nullable=False)
    object_type = Column(String(30), nullable=False)
    app_name = Column(String(50))
    module_path = Column(String(500), nullable=False)
    file_path = Column(String(500), nullable=False)
    source_hash = Column(String(64), nullable=False)
    metadata_ = Column('metadata', JSON, default=dict, nullable=False)
    is_active = Column(Boolean, default=True, nullable=False)
    discovered_at = Column(DateTime(timezone=True), default=lambda: datetime.now(timezone.utc), nullable=False)
    updated_at = Column(DateTime(timezone=True), default=lambda: datetime.now(timezone.utc), nullable=False)


class PlatformConfig(Base):
    __tablename__ = 'platform_config'

    id = Column(Integer, primary_key=True, autoincrement=True)
    key = Column(String(100), unique=True, nullable=False)
    value = Column(JSON, nullable=False)
    category = Column(String(50), nullable=False)
    updated_at = Column(DateTime(timezone=True), default=lambda: datetime.now(timezone.utc), nullable=False)
    updated_by = Column(Integer, ForeignKey('users.id'))


class ScheduledTask(Base):
    __tablename__ = 'scheduled_tasks'

    id = Column(Integer, primary_key=True, autoincrement=True)
    task_name = Column(String(200), unique=True, nullable=False)
    schedule = Column(String(100), nullable=False)
    timezone = Column(String(50), default='UTC', nullable=False)
    app_name = Column(String(50), nullable=False)
    process_name = Column(String(100), nullable=False)
    inputs = Column(JSON, default=dict, nullable=False)
    is_active = Column(Boolean, default=True, nullable=False)
    last_run_at = Column(DateTime(timezone=True))
    next_run_at = Column(DateTime(timezone=True))
    created_at = Column(DateTime(timezone=True), default=lambda: datetime.now(timezone.utc), nullable=False)
    updated_at = Column(DateTime(timezone=True), default=lambda: datetime.now(timezone.utc), nullable=False)


class LoginAuditLog(Base):
    __tablename__ = 'login_audit_log'

    id = Column(Integer, primary_key=True, autoincrement=True)
    username = Column(String(100), nullable=False)
    user_id = Column(Integer, ForeignKey('users.id'))
    success = Column(Boolean, nullable=False)
    ip_address = Column(String(45))  # IPv6 max length
    user_agent = Column(Text)
    failure_reason = Column(String(100))
    timestamp = Column(DateTime(timezone=True), default=lambda: datetime.now(timezone.utc), nullable=False)
```

---

## Appendix E: What is NOT in the Database

These components are **file-based** or **in-memory only** — not stored in PostgreSQL:

| Component | Storage | Location |
|-----------|---------|----------|
| System logs (execution, performance, security) | JSONL files | `.appos/logs/{type}/{category}/{date}.jsonl` |
| Dependency graph (runtime) | In-memory (NetworkX) | RAM |
| Dependency graph (persisted) | JSON files | `.appos/runtime/dependencies/{ref}.json` |
| Object source code | Python files | `apps/{app}/{type}/{name}.py` |
| Generated SQLAlchemy models | Python files | `.appos/generated/models/` |
| Generated CRUD services | Python files | `.appos/generated/services/` |
| Generated interfaces | Python files | `.appos/generated/interfaces/` |
| Alembic migrations | Python files | `migrations/versions/` |
| Platform configuration (primary) | YAML file | `appos.yaml` |
| App configuration (primary) | YAML file | `apps/{app}/app.yaml` |
| Uploaded documents (files) | Physical files | `apps/{app}/runtime/documents/{folder}/` |
| Object cache | Redis | DB 3 |
| Permission cache | Redis | DB 2 |
| User sessions | Redis | DB 4 |

---

*Document Version: 1.0 | Created: February 13, 2026 | Source: AppOS_Design.md v2.1 + all Reference Docs*
