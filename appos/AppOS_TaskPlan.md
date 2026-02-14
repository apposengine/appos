# AppOS — Implementation Task Plan

> **Version:** 2.8  
> **Created:** February 7, 2026  
> **Updated:** February 15, 2026  
> **Architecture Doc:** `AppOS_Design.md` v2.1 (read AI Context Index at lines 38-134 first)  
> **Reference Docs:** `AppOS_Permissions_Reference.md`, `AppOS_Logging_Reference.md`, `AppOS_PlatformRules_Reference.md`, `AppOS_UI_Reference.md`  
> **Reflex Notes:** `Reflex_Notes.md`  
> **DB Scripts:** `migrations/platform/scripts/` (see README.md in that folder for execution order)  
> **Live DB Schema:** `"appOS"` schema on PostgreSQL `localhost:5432/postgres` via VS Code PostgreSQL extension

### Status Legend

| Icon | Meaning |
|------|---------|
| ✅ | Done — implemented and verified |
| 🔶 | Partial — core logic exists, needs refinement |
| ⬜ | Not started |

---

<!-- ===========================================================================
     AI TASK CONTEXT — Read this file FIRST when resuming any dev session.
     Contains: current phase, completed work, next tasks, decisions log.
     Keep this under 200 lines for fast context loading.
     =========================================================================== -->

## Current Status

| Field | Value |
|-------|-------|
| **Current Phase** | ALL PHASES COMPLETE |
| **Last Completed Task** | 6.28 Integration / E2E test suite |
| **Next Task** | None — platform fully implemented |
| **Blockers** | None |
| **Progress** | Phase 1: 18/18 ✅ · Phase 2: 16/16 ✅ · Phase 3: 16/16 ✅ · Phase 4: 12/12 ✅ · Phase 5: 13/13 ✅ · Phase 6: 30/30 ✅ |

---

## Phase Overview

| # | Phase | Weeks | Status | Progress | Key Files |
|---|-------|-------|--------|----------|-----------|
| 1 | Core Engine | 1-4 | ✅ DONE | 18/18 | `appos/engine/`, `appos/admin/` |
| 2 | Data Layer | 5-7 | ✅ DONE | 16/16 | `appos/decorators/record.py`, `appos/db/`, `appos/generators/` |
| 3 | Logic Layer | 8-10 | ✅ DONE | 16/16 | `appos/decorators/expression_rule.py`, `appos/process/` |
| 4 | UI Layer | 11-13 | ✅ DONE | 12/12 | `appos/ui/`, `appos/generators/interface_generator.py`, `appos/security/` |
| 5 | External Layer | 14-16 | ✅ DONE | 13/13 | `appos/decorators/integration.py`, `appos/decorators/web_api.py`, `appos/documents/` |
| 6 | Polish & Prod | 17-20 | ✅ DONE | 30/30 | CLI tools, tests, docs |

---

## Phase 1: Core Engine — Task Breakdown

