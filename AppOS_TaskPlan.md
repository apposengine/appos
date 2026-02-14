# AppOS — Implementation Task Plan

> **Version:** 2.1  
> **Created:** February 7, 2026  
> **Updated:** February 12, 2026  
> **Architecture Doc:** `AppOS_Design.md` v2.1 (read AI Context Index at lines 38-134 first)  
> **Reference Docs:** `AppOS_Permissions_Reference.md`, `AppOS_Logging_Reference.md`, `AppOS_PlatformRules_Reference.md`  
> **Reflex Notes:** `Reflex_Notes.md`

---

<!-- ===========================================================================
     AI TASK CONTEXT — Read this file FIRST when resuming any dev session.
     Contains: current phase, completed work, next tasks, decisions log.
     Keep this under 200 lines for fast context loading.
     =========================================================================== -->

## Current Status

| Field | Value |
|-------|-------|
| **Current Phase** | Not started |
| **Last Completed Task** | Architecture design v2.0 finalized |
| **Next Task** | Phase 1: Core Engine — Auto-Import System |
| **Blockers** | None |

---

## Phase Overview

| # | Phase | Weeks | Status | Key Files |
|---|-------|-------|--------|-----------|
| 1 | Core Engine | 1-4 | `NOT_STARTED` | `appos/engine/`, `appos/admin/` |
| 2 | Data Layer | 5-7 | `NOT_STARTED` | `appos/decorators/record.py`, `appos/db/` |
| 3 | Logic Layer | 8-10 | `NOT_STARTED` | `appos/decorators/expression_rule.py`, `appos/process/` |
| 4 | UI Layer | 11-13 | `NOT_STARTED` | `appos/ui/`, `apps/*/pages/` |
| 5 | External Layer | 14-16 | `NOT_STARTED` | `appos/decorators/integration.py`, `appos/decorators/web_api.py` |
| 6 | Polish & Prod | 17-20 | `NOT_STARTED` | CLI tools, tests, docs |

---

## Phase 1: Core Engine — Task Breakdown

| # | Task | Status | Files | Notes |
|---|------|--------|-------|-------|
| 1.1 | Project scaffold + folder structure | `TODO` | `appos/`, `apps/`, `.appos/` | See design §15 (L3271) |
| 1.2 | SecureAutoImportNamespace | `TODO` | `appos/engine/namespaces.py` | See design §4 (L338), cross-app prefix resolution |
| 1.3 | ExecutionContext (contextvars) | `TODO` | `appos/engine/context.py` | See design §7 (L1823) |
| 1.4 | Unified 6-permission model + object_permission table | `TODO` | `appos/engine/security.py`, `appos/db/platform_models.py` | See design §6 (L1579), Permissions Ref |
| 1.5 | Redis permission cache (cache-first check) | `TODO` | `appos/engine/cache.py` | TTL=5min, see §6 |
| 1.6 | Object Registry | `TODO` | `appos/engine/registry.py` | Register/retrieve by type+app+name |
| 1.7 | CentralizedRuntime (basic) | `TODO` | `appos/engine/runtime.py` | See design §8 (L1923), incl. engine.dispatch() |
| 1.8 | Per-object-type FileLoggers + AsyncLogQueue | `TODO` | `appos/engine/runtime.py` | See §8, Logging Ref: async queue + background flush |
| 1.9 | NetworkX dependency graph | `TODO` | `appos/engine/dependency.py` | See design §10 (L2339) |
| 1.10 | Platform DB models (User: user_type, Group) | `TODO` | `appos/db/platform_models.py` | user_type: basic/system_admin/service_account (§5.2) |
| 1.11 | Default system_admin + public_access group bootstrap (appos init) | `TODO` | `appos/cli.py` | See Permissions Ref — both groups created on init |
| 1.12 | Session-based auth (Redis DB 4) | `TODO` | `appos/engine/security.py` | Idle timeout, max concurrent sessions, CSRF token |
| 1.13 | AppOSError hierarchy | `TODO` | `appos/engine/errors.py` | AppOSSecurityError, AppOSDispatchError, etc. (Permissions Ref) |
| 1.14 | Admin: Login page | `TODO` | `appos/admin/pages/login.py` | Common for all apps |
| 1.15 | Admin: User CRUD (incl. service accounts) | `TODO` | `appos/admin/pages/users.py` | |
| 1.16 | Admin: Group CRUD + user assignment | `TODO` | `appos/admin/pages/groups.py` | |
| 1.17 | Reflex app entry point (rxconfig) | `TODO` | `rxconfig.py` | Single port, admin routes |
| 1.18 | Unit tests for Phase 1 | `TODO` | `tests/test_engine.py` | |

