# AppOS Platform Database Scripts

> **Schema:** `"appOS"` on PostgreSQL  
> **Connection:** VS Code PostgreSQL extension → `localhost:5432/postgres`  
> **Created:** February 14, 2026  
> **Source:** `AppOS_Database_Design.md` v1.0

## Execution Order

Run scripts in numbered order for a clean install. Each script is **idempotent** where possible (uses `IF NOT EXISTS`).

| # | Script | Purpose | Idempotent |
|---|--------|---------|------------|
| 1 | `001_schema.sql` | Create `"appOS"` schema | Yes |
| 2 | `002_core_tables.sql` | `users`, `groups`, `apps`, `connected_systems` | Yes |
| 3 | `003_junction_tables.sql` | `user_groups`, `group_apps`, `connected_system_groups` | Yes |
| 4 | `004_security_tables.sql` | `object_permission`, `login_audit_log` | Yes |
| 5 | `005_process_tables.sql` | `process_instances`, `process_step_log` (partitioned) | Yes |
| 6 | `006_supporting_tables.sql` | `dependency_changes`, `object_registry`, `platform_config`, `scheduled_tasks` | Yes |
| 7 | `007_indexes.sql` | All indexes for all tables | Yes |
| 8 | `008_partitions.sql` | Monthly partition creation + archival tables | Additive |
| 9 | `009_bootstrap_data.sql` | Seed data: admin user, default groups, permissions | Run once |
| 10 | `010_platform_config_seed.sql` | Default platform configuration entries | Run once |

## Quick Start

```sql
-- Run all scripts in order via psql:
\i migrations/platform/scripts/001_schema.sql
\i migrations/platform/scripts/002_core_tables.sql
\i migrations/platform/scripts/003_junction_tables.sql
\i migrations/platform/scripts/004_security_tables.sql
\i migrations/platform/scripts/005_process_tables.sql
\i migrations/platform/scripts/006_supporting_tables.sql
\i migrations/platform/scripts/007_indexes.sql
\i migrations/platform/scripts/008_partitions.sql
\i migrations/platform/scripts/009_bootstrap_data.sql
\i migrations/platform/scripts/010_platform_config_seed.sql
```

## Environment Notes

- **Dev:** Tables are flat (no partitioning). Use VS Code PostgreSQL extension against `"appOS"` schema for verification.
- **Prod:** `process_instances` and `process_step_log` are range-partitioned by `started_at` (monthly).
- **Schema:** All objects live in `"appOS"` schema — never in `public`.

## VS Code PostgreSQL Extension

The `"appOS"` schema is accessible via the VS Code PostgreSQL extension connection at `localhost:5432`. Use it for:
- Table/column inspection
- Running ad-hoc queries
- Verifying migrations
- Browsing data
