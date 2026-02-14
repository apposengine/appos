-- ============================================================================
-- AppOS Platform Database — 005: Process Engine Tables (Partitioned)
-- ============================================================================
-- Purpose:  Create process_instances and process_step_log as partitioned tables
-- Source:   AppOS_Database_Design.md v1.0, §2.9, §2.10, §6
-- Depends:  002_core_tables.sql
-- Note:     PRODUCTION version uses PARTITION BY RANGE.
--           For dev without partitioning, use the flat table alternative at bottom.
-- Idempotent: Yes (IF NOT EXISTS)
-- ============================================================================

SET search_path TO "appOS", public;

-- ---------------------------------------------------------------------------
-- 1. process_instances — Process execution tracking (PARTITIONED monthly)
-- ---------------------------------------------------------------------------
-- NOTE: Partitioned tables require the partition key in the PRIMARY KEY.

CREATE TABLE IF NOT EXISTS "appOS".process_instances (
    id                   SERIAL,
    instance_id          VARCHAR(50)  NOT NULL,                 -- "proc_abc123" (human-readable)
    process_name         VARCHAR(100) NOT NULL,
    app_name             VARCHAR(50)  NOT NULL,
    display_name         VARCHAR(255),                          -- "Onboard: Acme Corp" (from template)
    status               VARCHAR(20)  NOT NULL DEFAULT 'pending'
                         CHECK (status IN ('pending', 'running', 'paused',
                                           'completed', 'failed', 'cancelled', 'interrupted')),
    current_step         VARCHAR(100),
    inputs               JSONB        NOT NULL DEFAULT '{}',    -- initial process inputs
    variables            JSONB        NOT NULL DEFAULT '{}',    -- ctx.var values (runtime state)
    variable_visibility  JSONB        NOT NULL DEFAULT '{}',    -- {"var_name": "logged"|"hidden"|"sensitive"}
    outputs              JSONB,                                 -- final outputs on completion
    error_info           JSONB,                                 -- AppOSError JSON on failure
    started_at           TIMESTAMP WITH TIME ZONE NOT NULL DEFAULT NOW(),
    completed_at         TIMESTAMP WITH TIME ZONE,
    started_by           INTEGER      NOT NULL,                 -- FK to users.id (no FK on partitioned tables)
    parent_instance_id   INTEGER,                               -- self-reference for sub-processes
    triggered_by         VARCHAR(255),                          -- "web_api:crm.web_apis.submit_order"
                                                                -- or "event:records.customer.on_create"
                                                                -- or "schedule:0 9 * * *"
                                                                -- or "manual:user_456"
    created_at           TIMESTAMP WITH TIME ZONE NOT NULL DEFAULT NOW(),
    updated_at           TIMESTAMP WITH TIME ZONE NOT NULL DEFAULT NOW(),

    PRIMARY KEY (id, started_at)                                -- partition key must be in PK
) PARTITION BY RANGE (started_at);

COMMENT ON TABLE "appOS".process_instances IS 'Process execution tracking — partitioned monthly by started_at for performance at scale.';
COMMENT ON COLUMN "appOS".process_instances.instance_id IS 'Human-readable instance ID (e.g., proc_abc123)';
COMMENT ON COLUMN "appOS".process_instances.variable_visibility IS 'Per-variable visibility: logged=plaintext, hidden=hashed, sensitive=encrypted';
COMMENT ON COLUMN "appOS".process_instances.triggered_by IS 'Trigger source: web_api:ref, event:ref, schedule:cron, manual:user_id';

-- Unique constraint on instance_id (includes partition key)
CREATE UNIQUE INDEX IF NOT EXISTS idx_pi_instance_id_unique
    ON "appOS".process_instances(instance_id, started_at);