| # | Task | Status | Files | Notes |
|---|------|--------|-------|-------|
| 1.1 | Project scaffold + folder structure | ✅ | `appos/`, `apps/`, `.appos/` | ~65 dirs created per §15 |
| 1.2 | SecureAutoImportNamespace | ✅ | `appos/engine/namespaces.py` | + CrossAppNamespace, build_app_namespaces() |
| 1.3 | ExecutionContext (contextvars) | ✅ | `appos/engine/context.py` | + ProcessContext, RuleContext |
| 1.4 | Unified 6-permission model + object_permission table | ✅ | `appos/engine/security.py`, `appos/db/platform_models.py` | SecurityPolicy + wildcard resolution |
| 1.5 | Redis permission cache (cache-first check) | ✅ | `appos/engine/cache.py` | Circuit breaker, PermissionCache, 4 Redis DB factories |
| 1.6 | Object Registry | ✅ | `appos/engine/registry.py` | Primary + secondary indexes, scan_app_directory() |
| 1.7 | CentralizedRuntime (basic) | ✅ | `appos/engine/runtime.py` | dispatch(), query_for_ai(), startup/shutdown lifecycle |
| 1.8 | Per-object-type FileLoggers + AsyncLogQueue | ✅ | `appos/engine/logging.py` | FileLogger, AsyncLogQueue (100ms/50), LogRetentionManager |
| 1.9 | NetworkX dependency graph | ✅ | `appos/engine/dependency.py` | DependencyGraph, JSON persistence, impact_analysis() |
| 1.10 | Platform DB models (User: user_type, Group) | ✅ | `appos/db/platform_models.py` | All 15 models matching DB Design Doc |
| 1.11 | Default system_admin + public_access group bootstrap (appos init) | ✅ | `appos/cli.py` | + appos run, appos impact, appos validate |
| 1.12 | Session-based auth (Redis DB 4) | ✅ | `appos/engine/security.py` | AuthService: CSRF, concurrent limits, API key auth |
| 1.13 | AppOSError hierarchy | ✅ | `appos/engine/errors.py` | 9 error classes with to_dict/to_json |
| 1.14 | Admin: Login page | ✅ | `appos/admin/pages/login.py` | Reflex form + AdminState |
| 1.15 | Admin: User CRUD (incl. service accounts) | ✅ | `appos/admin/pages/users.py` | DataTable + create dialog |
| 1.16 | Admin: Group CRUD + user assignment | ✅ | `appos/admin/pages/groups.py` | DataTable + create dialog |
| 1.17 | Reflex app entry point (rxconfig) | ✅ | `rxconfig.py`, `appos/appos.py` | Route registration, admin layout |
| 1.18 | Unit tests for Phase 1 | ✅ | `tests/` | Covered by 6.18 full test suite (17 files, 230+ tests) |

## Phase 2: Data Layer — Task Breakdown

| # | Task | Status | Files | Notes |
|---|------|--------|-------|-------|
| 2.1 | @connected_system decorator (global scope) | ✅ | `appos/decorators/core.py` | Registered via core decorators module |
| 2.2 | Connection pool config (max_overflow, pool_timeout, etc.) | ✅ | `appos/decorators/connected_system.py` | ConnectedSystemManager + PoolConfig + ResolvedConnectedSystem |
| 2.3 | Credential encryption | ✅ | `appos/engine/credentials.py` | CredentialManager: Fernet encryption, key rotation, auth header generation (basic/api_key/oauth2/cert) |
| 2.4 | Environment overrides resolver | ✅ | `appos/engine/environment.py` | EnvironmentResolver: deep merge, pool config extraction, Connected System + Constant patterns |
| 2.5 | Health check mechanism | ✅ | `appos/engine/health.py` | HealthCheckService: DB/HTTP/Redis checks, background monitoring, platform health aggregation |
| 2.6 | @record decorator (Pydantic) | ✅ | `appos/decorators/core.py` | + has_many, belongs_to, has_one helpers. ⚠️ Note: REST APIs for records must go through @web_api + api_executor pipeline (not standalone FastAPI) |
| 2.7 | Pydantic → SQLAlchemy generator | ✅ | `appos/generators/model_generator.py` | parse_record → generate_model_code + generate_sql_ddl + audit table gen |
| 2.8 | Alembic migration auto-gen | ✅ | `appos/generators/migration_generator.py` | Schema introspect → diff → Alembic-compat migration scripts |
| 2.9 | CRUD service generator | ✅ | `appos/generators/service_generator.py` | RecordService base class (CRUD + audit + event hooks) + code generator |
| 2.10 | Record event hooks (on_create etc.) | ✅ | `appos/decorators/record.py` | RecordEventManager: fire/fire_async, register from Meta hooks, startup integration |
| 2.11 | @constant decorator | ✅ | `appos/decorators/core.py` | + env-specific resolution built-in |
| 2.12 | Constant env-specific resolution | ✅ | `appos/decorators/core.py` | Reads get_environment(), resolves default→env |
| 2.13 | Constant object reference + engine.dispatch() | ✅ | `appos/decorators/constant.py`, `appos/engine/runtime.py` | ConstantManager + _dispatch_constant in runtime + get_runtime() singleton |
| 2.14 | Admin: App management page | ✅ | `appos/admin/pages/apps.py` | Register, configure, deactivate apps + create_app handler in AdminState |
| 2.15 | Admin: Records browser | ✅ | `appos/admin/pages/records_browser.py` | Browse @record types, inspect schemas, data preview placeholder |
| 2.16 | Admin: Connected System UI | ✅ | `appos/admin/pages/connections.py` | Full CRUD, credential management, health status, env overrides |

