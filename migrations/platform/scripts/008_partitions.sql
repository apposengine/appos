-- ============================================================================
-- AppOS Platform Database — 008: Partitions & Archival
-- ============================================================================
-- Purpose:  Create monthly partitions for process_instances and process_step_log,
--           plus archive tables for completed process data.
-- Source:   AppOS_Database_Design.md v1.0, §6
-- Depends:  005_process_tables.sql
-- Note:     Run monthly to create upcoming partitions.
--           Update date ranges as needed for your deployment window.
-- ============================================================================

SET search_path TO "appOS", public;

-- ============================================================================
-- MONTHLY PARTITIONS — process_instances
-- ============================================================================
-- Create partitions covering Feb 2026 through Dec 2026.
-- Add new partitions monthly via scheduled task or pg_partman.

CREATE TABLE IF NOT EXISTS "appOS".process_instances_2026_02 PARTITION OF "appOS".process_instances
    FOR VALUES FROM ('2026-02-01') TO ('2026-03-01');

CREATE TABLE IF NOT EXISTS "appOS".process_instances_2026_03 PARTITION OF "appOS".process_instances
    FOR VALUES FROM ('2026-03-01') TO ('2026-04-01');

CREATE TABLE IF NOT EXISTS "appOS".process_instances_2026_04 PARTITION OF "appOS".process_instances
    FOR VALUES FROM ('2026-04-01') TO ('2026-05-01');

CREATE TABLE IF NOT EXISTS "appOS".process_instances_2026_05 PARTITION OF "appOS".process_instances
    FOR VALUES FROM ('2026-05-01') TO ('2026-06-01');

CREATE TABLE IF NOT EXISTS "appOS".process_instances_2026_06 PARTITION OF "appOS".process_instances
    FOR VALUES FROM ('2026-06-01') TO ('2026-07-01');

CREATE TABLE IF NOT EXISTS "appOS".process_instances_2026_07 PARTITION OF "appOS".process_instances
    FOR VALUES FROM ('2026-07-01') TO ('2026-08-01');

CREATE TABLE IF NOT EXISTS "appOS".process_instances_2026_08 PARTITION OF "appOS".process_instances
    FOR VALUES FROM ('2026-08-01') TO ('2026-09-01');

CREATE TABLE IF NOT EXISTS "appOS".process_instances_2026_09 PARTITION OF "appOS".process_instances
    FOR VALUES FROM ('2026-09-01') TO ('2026-10-01');

CREATE TABLE IF NOT EXISTS "appOS".process_instances_2026_10 PARTITION OF "appOS".process_instances
    FOR VALUES FROM ('2026-10-01') TO ('2026-11-01');

CREATE TABLE IF NOT EXISTS "appOS".process_instances_2026_11 PARTITION OF "appOS".process_instances
    FOR VALUES FROM ('2026-11-01') TO ('2026-12-01');

CREATE TABLE IF NOT EXISTS "appOS".process_instances_2026_12 PARTITION OF "appOS".process_instances
    FOR VALUES FROM ('2026-12-01') TO ('2027-01-01');


-- ============================================================================
-- MONTHLY PARTITIONS — process_step_log
-- ============================================================================

CREATE TABLE IF NOT EXISTS "appOS".process_step_log_2026_02 PARTITION OF "appOS".process_step_log
    FOR VALUES FROM ('2026-02-01') TO ('2026-03-01');

CREATE TABLE IF NOT EXISTS "appOS".process_step_log_2026_03 PARTITION OF "appOS".process_step_log
    FOR VALUES FROM ('2026-03-01') TO ('2026-04-01');

CREATE TABLE IF NOT EXISTS "appOS".process_step_log_2026_04 PARTITION OF "appOS".process_step_log
    FOR VALUES FROM ('2026-04-01') TO ('2026-05-01');

CREATE TABLE IF NOT EXISTS "appOS".process_step_log_2026_05 PARTITION OF "appOS".process_step_log
    FOR VALUES FROM ('2026-05-01') TO ('2026-06-01');

CREATE TABLE IF NOT EXISTS "appOS".process_step_log_2026_06 PARTITION OF "appOS".process_step_log
    FOR VALUES FROM ('2026-06-01') TO ('2026-07-01');

CREATE TABLE IF NOT EXISTS "appOS".process_step_log_2026_07 PARTITION OF "appOS".process_step_log
    FOR VALUES FROM ('2026-07-01') TO ('2026-08-01');