## Phase 2: Data Layer — Task Breakdown

| # | Task | Status | Files | Notes |
|---|------|--------|-------|-------|
| 2.1 | @connected_system decorator (global scope) | `TODO` | `appos/decorators/connected_system.py` | See §5.5 (L632), global only, imap type added |
| 2.2 | Connection pool config (max_overflow, pool_timeout, etc.) | `TODO` | `appos/decorators/connected_system.py` | See §5.5 |
| 2.3 | Credential encryption + admin UI | `TODO` | `appos/admin/pages/connections.py` | Admin-managed |
| 2.4 | Environment overrides resolver | `TODO` | `appos/engine/environment.py` | dev/staging/prod |
| 2.5 | Health check mechanism | `TODO` | `appos/engine/health.py` | Per connected system |
| 2.6 | @record decorator (Pydantic) | `TODO` | `appos/decorators/record.py` | See §5.7 (L803), §9 (L2218) |
| 2.7 | Pydantic → SQLAlchemy generator | `TODO` | `appos/generators/model_generator.py` | See §9 |
| 2.8 | Alembic migration auto-gen | `TODO` | `appos/generators/migration_generator.py` | |
| 2.9 | CRUD service generator | `TODO` | `appos/generators/service_generator.py` | See §9 |
| 2.10 | Record event hooks (on_create etc.) | `TODO` | `appos/decorators/record.py` | Meta config |
| 2.11 | @constant decorator | `TODO` | `appos/decorators/constant.py` | See §5.6 (L715) |
| 2.12 | Constant env-specific resolution | `TODO` | `appos/decorators/constant.py` | dev/staging/prod values |
| 2.13 | Constant object reference + engine.dispatch() | `TODO` | `appos/decorators/constant.py`, `appos/engine/runtime.py` | See §5.6, §8 (L2067) |
| 2.14 | Admin: App management page | `TODO` | `appos/admin/pages/apps.py` | See §5.4 (L585) |
| 2.15 | Admin: Records browser | `TODO` | `appos/admin/pages/records_browser.py` | |
| 2.16 | Admin: Connected System UI | `TODO` | `appos/admin/pages/connections.py` | See §13 (L2898) |

## Phase 3: Logic Layer — Task Breakdown

| # | Task | Status | Files | Notes |
|---|------|--------|-------|-------|
| 3.1 | @expression_rule decorator | `TODO` | `appos/decorators/expression_rule.py` | See §5.8 (L891) |
| 3.2 | Rule ctx (input/output/local) | `TODO` | `appos/engine/context.py` | Extend ExecutionContext |
| 3.3 | Auto-dependency tracking on rules | `TODO` | `appos/engine/namespaces.py` | Via auto-import intercept |
| 3.4 | step() function + fire_and_forget | `TODO` | `appos/decorators/step.py` | See §5.9 (L969), fire_and_forget=True |
| 3.5 | @process decorator + display_name | `TODO` | `appos/decorators/process.py` | See §5.10 (L1019), display_name template |
| 3.6 | parallel() construct → Celery group | `TODO` | `appos/decorators/process.py` | See §5.10, §11 (L2519) |
| 3.7 | ProcessContext (ctx.var) | `TODO` | `appos/engine/context.py` | See §7 (L1879) |
| 3.8 | ProcessInstance DB model (partitioned) | `TODO` | `appos/db/platform_models.py` | See §11 (L2570), partitioned by started_at |
| 3.9 | process_step_log table (separate) | `TODO` | `appos/db/platform_models.py` | See §11 (L2610), not JSON array |
| 3.10 | Celery integration | `TODO` | `appos/process/executor.py` | See §11 (L2635) |
| 3.11 | Process triggers (event, schedule) | `TODO` | `appos/process/scheduler.py` | |
| 3.12 | Celery Beat setup | `TODO` | `appos/process/scheduler.py` | |
| 3.13 | Variable visibility (logged/hidden/sensitive) | `TODO` | `appos/engine/context.py` | See §5.10 (L1105) |
| 3.14 | Zero-import process start: processes.X.start() | `TODO` | `appos/engine/namespaces.py` | See §4 (L449) |
| 3.15 | Admin: Process monitor | `TODO` | `appos/admin/pages/processes.py` | Step-by-step viewer |
| 3.16 | Admin: Rule browser + metrics | `TODO` | `appos/admin/pages/object_browser.py` | |