## Phase 3: Logic Layer — Task Breakdown

| # | Task | Status | Files | Notes |
|---|------|--------|-------|-------|
| 3.1 | @expression_rule decorator | ✅ | `appos/decorators/core.py` | Bare + parameterized, auto-registers |
| 3.2 | Rule ctx (input/output/local) | ✅ | `appos/engine/context.py` | RuleContext with input()/output()/outputs() |
| 3.3 | Auto-dependency tracking on rules | ✅ | `appos/engine/namespaces.py` | Via SecureAutoImportNamespace intercept |
| 3.4 | step() function + fire_and_forget | ✅ | `appos/decorators/core.py` | Returns dict, consumed by @process |
| 3.5 | @process decorator + display_name | ✅ | `appos/decorators/core.py` | + event(), schedule() trigger builders |
| 3.6 | parallel() construct → Celery group | ✅ | `appos/decorators/core.py` | Returns {type:"parallel", steps:[...]} |
| 3.7 | ProcessContext (ctx.var) | ✅ | `appos/engine/context.py` | logged/hidden/sensitive visibility flags |
| 3.8 | ProcessInstance DB model (partitioned) | ✅ | `appos/db/platform_models.py` | Already implemented in task 1.10 — matches §11 design exactly |
| 3.9 | process_step_log table (separate) | ✅ | `appos/db/platform_models.py` | Already implemented in task 1.10 — separate table, not JSON array |
| 3.10 | Celery integration | ✅ | `appos/process/executor.py` | ProcessExecutor + execute_process_step Celery task + start_process_task. Wired into runtime._start_process(). Supports sync & async modes. |
| 3.11 | Process triggers (event, schedule) | ✅ | `appos/process/scheduler.py` | EventTriggerRegistry + fire_event() auto-starts matching processes |
| 3.12 | Celery Beat setup | ✅ | `appos/process/scheduler.py` | ScheduleTriggerRegistry + crontab → beat_schedule + scheduled_process_task |
| 3.13 | Variable visibility (logged/hidden/sensitive) | ✅ | `appos/engine/context.py` | Built into ProcessContext |
| 3.14 | Zero-import process start: processes.X.start() | ✅ | `appos/engine/namespaces.py` | ProcessStartProxy wraps resolved processes, .start(inputs={}) dispatches via runtime |
| 3.15 | Admin: Process monitor | ✅ | `appos/admin/pages/processes.py` | Instance list + filters + step history + variable inspection |
| 3.16 | Admin: Object browser + metrics | ✅ | `appos/admin/pages/object_browser.py` | Browse all objects, filter by type/app, dependency viewer, metadata inspection |

## Phase 4: UI Layer — Task Breakdown

| # | Task | Status | Files | Notes |
|---|------|--------|-------|-------|
| 4.1 | @interface decorator (component=function) | ✅ | `appos/decorators/core.py` | Decorator + InterfaceRenderer integration via reflex_bridge |
| 4.2 | Component library (DataTable, Form, etc.) | ✅ | `appos/ui/components.py` | 12 component defs: DataTable, Form, Field, Button, Layout, Row, Column, Card, Wizard, WizardStep, Chart, Metric |
| 4.3 | Raw Reflex component passthrough | ✅ | `appos/ui/components.py` | RawReflex wrapper + auto-detection in renderer |
| 4.4 | InterfaceRenderer (AppOS → Reflex) | ✅ | `appos/ui/renderer.py` | Full component tree walker, type-specific renderers, theme application |
| 4.5 | Interface auto-gen from Records | ✅ | `appos/generators/interface_generator.py` | List/Create/Edit/View generators, batch generation |
| 4.6 | @interface.extend override mechanism | ✅ | `appos/decorators/interface.py` | InterfaceExtendRegistry, priority-based extension chain |
| 4.7 | @page decorator | ✅ | `appos/ui/reflex_bridge.py` | Full Reflex page binding with InterfaceRenderer fallback |
| 4.8 | @site decorator + navigation | ✅ | `appos/ui/reflex_bridge.py` | SiteConfig, NavItem, auto-gen nav from @page objects, sidebar layout |
| 4.9 | Single-port multi-app Reflex routing | ✅ | `appos/ui/reflex_bridge.py` | Enhanced routing with site layout wrapping |
| 4.10 | Per-app theming | ✅ | `appos/ui/reflex_bridge.py` | Theme resolution + application via InterfaceRenderer + site layout |
| 4.11 | Inherited UI security from app.yaml | ✅ | `appos/security/permissions.py` | UISecurityResolver: 3-tier inheritance, validate_explicit_required |
| 4.12 | Form submission → Record save | ✅ | `appos/ui/renderer.py` | RecordFormState: validate → dispatch → save pipeline |

