-- ============================================================================
-- AppOS Platform Database — 002: Core Tables
-- ============================================================================
-- Purpose:  Create primary entity tables (users, groups, apps, connected_systems)
-- Source:   AppOS_Database_Design.md v1.0, §2.1, §2.2, §2.4, §2.7
-- Depends:  001_schema.sql
-- Idempotent: Yes (IF NOT EXISTS)
-- ============================================================================

SET search_path TO "appOS", public;

-- ---------------------------------------------------------------------------
-- 1. users — User accounts (basic, system_admin, service_account)
-- ---------------------------------------------------------------------------
CREATE TABLE IF NOT EXISTS "appOS".users (
    id                  SERIAL PRIMARY KEY,
    username            VARCHAR(100)  NOT NULL UNIQUE,
    email               VARCHAR(255)  NOT NULL UNIQUE,
    password_hash       VARCHAR(255)  NOT NULL,                 -- bcrypt
    full_name           VARCHAR(200)  NOT NULL,
    is_active           BOOLEAN       NOT NULL DEFAULT TRUE,
    user_type           VARCHAR(20)   NOT NULL DEFAULT 'basic'
                        CHECK (user_type IN ('basic', 'system_admin', 'service_account')),
    preferred_language  VARCHAR(10)   NOT NULL DEFAULT 'en',
    timezone            VARCHAR(50)   NOT NULL DEFAULT 'UTC',
    last_login          TIMESTAMP WITH TIME ZONE,
    api_key_hash        VARCHAR(255),                           -- bcrypt hash for service_account auth
    created_at          TIMESTAMP WITH TIME ZONE NOT NULL DEFAULT NOW(),
    updated_at          TIMESTAMP WITH TIME ZONE NOT NULL DEFAULT NOW(),
    created_by          INTEGER       REFERENCES "appOS".users(id),
    updated_by          INTEGER       REFERENCES "appOS".users(id)
);

COMMENT ON TABLE "appOS".users IS 'All user accounts — basic users, system admins, and service accounts.';
COMMENT ON COLUMN "appOS".users.user_type IS 'basic=regular user, system_admin=full platform access, service_account=API-only (no UI login)';
COMMENT ON COLUMN "appOS".users.api_key_hash IS 'bcrypt hash of API key — only set for service_account users';

-- ---------------------------------------------------------------------------
-- 2. groups — Access control groups
-- ---------------------------------------------------------------------------
CREATE TABLE IF NOT EXISTS "appOS".groups (
    id              SERIAL PRIMARY KEY,
    name            VARCHAR(100) NOT NULL UNIQUE,
    type            VARCHAR(20)  NOT NULL DEFAULT 'security'
                    CHECK (type IN ('security', 'team', 'app', 'system')),
    description     TEXT,
    is_active       BOOLEAN      NOT NULL DEFAULT TRUE,
    created_at      TIMESTAMP WITH TIME ZONE NOT NULL DEFAULT NOW(),
    updated_at      TIMESTAMP WITH TIME ZONE NOT NULL DEFAULT NOW(),
    created_by      INTEGER      REFERENCES "appOS".users(id),
    updated_by      INTEGER      REFERENCES "appOS".users(id)
);

COMMENT ON TABLE "appOS".groups IS 'Access control groups — core unit of the permission system.';
COMMENT ON COLUMN "appOS".groups.type IS 'security=permission group, team=organizational, app=app-specific, system=platform-managed';

-- ---------------------------------------------------------------------------
-- 3. apps — Application registry
-- ---------------------------------------------------------------------------
CREATE TABLE IF NOT EXISTS "appOS".apps (
    id                  SERIAL PRIMARY KEY,
    name                VARCHAR(200) NOT NULL,
    short_name          VARCHAR(50)  NOT NULL UNIQUE,           -- URL prefix: "crm", "finance"
    description         TEXT,
    version             VARCHAR(20)  NOT NULL DEFAULT '1.0.0',
    is_active           BOOLEAN      NOT NULL DEFAULT TRUE,
    environment         VARCHAR(20)  NOT NULL DEFAULT 'dev'
                        CHECK (environment IN ('dev', 'staging', 'prod')),
    db_connected_system VARCHAR(100),                           -- FK to connected_systems.name
    theme               JSONB        NOT NULL DEFAULT '{}',     -- {primary_color, font_family, ...}
    security_defaults   JSONB        NOT NULL DEFAULT '{}',     -- {logic: {groups: [...]}, ui: {groups: [...]}}
    config              JSONB        NOT NULL DEFAULT '{}',     -- full app.yaml parsed config
    created_at          TIMESTAMP WITH TIME ZONE NOT NULL DEFAULT NOW(),
    updated_at          TIMESTAMP WITH TIME ZONE NOT NULL DEFAULT NOW()
);

COMMENT ON TABLE "appOS".apps IS 'Registry of all applications in the platform.';
COMMENT ON COLUMN "appOS".apps.short_name IS 'URL prefix for routing (e.g., "crm" → /crm/...)';
COMMENT ON COLUMN "appOS".apps.db_connected_system IS 'Name of the Connected System used for this apps database';
COMMENT ON COLUMN "appOS".apps.security_defaults IS 'Inherited security: {logic: {groups: [...]}, ui: {groups: [...]}}';
COMMENT ON COLUMN "appOS".apps.theme IS 'App theme: {primary_color, secondary_color, accent_color, font_family, border_radius}';

-- ---------------------------------------------------------------------------
-- 4. connected_systems — External connections (DB, API, FTP, SMTP, IMAP)
-- ---------------------------------------------------------------------------
CREATE TABLE IF NOT EXISTS "appOS".connected_systems (
    id                    SERIAL PRIMARY KEY,
    name                  VARCHAR(100) NOT NULL UNIQUE,         -- "crm_database", "stripe_api"
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
    credentials_encrypted BYTEA,                                -- Fernet-encrypted JSON blob
    -- {username, password, api_key, client_id, client_secret, tenant_id, certificate_path, ...}

    environment_overrides JSONB        NOT NULL DEFAULT '{}',
    -- {"staging": {"host": "staging-db"}, "prod": {"host": "prod-db", "pool_size": 50}}

    health_check          JSONB        NOT NULL DEFAULT '{}',
    -- {"enabled": true, "interval_seconds": 60, "endpoint": "/health", "timeout": 10}

    is_sensitive          BOOLEAN      NOT NULL DEFAULT FALSE,  -- if true, payloads encrypted in logs
    created_at            TIMESTAMP WITH TIME ZONE NOT NULL DEFAULT NOW(),
    updated_at            TIMESTAMP WITH TIME ZONE NOT NULL DEFAULT NOW(),
    created_by            INTEGER      REFERENCES "appOS".users(id),
    updated_by            INTEGER      REFERENCES "appOS".users(id)
);

COMMENT ON TABLE "appOS".connected_systems IS 'Global external connections — not app-bound, shared across all apps, secured via groups.';
COMMENT ON COLUMN "appOS".connected_systems.credentials_encrypted IS 'Fernet-encrypted (AES-128-CBC + HMAC-SHA256) JSON blob of credentials';
COMMENT ON COLUMN "appOS".connected_systems.environment_overrides IS 'Per-environment connection overrides (staging, prod)';
COMMENT ON COLUMN "appOS".connected_systems.is_sensitive IS 'When true, request/response payloads are encrypted in integration logs';