CREATE TABLE IF NOT EXISTS "appOS".process_step_log_2026_08 PARTITION OF "appOS".process_step_log
    FOR VALUES FROM ('2026-08-01') TO ('2026-09-01');

CREATE TABLE IF NOT EXISTS "appOS".process_step_log_2026_09 PARTITION OF "appOS".process_step_log
    FOR VALUES FROM ('2026-09-01') TO ('2026-10-01');

CREATE TABLE IF NOT EXISTS "appOS".process_step_log_2026_10 PARTITION OF "appOS".process_step_log
    FOR VALUES FROM ('2026-10-01') TO ('2026-11-01');

CREATE TABLE IF NOT EXISTS "appOS".process_step_log_2026_11 PARTITION OF "appOS".process_step_log
    FOR VALUES FROM ('2026-11-01') TO ('2026-12-01');

CREATE TABLE IF NOT EXISTS "appOS".process_step_log_2026_12 PARTITION OF "appOS".process_step_log
    FOR VALUES FROM ('2026-12-01') TO ('2027-01-01');


-- ============================================================================
-- ARCHIVE TABLES — For completed process data older than archive_after_days
-- ============================================================================

CREATE TABLE IF NOT EXISTS "appOS".process_instances_archive (
    LIKE "appOS".process_instances INCLUDING ALL
);

COMMENT ON TABLE "appOS".process_instances_archive IS 'Archive of completed/failed/cancelled process instances older than archive_after_days (default 90).';

CREATE TABLE IF NOT EXISTS "appOS".process_step_log_archive (
    LIKE "appOS".process_step_log INCLUDING ALL
);

COMMENT ON TABLE "appOS".process_step_log_archive IS 'Archive of step logs for archived process instances.';


-- ============================================================================
-- ARCHIVAL QUERIES (run by platform scheduled task)
-- ============================================================================
-- These are provided as reference — executed by the platform's archival process,
-- not during initial setup.
--
-- -- Move completed instances older than 90 days to archive:
-- INSERT INTO "appOS".process_instances_archive
-- SELECT * FROM "appOS".process_instances
-- WHERE status IN ('completed', 'failed', 'cancelled')
--   AND completed_at < NOW() - INTERVAL '90 days';
--
-- DELETE FROM "appOS".process_instances
-- WHERE status IN ('completed', 'failed', 'cancelled')
--   AND completed_at < NOW() - INTERVAL '90 days';
--
-- -- Move related step logs:
-- INSERT INTO "appOS".process_step_log_archive
-- SELECT psl.* FROM "appOS".process_step_log psl
-- INNER JOIN "appOS".process_instances_archive pia
--   ON psl.process_instance_id = pia.id;
--
-- DELETE FROM "appOS".process_step_log psl
-- USING "appOS".process_instances_archive pia
-- WHERE psl.process_instance_id = pia.id;


-- ============================================================================
-- HELPER: Function to auto-create next month's partitions
-- ============================================================================
-- Call monthly via pg_cron or platform scheduled task.

CREATE OR REPLACE FUNCTION "appOS".create_next_month_partitions()
RETURNS VOID AS $$
DECLARE
    next_month_start DATE;
    next_month_end   DATE;
    partition_suffix VARCHAR;
    pi_partition     VARCHAR;
    psl_partition    VARCHAR;
BEGIN
    next_month_start := date_trunc('month', NOW()) + INTERVAL '1 month';
    next_month_end   := next_month_start + INTERVAL '1 month';
    partition_suffix := to_char(next_month_start, 'YYYY_MM');

    pi_partition  := '"appOS".process_instances_' || partition_suffix;
    psl_partition := '"appOS".process_step_log_'  || partition_suffix;

    -- Create process_instances partition
    EXECUTE format(
        'CREATE TABLE IF NOT EXISTS %s PARTITION OF "appOS".process_instances FOR VALUES FROM (%L) TO (%L)',
        pi_partition, next_month_start, next_month_end
    );

    -- Create process_step_log partition
    EXECUTE format(
        'CREATE TABLE IF NOT EXISTS %s PARTITION OF "appOS".process_step_log FOR VALUES FROM (%L) TO (%L)',
        psl_partition, next_month_start, next_month_end
    );

    RAISE NOTICE 'Created partitions: % and %', pi_partition, psl_partition;
END;
$$ LANGUAGE plpgsql;

COMMENT ON FUNCTION "appOS".create_next_month_partitions IS 'Auto-creates next months partitions for process_instances and process_step_log. Call monthly via pg_cron or scheduled task.';