## Phase 5: External Layer — Task Breakdown

| # | Task | Status | Files | Notes |
|---|------|--------|-------|-------|
| 5.1 | @integration decorator | ✅ | `appos/decorators/core.py` | connected_system + log_payload params |
| 5.2 | Connected System resolution in integrations | ✅ | `appos/engine/integration_executor.py` | ConnectedSystemResolver: registry lookup → env overrides → auth headers → pooled config |
| 5.3 | Retry logic + backoff | ✅ | `appos/engine/integration_executor.py` | exponential/linear/fixed backoff, configurable count+delay, per-CS circuit breaker |
| 5.4 | @web_api decorator | ✅ | `appos/decorators/core.py` | method, path, auth, rate_limit, version |
| 5.5 | Web API async mode (returns instance_id) | ✅ | `appos/engine/api_executor.py` | Returns {instance_id, status, poll_url} for async=True. ⚠️ Full async needs Celery (3.10) |
| 5.6 | API route registration | ✅ | `appos/ui/reflex_bridge.py` | Uses Reflex app.api.add_api_route() — single port, /api/{app}/{ver}/{path} |
| 5.7 | API auth: service account flow | ✅ | `appos/engine/api_executor.py` | api_key → AuthService.authenticate_api_key() → service_account user → group perms |
| 5.8 | Rate limiting | ✅ | `appos/engine/api_executor.py` | RateLimiter: Redis DB 5, sliding window INCR+EXPIRE, graceful degrade on Redis fail |
| 5.9 | Document record + versioning | ✅ | `appos/documents/models.py` | Document + DocumentVersion Pydantic models, SHA-256 hashing, physical path helpers |
| 5.10 | Folder management | ✅ | `appos/documents/models.py` | Folder model with MIME validation, size limit checks, retention policy |
| 5.11 | rx.upload integration | ✅ | `appos/ui/components.py`, `appos/ui/renderer.py` | FileUploadDef ComponentDef + FileUploadState + DocumentService integration |
| 5.12 | @translation_set decorator | ✅ | `appos/decorators/core.py` | + .get() lang resolver, .ref() lazy refs |
| 5.13 | Language resolution (ctx.user.preferred_language) | ✅ | `appos/engine/context.py`, `appos/engine/namespaces.py` | get_preferred_language(), resolve_translation() + TranslationsNamespace with .get()/.ref() proxy |

## Phase 6: Polish — Task Breakdown

