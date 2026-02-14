-- ============================================================================
-- AppOS Platform Database — 009: Bootstrap Data
-- ============================================================================
-- Purpose:  Seed initial data required by the platform (appos init equivalent)
-- Source:   AppOS_Database_Design.md v1.0, Appendix A
-- Depends:  002-006 (all tables must exist)
-- Run:      ONCE on initial setup. Running again is safe (uses ON CONFLICT).
-- ============================================================================

SET search_path TO "appOS", public;

-- ---------------------------------------------------------------------------
-- 1. System administrator user
-- ---------------------------------------------------------------------------
-- Password: "admin" hashed with bcrypt (12 rounds)
-- IMPORTANT: Change this password immediately after first login!
INSERT INTO "appOS".users (username, email, password_hash, full_name, user_type)
VALUES (
    'admin',
    'admin@localhost',
    '$2b$12$LJ3m4ys3Lk0TSwMCkVc3/.uoJGFDAGEKK1G5Cw9LF/F4MJznH5Ovy',   -- bcrypt("admin")
    'System Administrator',
    'system_admin'
)
ON CONFLICT (username) DO NOTHING;

-- ---------------------------------------------------------------------------
-- 2. Default system groups
-- ---------------------------------------------------------------------------
INSERT INTO "appOS".groups (name, type, description) VALUES
    ('system_admin',  'system', 'Full platform access, admin console, user/group management'),
    ('public_access', 'system', 'Public Web API access with limited permissions')
ON CONFLICT (name) DO NOTHING;

-- ---------------------------------------------------------------------------
-- 3. Assign admin user to system_admin group
-- ---------------------------------------------------------------------------
INSERT INTO "appOS".user_groups (user_id, group_id, added_by)
SELECT u.id, g.id, u.id
FROM "appOS".users u, "appOS".groups g
WHERE u.username = 'admin' AND g.name = 'system_admin'
ON CONFLICT (user_id, group_id) DO NOTHING;

-- ---------------------------------------------------------------------------
-- 4. Public API service account
-- ---------------------------------------------------------------------------
INSERT INTO "appOS".users (username, email, password_hash, full_name, user_type)
VALUES (
    'public_api',
    'public_api@system',
    '$2b$12$placeholder_not_used_for_service_accounts_____________',   -- service accounts use API keys, not passwords
    'Public API Service Account',
    'service_account'
)
ON CONFLICT (username) DO NOTHING;

-- ---------------------------------------------------------------------------
-- 5. Assign public_api to public_access group
-- ---------------------------------------------------------------------------
INSERT INTO "appOS".user_groups (user_id, group_id)
SELECT u.id, g.id
FROM "appOS".users u, "appOS".groups g
WHERE u.username = 'public_api' AND g.name = 'public_access'
ON CONFLICT (user_id, group_id) DO NOTHING;

-- ---------------------------------------------------------------------------
-- 6. Grant system_admin full platform permissions (wildcard)
-- ---------------------------------------------------------------------------
INSERT INTO "appOS".object_permission (group_name, object_ref, permission)
VALUES ('system_admin', '*', 'admin')
ON CONFLICT (group_name, object_ref, permission) DO NOTHING;