## Phase 4: UI Layer — Task Breakdown

| # | Task | Status | Files | Notes |
|---|------|--------|-------|-------|
| 4.1 | @interface decorator (component=function) | `TODO` | `appos/decorators/interface.py` | See §5.13 (L1253), component is a plain function |
| 4.2 | Component library (DataTable, Form, etc.) | `TODO` | `appos/ui/components.py` | See §12 (L2766) |
| 4.3 | Raw Reflex component passthrough | `TODO` | `appos/ui/components.py` | Alongside AppOS components |
| 4.4 | InterfaceRenderer (AppOS → Reflex) | `TODO` | `appos/ui/renderer.py` | Page→Interface→Component hierarchy |
| 4.5 | Interface auto-gen from Records | `TODO` | `appos/generators/interface_generator.py` | List/Create/Edit/View |
| 4.6 | @interface.extend override mechanism | `TODO` | `appos/decorators/interface.py` | |
| 4.7 | @page decorator | `TODO` | `appos/decorators/page.py` | See §5.14 (L1310) |
| 4.8 | @site decorator + navigation | `TODO` | `appos/decorators/site.py` | See §5.15 (L1361) |
| 4.9 | Single-port multi-app Reflex routing | `TODO` | `appos/ui/reflex_bridge.py` | See §12 (L2766) |
| 4.10 | Per-app theming | `TODO` | `appos/ui/reflex_bridge.py` | See §12 (L2856) |
| 4.11 | Inherited UI security from app.yaml | `TODO` | `appos/security/permissions.py` | security.defaults.ui from app.yaml |
| 4.12 | Form submission → Record save | `TODO` | `appos/ui/renderer.py` | |

## Phase 5: External Layer — Task Breakdown

| # | Task | Status | Files | Notes |
|---|------|--------|-------|-------|
| 5.1 | @integration decorator | `TODO` | `appos/decorators/integration.py` | See §5.11 (L1115) |
| 5.2 | Connected System resolution in integrations | `TODO` | `appos/decorators/integration.py` | |
| 5.3 | Retry logic + backoff | `TODO` | `appos/decorators/integration.py` | |
| 5.4 | @web_api decorator | `TODO` | `appos/decorators/web_api.py` | See §5.12 (L1181) |
| 5.5 | Web API async mode (returns instance_id) | `TODO` | `appos/decorators/web_api.py` | async_mode=True triggers process |
| 5.6 | API route registration | `TODO` | `appos/ui/reflex_bridge.py` | /api/{app}/{ver}/{path} |
| 5.7 | API auth: service account flow | `TODO` | `appos/decorators/web_api.py` | /api/auth/token → session token |
| 5.8 | Rate limiting | `TODO` | `appos/decorators/web_api.py` | |
| 5.9 | Document record + versioning | `TODO` | `apps/*/records/document.py` | See §5.16 (L1390) |
| 5.10 | Folder management | `TODO` | `apps/*/records/folder.py` | See §5.17 (L1467) |
| 5.11 | rx.upload integration | `TODO` | `appos/ui/components.py` | |
| 5.12 | @translation_set decorator | `TODO` | `appos/decorators/translation_set.py` | See §5.18 (L1516) |
| 5.13 | Language resolution (ctx.user.preferred_language) | `TODO` | `appos/engine/context.py` | |

## Phase 6: Polish — Task Breakdown