| # | Task | Status | Files | Notes |
|---|------|--------|-------|-------|
| 6.1 | Complete admin console (all screens) | ✅ | `appos/admin/` | 6 new pages + sidebar update, system_admin only |
| 6.2 | Admin Settings page (DB, YAML, cache) | ✅ | `appos/admin/pages/settings.py` | CRUD for PlatformConfigEntry, category filter |
| 6.3 | Admin Active Sessions + cache flush | ✅ | `appos/admin/pages/sessions.py` | Redis session scan, kill, permission/object cache flush |
| 6.4 | Admin Theme Editor per app | ✅ | `appos/admin/pages/themes.py` | Per-app color/font/radius editor, saves to App.theme JSON |
| 6.5 | Admin log viewer with filters | ✅ | `appos/admin/pages/logs.py` | JSONL file reader, type/category/search filters, pagination |
| 6.6 | Admin metrics dashboard | ✅ | `appos/admin/pages/metrics.py` | Aggregates performance JSONL, calls/avg/p95/errors per object |
| 6.7 | Admin worker management UI | ✅ | `appos/admin/pages/workers.py` | WorkerManager + pool_grow/shrink + autoscale + queue status |
| 6.8 | Platform rules implementation | ✅ | `appos/platform_rules/user_rules.py` | get_current_user, create_user, create_group, etc. |
| 6.9 | AI query interface | ✅ | `appos/engine/runtime.py` | query_for_ai() — deps, impact, status |
| 6.10 | Impact analysis → `appos impact` CLI | ✅ | `appos/cli.py` | Uses DependencyGraph.impact_analysis() |
| 6.11 | CLI: appos init | ✅ | `appos/cli.py` | DB bootstrap, admin user, groups, API key |
| 6.12 | CLI: appos new-app | ✅ | `appos/cli.py` | Scaffolds apps/{name}/ with 11 subdirs + app.yaml |
| 6.13 | CLI: appos generate | ✅ | `appos/cli.py` | Runs model/service/interface/audit/api/migration generators |
| 6.14 | CLI: appos migrate | ✅ | `appos/cli.py` | Generate migration or --apply pending migrations |
| 6.15 | CLI: appos run | ✅ | `appos/cli.py` | Wraps `reflex run` |
| 6.16 | CLI: appos check | ✅ | `appos/cli.py` | Syntax, imports, deps, permissions check + JSON report |
| 6.17 | CLI: appos impact {object_ref} | ✅ | `appos/cli.py` | (merged with 6.10) |
| 6.18 | Full test suite | ✅ | `tests/` | 17 unit-test files, 230+ tests, conftest fixtures, pyproject.toml |
| 6.19 | Documentation | ✅ | `docs/` | getting-started.md, api-reference.md, architecture.md |
| 6.20 | Audit log table generator | ✅ | `appos/generators/audit_generator.py` | AuditGenerator: discovers @record Meta.audit, generates SQLAlchemy model + SQL DDL |
| 6.21 | REST API generator | ✅ | `appos/generators/api_generator.py` | ApiGenerator: CRUD @web_api endpoints routing through api_executor.py pipeline |
| 6.22 | event_log table creation | ✅ | `appos/db/platform_models.py` | EventLog model (table #16): app_name, event_type, severity, payload, correlation_id |
| 6.23 | dependency_changes table | ✅ | `appos/db/platform_models.py` | DependencyChange model already exists (table #11) — added/removed/modified + hash tracking |
| 6.24 | JSON dependency persistence | ✅ | `appos/engine/dependency.py` | persist(), persist_all(), load() with JSON files |
| 6.25 | Log cleanup cron job | ✅ | `appos/engine/runtime.py` | cleanup_logs() — deletes JSONL files past retention (exec 90d, perf 30d, sec 365d) |
| 6.26 | ProcessInstance table partitioning | ✅ | `appos/engine/runtime.py` | create_monthly_partitions() — creates RANGE partitions for process_instances + step_log |
| 6.27 | Process instance archival | ✅ | `appos/engine/runtime.py` | archive_completed_instances() — sets status='archived' for completed > N days |
| 6.28 | Integration / E2E test suite | ✅ | `tests/integration/` | 7 workflow tests, 3 CLI E2E tests, integration conftest |
| 6.29 | YAML config parsing (appos.yaml + app.yaml) | ✅ | `appos/engine/config.py` | PlatformConfig + AppConfig Pydantic models |
| 6.30 | Row security rule (future) | ✅ | `appos/engine/security.py` | RowSecurityPolicy placeholder: register_policy(), apply_filter(), design docs |

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
| 2026-02-14 | Reflex app.api for Web APIs | Web API routes registered via Reflex's internal FastAPI router (app.api.add_api_route) — no separate server, single-port architecture per §12 |
| 2026-02-14 | httpx for outbound calls | IntegrationExecutor uses httpx.AsyncClient (connection pooled per Connected System) — not requests library |
| 2026-02-14 | API/Integration execution pipeline | Inbound: reflex_bridge → api_executor (auth→rate_limit→CSRF→dispatch). Outbound: runtime.dispatch → integration_executor (CS resolve→httpx→retry→circuit breaker) |
| 2026-02-14 | No separate FastAPI instance | Reflex already embeds FastAPI — adding a second would create port conflicts. All /api/* routes go through Reflex's router |
| 2026-02-14 | `"appOS"` schema for all platform DB objects | All 15 platform tables live in `"appOS"` schema (not `public`). Created via VS Code PostgreSQL extension at `localhost:5432/postgres`. Use this schema for all DB object creation and verification. |
| 2026-02-14 | Prod-ready DB scripts in `migrations/platform/scripts/` | 10 numbered SQL scripts (001-010) covering schema, tables, indexes, partitioning, bootstrap data, and platform config seed. Idempotent where possible. See `README.md` in that folder. |
| 2026-02-14 | Partitioned process tables (prod) | `process_instances` and `process_step_log` use `PARTITION BY RANGE (started_at)` with monthly partitions. Auto-partition function `create_next_month_partitions()` provided. Dev uses flat tables already created in `"appOS"` schema. |
| 2026-02-14 | ComponentDef intermediate representation | Components are dataclass definitions (not Reflex components) — InterfaceRenderer converts them to rx.Component at render time. Allows building interfaces without importing reflex at module level. |
| 2026-02-14 | InterfaceRenderer walks component tree | Recursive _render_node() handles ComponentDef, raw rx.Component (passthrough), str/int (wrap in text), list (fragment), callable (invoke), dict (translation ref). |
| 2026-02-14 | @interface.extend priority chain | Extensions are registered in InterfaceExtendRegistry, applied in registration order after base handler runs but before Reflex rendering. Each extension receives and must return the modified component tree. |
| 2026-02-14 | Auto-generated nav from @page objects | If no @site decorator exists for an app, reflex_bridge auto-generates navigation from all @page definitions (label from title, route from page route). |
| 2026-02-14 | Site layout sidebar | App pages wrapped in a fixed sidebar (240px) with navigation links from SiteConfig. Theme colors applied to sidebar and content area. |
| 2026-02-14 | UISecurityResolver 3-tier model | UI objects inherit from app.yaml security.defaults.ui.groups. Logic objects from security.defaults.logic.groups. Always-explicit types validated by appos check. |
| 2026-02-14 | RecordFormState save pipeline | Form on_submit → RecordFormState.handle_record_submit → runtime.dispatch(record, action=create/update) → success/error state update + optional redirect. |
| 2026-02-14 | Platform-level Document/Folder models | Document, DocumentVersion, Folder are Pydantic models in `appos/documents/` (not per-app records). DocumentService handles upload, versioning, folder creation, and cleanup. Physical files in `apps/{app}/runtime/documents/`. |
| 2026-02-14 | DocumentService per-app instantiation | Each app gets its own DocumentService instance with app-specific document root. Validates against both platform max_upload_size_mb and per-folder max_size_mb/document_types. |
| 2026-02-14 | FileUploadDef + FileUploadState | FileUpload is a new ComponentDef wrapping rx.upload. FileUploadState handles the async upload pipeline: validate MIME → check size → write file → create Document record. Supports multiple files, drag-and-drop, progress tracking. |
| 2026-02-14 | TranslationsNamespace with proxy | `translations.crm_labels.get("key")` syntax via TranslationsNamespace + TranslationSetProxy. Separate from raw `translation_sets` namespace. Proxy wraps handler with .get()/.ref()/.keys()/.languages(). |
| 2026-02-14 | resolve_translation() fallback chain | Full chain: preferred_language → "en" (mandatory) → key name as-is. Added to context.py alongside get_preferred_language() helper. Used by both @translation_set .get() and InterfaceRenderer for translation_ref dicts. |

---

## Database Schema Reference

> **Schema:** `"appOS"` on `localhost:5432/postgres`  
> **Access:** VS Code PostgreSQL extension (active connection, green indicator)  
> **Scripts:** `migrations/platform/scripts/` — run in numbered order (001→010)  
> **Use for:** All DB object creation, verification, ad-hoc queries, data inspection

All 15 platform tables + indexes + partitions + bootstrap data are defined as production-ready SQL scripts:

| Script | Tables / Objects |
|--------|------------------|
| `001_schema.sql` | `CREATE SCHEMA "appOS"` |
| `002_core_tables.sql` | `users`, `groups`, `apps`, `connected_systems` |
| `003_junction_tables.sql` | `user_groups`, `group_apps`, `connected_system_groups` |
| `004_security_tables.sql` | `object_permission`, `login_audit_log` |
| `005_process_tables.sql` | `process_instances` (partitioned), `process_step_log` (partitioned) |
| `006_supporting_tables.sql` | `dependency_changes`, `object_registry`, `platform_config`, `scheduled_tasks` |
| `007_indexes.sql` | All 65+ indexes across all tables |
| `008_partitions.sql` | Monthly partitions (2026-02 through 2026-12), archive tables, auto-partition function |
| `009_bootstrap_data.sql` | Admin user, system_admin/public_access groups, wildcard permission |
| `010_platform_config_seed.sql` | Default config: security, logging, process, database, documents, celery, UI |

**Current live state:** All 15 tables + 80 indexes exist in `"appOS"` schema (flat dev tables, not partitioned).

---

## File Quick Reference

| File | Purpose | Design Section |
|------|---------|---------------|
| `AppOS_Design.md` | Full architecture (read AI Index at L39-L145) | All |
| `appos/engine/api_executor.py` | Inbound Web API pipeline (auth, rate limit, CSRF, dispatch, response mapping) | §5.12, §6, §8 |
| `appos/engine/integration_executor.py` | Outbound integration pipeline (CS resolve, httpx, retry, circuit breaker) | §5.5, §5.11, §8 |
| `appos/ui/components.py` | Component library: 12 ComponentDef dataclasses + constructor functions | §12 UI Layer |
| `appos/ui/renderer.py` | InterfaceRenderer: ComponentDef → rx.Component tree + RecordFormState | §12, §9 |
| `appos/ui/reflex_bridge.py` | Single-port Reflex wrapper (admin, app pages, APIs, site nav, themes) | §12 |
| `appos/generators/interface_generator.py` | Auto-gen List/Create/Edit/View interfaces from @record | §9 |
| `appos/decorators/interface.py` | @interface.extend override mechanism + InterfaceExtendRegistry | §9, §5.13 |
| `appos/security/permissions.py` | UISecurityResolver: 3-tier inherited security from app.yaml | §6 Security |
| `appos/documents/models.py` | Document, DocumentVersion, Folder Pydantic models | §5.16, §5.17 |
| `appos/documents/service.py` | DocumentService: upload, versioning, folder mgmt, cleanup | §5.16, §5.17 |
| `AppOS_TaskPlan.md` | This file — task tracking + decisions | — |
| `AppOS_Permissions_Reference.md` | Unified permissions, three-tier security, user types, error hierarchy | §6 Security |
| `AppOS_Logging_Reference.md` | Per-type log folders, entry formats, async pipeline, rotation | §14 Logging |
| `AppOS_PlatformRules_Reference.md` | Prebuilt user/group management rules | §5.8 Rules |
| `AppOS_UI_Reference.md` | Interface architecture: render pipeline, components, @interface.extend, auto-gen, site nav, theming, security | §12 UI Layer |
| `AppOS_Email_Reference.md` | Outlook email integration (send/receive) | — |
| `AppOS_Shutdown_Reference.md` | Graceful shutdown procedure | — |
| `AppOS_Monitoring_Reference.md` | Health endpoints (/health, /ready) | — |
| `AppOS_Backup_Reference.md` | Backup and restore strategy | — |
| `AppOS_CICD_Reference.md` | CI/CD and environment promotion | — |
| `Reflex_Notes.md` | Reflex framework patterns + best practices | §12 UI Layer |
| `AppOS_Design_v1_backup.md` | Archived v1 design | — |
| `migrations/platform/scripts/` | Production-ready DB scripts (001-010) for `"appOS"` schema | §2 DB Design |
| `migrations/platform/scripts/README.md` | DB scripts execution order + environment notes | §2 DB Design |

---

*Last updated: February 14, 2026*
