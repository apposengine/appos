-- ============================================================================
-- AppOS Platform Database — 003: Junction Tables
-- ============================================================================
-- Purpose:  Create many-to-many junction tables
-- Source:   AppOS_Database_Design.md v1.0, §2.3, §2.5, §2.8
-- Depends:  002_core_tables.sql
-- Idempotent: Yes (IF NOT EXISTS)
-- ============================================================================

SET search_path TO "appOS", public;

-- ---------------------------------------------------------------------------
-- 1. user_groups — User ↔ Group junction
-- ---------------------------------------------------------------------------
CREATE TABLE IF NOT EXISTS "appOS".user_groups (
    id         SERIAL PRIMARY KEY,
    user_id    INTEGER NOT NULL REFERENCES "appOS".users(id) ON DELETE CASCADE,
    group_id   INTEGER NOT NULL REFERENCES "appOS".groups(id) ON DELETE CASCADE,
    added_at   TIMESTAMP WITH TIME ZONE NOT NULL DEFAULT NOW(),
    added_by   INTEGER REFERENCES "appOS".users(id),
    UNIQUE (user_id, group_id)
);

COMMENT ON TABLE "appOS".user_groups IS 'Many-to-many: which users belong to which groups.';

-- ---------------------------------------------------------------------------
-- 2. group_apps — Group ↔ App junction
-- ---------------------------------------------------------------------------
CREATE TABLE IF NOT EXISTS "appOS".group_apps (
    id        SERIAL PRIMARY KEY,
    group_id  INTEGER NOT NULL REFERENCES "appOS".groups(id) ON DELETE CASCADE,
    app_id    INTEGER NOT NULL REFERENCES "appOS".apps(id) ON DELETE CASCADE,
    added_at  TIMESTAMP WITH TIME ZONE NOT NULL DEFAULT NOW(),
    UNIQUE (group_id, app_id)
);

COMMENT ON TABLE "appOS".group_apps IS 'Many-to-many: which groups have access to which apps.';

-- ---------------------------------------------------------------------------
-- 3. connected_system_groups — Connected System ↔ Group junction
-- ---------------------------------------------------------------------------
CREATE TABLE IF NOT EXISTS "appOS".connected_system_groups (
    id                  SERIAL PRIMARY KEY,
    connected_system_id INTEGER NOT NULL REFERENCES "appOS".connected_systems(id) ON DELETE CASCADE,
    group_id            INTEGER NOT NULL REFERENCES "appOS".groups(id) ON DELETE CASCADE,
    added_at            TIMESTAMP WITH TIME ZONE NOT NULL DEFAULT NOW(),
    UNIQUE (connected_system_id, group_id)
);

COMMENT ON TABLE "appOS".connected_system_groups IS 'Many-to-many: which groups can access which connected systems.';