-- ---------------------------------------------------------------------------
-- 2. process_step_log — Step execution history (PARTITIONED monthly)
-- ---------------------------------------------------------------------------
CREATE TABLE IF NOT EXISTS "appOS".process_step_log (
    id                    SERIAL,
    process_instance_id   INTEGER      NOT NULL,
    step_name             VARCHAR(100) NOT NULL,
    rule_ref              VARCHAR(200) NOT NULL,                -- "crm.rules.validate_customer"
    status                VARCHAR(30)  NOT NULL
                          CHECK (status IN ('pending', 'running', 'completed', 'failed',
                                            'skipped', 'async_dispatched', 'interrupted')),
    started_at            TIMESTAMP WITH TIME ZONE NOT NULL DEFAULT NOW(),
    completed_at          TIMESTAMP WITH TIME ZONE,
    duration_ms           NUMERIC(12,3),
    inputs                JSONB,                                -- step inputs (opt-in via logging config)
    outputs               JSONB,                                -- step outputs (opt-in)
    error_info            JSONB,                                -- AppOSError JSON if failed
    attempt               INTEGER      NOT NULL DEFAULT 1,      -- retry attempt number
    is_fire_and_forget    BOOLEAN      NOT NULL DEFAULT FALSE,
    is_parallel           BOOLEAN      NOT NULL DEFAULT FALSE,

    PRIMARY KEY (id, started_at)                                -- partition key must be in PK
) PARTITION BY RANGE (started_at);

COMMENT ON TABLE "appOS".process_step_log IS 'Step execution history — one row per step attempt. Partitioned monthly by started_at.';
COMMENT ON COLUMN "appOS".process_step_log.rule_ref IS 'Object reference of the rule executed (e.g., crm.rules.validate_customer)';
COMMENT ON COLUMN "appOS".process_step_log.attempt IS 'Retry attempt number (1 = first attempt)';
COMMENT ON COLUMN "appOS".process_step_log.is_fire_and_forget IS 'True if step was dispatched asynchronously (fire_and_forget=True)';


-- ============================================================================
-- ALTERNATIVE: Flat tables for development (no partitioning)
-- ============================================================================
-- Uncomment below and comment out the partitioned versions above for dev use.
--
-- CREATE TABLE IF NOT EXISTS "appOS".process_instances (
--     id                   SERIAL PRIMARY KEY,
--     instance_id          VARCHAR(50)  NOT NULL UNIQUE,
--     process_name         VARCHAR(100) NOT NULL,
--     app_name             VARCHAR(50)  NOT NULL,
--     display_name         VARCHAR(255),
--     status               VARCHAR(20)  NOT NULL DEFAULT 'pending'
--                          CHECK (status IN ('pending', 'running', 'paused',
--                                            'completed', 'failed', 'cancelled', 'interrupted')),
--     current_step         VARCHAR(100),
--     inputs               JSONB        NOT NULL DEFAULT '{}',
--     variables            JSONB        NOT NULL DEFAULT '{}',
--     variable_visibility  JSONB        NOT NULL DEFAULT '{}',
--     outputs              JSONB,
--     error_info           JSONB,
--     started_at           TIMESTAMP WITH TIME ZONE NOT NULL DEFAULT NOW(),
--     completed_at         TIMESTAMP WITH TIME ZONE,
--     started_by           INTEGER      NOT NULL REFERENCES "appOS".users(id),
--     parent_instance_id   INTEGER,
--     triggered_by         VARCHAR(255),
--     created_at           TIMESTAMP WITH TIME ZONE NOT NULL DEFAULT NOW(),
--     updated_at           TIMESTAMP WITH TIME ZONE NOT NULL DEFAULT NOW()
-- );
--
-- CREATE TABLE IF NOT EXISTS "appOS".process_step_log (
--     id                    SERIAL PRIMARY KEY,
--     process_instance_id   INTEGER      NOT NULL,
--     step_name             VARCHAR(100) NOT NULL,
--     rule_ref              VARCHAR(200) NOT NULL,
--     status                VARCHAR(30)  NOT NULL
--                           CHECK (status IN ('pending', 'running', 'completed', 'failed',
--                                             'skipped', 'async_dispatched', 'interrupted')),
--     started_at            TIMESTAMP WITH TIME ZONE NOT NULL DEFAULT NOW(),
--     completed_at          TIMESTAMP WITH TIME ZONE,
--     duration_ms           NUMERIC(12,3),
--     inputs                JSONB,
--     outputs               JSONB,
--     error_info            JSONB,
--     attempt               INTEGER      NOT NULL DEFAULT 1,
--     is_fire_and_forget    BOOLEAN      NOT NULL DEFAULT FALSE,
--     is_parallel           BOOLEAN      NOT NULL DEFAULT FALSE
-- );
