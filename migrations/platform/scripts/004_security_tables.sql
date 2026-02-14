-- ============================================================================
-- AppOS Platform Database — 004: Security Tables
-- ============================================================================
-- Purpose:  Create object_permission and login_audit_log tables
-- Source:   AppOS_Database_Design.md v1.0, §2.6, §2.15
-- Depends:  002_core_tables.sql
-- Idempotent: Yes (IF NOT EXISTS)
-- ============================================================================

SET search_path TO "appOS", public;

-- ---------------------------------------------------------------------------
-- 1. object_permission — Unified 6-permission model with wildcard support
-- ---------------------------------------------------------------------------
CREATE TABLE IF NOT EXISTS "appOS".object_permission (
    id          SERIAL PRIMARY KEY,
    group_name  VARCHAR(100) NOT NULL,
    object_ref  VARCHAR(255) NOT NULL,      -- e.g., "crm.rules.*", "crm.records.customer", "crm.*"
    permission  VARCHAR(20)  NOT NULL
                CHECK (permission IN ('view', 'use', 'create', 'update', 'delete', 'admin')),
    created_at  TIMESTAMP WITH TIME ZONE NOT NULL DEFAULT NOW(),
    created_by  INTEGER      REFERENCES "appOS".users(id),
    UNIQUE (group_name, object_ref, permission)
);

COMMENT ON TABLE "appOS".object_permission IS 'Unified 6-permission model — heart of the security system. Supports wildcard object_ref patterns.';
COMMENT ON COLUMN "appOS".object_permission.object_ref IS 'Object reference with wildcard support. Resolution order: most specific wins (crm.rules.X > crm.rules.* > crm.*)';
COMMENT ON COLUMN "appOS".object_permission.permission IS 'view=read metadata, use=execute, create/update/delete=record CRUD, admin=full control';

-- ---------------------------------------------------------------------------
-- 2. login_audit_log — Login attempt audit trail
-- ---------------------------------------------------------------------------
CREATE TABLE IF NOT EXISTS "appOS".login_audit_log (
    id              SERIAL PRIMARY KEY,
    username        VARCHAR(100) NOT NULL,
    user_id         INTEGER      REFERENCES "appOS".users(id),
    success         BOOLEAN      NOT NULL,
    ip_address      INET,                                       -- supports IPv4 and IPv6
    user_agent      TEXT,
    failure_reason  VARCHAR(100),                                -- "invalid_password", "account_disabled", "max_attempts"
    timestamp       TIMESTAMP WITH TIME ZONE NOT NULL DEFAULT NOW()
);

COMMENT ON TABLE "appOS".login_audit_log IS 'Tracks all login attempts for security compliance and audit.';
COMMENT ON COLUMN "appOS".login_audit_log.failure_reason IS 'Reason codes: invalid_password, account_disabled, max_attempts, invalid_csrf, session_expired';