| # | Task | Status | Files | Notes |
|---|------|--------|-------|-------|
| 6.1 | Complete admin console (all screens) | `TODO` | `appos/admin/` | See §13 (L2898), system_admin only |
| 6.2 | Admin Settings page (DB, YAML, cache) | `TODO` | `appos/admin/pages/settings.py` | See §13 (L2922) |
| 6.3 | Admin Active Sessions + cache flush | `TODO` | `appos/admin/pages/sessions.py` | See §13 (L2923) |
| 6.4 | Admin Theme Editor per app | `TODO` | `appos/admin/pages/themes.py` | See §13 (L2924) |
| 6.5 | Admin log viewer with filters | `TODO` | `appos/admin/pages/logs.py` | |
| 6.6 | Admin metrics dashboard | `TODO` | `appos/admin/pages/metrics.py` | See §13 (L2917) |
| 6.7 | Admin worker management UI | `TODO` | `appos/admin/pages/workers.py` | See §13 (L3012), WorkerManager class |
| 6.8 | Platform rules implementation | `TODO` | `appos/platform_rules/` | user_rules.py, group_rules.py, utility_rules.py |
| 6.9 | AI query interface | `TODO` | `appos/engine/runtime.py` | See §10 (L2339) |
| 6.10 | Impact analysis → `appos impact` CLI | `TODO` | `appos/cli.py` | See §10 (L2492), CLI tool not runtime |
| 6.11 | CLI: appos init | `TODO` | `appos/cli.py` | Scaffold project |
| 6.12 | CLI: appos new-app | `TODO` | `appos/cli.py` | Create app structure |
| 6.13 | CLI: appos generate | `TODO` | `appos/cli.py` | Run all generators |
| 6.14 | CLI: appos migrate | `TODO` | `appos/cli.py` | Run Alembic |
| 6.15 | CLI: appos run | `TODO` | `appos/cli.py` | Start Reflex |
| 6.16 | CLI: appos check | `TODO` | `appos/cli.py` | Validate objects + deps + AppOS-only imports |
| 6.17 | CLI: appos impact {object_ref} | `TODO` | `appos/cli.py` | Show upstream/downstream deps |
| 6.18 | Full test suite | `TODO` | `tests/` | |
| 6.19 | Documentation | `TODO` | `docs/` | Getting started, API ref |
| 6.20 | Audit log table generator | `TODO` | `appos/generators/audit_generator.py` | Auto-generate `{app}_{record}_audit_log` tables for records with `audit=True` |
| 6.21 | REST API generator | `TODO` | `appos/generators/api_generator.py` | Auto-generate REST endpoints from @record definitions |
| 6.22 | event_log table creation | `TODO` | `appos/db/platform_models.py` | `{app}_event_log` table for custom business event logging |
| 6.23 | dependency_changes table | `TODO` | `appos/db/platform_models.py` | Track dependency graph changes over time |
| 6.24 | JSON dependency persistence | `TODO` | `appos/engine/dependency.py` | Persist NetworkX graph to `.appos/runtime/dependencies/` JSON files |
| 6.25 | Log cleanup cron job | `TODO` | `appos/engine/runtime.py` | Nightly cleanup per `logging.cleanup_schedule` + retention config |
| 6.26 | ProcessInstance table partitioning | `TODO` | `appos/db/platform_models.py` | Monthly partitions on `started_at`, archive policy |
| 6.27 | Process instance archival | `TODO` | `appos/engine/runtime.py` | Move completed instances older than `archive_after_days` to archive partition |
| 6.28 | Integration / E2E test suite | `TODO` | `tests/integration/` | Cross-app, process, Web API integration tests |
| 6.29 | YAML config parsing (appos.yaml + app.yaml) | `TODO` | `appos/engine/config.py` | Load and validate platform + app YAML configs at startup |
| 6.30 | Row security rule (future) | `TODO` | `appos/engine/security.py` | Future: per-row security rules for Records — design placeholder only |

---

## Decisions Log

