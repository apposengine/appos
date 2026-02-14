-- ============================================================================
-- AppOS Platform Database — 010: Platform Configuration Seed
-- ============================================================================
-- Purpose:  Insert default platform configuration values into platform_config.
--           These match the defaults from appos.yaml and can be overridden
--           at runtime via Admin Console → Settings.
-- Source:   AppOS_Database_Design.md v1.0, §2.13
-- Depends:  006_supporting_tables.sql
-- Run:      ONCE on initial setup. Running again is safe (uses ON CONFLICT).
-- ============================================================================

SET search_path TO "appOS", public;

-- ---------------------------------------------------------------------------
-- Security defaults
-- ---------------------------------------------------------------------------
INSERT INTO "appOS".platform_config (key, value, category) VALUES
    ('security.session_timeout',         '3600',     'security'),
    ('security.idle_timeout',            '1800',     'security'),
    ('security.max_concurrent_sessions', '5',        'security'),
    ('security.permission_cache_ttl',    '300',      'security'),
    ('security.max_login_attempts',      '5',        'security'),
    ('security.lockout_duration',        '900',      'security'),
    ('security.csrf_enabled',            'true',     'security'),
    ('security.cookie_secure',           'false',    'security'),     -- set to true in prod
    ('security.cookie_samesite',         '"Lax"',    'security')
ON CONFLICT (key) DO NOTHING;

-- ---------------------------------------------------------------------------
-- Logging defaults
-- ---------------------------------------------------------------------------
INSERT INTO "appOS".platform_config (key, value, category) VALUES
    ('logging.level',                       '"INFO"',   'logging'),
    ('logging.retention.execution_days',    '90',       'logging'),
    ('logging.retention.performance_days',  '30',       'logging'),
    ('logging.retention.security_days',     '365',      'logging'),
    ('logging.async_queue.batch_size',      '50',       'logging'),
    ('logging.async_queue.flush_interval_ms','100',     'logging')
ON CONFLICT (key) DO NOTHING;

-- ---------------------------------------------------------------------------
-- Process engine defaults
-- ---------------------------------------------------------------------------
INSERT INTO "appOS".platform_config (key, value, category) VALUES
    ('process_instances.archive_after_days',    '90',       'process'),
    ('process_instances.partition_range',        '"monthly"','process'),
    ('process.default_timeout',                 '3600',     'process'),
    ('process.max_parallel_steps',              '10',       'process')
ON CONFLICT (key) DO NOTHING;

-- ---------------------------------------------------------------------------
-- Database / connection pool defaults
-- ---------------------------------------------------------------------------
INSERT INTO "appOS".platform_config (key, value, category) VALUES
    ('database.pool_size',              '10',       'database'),
    ('database.max_overflow',           '20',       'database'),
    ('database.pool_timeout',           '30',       'database'),
    ('database.pool_recycle',           '1800',     'database'),
    ('database.pool_pre_ping',          'true',     'database')
ON CONFLICT (key) DO NOTHING;

-- ---------------------------------------------------------------------------
-- Document / upload defaults
-- ---------------------------------------------------------------------------
INSERT INTO "appOS".platform_config (key, value, category) VALUES
    ('documents.max_upload_size_mb',    '50',       'documents'),
    ('documents.allowed_mime_types',    '["*/*"]',  'documents')
ON CONFLICT (key) DO NOTHING;

-- ---------------------------------------------------------------------------
-- Celery / worker defaults
-- ---------------------------------------------------------------------------
INSERT INTO "appOS".platform_config (key, value, category) VALUES
    ('celery.broker_db',        '0',        'celery'),
    ('celery.result_db',        '1',        'celery'),
    ('celery.worker_concurrency','4',       'celery'),
    ('celery.task_soft_time_limit','300',   'celery'),
    ('celery.task_time_limit',  '600',      'celery')
ON CONFLICT (key) DO NOTHING;

-- ---------------------------------------------------------------------------
-- UI defaults
-- ---------------------------------------------------------------------------
INSERT INTO "appOS".platform_config (key, value, category) VALUES
    ('ui.default_theme',        '{"primary_color": "#3B82F6", "font_family": "Inter"}', 'ui'),
    ('ui.admin_items_per_page', '25',       'ui')
ON CONFLICT (key) DO NOTHING;
