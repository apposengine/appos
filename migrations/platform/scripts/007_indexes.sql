-- ============================================================================
-- AppOS Platform Database — 007: All Indexes
-- ============================================================================
-- Purpose:  Create all indexes for all platform tables
-- Source:   AppOS_Database_Design.md v1.0, §7
-- Depends:  002-006 (all tables must exist)
-- Idempotent: Yes (IF NOT EXISTS on all indexes)
-- ============================================================================

SET search_path TO "appOS", public;

-- ===== users =====
CREATE INDEX IF NOT EXISTS idx_users_username      ON "appOS".users(username);
CREATE INDEX IF NOT EXISTS idx_users_email         ON "appOS".users(email);
CREATE INDEX IF NOT EXISTS idx_users_user_type     ON "appOS".users(user_type);
CREATE INDEX IF NOT EXISTS idx_users_is_active     ON "appOS".users(is_active);
CREATE INDEX IF NOT EXISTS idx_users_last_login    ON "appOS".users(last_login);

-- ===== groups =====
CREATE INDEX IF NOT EXISTS idx_groups_name         ON "appOS".groups(name);
CREATE INDEX IF NOT EXISTS idx_groups_type         ON "appOS".groups(type);
CREATE INDEX IF NOT EXISTS idx_groups_is_active    ON "appOS".groups(is_active);

-- ===== user_groups =====
CREATE INDEX IF NOT EXISTS idx_ug_user_id          ON "appOS".user_groups(user_id);
CREATE INDEX IF NOT EXISTS idx_ug_group_id         ON "appOS".user_groups(group_id);

-- ===== apps =====
CREATE INDEX IF NOT EXISTS idx_apps_short_name     ON "appOS".apps(short_name);
CREATE INDEX IF NOT EXISTS idx_apps_is_active      ON "appOS".apps(is_active);
CREATE INDEX IF NOT EXISTS idx_apps_environment    ON "appOS".apps(environment);

-- ===== group_apps =====
CREATE INDEX IF NOT EXISTS idx_ga_group_id         ON "appOS".group_apps(group_id);
CREATE INDEX IF NOT EXISTS idx_ga_app_id           ON "appOS".group_apps(app_id);

-- ===== object_permission =====
CREATE INDEX IF NOT EXISTS idx_perm_group          ON "appOS".object_permission(group_name);
CREATE INDEX IF NOT EXISTS idx_perm_obj            ON "appOS".object_permission(object_ref);
CREATE INDEX IF NOT EXISTS idx_perm_group_obj      ON "appOS".object_permission(group_name, object_ref);
CREATE INDEX IF NOT EXISTS idx_perm_permission     ON "appOS".object_permission(permission);

-- ===== connected_systems =====
CREATE INDEX IF NOT EXISTS idx_cs_name             ON "appOS".connected_systems(name);
CREATE INDEX IF NOT EXISTS idx_cs_type             ON "appOS".connected_systems(type);
CREATE INDEX IF NOT EXISTS idx_cs_is_active        ON "appOS".connected_systems(is_active);

-- ===== connected_system_groups =====
CREATE INDEX IF NOT EXISTS idx_csg_cs_id           ON "appOS".connected_system_groups(connected_system_id);
CREATE INDEX IF NOT EXISTS idx_csg_group_id        ON "appOS".connected_system_groups(group_id);

-- ===== process_instances =====
CREATE INDEX IF NOT EXISTS idx_pi_instance_id      ON "appOS".process_instances(instance_id);
CREATE INDEX IF NOT EXISTS idx_pi_process_name     ON "appOS".process_instances(process_name);
CREATE INDEX IF NOT EXISTS idx_pi_app_name         ON "appOS".process_instances(app_name);
CREATE INDEX IF NOT EXISTS idx_pi_status           ON "appOS".process_instances(status);
CREATE INDEX IF NOT EXISTS idx_pi_started_at       ON "appOS".process_instances(started_at);
CREATE INDEX IF NOT EXISTS idx_pi_started_by       ON "appOS".process_instances(started_by);
CREATE INDEX IF NOT EXISTS idx_pi_parent           ON "appOS".process_instances(parent_instance_id);
CREATE INDEX IF NOT EXISTS idx_pi_app_status       ON "appOS".process_instances(app_name, status);

-- ===== process_step_log =====
CREATE INDEX IF NOT EXISTS idx_psl_instance_id     ON "appOS".process_step_log(process_instance_id);
CREATE INDEX IF NOT EXISTS idx_psl_step_name       ON "appOS".process_step_log(step_name);
CREATE INDEX IF NOT EXISTS idx_psl_status          ON "appOS".process_step_log(status);
CREATE INDEX IF NOT EXISTS idx_psl_started_at      ON "appOS".process_step_log(started_at);
CREATE INDEX IF NOT EXISTS idx_psl_instance_step   ON "appOS".process_step_log(process_instance_id, step_name, started_at);

-- ===== dependency_changes =====
CREATE INDEX IF NOT EXISTS idx_depchange_obj       ON "appOS".dependency_changes(object_ref);
CREATE INDEX IF NOT EXISTS idx_depchange_time      ON "appOS".dependency_changes(changed_at);
CREATE INDEX IF NOT EXISTS idx_depchange_type      ON "appOS".dependency_changes(change_type);

-- ===== object_registry =====
CREATE INDEX IF NOT EXISTS idx_or_type             ON "appOS".object_registry(object_type);
CREATE INDEX IF NOT EXISTS idx_or_app              ON "appOS".object_registry(app_name);
CREATE INDEX IF NOT EXISTS idx_or_type_app         ON "appOS".object_registry(object_type, app_name);

-- ===== platform_config =====
CREATE INDEX IF NOT EXISTS idx_pc_key              ON "appOS".platform_config(key);
CREATE INDEX IF NOT EXISTS idx_pc_category         ON "appOS".platform_config(category);

-- ===== scheduled_tasks =====
CREATE INDEX IF NOT EXISTS idx_st_app              ON "appOS".scheduled_tasks(app_name);
CREATE INDEX IF NOT EXISTS idx_st_is_active        ON "appOS".scheduled_tasks(is_active);
CREATE INDEX IF NOT EXISTS idx_st_next_run         ON "appOS".scheduled_tasks(next_run_at);

-- ===== login_audit_log =====
CREATE INDEX IF NOT EXISTS idx_lal_username        ON "appOS".login_audit_log(username);
CREATE INDEX IF NOT EXISTS idx_lal_user_id         ON "appOS".login_audit_log(user_id);
CREATE INDEX IF NOT EXISTS idx_lal_success         ON "appOS".login_audit_log(success);
CREATE INDEX IF NOT EXISTS idx_lal_timestamp       ON "appOS".login_audit_log(timestamp);