| Date | Decision | Rationale |
|------|----------|-----------|
| 2026-02-07 | Merge Data Store into Connected System | Single object with `type` field (database/api/ftp/smtp) |
| 2026-02-07 | Merge Query Rule into Expression Rule | Both modular functions, no need for separate type |
| 2026-02-07 | Drop Module system | Use App-level objects directly, simpler |
| 2026-02-07 | Pydantic-native Records | Standard field definitions, not custom AppOS types |
| 2026-02-07 | System logs → files, app logs → DB | Sustainable, fast writes, no DB dependency for system logs |
| 2026-02-07 | Process vars across all steps | ctx.var accessible by all steps, not scoped per step |
| 2026-02-07 | Step as separate object | Wraps expression rule with retry/timeout/condition metadata |
| 2026-02-07 | Single port Reflex | URL-prefix routing (/admin, /crm, /finance) |
| 2026-02-07 | Redis for permission cache | TTL=5min, 100-200ms cold acceptable |
| 2026-02-07 | NetworkX for dependency graph | In-memory fast traversal + JSON file persistence |
| 2026-02-07 | Credentials in admin console (encrypted DB) | Not env files — admin-managed for easier rotation |
| 2026-02-07 | Document versioning via DB | DocumentVersion table tracks history |
| 2026-02-07 | Constants support env overrides | dev/staging/prod values per constant |
| 2026-02-07 | Shared users/groups, app-level isolation | Multi-tenancy via group→app association |
| 2026-02-07 | Unified engine.dispatch() for object refs | Constants with object_ref type can point to rules, processes, or integrations — engine.dispatch() auto-detects target type and calls correct executor. See §8 (L2067) |
| 2026-02-12 | Unified 6-permission model | view/use/create/update/delete/admin — replaces type-specific permissions |
| 2026-02-12 | Three-tier inherited security | App defaults → inheriting objects → always-explicit objects |
| 2026-02-12 | user_type field replaces is_admin | basic/system_admin/service_account — extensible enum |
| 2026-02-12 | Connected Systems global only | Not app-bound — shared across all apps |
| 2026-02-12 | Per-object-type log folders | 10 folders (rules/, processes/, etc.) not per-category |
| 2026-02-12 | Async non-blocking logging | In-memory queue, batch flush, no I/O in request path |
| 2026-02-12 | Separate process_step_log table | Not JSON array — proper DB table, partitioned by started_at |
| 2026-02-12 | Zero-config cross-app access | Prefix = declaration, no import config needed |
| 2026-02-12 | processes.X.start() namespace | Zero-import process starting via auto-import |
| 2026-02-12 | Session-based auth (not JWT) | Redis-backed sessions, server-side revocation |
| 2026-02-12 | Platform rules (prebuilt) | User/group management rules ship with platform |
| 2026-02-12 | Components are functions | Not a separate object type — plain Python functions |
| 2026-02-12 | `appos impact` CLI tool | Impact analysis at dev time, not runtime |
| 2026-02-12 | No hard deletes for users/groups | Use deactivate_user / deactivate_group instead — retains audit trail |
| 2026-02-12 | Connected System multi-engine registry | Each DB Connected System registers its own SQLAlchemy engine, managed centrally |
| 2026-02-12 | platform_connected_systems/ folder | Global Connected Systems live at platform level, not per-app |
| 2026-02-12 | Translation fallback chain | preferred_language → en (mandatory default) → key name as-is |
| 2026-02-12 | Global max_upload_size_mb | Platform-wide upload limit in appos.yaml documents section |
| 2026-02-12 | CSRF token + SameSite=Lax | Session auth includes CSRF protection and cookie hardening |
| 2026-02-12 | Redis failure strategy | Circuit breaker → fallback to DB for permission checks when Redis unavailable |
| 2026-02-12 | Steps have no security/ log folder | Steps delegate security to the rules they invoke; no separate security logging |

---

## File Quick Reference

| File | Purpose | Design Section |
|------|---------|---------------|
| `AppOS_Design.md` | Full architecture (read AI Index at L39-L145) | All |
| `AppOS_TaskPlan.md` | This file — task tracking + decisions | — |
| `AppOS_Permissions_Reference.md` | Unified permissions, three-tier security, user types, error hierarchy | §6 Security |
| `AppOS_Logging_Reference.md` | Per-type log folders, entry formats, async pipeline, rotation | §14 Logging |
| `AppOS_PlatformRules_Reference.md` | Prebuilt user/group management rules | §5.8 Rules |
| `AppOS_Email_Reference.md` | Outlook email integration (send/receive) | — |
| `AppOS_Shutdown_Reference.md` | Graceful shutdown procedure | — |
| `AppOS_Monitoring_Reference.md` | Health endpoints (/health, /ready) | — |
| `AppOS_Backup_Reference.md` | Backup and restore strategy | — |
| `AppOS_CICD_Reference.md` | CI/CD and environment promotion | — |
| `Reflex_Notes.md` | Reflex framework patterns + best practices | §12 UI Layer |
| `AppOS_Design_v1_backup.md` | Archived v1 design | — |

---

*Last updated: February 12, 2026*
