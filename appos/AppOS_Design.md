# AppOS — Python Low-Code Platform Design Document

> **Version:** 2.1  
> **Date:** February 12, 2026  
> **Previous Version:** 2.0 (February 7, 2026) → 1.0 (January 25, 2026, archived as `AppOS_Design_v1_backup.md`)  
> **Goal:** Accelerate Python application development by 50%+ through zero-import architecture, auto-generation, centralized runtime engine with pre-recorded logs/metrics, and AI-native debugging.  
> **Reference Docs:** `AppOS_Permissions_Reference.md`, `AppOS_Logging_Reference.md`, `AppOS_PlatformRules_Reference.md`, `AppOS_Email_Reference.md`, `AppOS_Shutdown_Reference.md`, `AppOS_Monitoring_Reference.md`, `AppOS_Backup_Reference.md`, `AppOS_CICD_Reference.md`

---

## Table of Contents

1. [Philosophy & Goals](#1-philosophy--goals)
2. [Architecture Overview](#2-architecture-overview)
3. [Technology Stack](#3-technology-stack)
4. [Auto-Import & Zero-Import System](#4-auto-import--zero-import-system)
5. [Core Object Types](#5-core-object-types)
6. [Security Model](#6-security-model)
7. [State Management](#7-state-management)
8. [Centralized Runtime Engine](#8-centralized-runtime-engine)
9. [Record System & Auto-Generation](#9-record-system--auto-generation)
10. [Dependency Management & AI Integration](#10-dependency-management--ai-integration)
11. [Process Engine](#11-process-engine)
12. [UI Layer — Reflex Integration](#12-ui-layer--reflex-integration)
13. [Admin Console](#13-admin-console)
14. [Logging & Metrics Strategy](#14-logging--metrics-strategy)
15. [Multi-App Project Structure](#15-multi-app-project-structure)
16. [Configuration](#16-configuration)
17. [Implementation Phases](#17-implementation-phases)

---

<!-- ===========================================================================
     AI CONTEXT INDEX — Machine-readable section map for minimal-context navigation.
     Read ONLY this block to locate any section. Use line ranges with read_file.
     Last updated: 2026-02-12 | Total lines: ~3640
     =========================================================================== -->

## AI Context Index

> **How to use:** Read this index first (lines 39–145). Then `read_file` only the line range you need. Each entry shows `[L{start}-L{end}]` for the line range of that section.
> **Reference Docs:** `AppOS_Permissions_Reference.md`, `AppOS_Logging_Reference.md`, `AppOS_PlatformRules_Reference.md`, `AppOS_Email_Reference.md`, `AppOS_Shutdown_Reference.md`, `AppOS_Monitoring_Reference.md`, `AppOS_Backup_Reference.md`, `AppOS_CICD_Reference.md`

### Document Map

```
SECTION                                          LINES         KEY CONTENT
─────────────────────────────────────────────────────────────────────────────
1.  Philosophy & Goals                           L151-L222     Principles, what AppOS provides
2.  Architecture Overview                        L224-L318     High-level diagram, request flow
3.  Technology Stack                             L320-L336     Tech table (Postgres, Redis, Celery, Reflex, etc.)
4.  Auto-Import & Zero-Import System             L338-L471     SecureAutoImportNamespace, cross-app prefix, process namespace, async logging
5.  Core Object Types                            L473-L1577    ALL 17 object types (see sub-index below)
6.  Security Model                               L1579-L1821   Unified 6-perm model, three-tier inherited security, wildcards, public_access, session auth
7.  State Management                             L1823-L1921   Four-state model, ExecutionContext, ProcessContext (ctx.var)
8.  Centralized Runtime Engine                   L1923-L2216   Runtime class, engine.dispatch(), per-type loggers, async queue, AppOSError hierarchy, platform rules
9.  Record System & Auto-Generation              L2218-L2337   Pipeline (+ audit_log), Pydantic→SQLAlchemy, generated models/services/UIs
10. Dependency Management & AI Integration       L2339-L2517   Auto-tracking, dependency_changes table, AI query, appos impact CLI
11. Process Engine                               L2519-L2764   ProcessInstance (partitioned), process_step_log table, parallel(), fire_and_forget, Celery
12. UI Layer — Reflex Integration                L2766-L2896   Single-port routing, component=function, raw Reflex passthrough, Page→Interface→Component
13. Admin Console                                L2898-L3108   Screens + Settings + Sessions + Theme editor, system_admin only
14. Logging & Metrics Strategy                   L3109-L3269   Per-object-type log folders with execution/performance/security sub-folders, async queue, payload opt-in
15. Multi-App Project Structure                  L3271-L3499   Full folder tree, platform_rules/ folder, naming conventions
16. Configuration                                L3501-L3637   appos.yaml (pool, session, per-category log retention, process archive), app.yaml (security defaults)
17. Implementation Phases                        L3639-L3906   6 phases (weeks 1-20), deliverables per phase
    Quick Reference Card                         L3908-L4076   All decorators/syntax, permission tiers, error hierarchy, CLI commands, log structure
    Summary                                      L4078-L4101   13-point summary
```

### Object Type Sub-Index (Section 5)

```
OBJECT TYPE              LINES         SCOPE       DECORATOR/DEFINITION
─────────────────────────────────────────────────────────────────────────────
5.1  Object Taxonomy     L475-L521     —           Overview diagram of all 17 types + log categories
5.2  User                L522-L555     Platform    DB model (user_type: basic/system_admin/service_account)
5.3  Group               L556-L584     Platform    DB model (unified permissions, default groups, public_access)
5.4  App                 L585-L631     Platform    app.yaml config + security.defaults
5.5  Connected System    L632-L714     Global      @connected_system — DB, API, FTP, SMTP, IMAP (pool config + pool_reset_on_return + multi-engine)
5.6  Constant            L715-L802     Per-App     @constant — primitives, obj refs, env overrides, unified dispatch, log refs
5.7  Record (Data Model) L803-L890     Per-App     @record + Pydantic BaseModel, audit_log, row_security_rule, view permissions
5.8  Expression Rule     L891-L968     Per-App     @expression_rule — all logic + queries + platform rules ref, log refs
5.9  Step                L969-L1018    Per-App     step() — process step + fire_and_forget tracking, log refs
5.10 Process             L1019-L1114   Per-App     @process — display_name, parallel(), orchestrator, log refs
5.11 Integration         L1115-L1180   Per-App     @integration — outbound API calls + log_payload, log refs
5.12 Web API             L1181-L1252   Per-App     @web_api — REST endpoints + service account auth + async mode, log refs
5.13 Interface           L1253-L1309   Per-App     @interface — UI components (inherited security, raw Reflex), log refs
5.14 Page                L1310-L1360   Per-App     @page — Reflex routable page (inherited security), log refs
5.15 Site                L1361-L1389   Per-App     @site — collection of pages
5.16 Document            L1390-L1466   Per-App     @record — file/artifact with versioning, MIME validation, log refs
5.17 Folder              L1467-L1515   Per-App     @record — runtime folder management, auto_cleanup, log refs
5.18 Translation Set     L1516-L1577   Per-App     @translation_set — i18n + ctx.user.preferred_language + explicit lang override, log refs
```

### Cross-Reference: Key Concepts by Topic

```
TOPIC                          PRIMARY SECTION    ALSO SEE
─────────────────────────────────────────────────────────────────────────────
Zero-import / auto-import      §4 (L338)          §8 Runtime Engine (L1923)
Cross-app access (prefix)      §4 (L431)          §5.4 App (L585)
Security / permissions         §6 (L1579)         §5.2 User (L522), §5.3 Group (L556), Permissions Ref
Wildcard permissions           §6 (L1616)         Permissions Ref (object_permission table)
Public access pattern          §6 (L1776)         §5.3 Group (L556, public_access group)
Session authentication         §6 (L1790)         §16 security config (L3501)
Process variables (ctx.var)    §7 (L1879)         §5.10 Process (L1019), §11 (L2519)
Variable visibility            §5.10 (L1105)      §11 Process History (L2738)
Logging (per-type folders)     §14 (L3109)        §8 AsyncLogQueue (L1923), Logging Ref
Logging (app → DB)             §14 (L3109)        §16 app.yaml config (L3589)
Log categories (exec/perf/sec) §14 (L3111)        §16 retention config (L3561)
AI debugging / queries         §10 (L2339)        §8 query_for_ai (L2061)
Record auto-generation         §9 (L2218)         §5.7 Record (L803)
Audit log (per record)         §9 (L2248)         §5.7 Record Meta.audit (L803)
Error hierarchy                §8 (L2127)         Quick Reference Card (L3908)
Platform rules                 §8 (L2166)         §15 (L3271), PlatformRules Ref
Reflex integration             §12 (L2766)        §5.14 Page (L1310), §5.15 Site (L1361)
Admin console screens          §13 (L2898)        §6 Security (L1579), §14 Logging (L3109)
Connected System + creds       §5.5 (L632)        §13 Admin UI (L2926)
Process execution (Celery)     §11 (L2519)        §5.9 Step (L969), §5.10 Process (L1019)
Process partitioning           §11 (L2570)        §16 process_instances config (L3571)
Worker management / scaling    §13 (L3012)        §16 celery config (L3501)
Folder structure               §15 (L3271)        §16 Configuration (L3501)
Unified dispatch (engine)      §8 (L2067)         §5.6 Constant obj refs (L715), §11 Process (L2519)
Payload opt-in                 §14 (L3258)        §5.11 Integration (L1115), §5.12 Web API (L1181)
```

### Quick Lookup: Decorators

```
@constant                → §5.6  (L715)
@record                  → §5.7  (L803)
@expression_rule         → §5.8  (L891)
step()                   → §5.9  (L969)
@process                 → §5.10 (L1019)
@connected_system        → §5.5  (L632)
@integration             → §5.11 (L1115)
@web_api                 → §5.12 (L1181)
@interface               → §5.13 (L1253)
@page                    → §5.14 (L1310)
@site                    → §5.15 (L1361)
@translation_set         → §5.18 (L1516)
engine.dispatch()        → §8    (L2067)   ← unified dispatcher for object refs
processes.X.start()      → §4    (L449)    ← zero-import process start
platform.rules.*         → §8    (L2166)   ← prebuilt platform rules
```

<!-- =========================================================================== -->

---

## 1. Philosophy & Goals

### Core Principles

| Principle | Description |
|-----------|-------------|
| **Python-First** | Everything is Python. Decorators + type hints + Pydantic. No custom DSL. |
| **Zero-Import DX** | Developers never write `import` statements. Auto-import layer resolves all object access. |
| **Security-First Execution** | Every object access is security-checked against logged-in user's groups. No bypass. |
| **AI-Native Debugging** | Pre-recorded logs, metrics, and dependency graphs make AI debugging intuitive and low-context. |
| **Convention over Configuration** | Sensible defaults, override when needed. Naming prefix convention (app shorthand) recommended but not mandatory. |
| **Auto-Generate, Allow Override** | Generate CRUD, UI, migrations, APIs. Developer can customize or replace. |
| **Multi-App, Shared Infrastructure** | Multiple apps run on shared users/groups. App-level isolation through group association. |
| **Stateless Objects, Stateful Execution** | Objects are pure definitions. State lives in execution context or process scope. |

### What AppOS Provides

```
┌─────────────────────────────────────────────────────────────────┐
│                      DEVELOPER WRITES                           │
├─────────────────────────────────────────────────────────────────┤
│  NO IMPORTS — just use objects directly:                        │
│                                                                 │
│  @expression_rule                                               │
│  def calculate_discount(ctx):                                   │
│      customer = records.customer.get(ctx.input("id"))           │
│      rate = constants.TAX_RATE()                                │
│      ...                                                        │
│                                                                 │
│  @process                                                       │
│  def onboard_customer():                                        │
│      return [                                                   │
│          step("validate", rule="validate_customer"),            │
│          step("setup",    rule="create_account"),               │
│      ]                                                          │
└─────────────────────────────────────────────────────────────────┘
                                 │
                                 ▼
┌─────────────────────────────────────────────────────────────────┐
│               APPOS AUTO-IMPORT LAYER (INTERCEPTS)              │
├─────────────────────────────────────────────────────────────────┤
│  ✓ Lazy-loads modules on access                                 │
│  ✓ Checks security (user groups ↔ object permissions)          │
│  ✓ Logs every dependency access                                 │
│  ✓ Tracks execution context (who, when, from where)            │
│  ✓ Builds dependency graph automatically                        │
└─────────────────────────────────────────────────────────────────┘
                                 │
                                 ▼
┌─────────────────────────────────────────────────────────────────┐
│                  APPOS AUTO-GENERATES                            │
├─────────────────────────────────────────────────────────────────┤
│  • SQLAlchemy models       • Alembic migrations                 │
│  • CRUD services           • REST API endpoints                 │
│  • Reflex UI (list/create/ • Audit hooks                        │
│    edit/view)              • Process task queues                 │
│  • Validation rules        • Relationship handling              │
└─────────────────────────────────────────────────────────────────┘
                                 │
                                 ▼
┌─────────────────────────────────────────────────────────────────┐
│                CENTRALIZED RUNTIME ENGINE                        │
├─────────────────────────────────────────────────────────────────┤
│  ✓ Dependency graph (auto-built, AI-queryable)                  │
│  ✓ Execution logs (every rule, step, process logged)            │
│  ✓ Security audit trail (every access check recorded)           │
│  ✓ Performance metrics (timing, counts, trends)                 │
│  ✓ AI query interface (structured data for debugging)           │
└─────────────────────────────────────────────────────────────────┘
```

---

## 2. Architecture Overview

### High-Level Architecture

```
┌──────────────────────────────────────────────────────────────────────────┐
│                           APPOS PLATFORM                                 │
├──────────────────────────────────────────────────────────────────────────┤
│                                                                          │
│  ┌──────────────────────────────────────────────────────┐                │
│  │              ADMIN CONSOLE (Reflex)                   │                │
│  │  Login │ Users │ Groups │ Apps │ Logs │ Metrics       │                │
│  └──────────────────────┬───────────────────────────────┘                │
│                          │                                                │
│  ┌──────────────────────┴───────────────────────────────┐                │
│  │            MULTI-APP LAYER (Reflex Router)            │                │
│  │  /admin/* │ /crm/* │ /finance/* │ /api/*              │                │
│  └──────────────────────┬───────────────────────────────┘                │
│                          │                                                │
│  ┌──────────────────────┴───────────────────────────────┐                │
│  │             AUTO-IMPORT LAYER (Zero-Import)           │                │
│  │  ✓ Intercepts all object access                       │                │
│  │  ✓ Security check → Dependency log → Lazy load        │                │
│  └──────────────────────┬───────────────────────────────┘                │
│                          │                                                │
│  ┌──────────────────────┴───────────────────────────────┐                │
│  │               OBJECT REGISTRY                         │                │
│  ├───────┬───────┬───────┬───────┬───────┬──────────────┤                │
│  │Record │Rule   │Step   │Process│Const  │Connected Sys │                │
│  │Page   │Site   │Integ  │WebAPI │Doc    │Translation   │                │
│  │Folder │Interf │       │       │       │              │                │
│  └──────────────────────┬───────────────────────────────┘                │
│                          │                                                │
│  ┌──────────────────────┴───────────────────────────────┐                │
│  │           CENTRALIZED RUNTIME ENGINE                   │                │
│  ├───────────────┬────────────────┬─────────────────────┤                │
│  │ Dependency    │ Execution      │ Security            │                │
│  │ Graph         │ Logger         │ Auditor             │                │
│  │ (NetworkX)    │ (File-based)   │ (File-based)        │                │
│  ├───────────────┼────────────────┼─────────────────────┤                │
│  │ Performance   │ AI Query       │ Permission          │                │
│  │ Collector     │ Interface      │ Cache (Redis)       │                │
│  └──────────────────────┬───────────────────────────────┘                │
│                          │                                                │
│  ┌──────────────────────┴───────────────────────────────┐                │
│  │                 INFRASTRUCTURE                         │                │
│  ├─────────────┬─────────────┬─────────────┬────────────┤                │
│  │ PostgreSQL  │ Redis       │ Celery      │ Reflex     │                │
│  │ (Data)      │ (Cache +    │ (Async      │ (UI)       │                │
│  │             │  Broker)    │  Tasks)     │            │                │
│  └─────────────┴─────────────┴─────────────┴────────────┘                │
│                                                                          │
└──────────────────────────────────────────────────────────────────────────┘
```

### Request Flow

```
User Login
    │
    ▼
┌──────────────┐
│ Auth Layer   │──► Session created with user_id, groups, lang, timezone
└──────┬───────┘
       │
       ▼
┌──────────────┐
│ Execution    │──► Thread-safe context: user, groups, execution_id, app
│ Context Set  │
└──────┬───────┘
       │
       ▼
┌──────────────┐    ┌──────────────┐    ┌──────────────┐
│ Developer    │───►│ Auto-Import  │───►│ Object       │
│ Code Runs    │    │ Intercepts   │    │ Resolved     │
└──────────────┘    └──────┬───────┘    └──────────────┘
                           │
                    ┌──────┴───────┐
                    │ For EVERY    │
                    │ access:      │
                    │              │
                    │ 1. Security  │──► DENY → log violation, raise error
                    │    Check     │──► ALLOW → continue
                    │              │
                    │ 2. Log       │──► Dependency graph updated
                    │    Access    │──► Caller → Object edge recorded
                    │              │
                    │ 3. Load &    │──► Module cached after first load
                    │    Cache     │
                    │              │
                    │ 4. Return    │──► Object returned to caller
                    └──────────────┘
```

---

## 3. Technology Stack

| Layer | Technology | Purpose |
|-------|------------|---------|
| **Database** | PostgreSQL | Primary data store (app data + platform tables) |
| **ORM** | SQLAlchemy 2.0 | Record → Table mapping (auto-generated from Pydantic) |
| **Validation** | Pydantic v2 | Record/Data Model definitions, request validation |
| **Migrations** | Alembic | Auto-generated from Records |
| **Task Queue** | Celery + Redis | Process execution, scheduled tasks |
| **Cache** | Redis | Permission cache, object cache, session store |
| **UI Framework** | Reflex | All UI — admin console, app pages, CRUD interfaces |
| **Dependency Graph** | NetworkX | In-memory graph for fast traversal + JSON persistence |
| **State** | Python `contextvars` | Thread-safe execution context |
| **Logging** | Structured JSON files | System logs (access, security, performance, dependencies) |
| **Secrets** | Admin-managed (encrypted DB) | Connected System credentials |

---

## 4. Auto-Import & Zero-Import System

### The Core Innovation

Developers **never write import statements**. All AppOS objects (records, constants, rules, etc.) are available through globally-injected namespaces that the engine intercepts.

```python
# ─── TRADITIONAL PYTHON ───
from app.rules.pricing import calculate_discount
from app.constants.config import TAX_RATE
from app.models.customer import Customer

result = calculate_discount(customer_id=123)

# ─── APPOS (Zero-Import) ───
@expression_rule
def calculate_total(ctx):
    customer = records.customer.get(ctx.input("id"))     # Auto-resolved
    rate = constants.TAX_RATE()                           # Auto-resolved
    discount = rules.calculate_discount(customer_id=123)  # Auto-resolved
    # Security checked, dependency logged, performance tracked — automatically
```

### SecureAutoImportNamespace

```python
class SecureAutoImportNamespace:
    """
    Intercepts attribute access on global namespaces (records, constants, rules, etc.).
    On every access:
      1. Checks execution context for current user/groups
      2. Validates permissions against security policy
      3. Logs the dependency access (caller → target)
      4. Lazy-loads and caches the resolved module
    """

    def __init__(self, base_path: str, package_name: str, security_policy):
        self.base_path = Path(base_path)
        self.package_name = package_name
        self.security_policy = security_policy
        self._cache = {}
        self._access_log = []

    def __getattr__(self, name: str) -> Any:
        module_path = f"{self.package_name}.{name}"

        # 1. SECURITY CHECK
        context = current_execution_context.get()
        if context:
            if not self.security_policy.check_access(
                user_groups=context.user_groups,
                module_path=module_path,
                permission="view"
            ):
                self._log_access(module_path, context, status="DENIED")
                raise AppOSSecurityError(
                    f"Access denied: {context.user_id} → {module_path}",
                    user_id=context.user_id,
                    object_ref=module_path,
                    user_groups=context.user_groups,
                )

        # 2. DEPENDENCY TRACKING
        caller = inspect.currentframe().f_back
        caller_info = {
            'file': caller.f_code.co_filename,
            'function': caller.f_code.co_name,
            'line': caller.f_lineno,
        }

        # 3. LOGGING
        self._log_access(module_path, context, caller_info, status="ALLOWED")

        # 4. LAZY LOAD + CACHE
        if name not in self._cache:
            self._cache[name] = importlib.import_module(module_path)
        return self._cache[name]
```

### Global Namespace Registration

```python
# appos/engine/namespaces.py — injected into every app's execution scope

records    = SecureAutoImportNamespace("app/records",    "app.records",    security_policy)
constants  = SecureAutoImportNamespace("app/constants",  "app.constants",  security_policy)
rules      = SecureAutoImportNamespace("app/rules",      "app.rules",      security_policy)
processes  = SecureAutoImportNamespace("app/processes",  "app.processes",  security_policy)
integrations = SecureAutoImportNamespace("app/integrations", "app.integrations", security_policy)
web_apis   = SecureAutoImportNamespace("app/web_apis",   "app.web_apis",   security_policy)
translations = SecureAutoImportNamespace("app/translations", "app.translations", security_policy)
```

### Multi-App Resolution (Zero-Config Cross-App Access)

When a developer in the CRM app accesses `records.customer`, the engine resolves:
1. Check current app context → `crm`
2. Resolve path → `apps/crm/records/customer.py`
3. Security check → does user's group have access to `crm.records.customer`?
4. Log → `crm.records.customer` accessed by `rules.calculate_discount` in `crm`

**Cross-app access** — the app prefix IS the declaration. No imports, no `from_app()`:
```python
# From CRM app, accessing Finance objects — prefix auto-detected
total = finance.rules.calculate_tax(amount=100)    # → apps/finance/rules/...
rate = finance.constants.FISCAL_YEAR_START()        # → apps/finance/constants/...
shared.records.user.get(user_id)                    # → apps/shared/records/...
```

The auto-import layer detects the app prefix, resolves it, security-checks, and logs — all transparently.

### Process Namespace

Processes are globally startable via the `processes` namespace without import:
```python
# Start a process from anywhere — zero import
instance = processes.onboard_customer.start(inputs={"customer_id": 123})

# Cross-app process start
instance = finance.processes.monthly_close.start(inputs={"month": "2026-02"})
```

### Auto-Import Performance: Non-Blocking Logging

The auto-import layer blocks **only** on the security check. All other operations are async:
```
Object Access → [BLOCKING] Security Check (Redis cache → DB fallback)
             → [NON-BLOCKING] Push to in-memory log queue (dependency, execution, performance)
             → Background flush thread writes to log files (every 100ms or 50 entries)
```

Security denial raises `AppOSSecurityError` with full context (user, groups, object_ref, dependency chain). See `AppOS_Permissions_Reference.md` for error format.

---

## 5. Core Object Types

### 5.1 Object Taxonomy

```
┌──────────────────────────────────────────────────────────────────────┐
│                     PLATFORM OBJECTS (Global)                        │
├──────────────────────────────────────────────────────────────────────┤
│  User              │  Authentication, profile, language preference   │
│   ├─ basic         │  Standard user, can login to UI                │
│   ├─ system_admin  │  Full platform access, admin console           │
│   └─ service_acct  │  API-only (no UI login), API key/OAuth auth    │
│  Group             │  Access control unit, associated with apps      │
│  App               │  Container for all app-level objects            │
│  Connected System  │  External connections (DB, API, FTP, SMTP/IMAP)│
│                    │  GLOBAL scope — not app-bound                   │
└──────────────────────────────────────────────────────────────────────┘

┌──────────────────────────────────────────────────────────────────────┐
│                       APP OBJECTS (Per-App)                           │
├──────────────────────────────────────────────────────────────────────┤
│  DATA LAYER                                                          │
│  ├─ Constant          │  Static values, object refs, env overrides   │
│  ├─ Record            │  Pydantic data models → auto-gen everything  │
│  ├─ Document          │  File/artifact management with versioning    │
│  └─ Folder            │  Dynamic runtime folder management           │
│                                                                      │
│  LOGIC LAYER                                                         │
│  ├─ Expression Rule   │  Modular functions (queries, logic, etc.)    │
│  ├─ Step              │  Process step wrapping a rule                │
│  └─ Process           │  Multi-step orchestrator (workflow)          │
│                                                                      │
│  EXTERNAL LAYER                                                      │
│  ├─ Integration       │  Outbound API calls (uses Connected System)  │
│  └─ Web API           │  Expose functions as REST endpoints          │
│                                                                      │
│  UI LAYER                                                            │
│  ├─ Interface         │  UI components (DataTable, Form, etc.)       │
│  ├─ Page              │  Reflex page with route and state            │
│  ├─ Site              │  Collection of pages (Reflex app wrapper)    │
│  └─ Translation Set   │  i18n labels per app                         │
│                                                                      │
│  LOG CATEGORIES (per object type — sub-folders):                     │
│  ├─ execution/   │  What ran, inputs/outputs, status, errors         │
│  ├─ performance/ │  Duration, timing metrics                         │
│  └─ security/    │  Permission checks, allow/deny decisions          │
└──────────────────────────────────────────────────────────────────────┘
```

### 5.2 User

**Scope:** Platform-global. Stored in core AppOS database.

| Property | Type | Description |
|----------|------|-------------|
| `id` | int | Auto-generated primary key |
| `username` | str | Unique login name |
| `email` | str | Unique email |
| `password_hash` | str | Bcrypt hashed password |
| `full_name` | str | Display name |
| `is_active` | bool | Account enabled/disabled |
| `user_type` | str | `"basic"` / `"system_admin"` / `"service_account"` |
| `preferred_language` | str | For Translation Set resolution (e.g., "en", "fr") |
| `timezone` | str | User's timezone (e.g., "America/New_York") |
| `last_login` | datetime | Last successful login timestamp |
| `groups` | List[Group] | Many-to-many relationship |

```python
# Managed via Admin Console — not defined by developers.
# Login flow:
#   1. User authenticates via /admin/login
#   2. Session created (Redis) with user_id, groups, language, timezone
#   3. ExecutionContext set for all subsequent requests
#   4. Every object access checked against user's groups
#
# User types:
#   - basic: Standard user, can login
#   - system_admin: Full platform access, admin console
#   - service_account: API-only (no UI login), authenticates via API key/OAuth
#
# See AppOS_Permissions_Reference.md for full user type matrix.
```

### 5.3 Group

**Scope:** Platform-global. Core unit of access control.

| Property | Type | Description |
|----------|------|-------------|
| `id` | int | Auto-generated primary key |
| `name` | str | Unique group name (e.g., "sales", "finance_admins") |
| `type` | str | "security" / "team" / "app" |
| `description` | str | Human-readable description |
| `is_active` | bool | Group enabled/disabled |
| `users` | List[User] | Many-to-many relationship |
| `apps` | List[App] | Which apps this group can access |

```python
# Group Security — Unified 6-Permission Model:
#
# Groups are associated with:
#   1. Apps — which apps the group members can access
#   2. Objects — permissions via object_permission table (view/use/create/update/delete/admin)
#
# Default groups (bootstrapped on appos init):
#   - system_admin: Full platform access, admin console, user/group management
#   - public_access: For unauthenticated Web API access (service account pattern)
#
# See AppOS_Permissions_Reference.md for full permission model, applicability matrix,
# three-tier inherited security, and object_permission table schema.
```

### 5.4 App

**Scope:** Platform-level container. Each app groups its objects and has its own URL prefix.

| Property | Type | Description |
|----------|------|-------------|
| `name` | str | Full name (e.g., "Customer Relationship Manager") |
| `short_name` | str | URL prefix and naming convention (e.g., "crm") |
| `description` | str | App description |
| `is_active` | bool | App enabled/disabled |
| `version` | str | App version |
| `groups` | List[Group] | Groups that can access this app |
| `theme` | dict | Reflex theme configuration for this app |
| `environment` | str | Current environment: "dev" / "staging" / "prod" |
| `db_connected_system` | str | Convenience pointer to Connected System for this app's DB (not binding) |

```python
# apps/crm/app.yaml
app:
  name: "Customer Relationship Manager"
  short_name: "crm"
  version: "1.0.0"
  description: "CRM application for sales and support teams"
  groups: ["sales", "support", "crm_admins"]
  db_connected_system: "crm_database"   # convenience pointer, not binding
  theme:
    primary_color: "#3B82F6"
    font_family: "Inter"
  environment: "dev"

  # Three-tier inherited security defaults
  security:
    defaults:
      logic:     # inherited by: rules, constants
        groups: ["sales", "support", "crm_admins"]
      ui:        # inherited by: interfaces, pages, translation_sets
        groups: ["sales", "support", "crm_admins"]
  # Records, processes, web_apis, integrations, connected_systems → always explicit
```

**URL Routing:** Single Reflex instance routes by app prefix:
- `/admin/*` → Admin Console (built-in)
- `/crm/*` → CRM app pages
- `/finance/*` → Finance app pages
- `/api/crm/*` → CRM Web APIs
- `/api/finance/*` → Finance Web APIs

### 5.5 Connected System

**Scope:** Global only — NOT app-specific. Secured via groups. Any app can reference any connected system the user's group has access to.

**Merged with Data Store** — the `type` property distinguishes DB connections from API/FTP/SMTP/IMAP.

**Multi-engine support:** Each Connected System of `type="database"` registers its own SQLAlchemy engine in the platform engine registry. The runtime resolves `db_connected_system` from `app.yaml` to the correct engine at startup. Multiple apps can share the same Connected System, or each can point to a dedicated database. Engine lifecycle (pool creation, disposal, health checks) is managed centrally by the platform.

| Property | Type | Description |
|----------|------|-------------|
| `name` | str | Unique identifier (e.g., "crm_database", "stripe_api") |
| `type` | str | "database" / "rest_api" / "ftp" / "smtp" / "imap" / "custom" |
| `description` | str | Human-readable description |
| `is_active` | bool | Connection enabled/disabled |
| `connection_details` | dict | Host, port, path, base_url, etc. |
| `auth_type` | str | "none" / "basic" / "oauth2" / "api_key" / "certificate" |
| `credentials` | dict | Encrypted: username, password, api_key, client_id, etc. |
| `environment_overrides` | dict | Per-environment connection details |
| `health_check` | dict | Health check config (endpoint, interval, timeout) |
| `groups` | List[str] | Which groups can use this connection |

```python
# Managed via Admin Console — credentials encrypted at rest.
# Environment-specific overrides:

@connected_system(
    name="crm_database",
    type="database",
    description="CRM PostgreSQL database"
)
def crm_database():
    return {
        "default": {
            "driver": "postgresql",
            "host": "localhost",
            "port": 5432,
            "database": "crm_dev",
            "pool_size": 10,
            "max_overflow": 20,
            "pool_timeout": 30,
            "pool_recycle": 1800,
            "pool_pre_ping": True,
            "pool_reset_on_return": "rollback",  # clean state on return to pool
        },
        "auth": {
            "type": "basic",
            # credentials managed in admin console, not in code
        },
        "environment_overrides": {
            "staging": {"host": "staging-db.internal", "database": "crm_staging"},
            "prod": {"host": "prod-db.internal", "database": "crm_prod", "pool_size": 50},
        },
        "health_check": {
            "enabled": True,
            "interval_seconds": 60,
        }
    }


@connected_system(
    name="stripe_api",
    type="rest_api",
    description="Stripe payment gateway"
)
def stripe_api():
    return {
        "default": {
            "base_url": "https://api.stripe.com/v1",
            "timeout": 30,
        },
        "auth": {
            "type": "api_key",
            "header": "Authorization",
            "prefix": "Bearer",
            # api_key managed in admin console
        },
        "environment_overrides": {
            "dev": {"base_url": "https://api.stripe.com/v1", "use_test_key": True},
            "prod": {"base_url": "https://api.stripe.com/v1", "use_test_key": False},
        }
    }
```

### 5.6 Constant

**Scope:** Per-app. Supports primitive values, object references, and environment overrides.

| Property | Type | Description |
|----------|------|-------------|
| `name` | str | Constant name (prefix convention: `CRM_TAX_RATE`) |
| `type` | str | "string" / "int" / "float" / "bool" / "object_ref" |
| `value` | Any | The constant value |
| `description` | str | Documentation |
| `validate` | callable | Optional validation function |
| `environment_overrides` | dict | Per-env values |
| `groups` | List[str] | Access permissions |

```python
# Primitive constant with environment overrides
@constant
def TAX_RATE() -> float:
    """Standard tax rate for calculations."""
    return {
        "default": 0.18,
        "dev": 0.0,       # No tax in dev
        "staging": 0.18,
        "prod": 0.18,
    }


# Object reference constant — points to an expression rule (dynamic dispatch)
@constant
def DEFAULT_VALIDATION_RULE() -> str:
    """Points to the expression rule used for customer validation.
    Can be changed via admin console without code deployment."""
    return {
        "default": "crm.rules.validate_customer_v2",
        "dev": "crm.rules.validate_customer_simple",  # Simpler in dev
        "prod": "crm.rules.validate_customer_v2",
    }


# Object reference constant — points to a process (dynamic dispatch)
@constant
def DEFAULT_ONBOARDING_PROCESS() -> str:
    """Points to the process used for customer onboarding.
    Swappable per environment — simpler flow in dev, full flow in prod."""
    return {
        "default": "crm.processes.onboard_customer",
        "dev": "crm.processes.onboard_customer_simple",
        "prod": "crm.processes.onboard_customer",
    }


# Usage in rules — engine.dispatch() handles both rules and processes:
@expression_rule
def process_order(ctx):
    rate = constants.TAX_RATE()  # Resolves to env-appropriate value

    # Dynamic dispatch via object reference constant (resolves to expression_rule)
    validator_ref = constants.DEFAULT_VALIDATION_RULE()
    result = engine.dispatch(validator_ref, inputs={"customer_id": 123})
    # engine.dispatch() detects it's a rule → calls execute_rule()


@expression_rule
def handle_new_customer(ctx):
    # Dynamic dispatch via object reference constant (resolves to process)
    process_ref = constants.DEFAULT_ONBOARDING_PROCESS()
    instance = engine.dispatch(process_ref, inputs={
        "customer_id": ctx.input("customer_id"),
        "send_welcome": True,
    })
    # engine.dispatch() detects it's a process → calls start_process()
    ctx.output("process_instance_id", instance.id)


# Simple constants
@constant
def MAX_RETRY_COUNT() -> int:
    return 3

@constant(validate=lambda x: x > 0)
def PAGE_SIZE() -> int:
    return 25
```

**Security:** Inherits from `app.yaml → security.defaults.logic`. Override with `@constant(permissions=["finance"])`.

**Log files:** `constants/execution/` (access events), `constants/security/` (permission checks). No separate performance log — constant lookups are sub-millisecond.

### 5.7 Record (Data Model)

**Scope:** Per-app. Pydantic-native models that auto-generate SQLAlchemy, migrations, CRUD, API, and UI.

| Property | Type | Description |
|----------|------|-------------|
| Class fields | Pydantic `Field()` | Column definitions with validation |
| Relationships | `has_many`, `belongs_to`, `has_one` | ORM relationships |
| `Meta.table_name` | str | DB table name (defaults to snake_case) |
| `Meta.audit` | bool | Enable field-level audit logging (generates audit_log table) |
| `Meta.soft_delete` | bool | Use `is_deleted` flag |
| `Meta.display_field` | str | Field shown in lists/dropdowns |
| `Meta.search_fields` | List[str] | Fields included in search |
| `Meta.permissions` | dict | Group-level CRUD permissions |
| `Meta.row_security_rule` | str | Future: rule name that filters query results per user |
| `Meta.on_create` / `on_update` / `on_delete` | List[str] | Rule/process triggers |
| `Meta.connected_system` | str | DB connection to use |

```python
from pydantic import BaseModel, Field
from typing import List, Optional
from datetime import datetime

@record
class Customer(BaseModel):
    """Customer record with orders relationship."""

    name: str = Field(max_length=100, description="Customer full name")
    email: str = Field(max_length=255, pattern=r"^[\w.-]+@[\w.-]+\.\w+$", description="Email")
    phone: Optional[str] = Field(default=None, max_length=20)
    tier: str = Field(default="bronze", json_schema_extra={"choices": ["bronze", "silver", "gold", "platinum"]})
    credit_limit: float = Field(default=0.0, ge=0, decimal_places=2)
    is_active: bool = Field(default=True)
    created_at: datetime = Field(default_factory=datetime.utcnow)

    # Relationships
    orders: List["Order"] = has_many("Order", back_ref="customer")
    primary_address: Optional["Address"] = has_one("Address")

    class Meta:
        table_name = "customers"
        audit = True                    # Generates {app}_customers_audit_log table:
        # | record_id | field | old_value | new_value | changed_by | timestamp |
        soft_delete = True
        display_field = "name"
        search_fields = ["name", "email", "phone"]
        connected_system = "crm_database"
        permissions = {
            "view": ["sales", "support", "crm_admins"],
            "create": ["sales", "crm_admins"],
            "update": ["sales", "crm_admins"],
            "delete": ["crm_admins"],
        }
        row_security_rule = None        # Future: "filter_customers_by_region"
        # Rule receives ctx with user info, returns additional WHERE conditions
        on_create = ["onboard_customer"]  # Triggers process
        on_update = ["log_customer_change"]


@record
class Order(BaseModel):
    """Order record belonging to a customer."""

    order_number: str = Field(max_length=50, json_schema_extra={"auto_generate": True})
    customer_id: int = Field(description="FK to Customer")
    status: str = Field(default="draft", json_schema_extra={"choices": ["draft", "pending", "confirmed", "shipped", "delivered"]})
    total_amount: float = Field(ge=0, decimal_places=2)
    order_date: datetime = Field(default_factory=datetime.utcnow)

    # Relationships
    customer: "Customer" = belongs_to("Customer", required=True)
    items: List["OrderItem"] = has_many("OrderItem", cascade="all, delete-orphan")

    class Meta:
        audit = True
        permissions = {
            "view": ["sales", "support", "crm_admins"],
            "create": ["sales", "crm_admins"],
            "update": ["sales", "crm_admins"],
            "delete": ["crm_admins"],
        }
```

**What gets auto-generated from a Record** — see [Section 9: Record System & Auto-Generation](#9-record-system--auto-generation).

> **Document security inheritance:** Documents associated with a Record inherit the Record's security permissions. If a user can `view` a Record, they can view its Documents.
> **Log files:** `records/execution/` (CRUD operations), `records/performance/`, `records/security/`

### 5.8 Expression Rule

**Scope:** Per-app. Modular functions — the universal logic unit. Replaces both "Rule" and "Query Rule" from v1.

| Property | Type | Description |
|----------|------|-------------|
| `name` | str | Function name |
| `inputs` | List[str] | Declared input parameters |
| `outputs` | List[str] | Declared output values |
| `depends_on` | List[str] | Explicit dependency declarations |
| `permissions` | List[str] | Groups that can execute |
| `cacheable` | bool | Whether results can be cached |
| `cache_ttl` | int | Cache time-to-live in seconds |

```python
@expression_rule(
    inputs=["amount", "customer_tier"],
    outputs=["final_amount", "discount_applied"],
    depends_on=["constants.TAX_RATE", "rules.get_tier_discount"],
    permissions=["sales", "crm_admins"]
)
def calculate_final_price(ctx):
    """Calculate final price with tax and tier discount."""

    amount = ctx.input("amount")
    tier = ctx.input("customer_tier")

    # Access constants (auto-import, security-checked)
    tax_rate = constants.TAX_RATE()

    # Call other rules (auto-import, dependency logged)
    discount = rules.get_tier_discount(tier=tier)

    # Local scope variables
    subtotal = amount * (1 - discount)
    tax = subtotal * tax_rate

    ctx.output("discount_applied", discount)
    ctx.output("final_amount", subtotal + tax)
    return ctx.outputs()


# Query logic (merged Query Rule — same object type)
@expression_rule(
    inputs=["customer_id"],
    outputs=["orders"],
    permissions=["sales", "support"]
)
def get_customer_orders(ctx):
    """Fetch orders for a customer — query logic as Expression Rule."""
    customer = records.customer.get(ctx.input("customer_id"))
    orders = records.order.list(
        filters={"customer_id": customer.id, "status__ne": "draft"},
        sort="-order_date",
        limit=50
    )
    ctx.output("orders", orders)
    return ctx.outputs()


# Simple utility rule
@expression_rule(
    inputs=["tier"],
    outputs=["discount"]
)
def get_tier_discount(ctx):
    """Get discount percentage based on customer tier."""
    discounts = {"bronze": 0.05, "silver": 0.10, "gold": 0.15, "platinum": 0.20}
    ctx.output("discount", discounts.get(ctx.input("tier"), 0))
    return ctx.outputs()
```

**Security:** Inherits from `app.yaml → security.defaults.logic`. Override with `@expression_rule(permissions=["crm_admins"])`.

**Log files:** `rules/execution/`, `rules/performance/`, `rules/security/`. See `AppOS_Logging_Reference.md` for field details.

**Platform Rules:** AppOS ships prebuilt expression rules for user/group management (e.g., `platform.rules.get_current_user`, `platform.rules.create_user`, `platform.rules.add_user_to_group`). See `AppOS_PlatformRules_Reference.md` for the full list.

### 5.9 Step

**Scope:** Per-app. Individual unit within a Process. Wraps an Expression Rule call with process-specific metadata.

| Property | Type | Description |
|----------|------|-------------|
| `name` | str | Step identifier within process |
| `rule` | str | Expression Rule to execute |
| `retry_count` | int | Number of retries on failure (default: 0) |
| `retry_delay` | int | Seconds between retries (default: 5) |
| `timeout` | int | Step timeout in seconds |
| `on_error` | str | Error handling: "fail" / "skip" / "goto:{step}" |
| `on_success` | str | Next step override (default: sequential) |
| `condition` | str | Expression Rule that returns bool — skip if false |
| `input_mapping` | dict | Map process variables to rule inputs |
| `output_mapping` | dict | Map rule outputs to process variables |
| `fire_and_forget` | bool | If True, step runs async and process continues immediately (default: False) |

```python
# Steps are defined inline within a Process, not as standalone files.
# They wrap Expression Rules with orchestration metadata.

step("validate_data",
    rule="validate_customer",
    input_mapping={"customer_id": "ctx.var.customer_id"},
    output_mapping={"is_valid": "ctx.var.is_valid", "errors": "ctx.var.errors"},
    on_error="fail",
    timeout=30
)

step("setup_account",
    rule="create_account",
    condition="ctx.var.is_valid",  # Only runs if validation passed
    retry_count=3,
    retry_delay=10,
    input_mapping={"customer_id": "ctx.var.customer_id"},
)

step("send_welcome",
    rule="send_welcome_email",
    condition="ctx.var.send_welcome",
    on_error="skip",  # Non-critical — don't fail process
    fire_and_forget=True,  # Don't wait — process continues immediately
)
# fire_and_forget steps tracked in process_step_log with status "async_dispatched"
# until completion. They update independently.
```

**Log files:** `steps/execution/`, `steps/performance/`

### 5.10 Process

**Scope:** Per-app. Multi-step orchestrator — the workflow. Has its own state/scope. Executes Steps via Celery.

| Property | Type | Description |
|----------|------|-------------|
| `name` | str | Process identifier |
| `description` | str | Documentation |
| `inputs` | List[str] | Process input parameters |
| `triggers` | List | `event()`, `schedule()`, or manual |
| `permissions` | List[str] | Groups that can start/view |
| `timeout` | int | Overall process timeout |
| `on_error` | str | Global error handler |
| `display_name` | str | Template for human-readable instance name (e.g., `"Onboard: {customer_name}"`) |

**Process variables** are accessible across all steps:

```python
@process(
    name="onboard_customer",
    description="Complete customer onboarding workflow",
    inputs=["customer_id", "send_welcome"],
    display_name="Onboard: {customer_id}",
    triggers=[
        event("records.customer.on_create"),
        # schedule("0 9 * * *"),  # Or cron-based
    ],
    permissions=["sales", "crm_admins"]
)
def onboard_customer(ctx):
    """
    Process with its own scope. Variables accessible across all steps.
    ctx.var is the process-level state.
    """

    # Process-level variables (accessible across all steps)
    ctx.var("customer_id", ctx.input("customer_id"), logged=True)
    ctx.var("send_welcome", ctx.input("send_welcome"), logged=True)
    ctx.var("temp_token", generate_token(), logged=False)      # Hidden from logs
    ctx.var("internal_key", get_key(), sensitive=True)          # Encrypted, never shown

    return [
        step("validate_data",
            rule="validate_customer",
            input_mapping={"customer_id": "ctx.var.customer_id"},
            output_mapping={"is_valid": "ctx.var.is_valid"},
            on_error="fail"
        ),

        step("setup_account",
            rule="create_account",
            condition="ctx.var.is_valid",
            input_mapping={"customer_id": "ctx.var.customer_id"},
            retry_count=2
        ),

        step("send_welcome_email",
            rule="send_welcome",
            condition="ctx.var.send_welcome",
            on_error="skip"
        ),

        # parallel() runs steps concurrently as a Celery group — waits for all to complete
        parallel(
            step("notify_sales", rule="notify_team",
                 input_mapping={"message": "'New customer onboarded'"}),
            step("update_crm", rule="update_crm_status",
                 input_mapping={"customer_id": "ctx.var.customer_id"}),
        ),
    ]


# Scheduled process
@process(
    name="daily_report",
    triggers=[schedule("0 8 * * *", timezone="UTC")],
    permissions=["finance_admins"]
)
def daily_report(ctx):
    return [
        step("gather", rule="gather_report_data"),
        step("format", rule="format_report"),
        step("send", rule="distribute_report"),
    ]
```

**Process variable visibility:**

| Flag | In Logs | In Admin UI | In DB | In AI Queries |
|------|---------|-------------|-------|---------------|
| `logged=True` (default) | ✓ | ✓ | ✓ | ✓ |
| `logged=False` | ✗ | ✗ | ✓ (hashed) | ✗ |
| `sensitive=True` | ✗ | ✗ | ✓ (encrypted) | ✗ |

**Log files:** `processes/execution/`, `processes/performance/`, `processes/security/`

### 5.11 Integration

**Scope:** Per-app. Outbound API calls to external systems. Uses Connected System for connection details.

| Property | Type | Description |
|----------|------|-------------|
| `name` | str | Integration identifier |
| `connected_system` | str | Reference to Connected System |
| `method` | str | HTTP method |
| `path` | str | API endpoint path (supports templates) |
| `headers` | dict | Additional headers |
| `body_template` | dict | Request body template |
| `response_mapping` | dict | Map response to structured output |
| `error_handling` | dict | Status code → action mapping |
| `retry` | dict | Retry configuration |
| `permissions` | List[str] | Groups that can invoke |
| `log_payload` | bool | If True, request/response bodies included in execution log (default: False) |

```python
@integration(
    name="create_stripe_charge",
    connected_system="stripe_api",
    permissions=["finance", "crm_admins"]
)
def create_stripe_charge():
    return {
        "method": "POST",
        "path": "/charges",
        "headers": {"Idempotency-Key": "{idempotency_key}"},
        "body": {
            "amount": "{amount_cents}",
            "currency": "{currency}",
            "customer": "{stripe_customer_id}",
            "description": "{description}",
        },
        "response_mapping": {
            "charge_id": "$.id",
            "status": "$.status",
            "receipt_url": "$.receipt_url",
        },
        "error_handling": {
            "402": "payment_failed",
            "429": "retry",
            "5xx": "retry",
        },
        "retry": {"count": 3, "delay": 5, "backoff": "exponential"},
    }


# Called from an Expression Rule or Process:
@expression_rule
def charge_customer(ctx):
    result = integrations.create_stripe_charge.execute(
        amount_cents=ctx.input("amount") * 100,
        currency="usd",
        stripe_customer_id=ctx.input("stripe_id"),
        description="Order payment",
    )
    ctx.output("charge_id", result["charge_id"])
    return ctx.outputs()
```

**Log files:** `integrations/execution/` (method, target_url, status_code, duration — NO body by default), `integrations/performance/`, `integrations/security/`

**Payload opt-in:** Set `log_payload=True` on the decorator. Payload is encrypted at rest if Connected System is marked sensitive.

### 5.12 Web API

**Scope:** Per-app. Expose internal functions as REST endpoints to external systems.

| Property | Type | Description |
|----------|------|-------------|
| `name` | str | API endpoint identifier |
| `method` | str | HTTP method |
| `path` | str | URL path (under `/api/{app_short_name}/`) |
| `auth` | dict | Authentication requirements (Connected System ref or custom) |
| `request_schema` | dict | Expected request body (Pydantic model) |
| `response_schema` | dict | Response structure |
| `handler` | str | Expression Rule or Process to execute |
| `rate_limit` | dict | Rate limiting config |
| `version` | str | API version |

```python
@web_api(
    name="get_customer_info",
    method="GET",
    path="/customers/{customer_id}",
    auth={"type": "api_key", "connected_system": "external_api_auth"},
    version="v1",
    rate_limit={"requests": 100, "window": 60},
    permissions=["api_consumers"]
)
def get_customer_info():
    return {
        "handler": "rules.get_customer_details",  # Expression Rule
        "request_mapping": {
            "customer_id": "path.customer_id",
        },
        "response_mapping": {
            "id": "$.customer_id",
            "name": "$.customer_name",
            "tier": "$.tier",
        },
    }


# Web API that triggers a Process and returns output
@web_api(
    name="submit_order",
    method="POST",
    path="/orders",
    auth={"type": "oauth2", "connected_system": "partner_auth"},
    version="v1"
)
def submit_order():
    return {
        "handler": "processes.process_new_order",  # Triggers Process
        "request_schema": OrderSubmitRequest,       # Pydantic model
        "response_mapping": {
            "order_id": "$.order_id",
            "status": "$.status",
        },
        "async": False,  # Wait for process to complete
    }
```

**URL Resolution:** `/api/{app_short_name}/{version}/{path}`

**Service Account Auth:** Web APIs authenticate via Connected System (API key, OAuth). The token resolves to a `service_account` user → group membership → permissions apply uniformly. See `AppOS_Permissions_Reference.md`.

**Async Mode:** When `"async": True`, the Web API returns `{"instance_id": "proc_xxx", "status": "pending", "poll_url": "/api/crm/v1/processes/proc_xxx/status"}` immediately. Client polls for completion.

**Log files:** `web_apis/execution/` (method, path, status_code, handler, duration — NO body by default), `web_apis/performance/`, `web_apis/security/`. Set `log_payload=True` on the `@web_api` decorator to include request/response bodies.

**URL examples:**
- `GET /api/crm/v1/customers/123`
- `POST /api/crm/v1/orders`

### 5.13 Interface

**Scope:** Per-app. UI component definitions. Auto-generated from Records, overridable by developers.

| Property | Type | Description |
|----------|------|-------------|
| `name` | str | Interface identifier |
| `record` | str | Record this interface is for (optional) |
| `type` | str | "list" / "create" / "edit" / "view" / "custom" |
| `permissions` | List[str] | Groups that can access |
| `components` | List | UI component tree |

```python
# Auto-generated from Record — developer can override
@interface(
    name="CustomerList",
    record="Customer",
    type="list",
    permissions=["sales", "support", "crm_admins"]
)
def customer_list():
    return DataTable(
        record="Customer",
        columns=["name", "email", "tier", "is_active"],
        searchable=True,
        filterable=True,
        page_size=25,
        actions=[Button("Create", action="navigate", to="/crm/customers/new")],
        row_actions=[
            Button("Edit", action="navigate", to="/crm/customers/{id}/edit"),
            Button("Delete", action="delete", confirm=True),
        ]
    )


# Custom interface combining multiple elements
@interface(name="CustomerDashboard", permissions=["sales", "crm_admins"])
def customer_dashboard(ctx):
    return Layout([
        Row([
            Card("Total Customers", content=rules.count_customers()),
            Card("Active Orders", content=rules.count_active_orders()),
        ]),
        Row([
            DataTable(record="Customer", columns=["name", "tier"], page_size=10),
        ]),
    ])
```

**Component Library:** `DataTable`, `Form`, `Field`, `Button`, `Layout`, `Row`, `Column`, `Card`, `Wizard`, `WizardStep`, `Chart`, `Metric`

**Security:** Interface permissions inherit from `security.defaults.ui` in `app.yaml` by default. Explicit `permissions=[...]` overrides. Components are plain functions (not an object type). Hierarchy: Page → Interface → Component.

**Raw Reflex:** Developers can use any Reflex component (`rx.text()`, `rx.chart()`, etc.) directly alongside AppOS components inside Interfaces. No wrappers needed.

**Log files:** `interfaces/execution/` (render events), `interfaces/performance/` (render time), `interfaces/security/`

### 5.14 Page

**Scope:** Per-app. A single routable Reflex page.

| Property | Type | Description |
|----------|------|-------------|
| `route` | str | URL path (relative to app prefix) |
| `title` | str | Page title |
| `interface` | str | Interface to render |
| `permissions` | List[str] | Groups that can access |
| `state` | class | Reflex state class for this page |
| `on_load` | str | Expression Rule to run on page load |

```python
@page(
    route="/customers",
    title="Customers",
    interface="CustomerList",
    permissions=["sales", "support"]
)
def customers_page():
    pass


@page(
    route="/customers/{id}",
    title="Customer Detail",
    interface="CustomerView",
    permissions=["sales", "support"]
)
def customer_detail_page():
    pass


@page(
    route="/dashboard",
    title="CRM Dashboard",
    interface="CustomerDashboard",
    permissions=["sales", "crm_admins"],
    on_load="rules.load_dashboard_data"
)
def dashboard_page():
    pass
```

**Resolved URLs:** `/{app_short_name}/{route}` → `/crm/customers`, `/crm/dashboard`

**Security:** Page permissions inherit from `security.defaults.ui` in `app.yaml` by default. Explicit `permissions=[...]` overrides.

**Log files:** `pages/execution/` (route, on_load rule, render time), `pages/performance/`, `pages/security/`

### 5.15 Site

**Scope:** Per-app. Collection of Pages forming a navigable application.

| Property | Type | Description |
|----------|------|-------------|
| `name` | str | Site name (usually same as app name) |
| `pages` | List[str] | Page references |
| `navigation` | List[dict] | Nav menu structure |
| `theme` | str | Theme name or config |
| `auth_required` | bool | Require login |
| `default_page` | str | Landing page route |

```python
@site(name="CRM")
def crm_site():
    return {
        "pages": ["dashboard_page", "customers_page", "customer_detail_page", "orders_page"],
        "navigation": [
            {"label": "Dashboard", "route": "/dashboard", "icon": "home"},
            {"label": "Customers", "route": "/customers", "icon": "users"},
            {"label": "Orders", "route": "/orders", "icon": "shopping-cart"},
        ],
        "auth_required": True,
        "default_page": "/dashboard",
        "theme": "crm_theme",
    }
```

### 5.16 Document

**Scope:** Per-app. File and artifact management with versioning.

| Property | Type | Description |
|----------|------|-------------|
| `id` | int | Auto-generated primary key |
| `name` | str | Document name |
| `file_path` | str | Physical file path |
| `folder` | str | Folder reference |
| `mime_type` | str | File MIME type |
| `size_bytes` | int | File size |
| `version` | int | Version number (auto-incremented on update) |
| `tags` | List[str] | Searchable tags |
| `owner` | str | User who uploaded |
| `permissions` | dict | Group-level access |
| `created_at` | datetime | Upload timestamp |
| `updated_at` | datetime | Last modification timestamp |

```python
@record
class Document(BaseModel):
    """Document metadata — stored in DB. Physical files in app's runtime/documents/ folder."""

    name: str = Field(max_length=255)
    file_path: str = Field(max_length=500)
    folder_id: Optional[int] = Field(default=None)
    mime_type: str = Field(max_length=100)
    size_bytes: int = Field(ge=0)
    version: int = Field(default=1)
    tags: List[str] = Field(default_factory=list)
    owner_id: int = Field()
    is_archived: bool = Field(default=False)

    # Relationship
    folder: Optional["Folder"] = belongs_to("Folder")
    versions: List["DocumentVersion"] = has_many("DocumentVersion")

    class Meta:
        audit = True
        soft_delete = True
        permissions = {
            "view": ["*"],  # All groups in app
            "use": ["*"],
            "create": ["crm_admins", "sales"],
            "update": ["crm_admins", "sales"],
            "delete": ["crm_admins"],
        }


@record
class DocumentVersion(BaseModel):
    """Tracks document versions with timestamps."""
    document_id: int = Field()
    version: int = Field()
    file_path: str = Field(max_length=500)
    size_bytes: int = Field(ge=0)
    uploaded_by: int = Field()
    uploaded_at: datetime = Field(default_factory=datetime.utcnow)
    change_note: Optional[str] = Field(default=None, max_length=500)

    class Meta:
        permissions = {
            "view": ["*"],
            "create": ["crm_admins", "sales"],
            "delete": ["crm_admins"],
        }
```

**Physical storage:** `apps/{app_short_name}/runtime/documents/{folder_name}/`

**Security inheritance:** Documents associated with a Record inherit the Record's security permissions. If a user can `view` a Record, they can view its Documents. MIME type validation enforced by parent Folder's `document_types`.

**Reflex integration:** Documents use `rx.upload` for file uploads. The engine handles moving files to the correct folder and creating DB metadata records.

**Log files:** `documents/execution/` (upload, download, delete events), `documents/security/`

### 5.17 Folder

**Scope:** Per-app. Dynamic runtime folder management.

| Property | Type | Description |
|----------|------|-------------|
| `name` | str | Folder name |
| `path` | str | Relative path under app's runtime directory |
| `purpose` | str | What this folder is for (e.g., "invoices", "reports") |
| `document_types` | List[str] | Allowed MIME types |
| `max_size_mb` | int | Size limit |
| `auto_cleanup` | dict | Retention policy |

```python
@record
class Folder(BaseModel):
    """Folder configuration — DB table drives physical directory creation."""

    name: str = Field(max_length=100)
    path: str = Field(max_length=500)
    purpose: str = Field(max_length=200)
    app_id: int = Field()
    document_types: List[str] = Field(default_factory=lambda: ["*/*"])
    max_size_mb: int = Field(default=1000)
    auto_cleanup: Optional[dict] = Field(default=None)
    is_active: bool = Field(default=True)

    # Relationships
    documents: List["Document"] = has_many("Document")

    class Meta:
        unique_together = [("app_id", "path")]
        permissions = {
            "view": ["*"],
            "use": ["*"],
            "create": ["crm_admins"],
            "update": ["crm_admins"],
            "delete": ["crm_admins"],
        }
```

**Engine behavior:**
1. On app startup, reads Folder table
2. Creates physical directories that don't exist: `apps/{app}/runtime/documents/{folder.path}/`
3. On Document upload, validates against Folder's `document_types` and `max_size_mb`. Rejects with `AppOSValidationError` if MIME mismatch.
4. Auto-cleanup runs on schedule based on retention policy: when `auto_cleanup.retention_days` is set, a scheduled platform process deletes Documents older than the retention period (optionally archiving first)

**Log files:** `folders/execution/` (folder operations), `folders/security/`

### 5.18 Translation Set

**Scope:** Per-app. i18n labels and notification strings. One set per app can have many keys with translations.

| Property | Type | Description |
|----------|------|-------------|
| `name` | str | Translation set name (e.g., "crm_labels") |
| `app` | str | App reference |
| `labels` | dict | `{key: {lang_code: translated_string}}` |

```python
@translation_set(name="crm_labels", app="crm")
def crm_translations():
    return {
        "customer_name": {
            "en": "Customer Name",
            "fr": "Nom du Client",
            "es": "Nombre del Cliente",
            "de": "Kundenname",
        },
        "save_button": {
            "en": "Save",
            "fr": "Sauvegarder",
            "es": "Guardar",
            "de": "Speichern",
        },
        "welcome_message": {
            "en": "Welcome, {name}!",
            "fr": "Bienvenue, {name} !",
            "es": "¡Bienvenido, {name}!",
            "de": "Willkommen, {name}!",
        },
        "order_confirmation": {
            "en": "Order #{order_id} has been confirmed.",
            "fr": "La commande #{order_id} a été confirmée.",
            "es": "El pedido #{order_id} ha sido confirmado.",
        },
    }


# Usage in Interfaces and Rules:
@expression_rule
def get_welcome(ctx):
    # Automatically resolves based on logged-in user's preferred_language
    msg = translations.crm_labels.get("welcome_message", name=ctx.user.full_name)
    ctx.output("message", msg)
    return ctx.outputs()

# In Interfaces:
Field("name", label=translations.crm_labels.ref("customer_name"))
# → "Customer Name" for English user, "Nom du Client" for French user
```

**Why separate from Constants:** Translation Sets hold multi-language dictionaries per key. Constants hold single values (even if env-specific). Different lifecycle — translations are managed by content teams, constants by developers.

**Language resolution:** Uses `ctx.user.preferred_language` from the User profile. Access via `translations.{name}.get(key)` auto-detects language. Override with explicit `lang=` parameter: `translations.crm_labels.get("welcome", lang="es")`. Custom languages supported — not limited to standard ISO codes.

**Fallback chain:** Every translation key MUST include an `"en"` value (mandatory default). Resolution order: user's `preferred_language` → `"en"` → key name as-is. If the key is completely missing from the Translation Set, returns the key string itself (e.g., `"welcome_message"`).

**Log files:** `translation_sets/execution/` (access events), `translation_sets/security/`

---

## 6. Security Model

### Architecture

```
┌──────────────────────────────────────────────────────────────────┐
│                     SECURITY FLOW                                │
├──────────────────────────────────────────────────────────────────┤
│                                                                  │
│  1. User Login (Session-Based Auth — Redis)                      │
│     └─► Authenticate (bcrypt hash)                               │
│     └─► Load groups, permissions                                 │
│     └─► Create session (Redis DB 4)                              │
│     └─► Set ExecutionContext (contextvars)                        │
│                                                                  │
│  2. Every Object Access (Auto-Import Layer)                      │
│     └─► Get current ExecutionContext                              │
│     └─► Cache-first permission check (Redis, TTL=5min)           │
│     └─► If miss: query object_permission table                   │
│     └─► Cache result                                             │
│     └─► ALLOW → proceed (async log)                              │
│     └─► DENY → raise AppOSSecurityError (with full context)      │
│                                                                  │
│  3. Audit Trail                                                  │
│     └─► Every check logged (async, non-blocking)                 │
│     └─► Denials logged to security/ log folder with full context │
│     └─► Viewable in Admin Console                                │
│                                                                  │
└──────────────────────────────────────────────────────────────────┘
```

### Unified Permission Model

Six generic permissions across ALL object types: `view`, `use`, `create`, `update`, `delete`, `admin`. Stored in `object_permission` table. No type-specific permission names.

**Full details:** See `AppOS_Permissions_Reference.md` for the complete permission applicability matrix, DB schema, three-tier inherited security model, and examples.

### Object Permission Table — Wildcard Support

```sql
-- Single table for all object permissions. Supports wildcards.
CREATE TABLE object_permission (
    id SERIAL PRIMARY KEY,
    group_name VARCHAR(100) NOT NULL,
    object_ref VARCHAR(255) NOT NULL,    -- "crm.rules.calc_discount" or "crm.rules.*" or "crm.*"
    permission VARCHAR(20) NOT NULL,      -- "view" | "use" | "create" | "update" | "delete" | "admin"
    UNIQUE(group_name, object_ref, permission)
);

-- Examples:
-- All rules in CRM app: use permission for sales group
INSERT INTO object_permission VALUES (1, 'sales', 'crm.rules.*', 'use');
-- Specific record CRUD:
INSERT INTO object_permission VALUES (2, 'sales', 'crm.records.customer', 'view');
INSERT INTO object_permission VALUES (3, 'sales', 'crm.records.customer', 'create');
-- Full admin on entire app:
INSERT INTO object_permission VALUES (4, 'crm_admins', 'crm.*', 'admin');
```

**Wildcard resolution order:** Most specific match wins. `crm.rules.calc_discount` > `crm.rules.*` > `crm.*`.

### Three-Tier Inherited Security (Summary)

| Tier | Scope | Objects | Override |
|------|-------|---------|----------|
| App defaults (app.yaml) | `security.defaults.logic` | Rules, Constants | Explicit `permissions=[...]` on decorator |
| App defaults (app.yaml) | `security.defaults.ui` | Interfaces, Pages, Translation Sets | Explicit `permissions=[...]` on decorator |
| Always explicit | Per-object | Records, Processes, Web APIs, Integrations, Connected Systems | REQUIRED — `appos check` errors if missing |

### Permission Resolution Flow

```
User → Groups → object_permission table (cached in Redis) → ALLOW/DENY
  │       │              │
  │       │              └─ Unified permissions: view|use|create|update|delete|admin
  │       └─ User's group membership list
  └─ Authenticated user (basic / system_admin / service_account)
```

### Permission Cache Strategy

| Cache Layer | Storage | TTL | Invalidation |
|-------------|---------|-----|--------------|
| Session permissions | Redis | 5 minutes | On user/group change |
| Group membership | Redis | 5 minutes | On group membership change |
| Object permissions | Redis | 5 minutes | On object security change |
| Pre-computed access matrix | Memory | On startup | Full rebuild on admin change |

**Cold cache latency target:** 100-200ms (acceptable). Subsequent requests: <5ms from Redis.

### Redis Failure Strategy

```
┌──────────────────────────────────────────────────────────────────┐
│                  REDIS FAILURE HANDLING                           │
├──────────────────────────────────────────────────────────────────┤
│                                                                  │
│  Redis is used for: sessions, permission cache, Celery broker   │
│                                                                  │
│  If Redis is unavailable:                                        │
│  ┌────────────────────────────────────────────────────────────┐  │
│  │ Permission cache miss:                                     │  │
│  │   → Fall back to direct DB query (object_permission table) │  │
│  │   → Log warning to system/execution/ (degraded mode)       │  │
│  │   → Continue operating (slower but functional)             │  │
│  ├────────────────────────────────────────────────────────────┤  │
│  │ Session lookup fail:                                       │  │
│  │   → Return 503 Service Unavailable                         │  │
│  │   → Retry with exponential backoff (3 attempts, 100ms)     │  │
│  ├────────────────────────────────────────────────────────────┤  │
│  │ Celery broker fail:                                        │  │
│  │   → Process/step tasks queued locally until broker returns  │  │
│  │   → Admin console shows broker status warning               │  │
│  └────────────────────────────────────────────────────────────┘  │
│                                                                  │
│  Circuit breaker: After 5 consecutive Redis failures in 30s,    │
│  switch to DB-only mode for permissions (bypass cache).          │
│  Auto-recover when Redis health check succeeds.                  │
│                                                                  │
│  Health check: Redis PING every 10s from engine startup.        │
│  Status visible in Admin Console → Dashboard.                    │
│                                                                  │
└──────────────────────────────────────────────────────────────────┘
```

### Security Policy Implementation

```python
class SecurityPolicy:
    """Evaluated by Auto-Import layer on every object access. Cache-first."""

    def __init__(self, permission_cache: RedisCache):
        self.cache = permission_cache  # Redis, TTL=5min

    def check_access(self, user_groups: set, object_ref: str, permission: str) -> bool:
        """
        Check if any of user's groups have the required permission on the object.
        Uses unified 6-permission model (view/use/create/update/delete/admin).
        Supports wildcards (e.g., "crm.rules.*", "crm.*").
        Cache-first: Redis hit → return immediately. Miss → query DB → cache result.
        Denial raises AppOSSecurityError with full context.
        """
        cache_key = f"{frozenset(user_groups)}:{object_ref}:{permission}"
        cached = self.cache.get(cache_key)
        if cached is not None:
            return cached

        # DB fallback: query object_permission table
        allowed = self._query_permissions(user_groups, object_ref, permission)
        self.cache.set(cache_key, allowed)
        return allowed
```

### Applying Security to Objects

```python
# Record — always explicit (6 unified permissions)
@record
class Customer(BaseModel):
    ...
    class Meta:
        permissions = {
            "view": ["sales", "support", "crm_admins"],
            "use": ["sales", "support", "crm_admins"],
            "create": ["sales", "crm_admins"],
            "update": ["sales", "crm_admins"],
            "delete": ["crm_admins"],
        }

# Expression Rule — inherits from security.defaults.logic unless overridden
@expression_rule  # ← inherits app-level logic groups
def calculate_discount(ctx):
    ...

@expression_rule(permissions=["crm_admins"])  # ← explicit override
def sensitive_calculation(ctx):
    ...

# Page — inherits from security.defaults.ui unless overridden
@page(route="/customers")  # ← inherits app-level UI groups
def customers_page():
    ...

# Process — always explicit
@process(permissions=["sales", "crm_admins"])
def onboard_customer(ctx):
    ...

# Web API — always explicit, with service account auth
@web_api(auth={"type": "api_key", "connected_system": "partner_auth"},
         permissions=["api_consumers"])
def get_customer_info():
    ...
```

**Error hierarchy & session management details:** See `AppOS_Permissions_Reference.md`.

### Public Access Pattern

```python
# For Web APIs that don't require authentication:
@web_api(name="public_status", method="GET", path="/status", auth_required=False)
def public_status():
    return {"handler": "rules.get_system_status"}

# Internally, unauthenticated requests execute as the "public_api" service_account user.
# This user belongs to the "public_access" group (bootstrapped on appos init).
# The "public_access" group has explicitly limited permissions.
# No special code paths — the engine ALWAYS has a user/group context.
```

### Session-Based Authentication

```
┌──────────────────────────────────────────────────────────────────┐
│              SESSION-BASED AUTH (Redis-backed)                    │
├──────────────────────────────────────────────────────────────────┤
│                                                                  │
│  Why sessions over JWT:                                          │
│  • Instant revocation — delete from Redis (JWT needs blacklist) │
│  • Small cookie (session ID) vs large JWT header                │
│  • Server-controlled lifetime (not client-claimed expiry)       │
│  • Redis already in stack for cache + Celery broker             │
│                                                                  │
│  Flow:                                                           │
│  1. User logs in → server creates session in Redis              │
│  2. Session ID stored in secure HttpOnly cookie                 │
│     (SameSite=Lax, Secure=True in prod)                         │
│  3. CSRF token generated per session, sent via header           │
│     (X-CSRF-Token) — validated on all state-changing requests   │
│  4. Each request → session ID → Redis lookup → user context     │
│  5. Logout / timeout → session deleted from Redis               │
│                                                                  │
│  Configurable (admin console → Settings → Security):            │
│  • session_timeout (absolute): default 3600s                    │
│  • idle_timeout: default 1800s                                  │
│  • max_concurrent_sessions: default 5 per user                  │
│  • Active sessions view — admin can see and kill sessions       │
│                                                                  │
└──────────────────────────────────────────────────────────────────┘
```

---

## 7. State Management

### The Four-State Model

```
┌──────────────────────────────────────────────────────────────────┐
│                     STATE HIERARCHY                              │
├──────────────────────────────────────────────────────────────────┤
│                                                                  │
│  1. DEFINITION STATE (Files)                                     │
│     └── Object source code, decorators, configurations           │
│         Lives in: apps/{app}/records/, rules/, etc.              │
│         Never changes at runtime                                 │
│                                                                  │
│  2. COMPILED STATE (Memory — Object Registry)                    │
│     └── Parsed objects, dependency graph, cached ASTs            │
│         Rebuilt on startup / reload                               │
│         In-memory, fast access                                   │
│                                                                  │
│  3. RUNTIME STATE (Execution Context — contextvars)              │
│     └── Current user, groups, app, execution_id                  │
│         Thread-safe, request-scoped                              │
│         Set on login, used on every access                       │
│                                                                  │
│  4. PROCESS STATE (Process Context — DB-backed)                  │
│     └── Process variables (ctx.var)                              │
│         Accessible across all steps                              │
│         Persisted in ProcessInstance table                        │
│         Visibility control: logged / hidden / sensitive          │
│         Each start_process() creates unique instance + context   │
│                                                                  │
└──────────────────────────────────────────────────────────────────┘
```

### Execution Context

```python
from contextvars import ContextVar

# Thread-safe — one per request/execution
current_execution_context = ContextVar('execution_context', default=None)

@dataclass
class ExecutionContext:
    user_id: str
    user_groups: Set[str]
    execution_id: str
    app_name: str
    preferred_language: str
    timezone: str
    workflow_name: Optional[str] = None

    # Populated by auto-import layer
    dependencies_accessed: List[dict] = field(default_factory=list)
```

### Process Context (ctx.var)

```python
class ProcessContext:
    """
    Process-level state. Variables accessible across all steps.
    Persisted to ProcessInstance.context in DB.
    """

    def __init__(self, process_instance):
        self._instance = process_instance
        self._variables = {}
        self._visibility = {}  # {var_name: "logged" | "hidden" | "sensitive"}

    def var(self, name, value=None, logged=True, sensitive=False):
        """Get or set a process variable."""
        if value is not None:
            self._variables[name] = value
            if sensitive:
                self._visibility[name] = "sensitive"
            elif not logged:
                self._visibility[name] = "hidden"
            else:
                self._visibility[name] = "logged"
            self._persist()
            return value
        return self._variables.get(name)

    def input(self, name):
        """Get a process input."""
        return self._instance.inputs.get(name)

    @property
    def user(self):
        """Get current user from execution context."""
        return current_execution_context.get()

    def _persist(self):
        """Save variables to DB (encrypted if sensitive, hashed if hidden)."""
        ...
```

---

## 8. Centralized Runtime Engine

### Architecture

```
┌──────────────────────────────────────────────────────────────────┐
│                  CENTRALIZED RUNTIME ENGINE                      │
├──────────────────────────────────────────────────────────────────┤
│                                                                  │
│  ┌─────────────────┐  ┌─────────────────┐  ┌─────────────────┐  │
│  │  Dependency     │  │  Execution      │  │  Security       │  │
│  │  Tracker        │  │  Logger         │  │  Auditor        │  │
│  │                 │  │                 │  │                 │  │
│  │  NetworkX graph │  │  Per-type logs  │  │  security/ logs │  │
│  │  + JSON persist │  │  rules/, procs/ │  │  async queue    │  │
│  │  + AI queries   │  │  integrations/  │  │  AppOSSecError  │  │
│  └─────────────────┘  └─────────────────┘  └─────────────────┘  │
│                                                                  │
│  ┌─────────────────┐  ┌─────────────────┐  ┌─────────────────┐  │
│  │  Performance    │  │  Permission     │  │  Async Log      │  │
│  │  Collector      │  │  Cache          │  │  Queue          │  │
│  │                 │  │                 │  │                 │  │
│  │  Per-type logs  │  │  Redis          │  │  In-memory →    │  │
│  │  (same files)   │  │  TTL=5min       │  │  background     │  │
│  │                 │  │                 │  │  flush thread   │  │
│  └─────────────────┘  └─────────────────┘  └─────────────────┘  │
│                                                                  │
└──────────────────────────────────────────────────────────────────┘
```

### Runtime Engine Implementation

```python
class CentralizedRuntime:
    """
    Single source of truth for all runtime data.
    System logs → Files (filterable in admin console).
    App runtime logs → DB tables per app requirements.
    """

    def __init__(self):
        # In-memory dependency graph (NetworkX for fast traversal)
        self.dependency_graph = nx.DiGraph()

        # Per-object-type file loggers with sub-category routing (Option A)
        # Each type has execution/, performance/, security/ sub-folders
        # See AppOS_Logging_Reference.md for full folder structure and log formats
        self.log_queues = {}  # (type, category) → AsyncLogQueue

        OBJECT_TYPES = [
            "rules", "processes", "steps", "integrations", "web_apis",
            "records", "interfaces", "pages", "constants",
            "connected_systems", "documents", "translation_sets",
            "folders", "system", "admin",
        ]
        LOG_CATEGORIES = ["execution", "performance", "security"]

        for obj_type in OBJECT_TYPES:
            for category in LOG_CATEGORIES:
                key = (obj_type, category)
                self.log_queues[key] = AsyncLogQueue(
                    FileLogger(f"logs/{obj_type}/{category}/"),
                    flush_interval_ms=100, flush_batch_size=50
                )

        # Redis for permission caching
        self.permission_cache = RedisCache(prefix="appos:perms:", ttl=300)

    def log_dependency_access(self, log_entry: dict):
        """Called by Auto-Import layer on every object access. Non-blocking."""

        # Update in-memory graph
        if log_entry.get('caller_function'):
            self.dependency_graph.add_edge(
                log_entry['caller_function'],
                log_entry['module_path']
            )

        # Async push to appropriate type + category queue (non-blocking)
        obj_type = log_entry.get('object_type', 'system')
        log_category = log_entry.get('log_category', 'execution')
        self.log_queues[(obj_type, log_category)].push(log_entry)

        # Security denials also go to same type's security/ sub-folder
        if log_entry['status'] == 'DENIED':
            self.log_queues[(obj_type, 'security')].push(log_entry)

    def log_execution(self, step_name, context, inputs, duration_ms, status, output=None):
        """Called by @expression_rule and @step decorators after execution. Non-blocking."""

        execution_log = {
            'timestamp': datetime.utcnow().isoformat(),
            'execution_id': context.execution_id,
            'app': context.app_name,
            'step_name': step_name,
            'user_id': context.user_id,
            'duration_ms': duration_ms,
            'status': status,
            'dependencies': list(self.dependency_graph.successors(step_name)),
        }

        # Route to execution + performance log queues for this type
        obj_type = self._detect_object_type(step_name)  # "rules", "steps", etc.
        self.log_queues[(obj_type, 'execution')].push(execution_log)

        # Performance entry (separate sub-folder, 30-day retention)
        perf_log = {
            'timestamp': execution_log['timestamp'],
            'execution_id': execution_log['execution_id'],
            'object_ref': step_name,
            'duration_ms': duration_ms,
            'status': status,
        }
        self.log_queues[(obj_type, 'performance')].push(perf_log)

    def get_dependency_graph(self, object_name: str) -> dict:
        """Get full dependency tree for an object (used by AI)."""
        if object_name not in self.dependency_graph:
            return {}
        return nx.node_link_data(
            nx.subgraph(self.dependency_graph,
                         nx.descendants(self.dependency_graph, object_name) | {object_name})
        )

    def get_performance_stats(self, step_name: str) -> dict:
        """Aggregate performance metrics from log files."""
        entries = self.performance_logger.query(step_name=step_name, last_hours=24)
        durations = [e['duration_ms'] for e in entries]
        if not durations:
            return {}
        return {
            'avg_ms': sum(durations) / len(durations),
            'min_ms': min(durations),
            'max_ms': max(durations),
            'p95_ms': sorted(durations)[int(len(durations) * 0.95)],
            'count_24h': len(durations),
        }

    def query_for_ai(self, question: str) -> dict:
        """Structured endpoint for AI to query runtime state."""
        # Natural language → structured query
        # Returns dependency graphs, security violations, performance stats
        ...

    def dispatch(self, object_ref: str, inputs: dict = None, **kwargs) -> Any:
        """
        Unified dispatcher — resolves any object reference string and executes it.
        Detects whether the ref points to an expression_rule, process, or integration
        and calls the appropriate executor. This enables Constants with object_ref type
        to dynamically invoke ANY executable object type without the caller needing to
        know the target type.

        Args:
            object_ref: Fully-qualified object reference (e.g., "crm.rules.validate_customer"
                        or "crm.processes.onboard_customer" or "crm.integrations.stripe_charge")
            inputs:     Dict of inputs to pass to the resolved object.
            **kwargs:   Additional options (async_exec, timeout, etc.)

        Returns:
            - For expression_rule: the rule's output dict
            - For process: the ProcessInstance (running or completed)
            - For integration: the integration response

        Security: Checks execute permission for the resolved object before dispatch.
        Logging:  Logs the dispatch event including source constant (if applicable).
        """
        resolved = self.registry.resolve(object_ref)

        # Security check on the resolved target (uses unified permissions)
        self.security.check_permission(object_ref, "use")

        # Log the dispatch for dependency tracking
        self.log_dependency_access({
            'caller_function': self._get_caller_context(),
            'module_path': object_ref,
            'dispatch_type': resolved.object_type,  # "expression_rule" | "process" | "integration"
            'status': 'DISPATCHED',
            'timestamp': datetime.utcnow().isoformat(),
        })

        # Route to the correct executor based on object type
        if resolved.object_type == "expression_rule":
            return self.execute_rule(object_ref, inputs=inputs or {})

        elif resolved.object_type == "process":
            async_exec = kwargs.get('async_exec', True)  # Processes default to async
            return start_process(
                object_ref,
                inputs=inputs or {},
                wait=not async_exec,
                timeout=kwargs.get('timeout'),
            )

        elif resolved.object_type == "integration":
            return self.execute_integration(object_ref, inputs=inputs or {})

        else:
            raise AppOSDispatchError(
                f"Cannot dispatch to object type '{resolved.object_type}'. "
                f"Only expression_rule, process, and integration are executable. "
                f"Ref: {object_ref}"
            )
```

### AppOSError Hierarchy

```python
class AppOSError(Exception):
    """Base error for all AppOS engine failures. Structured for AI debugging."""
    def __init__(self, message, **context):
        self.execution_id = context.get("execution_id")
        self.object_ref = context.get("object_ref")
        self.object_type = context.get("object_type")
        self.error_type = self.__class__.__name__
        self.context = context
        self.dependency_chain = context.get("dependency_chain", [])
        self.process_instance_id = context.get("process_instance_id")
        self.step_name = context.get("step_name")
        super().__init__(message)

class AppOSSecurityError(AppOSError):
    """Access denied. Logged to security/ log files."""
    pass

class AppOSDispatchError(AppOSError):
    """Object not found or cannot be dispatched."""
    pass

class AppOSValidationError(AppOSError):
    """Input validation failed (Pydantic, MIME type, constraints)."""
    pass

class AppOSTimeoutError(AppOSError):
    """Execution exceeded timeout (process step, integration call)."""
    pass

class AppOSIntegrationError(AppOSError):
    """External system call failed."""
    pass
```

> **All errors** include `execution_id` for end-to-end tracing. When inside a process, also includes `process_instance_id` and `step_name`. Stored in `process_step_log.error_detail` JSON for failed steps. Queryable via `runtime.query_for_ai()`. See `AppOS_Permissions_Reference.md` for the full error hierarchy including `AppOSRecordError` and `AppOSObjectNotFoundError`.

### Prebuilt Platform Rules

```python
# Available globally via platform.rules namespace. No import needed.

platform.rules.get_current_user()               # Returns current user details
platform.rules.get_user(user_id)                 # Returns user by ID
platform.rules.get_user_groups(user_id)          # Returns list of group names
platform.rules.get_group_members(group_name)     # Returns list of users in group
platform.rules.create_user(username, email, full_name, user_type, groups=[])
platform.rules.update_user(user_id, fields={})   # Update user fields
platform.rules.add_user_to_group(user_id, group_name)
platform.rules.remove_user_from_group(user_id, group_name)
platform.rules.change_password(user_id, old_password, new_password)
platform.rules.create_group(name, description, apps=[], users=[])

# Security: system_admin required for all except:
# - get_current_user() — any authenticated user
# - change_password() — self only (user_id must match ctx.user.id)
```

> **Implementation:** Located in `appos/platform_rules/`. Registered in engine on startup. Cross-app accessible from any app. See `AppOS_PlatformRules_Reference.md`.

### File Logger

```python
class FileLogger:
    """
    Structured JSON file logger with daily rotation.
    Files: {base_path}/{date}.jsonl
    Each line is a JSON object — easy to parse, grep, stream.
    """

    def __init__(self, base_path: str):
        self.base_path = Path(base_path)

    def write(self, entry: dict):
        """Append structured JSON entry to current log file."""
        date = datetime.utcnow().strftime("%Y-%m-%d")
        path = self.base_path / f"{date}.jsonl"
        path.parent.mkdir(parents=True, exist_ok=True)

        with open(path, 'a') as f:
            f.write(json.dumps(entry) + '\n')

    def query(self, **filters) -> List[dict]:
        """Query log files with filters. Used by admin console."""
        ...
```

---

## 9. Record System & Auto-Generation

### Record Processing Pipeline

```
@record Customer(BaseModel)                   ← Developer writes Pydantic model
       │
       ├──► Record Parser                     ← Extract fields, relationships, Meta
       │
       ├──► SQLAlchemy Model Generator        ← Pydantic → SQLAlchemy Column mapping
       │    File: .appos/generated/models/customer.py
       │
       ├──► Alembic Migration Generator       ← Diff current model vs DB → migration
       │    File: migrations/versions/001_create_customer.py
       │
       ├──► Audit Log Table (if Meta.audit)   ← {app}_{record}_audit_log table
       │    Columns: record_id, field, old_value, new_value, changed_by, timestamp
       │
       ├──► CRUD Service Generator            ← create/get/update/delete/list/search
       │    File: .appos/generated/services/customer_service.py
       │
       ├──► API Endpoint Generator            ← REST endpoints auto-registered
       │    POST/GET/PUT/DELETE /api/{app}/customers
       │
       ├──► Interface Generator               ← List/Create/Edit/View Reflex components
       │    File: .appos/generated/interfaces/customer_interfaces.py
       │
       └──► Audit Hooks (if Meta.audit=True)  ← Log field-level changes to audit_log table
```

> **Audit log** is automatically created alongside the data table when `Meta.audit=True`. Every field-level change generates a row with old/new values, who changed it, and when. Useful for compliance, debugging, and undo.

### Pydantic → SQLAlchemy Mapping

| Pydantic Type | SQLAlchemy Column | Notes |
|---------------|-------------------|-------|
| `str` | `String(max_length)` | Uses `max_length` from `Field()` |
| `int` | `Integer` | |
| `float` | `Numeric(precision, scale)` | Uses `decimal_places` from `Field()` |
| `bool` | `Boolean` | |
| `datetime` | `DateTime` | |
| `date` | `Date` | |
| `Optional[T]` | `Column(T, nullable=True)` | |
| `List[str]` | `ARRAY(String)` or `JSON` | |
| `dict` | `JSON` | |
| Field with `choices` | `String` + CHECK constraint | |
| Field with `pattern` | `String` + validation | |

### Generated SQLAlchemy Model

```python
# Auto-generated from @record Customer
# .appos/generated/models/customer.py

from sqlalchemy import Column, String, Boolean, Numeric, DateTime, Integer
from sqlalchemy.orm import relationship
from appos.db.base import BaseModel, AuditMixin, SoftDeleteMixin

class CustomerModel(BaseModel, AuditMixin, SoftDeleteMixin):
    __tablename__ = "customers"

    id = Column(Integer, primary_key=True, autoincrement=True)
    name = Column(String(100), nullable=False)
    email = Column(String(255), unique=True, nullable=False)
    phone = Column(String(20), nullable=True)
    tier = Column(String(20), default="bronze")
    credit_limit = Column(Numeric(10, 2), default=0)
    is_active = Column(Boolean, default=True)
    created_at = Column(DateTime, default=datetime.utcnow)

    # Relationships
    orders = relationship("OrderModel", back_populates="customer")
    primary_address = relationship("AddressModel", uselist=False)

    # AuditMixin: created_by, created_at, updated_by, updated_at
    # SoftDeleteMixin: is_deleted, deleted_at, deleted_by
```

### Generated CRUD Service

```python
# .appos/generated/services/customer_service.py

class CustomerService(RecordService):
    model = CustomerModel
    pydantic_model = Customer  # Original Pydantic class

    # Inherited: create, get, update, delete, list, search
    # Generated hooks from Meta:

    def after_create(self, instance):
        # Triggers from Meta.on_create
        engine.trigger_process("onboard_customer", {"customer_id": instance.id})

    def after_update(self, instance, changes):
        # Triggers from Meta.on_update
        engine.execute_rule("log_customer_change", {
            "customer_id": instance.id, "changes": changes
        })
```

### Overriding Generated Interfaces

```python
# In app code: apps/crm/interfaces/customer.py

# Option 1: Completely replace generated interface
@interface(name="CustomerCreate", record="Customer", type="create")
def custom_customer_create(ctx):
    return Form(record="Customer", fields=["name", "email", "tier"])

# Option 2: Extend/modify generated interface
@interface.extend("CustomerList")
def extend_customer_list(base):
    base.columns.append("credit_limit")
    base.actions.append(Button("Export", action="rule", rule="export_customers"))
    return base
```

---

## 10. Dependency Management & AI Integration

### How Dependencies Are Tracked

Dependencies are **automatically tracked** by the Auto-Import layer — no manual `depends_on` declarations needed (though explicit declarations are supported for documentation).

```
Auto-Import layer intercepts:
  rules.calculate_discount → records access → constants access
       │                          │                  │
       └──────────────────────────┴──────────────────┘
                        │
                        ▼
              Dependency Graph
              (NetworkX DiGraph)
              ┌───────────────────────────────┐
              │ calculate_discount             │
              │   ├── records.customer         │
              │   ├── constants.TAX_RATE       │
              │   └── rules.get_tier_discount  │
              │         └── constants.TIERS    │
              └───────────────────────────────┘
```

### Storage Strategy

| Format | Location | Purpose | Tool |
|--------|----------|---------|------|
| **In-memory graph** | RAM | Fast runtime queries | NetworkX |
| **JSON persistence** | `.appos/runtime/dependencies/` | AI-readable, git-trackable | JSON files |
| **DB historical** | `dependency_changes` table | Track changes over time | PostgreSQL |

### dependency_changes Table Schema

```sql
CREATE TABLE dependency_changes (
    id          SERIAL PRIMARY KEY,
    object_ref  VARCHAR(255) NOT NULL,
    change_type VARCHAR(20) NOT NULL,  -- added | removed | modified
    old_hash    VARCHAR(64),
    new_hash    VARCHAR(64),
    changed_at  TIMESTAMP DEFAULT NOW(),
    changed_by  VARCHAR(100)
);
CREATE INDEX idx_depchange_obj ON dependency_changes(object_ref);
CREATE INDEX idx_depchange_time ON dependency_changes(changed_at);
```

### JSON Dependency File (AI-Optimized)

```json
// .appos/runtime/dependencies/crm.rules.calculate_discount.json
{
    "object": "crm.rules.calculate_discount",
    "type": "expression_rule",
    "app": "crm",
    "direct_dependencies": [
        {"type": "constant", "ref": "crm.constants.TAX_RATE", "access": "read"},
        {"type": "expression_rule", "ref": "crm.rules.get_tier_discount", "access": "execute"},
        {"type": "record", "ref": "crm.records.customer", "access": "read"}
    ],
    "full_dependency_tree": {
        "crm.rules.calculate_discount": {
            "crm.constants.TAX_RATE": {},
            "crm.rules.get_tier_discount": {
                "crm.constants.TIER_CONFIG": {}
            },
            "crm.records.customer": {}
        }
    },
    "dependents": [
        {"type": "process", "ref": "crm.processes.process_order"},
        {"type": "web_api", "ref": "crm.web_apis.get_quote"}
    ],
    "metrics": {
        "execution_count_24h": 1523,
        "avg_duration_ms": 12.4,
        "p95_duration_ms": 34.2,
        "error_rate_24h": 0.002,
        "last_executed": "2026-02-07T14:30:00Z"
    },
    "last_modified": "2026-02-07T10:00:00Z",
    "source_hash": "a1b2c3d4..."
}
```

### AI Query Interface

```python
# AI agent can query the runtime for debugging:

runtime.query_for_ai("What dependencies does calculate_discount have?")
# Returns:
{
    "type": "dependency_graph",
    "data": {
        "calculate_discount": ["constants.TAX_RATE", "rules.get_tier_discount", "records.customer"],
        "get_tier_discount": ["constants.TIER_CONFIG"]
    }
}

runtime.query_for_ai("Show security violations for user_123")
# Returns:
{
    "type": "security_violations",
    "data": [
        {
            "user_id": "user_123",
            "module_path": "finance.records.transactions",
            "reason": "Insufficient permissions",
            "user_groups": ["sales"],
            "required_groups": ["finance", "finance_admins"],
            "timestamp": "2026-02-07T10:30:00"
        }
    ]
}

runtime.query_for_ai("Why is process_order slow?")
# Returns:
{
    "type": "performance_analysis",
    "data": {
        "process": "process_order",
        "avg_duration_ms": 2340,
        "bottleneck_step": "charge_payment",
        "step_breakdown": {
            "validate_order": {"avg_ms": 15, "p95_ms": 30},
            "check_inventory": {"avg_ms": 120, "p95_ms": 450},
            "charge_payment": {"avg_ms": 1800, "p95_ms": 3200},
            "send_confirmation": {"avg_ms": 200, "p95_ms": 500}
        },
        "suggestion": "charge_payment step takes 77% of total time. Check stripe_api connected system latency."
    }
}

runtime.query_for_ai("What changed in the last deploy?")
# Returns:
{
    "type": "change_report",
    "data": {
        "modified_objects": [
            {"ref": "crm.rules.calculate_discount", "change": "logic_updated", "hash_diff": "abc→def"},
            {"ref": "crm.records.customer", "change": "field_added: loyalty_points"}
        ],
        "impacted_objects": [
            "crm.processes.process_order",
            "crm.web_apis.get_quote",
            "crm.interfaces.CustomerList"
        ]
    }
}
```

### Impact Analysis (CLI Tool)

Impact analysis is available as a CLI command:

```bash
$ appos impact crm.constants.TAX_RATE
```

```python
# Returns:
{
    "direct_dependents": [
        "crm.rules.calculate_discount",
        "crm.rules.calculate_invoice_total"
    ],
    "transitive_dependents": [
        "crm.processes.process_order",
        "crm.web_apis.get_quote",
        "crm.interfaces.OrderForm"
    ],
    "total_impact": 5,
    "recommendation": "Changing TAX_RATE affects 5 objects across 2 processes and 1 API endpoint."
}
```

---

## 11. Process Engine

### Architecture

```
┌──────────────────────────────────────────────────────────────────┐
│                     PROCESS ENGINE                               │
├──────────────────────────────────────────────────────────────────┤
│                                                                  │
│  @process (definition)                                           │
│       │                                                          │
│       ├── ctx.var() ─── Process-level variables                  │
│       │                 (accessible across all steps)            │
│       │                                                          │
│       ├── step("validate", rule="validate_order")                │
│       │     └── Wraps Expression Rule with retry/timeout/etc.    │
│       │                                                          │
│       ├── step("charge", rule="charge_payment")                  │
│       │     └── Can read/write ctx.var from previous steps       │
│       │                                                          │
│       └── step("confirm", rule="send_confirmation")              │
│                                                                  │
│  EXECUTION ─────────────────────────────────────────────────     │
│                                                                  │
│  ProcessInstance (DB record)                                     │
│  ┌──────────────────────────────────────────────────────────┐    │
│  │ id: "proc_abc123"                                        │    │
│  │ process: "process_order"                                 │    │
│  │ status: "running"                                        │    │
│  │ current_step: "charge"                                   │    │
│  │ variables: {order_id: 456, amount: 100.00, ...}         │    │
│  │ step_history: [                                          │    │
│  │   {step: "validate", status: "completed", duration: 15ms}│    │
│  │   {step: "charge", status: "running", started: ...}     │    │
│  │ ]                                                        │    │
│  └──────────────────────────────────────────────────────────┘    │
│                                                                  │
│  Celery Task Queue                                               │
│  ┌──────────────────────────────────────────────────────────┐    │
│  │ Each step → Celery task → Worker executes Expression Rule│    │
│  │ Step completion → triggers next step                      │    │
│  │ Parallelizable steps → Celery group                       │    │
│  └──────────────────────────────────────────────────────────┘    │
│                                                                  │
└──────────────────────────────────────────────────────────────────┘
```

### ProcessInstance Model

```python
@record
class ProcessInstance(BaseModel):
    """Tracks a running process instance. Stored in core DB."""

    process_name: str = Field(max_length=100)
    app_name: str = Field(max_length=50)
    status: str = Field(default="pending",
        json_schema_extra={"choices": ["pending", "running", "paused", "completed", "failed", "cancelled"]})
    current_step: Optional[str] = Field(default=None, max_length=100)

    # Process state
    inputs: dict = Field(default_factory=dict)      # Initial inputs
    variables: dict = Field(default_factory=dict)    # ctx.var values
    variable_visibility: dict = Field(default_factory=dict)  # Visibility flags
    outputs: Optional[dict] = Field(default=None)    # Final outputs

    # History — stored in separate process_step_log table (not JSON array)
    error_info: Optional[dict] = Field(default=None)

    # Timing
    started_at: datetime = Field(default_factory=datetime.utcnow)
    completed_at: Optional[datetime] = Field(default=None)

    # Relationships
    started_by: int = Field()          # User ID
    parent_instance_id: Optional[int] = Field(default=None)  # Sub-processes

    class Meta:
        audit = True
        # Table partitioned by started_at (monthly) for performance at scale
        # Archive policy: move completed instances older than retention to archive table
        # Configurable: process_instances.archive_after_days in appos.yaml
        permissions = {
            "view": ["system_admin"],
            "use": ["system_admin"],
            "create": ["system_admin"],
            "update": ["system_admin"],
            "delete": ["system_admin"],
        }


class ProcessStepLog(BaseModel):
    """Separate table for step execution history. One row per step execution."""
    process_instance_id: int = Field()
    step_name: str = Field(max_length=100)
    rule_ref: str = Field(max_length=200)    # e.g., "crm.rules.validate_customer"
    status: str = Field()  # pending | running | completed | failed | skipped | async_dispatched
    started_at: datetime = Field(default_factory=datetime.utcnow)
    completed_at: Optional[datetime] = Field(default=None)
    duration_ms: Optional[float] = Field(default=None)
    inputs: Optional[dict] = Field(default=None)       # step inputs (opt-in)
    outputs: Optional[dict] = Field(default=None)       # step outputs (opt-in)
    error_info: Optional[dict] = Field(default=None)    # AppOSError JSON if failed
    attempt: int = Field(default=1)  # retry attempt number
    is_fire_and_forget: bool = Field(default=False)
    is_parallel: bool = Field(default=False)

    class Meta:
        # Partitioned by started_at (monthly) — same strategy as ProcessInstance
        indexes = [("process_instance_id",), ("step_name", "status", "started_at")]
        permissions = {
            "view": ["system_admin"],
            "create": ["system_admin"],
        }
```

### Celery Integration

```python
celery_app = Celery('appos', broker='redis://localhost:6379/0')

@celery_app.task(bind=True)
def execute_process_step(self, instance_id, step_name):
    """Execute a single step in a process."""

    instance = ProcessInstance.get(instance_id)
    process_def = registry.get_process(instance.process_name)
    step_def = process_def.get_step(step_name)

    # Check condition
    if step_def.condition:
        if not evaluate_condition(step_def.condition, instance.variables):
            # Skip this step — log to process_step_log
            ProcessStepLog.create(
                process_instance_id=instance.id,
                step_name=step_name, status="skipped",
                started_at=datetime.utcnow(), completed_at=datetime.utcnow(),
            )
            trigger_next_step(instance)
            return

    # Execute the expression rule
    try:
        ctx = ProcessContext(instance)
        result = engine.execute_rule(
            step_def.rule,
            inputs=resolve_input_mapping(step_def.input_mapping, instance.variables)
        )

        # Map outputs to process variables
        if step_def.output_mapping:
            for rule_output, process_var in step_def.output_mapping.items():
                ctx.var(process_var, result.get(rule_output))

        # Log step completion to process_step_log table
        ProcessStepLog.create(
            process_instance_id=instance.id,
            step_name=step_name, status="completed",
            started_at=step_start, completed_at=datetime.utcnow(),
            duration_ms=...,
        )
        instance.save()

        # Trigger next step
        trigger_next_step(instance)

    except Exception as e:
        handle_step_error(instance, step_def, step_name, e)


def trigger_next_step(instance):
    """Determine and trigger the next step in the process."""
    process_def = registry.get_process(instance.process_name)
    next_step = process_def.get_next_step(instance.current_step)

    if next_step:
        instance.current_step = next_step.name
        instance.save()
        execute_process_step.delay(instance.id, next_step.name)
    else:
        instance.status = "completed"
        instance.completed_at = datetime.utcnow()
        instance.save()
```

### Starting a Process

```python
# Zero-import start via namespace (preferred)
instance = processes.onboard_customer.start(inputs={"customer_id": 123, "send_welcome": True})

# Cross-app process start via namespace
instance = finance.processes.monthly_close.start(inputs={"month": "2026-02"})

# Dynamic start via engine.dispatch() — type-agnostic, works with Constants
process_ref = constants.DEFAULT_ONBOARDING_PROCESS()  # Resolves per environment
instance = engine.dispatch(process_ref, inputs={"customer_id": 123, "send_welcome": True})
# engine.dispatch() detects the ref is a process → calls start_process() internally

# From Record event (configured in Meta.on_create)
# Automatically triggered when Customer is created

# From Web API
@web_api(name="submit_order", method="POST", path="/orders")
def submit_order():
    return {"handler": "processes.process_order", "async": False}

# From Expression Rule (zero-import namespace)
@expression_rule
def handle_payment_failure(ctx):
    processes.retry_payment.start(inputs={"order_id": ctx.input("order_id")})

# From Expression Rule (dynamic dispatch via constant)
@expression_rule
def handle_new_signup(ctx):
    ref = constants.DEFAULT_ONBOARDING_PROCESS()  # Could be rule OR process
    engine.dispatch(ref, inputs={"customer_id": ctx.input("customer_id")})
```

### Process History (Admin Console)

```
Process: onboard_customer (proc_abc123)
Status: completed ✓
Duration: 2.3s
Started: 2026-02-07 14:30:00 by user_456

Step History:
┌────┬──────────────────┬───────────┬──────────┬────────────────────┐
│ #  │ Step             │ Status    │ Duration │ Timestamp          │
├────┼──────────────────┼───────────┼──────────┼────────────────────┤
│ 1  │ validate_data    │ ✓ done    │ 15ms     │ 14:30:00.000       │
│ 2  │ setup_account    │ ✓ done    │ 1200ms   │ 14:30:00.015       │
│ 3  │ send_welcome     │ ✓ done    │ 800ms    │ 14:30:01.215       │
│ 4  │ notify_sales     │ ✓ done    │ 200ms    │ 14:30:02.015       │
└────┴──────────────────┴───────────┴──────────┴────────────────────┘

Variables (logged only):
  customer_id: 123
  send_welcome: true
  is_valid: true

Hidden variables: 2 (temp_token, internal_key)
```

---

## 12. UI Layer — Reflex Integration

### Single-Port Multi-App Routing

```
┌──────────────────────────────────────────────────────────────────┐
│                 SINGLE REFLEX INSTANCE                           │
│                 (one port, URL-based routing)                    │
├──────────────────────────────────────────────────────────────────┤
│                                                                  │
│  /admin/*                                                        │
│  ├── /admin/login         ← Common login screen                  │
│  ├── /admin/users         ← User management                     │
│  ├── /admin/groups        ← Group management                    │
│  ├── /admin/apps          ← App management                      │
│  ├── /admin/connections   ← Connected System management          │
│  ├── /admin/logs          ← Log viewer with filters              │
│  └── /admin/metrics       ← Performance metrics dashboard        │
│                                                                  │
│  /crm/*                   ← CRM app (theme: blue)               │
│  ├── /crm/dashboard                                              │
│  ├── /crm/customers                                              │
│  ├── /crm/customers/{id}                                         │
│  └── /crm/orders                                                 │
│                                                                  │
│  /finance/*               ← Finance app (theme: green)           │
│  ├── /finance/dashboard                                          │
│  ├── /finance/invoices                                           │
│  └── /finance/reports                                            │
│                                                                  │
│  /api/*                   ← Web API endpoints                    │
│  ├── /api/crm/v1/customers                                      │
│  └── /api/finance/v1/invoices                                    │
│                                                                  │
└──────────────────────────────────────────────────────────────────┘
```

### Reflex App Wrapper

```python
# appos/ui/reflex_bridge.py

import reflex as rx

class AppOSReflexApp:
    """Wraps all AppOS apps into a single Reflex application."""

    def __init__(self):
        self.app = rx.App()
        self._register_admin_routes()
        self._register_app_routes()
        self._register_api_routes()

    def _register_admin_routes(self):
        """Register built-in admin console pages."""
        # Login, user management, group management, logs, metrics
        ...

    def _register_app_routes(self):
        """Auto-register all pages from all active apps."""
        for app in registry.get_active_apps():
            for page_def in app.get_pages():
                route = f"/{app.short_name}{page_def.route}"
                self.app.add_page(
                    self._render_page(page_def, app),
                    route=route,
                    title=page_def.title,
                    on_load=self._get_auth_guard(page_def),
                )

    def _render_page(self, page_def, app):
        """Convert AppOS page/interface to Reflex component."""
        interface_def = registry.get_interface(page_def.interface)
        return InterfaceRenderer(interface_def, app.theme).to_reflex()

    def _register_api_routes(self):
        """Register Web API endpoints."""
        for app in registry.get_active_apps():
            for api_def in app.get_web_apis():
                route = f"/api/{app.short_name}/{api_def.version}/{api_def.path}"
                self.app.api.add_api_route(route, ...)
```

### Per-App Theming

```python
# apps/crm/app.yaml
app:
  theme:
    primary_color: "#3B82F6"     # Blue
    secondary_color: "#1E40AF"
    accent_color: "#DBEAFE"
    font_family: "Inter"
    border_radius: "8px"

# apps/finance/app.yaml
app:
  theme:
    primary_color: "#059669"     # Green
    secondary_color: "#047857"
    accent_color: "#D1FAE5"
    font_family: "Inter"
    border_radius: "4px"
```

Themes are applied per-app within the single Reflex instance using Reflex's theming capabilities. The engine wraps each app's pages with the appropriate theme provider.

### Component Library

Components are **plain functions** (not an object type). They map directly to Reflex components with minimal abstraction. Developers can use raw Reflex components alongside AppOS components.

**Hierarchy:** Page → Interface → Component (Page renders an Interface, Interface composes Components)

```python
# appos/ui/components.py — thin wrappers around Reflex components

class DataTable:     # → rx.data_table with sorting, filtering, pagination
class Form:          # → rx.form with validation, submit handling
class Field:         # → rx.input / rx.select / rx.checkbox depending on type
class Button:        # → rx.button with action handlers
class Layout:        # → rx.box with flex/grid layout
class Row:           # → rx.hstack
class Column:        # → rx.vstack
class Card:          # → rx.card with header and content
class Wizard:        # → Multi-step form with progress indicator
class WizardStep:    # → Single wizard step
class Chart:         # → rx.recharts integration
class Metric:        # → KPI card with label, value, trend
```

---

## 13. Admin Console

### Overview

The Admin Console is a built-in Reflex application at `/admin/*`. It is the management hub for all platform operations. **Restricted to `system_admin` group** — users with `user_type="system_admin"` only. Common login screen, available to all apps.

### Screens

| Screen | Route | Purpose |
|--------|-------|---------|
| **Login** | `/admin/login` | Common authentication screen for all apps |
| **Dashboard** | `/admin/dashboard` | Platform overview: apps, users, recent activity |
| **Users** | `/admin/users` | Create, edit, deactivate users (incl. service accounts) |
| **Groups** | `/admin/groups` | Manage groups, assign users, set app access |
| **Apps** | `/admin/apps` | Register apps, configure themes, manage environments |
| **Connected Systems** | `/admin/connections` | Manage connections, credentials, health checks |
| **Records Browser** | `/admin/records` | Browse all records across apps |
| **Object Browser** | `/admin/objects` | View all object types, their dependencies, metrics |
| **Logs** | `/admin/logs` | Filter and view system logs (per-type folders) |
| **Metrics** | `/admin/metrics` | Performance dashboards per object, app, time range |
| **Processes** | `/admin/processes` | View running/completed processes, step-by-step history |
| **Workers** | `/admin/workers` | View Celery workers, scale pool, queue depth, autoscale |
| **Translations** | `/admin/translations` | Manage translation sets across apps |
| **Documents** | `/admin/documents` | Browse documents and folders across apps |
| **Settings** | `/admin/settings` | DB connection, YAML editor, session timeout, cache TTL, log retention |
| **Active Sessions** | `/admin/sessions` | View/kill active user sessions, cache flush |
| **Theme Editor** | `/admin/themes` | Per-app theme editing (colors, fonts, borders) |

### Connected System Management in Admin

```
┌──────────────────────────────────────────────────────────────────┐
│  Admin > Connected Systems > stripe_api                          │
├──────────────────────────────────────────────────────────────────┤
│                                                                  │
│  Name:        stripe_api                                         │
│  Type:        rest_api                                           │
│  Status:      ● Active    Last Health Check: 2s ago ✓           │
│                                                                  │
│  ┌─────────────────────────────────────────────────────────┐    │
│  │  Connection Details                                      │    │
│  │  Base URL: https://api.stripe.com/v1                    │    │
│  │  Timeout:  30s                                           │    │
│  └─────────────────────────────────────────────────────────┘    │
│                                                                  │
│  ┌─────────────────────────────────────────────────────────┐    │
│  │  Credentials        [Edit] [Rotate]                      │    │
│  │  Auth Type:  API Key                                     │    │
│  │  API Key:    sk_****...****4242 (last updated: 2 days)  │    │
│  └─────────────────────────────────────────────────────────┘    │
│                                                                  │
│  ┌─────────────────────────────────────────────────────────┐    │
│  │  Environment Overrides                                   │    │
│  │  ┌──────────┬───────────────────────────────────────┐   │    │
│  │  │ dev      │ use_test_key: true                    │   │    │
│  │  │ staging  │ use_test_key: true                    │   │    │
│  │  │ prod     │ use_test_key: false                   │   │    │
│  │  └──────────┴───────────────────────────────────────┘   │    │
│  └─────────────────────────────────────────────────────────┘    │
│                                                                  │
│  ┌─────────────────────────────────────────────────────────┐    │
│  │  Health Check                                            │    │
│  │  Endpoint: GET /v1/balance                               │    │
│  │  Interval: 60s      Timeout: 10s                        │    │
│  │  Last 24h: ████████████████████████ 100% up             │    │
│  └─────────────────────────────────────────────────────────┘    │
│                                                                  │
│  ┌─────────────────────────────────────────────────────────┐    │
│  │  Used By:                                                │    │
│  │  • crm.integrations.create_stripe_charge                │    │
│  │  • crm.integrations.refund_stripe_charge                │    │
│  │  • finance.integrations.stripe_payout                   │    │
│  └─────────────────────────────────────────────────────────┘    │
│                                                                  │
└──────────────────────────────────────────────────────────────────┘
```

### Metrics Dashboard in Admin

```
┌──────────────────────────────────────────────────────────────────┐
│  Admin > Metrics > crm.rules.calculate_discount                  │
├──────────────────────────────────────────────────────────────────┤
│                                                                  │
│  ┌──────────┐  ┌──────────┐  ┌──────────┐  ┌──────────┐       │
│  │ Calls/24h│  │ Avg (ms) │  │ P95 (ms) │  │ Errors   │       │
│  │   1,523  │  │   12.4   │  │   34.2   │  │  0.2%    │       │
│  └──────────┘  └──────────┘  └──────────┘  └──────────┘       │
│                                                                  │
│  Execution Trend (last 7 days):                                 │
│  ▓▓▓▓▓▓▓▓▓▓▓▓▓▓▓▓▓▓▓▓▓▓▓▓▓▓▓▓▓▓▓▓▓▓▓▓▓▓▓▓                │
│                                                                  │
│  Dependencies:                                                   │
│  ├── constants.TAX_RATE (constant)                              │
│  ├── rules.get_tier_discount (expression_rule)                  │
│  │     └── constants.TIER_CONFIG (constant)                     │
│  └── records.customer (record, read)                            │
│                                                                  │
│  Depended On By:                                                 │
│  ├── processes.process_order                                    │
│  └── web_apis.get_quote                                         │
│                                                                  │
│  Recent Executions:                                              │
│  ┌──────┬────────┬──────┬────────┬──────────────────────┐      │
│  │ ID   │ Status │ ms   │ User   │ Timestamp            │      │
│  ├──────┼────────┼──────┼────────┼──────────────────────┤      │
│  │ e001 │ ✓      │ 11   │ user_1 │ 14:30:00.123         │      │
│  │ e002 │ ✓      │ 14   │ user_2 │ 14:30:01.456         │      │
│  │ e003 │ ✗      │ 45   │ user_1 │ 14:30:02.789         │      │
│  └──────┴────────┴──────┴────────┴──────────────────────┘      │
│                                                                  │
└──────────────────────────────────────────────────────────────────┘
```

### Worker Management in Admin

Admins can view, scale, and manage Celery workers at runtime — no restart needed. Uses `celery.control.inspect()` for read operations and `celery.control.pool_grow/shrink` for live scaling.

```
┌──────────────────────────────────────────────────────────────────┐
│  Admin > Workers                                                 │
├──────────────────────────────────────────────────────────────────┤
│                                                                  │
│  ┌──────────┐  ┌──────────┐  ┌──────────┐  ┌──────────┐       │
│  │ Workers  │  │ Pool Size│  │ Queued   │  │ Active   │       │
│  │    3     │  │   12     │  │   47     │  │    8     │       │
│  └──────────┘  └──────────┘  └──────────┘  └──────────┘       │
│                                                                  │
│  Autoscale: ● Enabled   Min: 4   Max: 16                       │
│  ─────────────────────────────────────────────────────────────   │
│                                                                  │
│  Workers:                                                        │
│  ┌──────────────┬────────┬──────┬────────┬───────┬──────────┐  │
│  │ Worker       │ Status │ Pool │ Active │ Queue │ Actions  │  │
│  ├──────────────┼────────┼──────┼────────┼───────┼──────────┤  │
│  │ worker-1     │ ● OK   │  4   │   3    │  12   │ [+] [-]  │  │
│  │ worker-2     │ ● OK   │  4   │   3    │  18   │ [+] [-]  │  │
│  │ worker-3     │ ● OK   │  4   │   2    │  17   │ [+] [-]  │  │
│  └──────────────┴────────┴──────┴────────┴───────┴──────────┘  │
│                                                                  │
│  [+] = pool_grow (add 1 worker thread to this node)             │
│  [-] = pool_shrink (remove 1 worker thread from this node)      │
│                                                                  │
│  ┌─────────────────────────────────────────────────────────┐    │
│  │  Global Scaling                                          │    │
│  │                                                          │    │
│  │  Concurrency Per Worker:  [  4  ]  [Apply]              │    │
│  │  Autoscale:  [✓] Enabled                                │    │
│  │  Autoscale Min: [  4  ]   Max: [ 16  ]  [Apply]        │    │
│  └─────────────────────────────────────────────────────────┘    │
│                                                                  │
│  ┌─────────────────────────────────────────────────────────┐    │
│  │  Queue Status                                            │    │
│  │                                                          │    │
│  │  celery (default):  ████████████░░░░  47 tasks           │    │
│  │  process_steps:     █████░░░░░░░░░░░  18 tasks           │    │
│  │  scheduled:         ██░░░░░░░░░░░░░░   6 tasks           │    │
│  └─────────────────────────────────────────────────────────┘    │
│                                                                  │
│  ┌─────────────────────────────────────────────────────────┐    │
│  │  Throughput (last 1h):                                   │    │
│  │  ▓▓▓▓▓▓▓▓▓▓▓▓▓▓▓▓▓▓▓▓▓▓▓▓▓▓▓▓▓▓▓▓  1,247 tasks/hr    │    │
│  │  Avg latency: 23ms   Failed: 0.3%                       │    │
│  └─────────────────────────────────────────────────────────┘    │
│                                                                  │
└──────────────────────────────────────────────────────────────────┘
```

**Implementation details:**

```python
# Worker control (admin only)
class WorkerManager:
    """Interface to Celery worker control for admin console."""

    def __init__(self):
        self.app = celery_app
        self.inspect = self.app.control.inspect()

    def get_workers(self) -> dict:
        """Get all active workers and their stats."""
        return {
            "active": self.inspect.active(),           # Currently executing
            "reserved": self.inspect.reserved(),       # Queued on worker
            "stats": self.inspect.stats(),             # Pool size, uptime, etc.
            "active_queues": self.inspect.active_queues(),
        }

    def scale_worker(self, worker: str, delta: int):
        """Grow or shrink a specific worker's pool. delta=+1 or -1."""
        if delta > 0:
            self.app.control.pool_grow(delta, destination=[worker])
        elif delta < 0:
            self.app.control.pool_shrink(abs(delta), destination=[worker])

    def set_autoscale(self, max_concurrency: int, min_concurrency: int):
        """Update autoscale range for all workers."""
        self.app.control.autoscale(
            max=max_concurrency, min=min_concurrency
        )

    def get_queue_lengths(self) -> dict:
        """Get pending task count per queue from Redis."""
        import redis
        r = redis.from_url(config.redis.url)
        queues = ["celery", "process_steps", "scheduled"]
        return {q: r.llen(q) for q in queues}
```

---

## 14. Logging & Metrics Strategy

### Two-Tier Logging

```
┌──────────────────────────────────────────────────────────────────┐
│                      LOGGING STRATEGY                            │
├──────────────────────────────────────────────────────────────────┤
│                                                                  │
│  TIER 1: SYSTEM/PLATFORM LOGS → FILES (per object type)         │
│  ─────────────────────────────────────                          │
│  Location: .appos/logs/{object_type}/{log_category}/{date}.jsonl│
│  Format: Structured JSON lines (one JSON object per line)       │
│  Rotation: Daily, with configurable retention per category      │
│  Viewable: Admin Console log viewer with filters                 │
│  Writing: Async via in-memory queue + background flush thread   │
│                                                                  │
│  Log Folders (per object type, 3 sub-folders each):             │
│  ├── rules/                                                      │
│  │   ├── execution/      What ran, status, inputs/outputs       │
│  │   ├── performance/    Duration, timing breakdown              │
│  │   └── security/       Permission checks, allow/deny          │
│  ├── processes/                                                  │
│  │   ├── execution/  ├── performance/  └── security/            │
│  ├── steps/                                                      │
│  │   ├── execution/  └── performance/                           │
│  ├── integrations/   (no payload by default — log_payload opt-in)│
│  │   ├── execution/  ├── performance/  └── security/            │
│  ├── web_apis/       (no payload by default — log_payload opt-in)│
│  │   ├── execution/  ├── performance/  └── security/            │
│  ├── records/                                                    │
│  │   ├── execution/  ├── performance/  └── security/            │
│  ├── interfaces/                                                 │
│  │   ├── execution/  ├── performance/  └── security/            │
│  ├── pages/                                                      │
│  │   ├── execution/  ├── performance/  └── security/            │
│  ├── constants/                                                  │
│  │   ├── execution/  └── security/     (no performance — sub-ms)│
│  ├── connected_systems/                                          │
│  │   ├── execution/  ├── performance/  └── security/            │
│  ├── documents/                                                  │
│  │   ├── execution/  └── security/                              │
│  ├── translation_sets/                                           │
│  │   ├── execution/  └── security/                              │
│  ├── folders/                                                    │
│  │   ├── execution/  └── security/                              │
│  └── validation/                                                 │
│      └── appos-check-*.json  (appos check output)               │
│                                                                  │
│  See AppOS_Logging_Reference.md for full log entry formats,     │
│  async pipeline details, rotation config, and payload logging.  │
│                                                                  │
│  TIER 2: APP RUNTIME LOGS → DATABASE                            │
│  ───────────────────────────────────                            │
│  Location: App-specific DB tables                                │
│  Purpose: Business events, process history, custom app logging  │
│  Retention: Per-app configuration                                │
│  Viewable: Admin Console + app-specific interfaces              │
│                                                                  │
│  Tables (per app):                                               │
│  ├── {app}_process_instances    Process execution history       │
│  ├── {app}_{record}_audit_log   Record field-level change trail │
│  └── {app}_event_log            Custom business event logging   │
│                                                                  │
└──────────────────────────────────────────────────────────────────┘
```

### Log File Format

```json
// .appos/logs/rules/execution/2026-02-07.jsonl
{"ts":"2026-02-07T14:30:00.123Z","exec_id":"e001","app":"crm","obj":"rules.calculate_discount","user":"user_1","dur_ms":11,"status":"ok","deps":["constants.TAX_RATE","rules.get_tier_discount"]}
{"ts":"2026-02-07T14:30:01.456Z","exec_id":"e002","app":"crm","obj":"rules.calculate_discount","user":"user_2","dur_ms":14,"status":"ok","deps":["constants.TAX_RATE","rules.get_tier_discount"]}

// .appos/logs/rules/performance/2026-02-07.jsonl
{"ts":"2026-02-07T14:30:00.123Z","exec_id":"e001","app":"crm","obj":"rules.calculate_discount","dur_ms":11,"breakdown":{"security_check_ms":1,"execution_ms":9,"logging_ms":1}}

// .appos/logs/rules/security/2026-02-07.jsonl
{"ts":"2026-02-07T14:30:02.789Z","exec_id":"e003","app":"crm","obj":"rules.calculate_discount","user":"user_3","action":"use","result":"DENIED","groups":["support"],"required":["crm_admins"]}
```

### Why Files for System Logs

| Consideration | Files | DB |
|---------------|-------|-----|
| Write throughput | ✓ Fast append | ✗ Write overhead |
| No DB dependency | ✓ Works even if DB is down | ✗ DB required |
| Log volume | ✓ Handles high volume cheaply | ✗ DB bloat |
| Grep/search | ✓ Good with structured JSON | ✓ SQL queries |
| Rotation/cleanup | ✓ Simple file rotation | ✗ Needs maintenance |
| AI parsing | ✓ JSON files easy to read | ✓ Also easy |
| Admin console | ✓ Stream + filter files | ✓ Query DB |

**Decision:** System logs in files (Tier 1) for sustainability and performance. App business logs in DB (Tier 2) for structured querying.

### Metrics Collection

```python
# Every decorated object (@expression_rule, @step, @process) automatically collects:

# 1. Execution count (24h, 7d, 30d)
# 2. Duration (avg, min, max, p50, p95, p99)
# 3. Error rate
# 4. Dependency count
# 5. Last execution timestamp

# Stored in: .appos/logs/{type}/performance/{date}.jsonl
# Aggregated on demand by admin console or AI queries
```

### Async Non-Blocking Log Pipeline

```
┌──────────────────────────────────────────────────────────────────┐
│                 ASYNC NON-BLOCKING LOGGING                       │
├──────────────────────────────────────────────────────────────────┤
│                                                                  │
│  Only SECURITY CHECK blocks the execution flow (needs result).  │
│  All other logging is fire-and-forget:                          │
│                                                                  │
│  1. Decorator wraps execution with timing                       │
│  2. Security check → synchronous (Redis cache, <5ms warm)       │
│  3. Execution log entry → pushed to in-memory Queue             │
│  4. Performance log entry → pushed to in-memory Queue           │
│  5. Background daemon thread flushes Queue to .jsonl files      │
│     every 100ms or every 50 entries (whichever first)           │
│                                                                  │
│  Implementation: Python logging.handlers.QueueHandler           │
│  + QueueListener with per-type file handlers                    │
│                                                                  │
└──────────────────────────────────────────────────────────────────┘
```

### Log Rotation & Cleanup

```yaml
# Configured in appos.yaml → logging section
logging:
  rotation: "daily"                  # "daily" | "hourly" | "size"
  max_file_size_mb: 100              # for size-based rotation
  retention:
    execution_days: 90
    performance_days: 30
    security_days: 365               # security kept longest (compliance)
  cleanup_schedule: "0 2 * * *"      # nightly cleanup cron
```

> All rotation/retention settings editable from admin console → Settings → Logging.

### Payload Opt-In

Web API and Integration logs do **not** include request/response bodies by default (size, PII concerns). Opt-in per object:

```python
@web_api(name="debug_api", method="POST", path="/debug", log_payload=True)
@integration(name="debug_int", connected_system="stripe", log_payload=True)
```

When `log_payload=True`, body is logged to execution log. Encrypted at rest if Connected System is marked sensitive.

---

## 15. Multi-App Project Structure

### Folder Structure

```
my_project/
│
├── rxconfig.py                    # Reflex configuration (single app entry point)
├── appos.yaml                     # Platform-level configuration
├── requirements.txt               # Python dependencies
│
├── appos/                         # AppOS engine (the platform itself)
│   ├── __init__.py
│   ├── engine/
│   │   ├── __init__.py
│   │   ├── runtime.py             # Centralized Runtime Engine
│   │   ├── namespaces.py          # Auto-Import SecureAutoImportNamespace
│   │   ├── security.py            # Security engine, permission checks
│   │   ├── registry.py            # Object registry (compiled state)
│   │   ├── context.py             # ExecutionContext, ProcessContext
│   │   ├── dependency.py          # NetworkX dependency graph
│   │   └── cache.py               # Redis permission/object cache
│   │
│   ├── decorators/
│   │   ├── __init__.py
│   │   ├── record.py              # @record decorator
│   │   ├── expression_rule.py     # @expression_rule decorator
│   │   ├── process.py             # @process decorator
│   │   ├── step.py                # step() function
│   │   ├── constant.py            # @constant decorator
│   │   ├── interface.py           # @interface decorator
│   │   ├── page.py                # @page decorator
│   │   ├── site.py                # @site decorator
│   │   ├── integration.py         # @integration decorator
│   │   ├── web_api.py             # @web_api decorator
│   │   ├── connected_system.py    # @connected_system decorator
│   │   └── translation_set.py     # @translation_set decorator
│   │
│   ├── db/
│   │   ├── __init__.py
│   │   ├── base.py                # SQLAlchemy base, mixins (Audit, SoftDelete)
│   │   ├── platform_models.py     # User, Group, App, ProcessInstance tables
│   │   └── session.py             # DB session management
│   │
│   ├── admin/                     # Admin console (built-in Reflex pages)
│   │   ├── __init__.py
│   │   ├── pages/
│   │   │   ├── login.py
│   │   │   ├── dashboard.py
│   │   │   ├── users.py
│   │   │   ├── groups.py
│   │   │   ├── apps.py
│   │   │   ├── connections.py
│   │   │   ├── records_browser.py
│   │   │   ├── object_browser.py
│   │   │   ├── logs.py
│   │   │   ├── metrics.py
│   │   │   ├── processes.py
│   │   │   ├── translations.py
│   │   │   └── documents.py
│   │   ├── components/            # Reusable admin UI components
│   │   └── state.py               # Admin Reflex state
│   │
│   ├── ui/
│   │   ├── __init__.py
│   │   ├── components.py          # DataTable, Form, Field, Button, etc.
│   │   ├── reflex_bridge.py       # AppOS components → Reflex components
│   │   └── renderer.py            # InterfaceRenderer
│   │
│   ├── generators/
│   │   ├── __init__.py
│   │   ├── model_generator.py     # Pydantic → SQLAlchemy
│   │   ├── migration_generator.py # Alembic integration
│   │   ├── service_generator.py   # CRUD service generation
│   │   ├── api_generator.py       # REST endpoint generation
│   │   └── interface_generator.py # UI generation from Records
│   │
│   └── process/
│       ├── __init__.py
│       ├── executor.py            # Celery task execution
│       ├── scheduler.py           # Celery Beat scheduling
│       └── instance.py            # ProcessInstance management
│
├── appos/platform_rules/          # Prebuilt platform rules (see AppOS_PlatformRules_Reference.md)
│   ├── __init__.py
│   ├── user_rules.py              # get_current_user, get_user, create_user, update_user, change_password, reset_password, deactivate_user
│   └── group_rules.py             # get_user_groups, get_group_members, create_group, add/remove_user_to/from_group, deactivate_group
│
├── appos/platform_connected_systems/  # Global Connected System definitions
│   ├── __init__.py
│   ├── crm_database.py            # @connected_system configs
│   └── stripe_api.py
│
├── apps/                          # Developer applications
│   │
│   ├── crm/                       # Example: CRM application
│   │   ├── __init__.py
│   │   ├── app.yaml               # App config (name, groups, theme, DB)
│   │   │
│   │   ├── records/               # Data models (Pydantic @record)
│   │   │   ├── __init__.py
│   │   │   ├── customer.py
│   │   │   ├── order.py
│   │   │   └── product.py
│   │   │
│   │   ├── rules/                 # Expression rules
│   │   │   ├── __init__.py
│   │   │   ├── pricing.py
│   │   │   ├── validation.py
│   │   │   └── notifications.py
│   │   │
│   │   ├── constants/             # Constants
│   │   │   ├── __init__.py
│   │   │   └── config.py
│   │   │
│   │   ├── steps/                 # Step definitions (if standalone)
│   │   │   └── __init__.py
│   │   │
│   │   ├── processes/             # Process orchestrators
│   │   │   ├── __init__.py
│   │   │   ├── onboarding.py
│   │   │   └── order_processing.py
│   │   │
│   │   ├── integrations/          # Outbound API integrations
│   │   │   ├── __init__.py
│   │   │   └── stripe.py
│   │   │
│   │   ├── web_apis/              # Inbound API endpoints
│   │   │   ├── __init__.py
│   │   │   └── customer_api.py
│   │   │
│   │   │
│   │   ├── pages/                 # Reflex pages
│   │   │   ├── __init__.py
│   │   │   ├── dashboard.py
│   │   │   ├── customers.py
│   │   │   └── orders.py
│   │   │
│   │   ├── interfaces/            # Custom UI (overrides generated)
│   │   │   ├── __init__.py
│   │   │   ├── customer_forms.py
│   │   │   └── dashboards.py
│   │   │
│   │   ├── translation_sets/       # i18n
│   │   │   ├── __init__.py
│   │   │   └── labels.py
│   │   │
│   │   └── runtime/               # Runtime files (gitignored)
│   │       └── documents/         # Uploaded files organized by folder
│   │           ├── invoices/
│   │           └── contracts/
│   │
│   └── finance/                   # Another app — same structure
│       ├── __init__.py
│       ├── app.yaml
│       ├── records/
│       ├── rules/
│       └── ...
│
├── .appos/                        # Platform runtime data (gitignored)
│   ├── logs/                      # System log files — per object type (Tier 1)
│   │   ├── rules/
│   │   │   ├── execution/
│   │   │   │   └── 2026-02-12.jsonl
│   │   │   ├── performance/
│   │   │   │   └── 2026-02-12.jsonl
│   │   │   └── security/
│   │   │       └── 2026-02-12.jsonl
│   │   ├── processes/
│   │   │   ├── execution/  ├── performance/  └── security/
│   │   ├── steps/
│   │   │   ├── execution/  └── performance/
│   │   ├── integrations/
│   │   │   ├── execution/  ├── performance/  └── security/
│   │   ├── web_apis/
│   │   │   ├── execution/  ├── performance/  └── security/
│   │   ├── records/
│   │   │   ├── execution/  ├── performance/  └── security/
│   │   ├── interfaces/
│   │   │   ├── execution/  ├── performance/  └── security/
│   │   ├── pages/
│   │   │   ├── execution/  ├── performance/  └── security/
│   │   ├── constants/
│   │   │   ├── execution/  └── security/
│   │   ├── connected_systems/
│   │   │   ├── execution/  ├── performance/  └── security/
│   │   ├── documents/
│   │   │   ├── execution/  └── security/
│   │   ├── translation_sets/
│   │   │   ├── execution/  └── security/
│   │   ├── folders/
│   │   │   ├── execution/  └── security/
│   │   └── validation/
│   │       └── appos-check-*.json
│   │
│   ├── runtime/
│   │   ├── dependencies/          # JSON dependency graph files (AI-readable)
│   │   │   ├── crm.rules.calculate_discount.json
│   │   │   ├── crm.records.customer.json
│   │   │   └── ...
│   │   └── cache/                 # Compiled object cache
│   │
│   └── generated/                 # Auto-generated code
│       ├── models/                # SQLAlchemy models
│       ├── services/              # CRUD services
│       ├── interfaces/            # Auto-generated UIs
│       └── migrations/            # Alembic migrations
│
├── migrations/                    # Alembic migrations
│   ├── env.py
│   └── versions/
│
└── tests/
    ├── test_rules.py
    ├── test_records.py
    ├── test_processes.py
    └── test_integrations.py
```

### Naming Convention (Recommended, Not Mandatory)

| Convention | Example | Purpose |
|------------|---------|---------|
| App prefix | `CRM_TAX_RATE`, `FIN_FISCAL_YEAR` | Distinguish constants across apps |
| Snake case | `calculate_discount`, `customer_tier` | All object names |
| Module grouping | `pricing.py` contains all pricing rules | Related rules in one file |
| Record singular | `Customer`, `Order` (not `Customers`) | Pydantic model naming |

---

## 16. Configuration

### Platform Config (appos.yaml)

```yaml
# appos.yaml — platform-level configuration

platform:
  name: "My Company Platform"
  version: "2.0.0"
  environment: "dev"  # dev | staging | prod

database:
  # Core platform database (users, groups, process instances)
  url: "postgresql://user:pass@localhost:5432/appos_core"
  pool_size: 10
  max_overflow: 20
  pool_timeout: 30
  pool_recycle: 1800
  pool_pre_ping: true

redis:
  url: "redis://localhost:6379/0"
  # Channels:
  # 0: Celery broker
  # 1: Celery results
  # 2: Permission cache
  # 3: Object cache
  # 4: Session store

celery:
  broker: "redis://localhost:6379/0"
  result_backend: "redis://localhost:6379/1"
  beat_schedule_check: 60  # seconds
  concurrency: 4            # worker pool size (processes per worker node)
  autoscale:
    enabled: true
    min: 4                  # minimum pool size
    max: 16                 # maximum pool size
  queues:
    - celery               # default queue
    - process_steps        # dedicated queue for process step execution
    - scheduled            # scheduled / cron tasks

security:
  session_timeout: 3600  # seconds
  idle_timeout: 1800     # seconds (30 min idle)
  max_concurrent_sessions: 5  # per user
  password_min_length: 8
  permission_cache_ttl: 300  # seconds (5 minutes)
  max_login_attempts: 5

logging:
  level: INFO
  format: json
  directory: logs
  rotation:
    strategy: daily
    max_file_size_mb: 100
    compress_after_days: 7
  retention:
    execution_days: 90         # execution logs
    performance_days: 30       # performance logs
    security_days: 365         # security/access logs (compliance)
  cleanup_schedule: "0 2 * * *"  # nightly cleanup cron
  async_queue:
    flush_interval_ms: 100
    flush_batch_size: 50
    max_queue_size: 10000

process_instances:
  archive_after_days: 90       # move completed instances to archive partition
  partition_range: monthly     # monthly partitions for process_instance table

documents:
  max_upload_size_mb: 50       # global max upload size (per-file)

ui:
  admin_theme:
    primary_color: "#1F2937"
    font_family: "Inter"
  default_pagination: 25

apps:
  - crm
  - finance
```

### App Config (app.yaml)

```yaml
# apps/crm/app.yaml

app:
  name: "Customer Relationship Manager"
  short_name: "crm"
  version: "1.0.0"
  description: "CRM for sales and support teams"

groups:
  - sales
  - support
  - crm_admins

# Three-tier inherited security defaults
security:
  defaults:
    logic:    # inherited by: rules, constants
      groups: ["sales", "support", "crm_admins"]
    ui:       # inherited by: interfaces, pages, translation_sets
      groups: ["sales", "support", "crm_admins"]
  # Records, processes, web_apis, integrations → always explicit per-object

db_connected_system: "crm_database"   # convenience pointer

theme:
  primary_color: "#3B82F6"
  secondary_color: "#1E40AF"
  accent_color: "#DBEAFE"
  font_family: "Inter"
  border_radius: "8px"

environment: "dev"

features:
  audit: true
  soft_delete: true
  document_versioning: true

logging:
  # App-specific runtime logs → DB
  process_logging: true
  audit_logging: true
  event_logging: true
```

---

## 17. Implementation Phases

### Phase 1: Core Engine (Weeks 1-4)

```
┌──────────────────────────────────────────────────────────────────┐
│ PHASE 1: CORE ENGINE                                             │
├──────────────────────────────────────────────────────────────────┤
│                                                                  │
│  ✓ Auto-Import System                                           │
│    - SecureAutoImportNamespace                                   │
│    - Global namespace injection (records, constants, rules, etc.)│
│    - Module caching                                              │
│                                                                  │
│  ✓ Security Engine                                               │
│    - User & Group models (PostgreSQL)                            │
│    - user_type field (basic/system_admin/service_account)        │
│    - Default system_admin group bootstrap on appos init          │
│    - SecurityPolicy & unified 6-permission model                 │
│    - object_permission table (see Permissions Reference)         │
│    - Redis permission cache (TTL=5min)                           │
│    - Session-based auth (Redis DB 4), not JWT                    │
│    - AppOSError hierarchy (see Permissions Reference)            │
│                                                                  │
│  ✓ Execution Context                                             │
│    - contextvars-based ExecutionContext                           │
│    - Thread-safe user/group/app tracking                         │
│    - Request-scoped lifecycle                                    │
│                                                                  │
│  ✓ Object Registry                                               │
│    - Register/retrieve objects by type, app, and name            │
│    - Object metadata storage                                     │
│                                                                  │
│  ✓ Centralized Runtime (Basic)                                   │
│    - Per-object-type file loggers (rules/, processes/, etc.)     │
│    - Async log queue + background flush thread                   │
│    - Dependency tracking (NetworkX in-memory)                    │
│    - JSON dependency file persistence                            │
│                                                                  │
│  ✓ Admin Console (Minimal)                                       │
│    - Login screen                                                │
│    - User management (CRUD)                                      │
│    - Group management (CRUD + user assignment)                   │
│                                                                  │
│  Deliverable: Working auto-import with security and logging.    │
└──────────────────────────────────────────────────────────────────┘
```

### Phase 2: Data Layer (Weeks 5-7)

```
┌──────────────────────────────────────────────────────────────────┐
│ PHASE 2: DATA LAYER                                              │
├──────────────────────────────────────────────────────────────────┤
│                                                                  │
│  ✓ Connected System                                              │
│    - @connected_system decorator                                 │
│    - Type support: database, rest_api, ftp, smtp, imap, custom   │
│    - Global scope (not app-bound), secured via groups only       │
│    - Connection pool config (max_overflow, pool_timeout, etc.)   │
│    - Credential encryption (stored in DB, managed via admin)     │
│    - Environment overrides (dev/staging/prod)                    │
│    - Health check mechanism                                      │
│                                                                  │
│  ✓ Record System                                                 │
│    - @record decorator (Pydantic BaseModel)                      │
│    - Pydantic → SQLAlchemy model generation                      │
│    - Relationship support (has_many, belongs_to, has_one)        │
│    - Meta configuration (audit, soft_delete, permissions)        │
│    - Alembic migration auto-generation                           │
│    - CRUD service generation (RecordService base)                │
│    - Record event hooks (on_create, on_update, on_delete)        │
│                                                                  │
│  ✓ Constant                                                      │
│    - @constant decorator                                         │
│    - Environment-specific values                                 │
│    - Object reference support (dynamic dispatch)                 │
│    - Validation support                                          │
│                                                                  │
│  ✓ Admin Console Extensions                                      │
│    - Connected System management (credentials, health checks)    │
│    - Records browser                                             │
│    - App management                                              │
│                                                                  │
│  Deliverable: Records auto-generate DB schema + CRUD + APIs.    │
└──────────────────────────────────────────────────────────────────┘
```

### Phase 3: Logic Layer (Weeks 8-10)

```
┌──────────────────────────────────────────────────────────────────┐
│ PHASE 3: LOGIC LAYER                                             │
├──────────────────────────────────────────────────────────────────┤
│                                                                  │
│  ✓ Expression Rule                                               │
│    - @expression_rule decorator                                  │
│    - Input/output declarations                                   │
│    - Execution logging & performance tracking                    │
│    - Dependency auto-tracking via auto-import                    │
│    - ctx.input(), ctx.output(), local variables                  │
│    - Cross-rule calling (auto-import resolved)                   │
│    - Record querying within rules                                │
│                                                                  │
│  ✓ Step                                                          │
│    - step() function with retry, timeout, condition              │
│    - Input/output mapping to process variables                   │
│    - Error handling (fail/skip/goto)                             │
│    - fire_and_forget=True option (async, non-blocking)           │
│                                                                  │
│  ✓ Process                                                       │
│    - @process decorator                                          │
│    - display_name template (e.g., "Onboard: {customer_id}")     │
│    - ProcessContext (ctx.var across steps)                        │
│    - Variable visibility (logged/hidden/sensitive)               │
│    - ProcessInstance DB model (partitioned by started_at)        │
│    - Separate process_step_log table (not JSON array)            │
│    - parallel() construct → Celery group                         │
│    - Celery integration (task execution, chaining)               │
│    - Triggers: event(), schedule(), manual                       │
│    - Celery Beat for scheduled processes                         │
│                                                                  │
│  ✓ Admin Console Extensions                                      │
│    - Process monitor (running/completed/failed)                  │
│    - Step-by-step execution viewer                               │
│    - Expression Rule browser with metrics                        │
│                                                                  │
│  Deliverable: Full logic layer with processes and scheduling.   │
└──────────────────────────────────────────────────────────────────┘
```

### Phase 4: UI Layer (Weeks 11-13)

```
┌──────────────────────────────────────────────────────────────────┐
│ PHASE 4: UI LAYER                                                │
├──────────────────────────────────────────────────────────────────┤
│                                                                  │
│  ✓ Interface Components                                          │
│    - @interface decorator                                        │
│    - Components are plain functions (not object type)            │
│    - Page → Interface → Component hierarchy                      │
│    - Component library (DataTable, Form, Field, Button, etc.)    │
│    - InterfaceRenderer (AppOS → Reflex, minimal abstraction)     │
│    - Developers can use raw Reflex components alongside AppOS    │
│                                                                  │
│  ✓ Interface Auto-Generation from Records                        │
│    - List / Create / Edit / View interfaces                      │
│    - Field type → component mapping                              │
│    - Override mechanism (@interface.extend)                       │
│                                                                  │
│  ✓ Page & Site                                                   │
│    - @page decorator with route, permissions, state              │
│    - @site decorator with navigation structure                   │
│    - Security inherited from app.yaml security.defaults.ui       │
│    - Single-port Reflex routing (/{app_short_name}/*)            │
│                                                                  │
│  ✓ Per-App Theming                                               │
│    - Theme config in app.yaml                                    │
│    - Reflex theme provider per app prefix                        │
│                                                                  │
│  ✓ Form Handling                                                 │
│    - Form submission → Record save                               │
│    - Validation integration (Pydantic)                           │
│    - Process trigger on submit                                   │
│                                                                  │
│  Deliverable: Auto-generated CRUD UIs, multi-app single port.   │
└──────────────────────────────────────────────────────────────────┘
```

### Phase 5: External Layer (Weeks 14-16)

```
┌──────────────────────────────────────────────────────────────────┐
│ PHASE 5: EXTERNAL LAYER                                          │
├──────────────────────────────────────────────────────────────────┤
│                                                                  │
│  ✓ Integration                                                   │
│    - @integration decorator                                      │
│    - Connected System resolution                                 │
│    - Request templating                                          │
│    - Response mapping                                            │
│    - Retry logic with backoff                                    │
│    - Error handling per status code                              │
│                                                                  │
│  ✓ Web API                                                       │
│    - @web_api decorator                                          │
│    - Route registration (/api/{app}/{version}/{path})            │
│    - Auth (Connected System based or custom)                     │
│    - Service account auth flow (API key/OAuth → service_account) │
│    - Request validation (Pydantic schema)                        │
│    - Process/Rule handler mapping                                │
│    - Async: True returns instance_id immediately                 │
│    - Rate limiting                                               │
│                                                                  │
│  ✓ Document Management                                           │
│    - Document record with versioning                             │
│    - Reflex rx.upload integration                                │
│    - Folder management (DB-driven, auto-created dirs)            │
│    - MIME type validation, size limits                            │
│                                                                  │
│  ✓ Translation Set                                               │
│    - @translation_set decorator                                  │
│    - Language resolution from ExecutionContext                    │
│    - Interface label binding                                     │
│    - String interpolation                                        │
│                                                                  │
│  Deliverable: Full inbound/outbound API + documents + i18n.     │
└──────────────────────────────────────────────────────────────────┘
```

### Phase 6: Polish & Production Readiness (Weeks 17-20)

```
┌──────────────────────────────────────────────────────────────────┐
│ PHASE 6: POLISH & PRODUCTION READINESS                           │
├──────────────────────────────────────────────────────────────────┤
│                                                                  │
│  ✓ Complete Admin Console                                        │
│    - All screens finalized                                       │
│    - Log viewer with advanced filtering (per-type logs)          │
│    - Metrics dashboard with charts                               │
│    - Object browser with dependency visualization                │
│    - Document/folder browser                                     │
│    - Translation set editor                                      │
│    - Settings: DB connection, YAML editor, session/cache config  │
│    - Active sessions view + cache flush button                   │
│    - Theme editor per app                                        │
│                                                                  │
│  ✓ AI Query Interface                                            │
│    - Structured query endpoint                                   │
│    - Dependency graph queries                                    │
│    - Performance analysis                                        │
│    - Security audit queries                                      │
│    - Impact analysis for changes                                 │
│                                                                  │
│  ✓ CLI Tools                                                     │
│    - appos init (scaffold new project + bootstrap system_admin)  │
│    - appos new-app {name} (create new app)                       │
│    - appos generate (run generators)                             │
│    - appos migrate (run migrations)                              │
│    - appos run (start Reflex server)                             │
│    - appos check (validate objects, deps, AppOS-only imports)    │
│    - appos impact {object_ref} (dependency impact analysis)      │
│                                                                  │
│  ✓ Performance Optimization                                      │
│    - Redis cache tuning                                          │
│    - Lazy loading optimization                                   │
│    - Connection pooling for Connected Systems                    │
│    - Log file write batching (async queue)                       │
│                                                                  │
│  ✓ Platform Rules                                                │
│    - Prebuilt user/group management rules                        │
│    - See AppOS_PlatformRules_Reference.md                        │
│                                                                  │
│  ✓ Testing & Documentation                                       │
│    - Unit tests for all decorators                               │
│    - Integration tests for auto-import + security                │
│    - Process execution tests                                     │
│    - Getting started guide                                       │
│    - API reference                                               │
│    - Example apps (CRM, Finance)                                 │
│                                                                  │
│  Deliverable: Production-ready platform with documentation.     │
└──────────────────────────────────────────────────────────────────┘
```

---

## Quick Reference Card

```
┌──────────────────────────────────────────────────────────────────┐
│                   APPOS v2.1 QUICK REFERENCE                     │
├──────────────────────────────────────────────────────────────────┤
│                                                                  │
│  ZERO-IMPORT ACCESS (auto-resolved, security-checked):          │
│  records.customer.get(id)     constants.TAX_RATE()              │
│  rules.calculate(...)         integrations.stripe.execute(...)   │
│  translations.labels.get(key)                                    │
│  processes.my_process.start(inputs={...})                        │
│  finance.rules.calc(...)      # cross-app (prefix = declaration)│
│  platform.rules.get_current_user(ctx)   # platform rules       │
│  ctx.user.preferred_language  # auto-detected from Accept-Lang  │
│                                                                  │
│  ─────────────────────────────────────────────────────────────   │
│                                                                  │
│  CONSTANT                                                        │
│  @constant                                                       │
│  def TAX_RATE() -> float:                                       │
│      return {"default": 0.18, "dev": 0.0, "prod": 0.18}        │
│  @constant  # object_ref → point to any executable object       │
│  def DEFAULT_PROCESS() -> str:                                   │
│      return {"default": "crm.processes.onboard_customer"}       │
│                                                                  │
│  ─────────────────────────────────────────────────────────────   │
│                                                                  │
│  RECORD (Pydantic)                                               │
│  @record                                                         │
│  class Customer(BaseModel):                                      │
│      name: str = Field(max_length=100)                           │
│      orders: List["Order"] = has_many("Order")                  │
│      class Meta:                                                 │
│          audit = True  # → auto audit_log table                 │
│          permissions = {"view": ["sales"], "create": [...],     │
│              "update": [...], "delete": [...], "use": [...],     │
│              "admin": ["crm_admins"]}                            │
│          row_security_rule = "rules.customer_row_filter"        │
│                                                                  │
│  ─────────────────────────────────────────────────────────────   │
│                                                                  │
│  EXPRESSION RULE                                                 │
│  @expression_rule(inputs=[...], outputs=[...])                  │
│  def my_rule(ctx):                                               │
│      val = records.customer.get(ctx.input("id"))                │
│      rate = constants.TAX_RATE()                                │
│      other = rules.other_rule(x=1)                              │
│      ctx.output("result", val)                                   │
│      return ctx.outputs()                                        │
│                                                                  │
│  ─────────────────────────────────────────────────────────────   │
│                                                                  │
│  UNIFIED DISPATCH (type-agnostic object ref execution)          │
│  ref = constants.MY_OBJECT_REF()  # rule, process, or integ    │
│  result = engine.dispatch(ref, inputs={...})                    │
│  # Auto-detects target type → calls correct executor            │
│                                                                  │
│  ─────────────────────────────────────────────────────────────   │
│                                                                  │
│  PROCESS + STEP                                                  │
│  @process(triggers=[event("records.customer.on_create")],       │
│           display_name="Onboard Customer")                       │
│  def my_process(ctx):                                            │
│      ctx.var("order_id", ctx.input("id"), logged=True)          │
│      ctx.var("secret", token, sensitive=True)                   │
│      return [                                                    │
│          step("validate", rule="validate_order"),               │
│          step("charge", rule="charge_payment",                  │
│               condition="ctx.var.is_valid", retry_count=3),     │
│          step("notify", rule="send_email",                      │
│               fire_and_forget=True),  # non-blocking            │
│          step("confirm", rule="send_confirmation",              │
│               on_error="skip"),                                  │
│          parallel("batch_ops", steps=[                           │
│              step("a", rule="task_a"),                           │
│              step("b", rule="task_b"),                           │
│          ]),                                                     │
│      ]                                                           │
│                                                                  │
│  ─────────────────────────────────────────────────────────────   │
│                                                                  │
│  CONNECTED SYSTEM                                                │
│  @connected_system(name="stripe_api", type="rest_api")          │
│  def stripe_api():                                               │
│      return {"default": {...}, "auth": {...},                   │
│              "environment_overrides": {...}}                     │
│                                                                  │
│  ─────────────────────────────────────────────────────────────   │
│                                                                  │
│  INTEGRATION (outbound)                                          │
│  @integration(name="charge", connected_system="stripe_api",    │
│               log_payload=True)   # opt-in payload logging      │
│  def create_charge():                                            │
│      return {"method": "POST", "path": "/charges",             │
│              "body": {...}, "response_mapping": {...}}          │
│                                                                  │
│  ─────────────────────────────────────────────────────────────   │
│                                                                  │
│  WEB API (inbound)                                               │
│  @web_api(method="GET", path="/customers/{id}",                │
│           log_payload=True)       # opt-in payload logging      │
│  def get_customer(): return {"handler": "rules.get_customer"}   │
│  @web_api(method="POST", path="/webhook", auth="service_acct") │
│  def webhook(): return {"handler": "rules.handle_hook"}        │
│                                                                  │
│  ─────────────────────────────────────────────────────────────   │
│                                                                  │
│  PAGE + SITE                                                     │
│  @page(route="/dashboard", interface="Dashboard")               │
│  @site(name="CRM")                                              │
│  def crm(): return {"pages": [...], "navigation": [...]}       │
│                                                                  │
│  ─────────────────────────────────────────────────────────────   │
│                                                                  │
│  TRANSLATION SET                                                 │
│  @translation_set(name="labels", app="crm")                    │
│  def labels(): return {"save": {"en": "Save", "fr": "..."}}    │
│  # translations.labels.get("save")  → auto picks user lang     │
│  # translations.labels.get("save", lang="fr")  → explicit lang │
│                                                                  │
│  ─────────────────────────────────────────────────────────────   │
│                                                                  │
│  PERMISSION TIERS                                                │
│  Tier 1: Record, Process, Web API, Integration → always explicit│
│  Tier 2: Rule, Constant → inherits security.defaults.logic      │
│  Tier 3: Interface, Page, TranslationSet →                      │
│          inherits security.defaults.ui                           │
│  Document, Folder → inherits parent Record's permissions        │
│                                                                  │
│  ─────────────────────────────────────────────────────────────   │
│                                                                  │
│  ERROR HIERARCHY                                                 │
│  AppOSError (base)                                               │
│    ├── AppOSSecurityError  — permission/auth failures           │
│    ├── AppOSDispatchError  — object resolution failures         │
│    ├── AppOSValidationError — input/schema/MIME violations      │
│    ├── AppOSTimeoutError   — step/integration timeouts          │
│    └── AppOSIntegrationError — external system failures         │
│  All include: execution_id, object_ref, object_type             │
│                                                                  │
│  ─────────────────────────────────────────────────────────────   │
│                                                                  │
│  CLI COMMANDS                                                    │
│  appos init              — scaffold new platform project        │
│  appos check             — validate imports (AppOS-only)        │
│  appos impact {obj_ref}  — show what depends on an object      │
│  appos migrate           — run DB migrations                    │
│                                                                  │
│  ─────────────────────────────────────────────────────────────   │
│                                                                  │
│  LOG STRUCTURE                                                   │
│  .appos/logs/{type}/{category}/{date}.jsonl                     │
│  Categories: execution/ performance/ security/                   │
│  Retention: exec=90d, perf=30d, security=365d                   │
│                                                                  │
│  ─────────────────────────────────────────────────────────────   │
│                                                                  │
│  17 OBJECT TYPES:                                                │
│  Platform: User, Group, App, Connected System                    │
│  Data:     Constant, Record, Document, Folder                   │
│  Logic:    Expression Rule, Step, Process                        │
│  External: Integration, Web API                                  │
│  UI:       Interface, Page, Site, Translation Set               │
│                                                                  │
└──────────────────────────────────────────────────────────────────┘
```

---

## Summary

**AppOS v2.1** is a Python-first low-code platform that:

1. **Zero-Import DX** — Developers never write imports. Auto-import layer resolves everything with security checks and dependency tracking.
2. **Security-First** — Every object access validated against user groups via unified 6-permission model (view/use/create/update/delete/admin). Cached in Redis for performance (100-200ms cold, <5ms warm). Three-tier inherited security. Wildcard permissions for bulk assignment.
3. **AI-Native Debugging** — Pre-recorded logs, metrics, and dependency graphs in structured JSON. AI can query runtime state for dependencies, performance bottlenecks, security violations, and impact analysis (`appos impact`).
4. **Multi-App Architecture** — Shared users/groups, app-level isolation via group association. Single-port Reflex routing.
5. **17 Object Types** — Comprehensive coverage: User, Group, App, Connected System, Constant, Record, Expression Rule, Step, Process, Integration, Web API, Interface, Page, Site, Document, Folder, Translation Set.
6. **Auto-Generation** — Records auto-generate SQLAlchemy models, migrations, CRUD services, REST APIs, and Reflex UI interfaces. Optional `audit_log` table per record.
7. **Pydantic-Native** — Records use standard Pydantic BaseModel. Type hints drive everything.
8. **Process Engine** — Multi-step workflows via Celery. Process-level variables accessible across all steps with visibility control. `parallel()` for concurrent steps, `fire_and_forget` for non-blocking. `display_name` for admin console. ProcessInstance partitioned monthly with archive config.
9. **Per-Category Logging** — System logs split into execution/performance/security sub-folders per object type (async queue, non-blocking). Differentiated retention: execution=90d, performance=30d, security=365d (compliance). App business logs in DB (queryable). Payload opt-in for integrations/web APIs.
10. **Admin Console** — Built-in Reflex app for user/group/app management, log viewing, metrics dashboards, object browsing, platform settings, session management, and theme editor.
11. **Connected Systems** — Unified external connection management (DB, APIs, FTP, SMTP) with admin-managed credentials, environment overrides, and connection pool tuning.
12. **Error Hierarchy** — Structured `AppOSError` with 5 subtypes (SecurityError, DispatchError, ValidationError, TimeoutError, IntegrationError), each carrying `execution_id`, `object_ref`, and `object_type` for AI-friendly debugging.
13. **Reflex Integration** — Single Reflex instance, per-app theming, auto-generated UI, single-port routing. Raw Reflex components usable alongside AppOS components.

**Goal:** Python developers + AI assistants get 50%+ acceleration through organized structure, zero-import DX, auto-generation, centralized observability, and AI-queryable runtime — without learning a new language.

---

*Document Version: 2.1 | Created: February 7, 2026 | Updated: February 12, 2026 | Previous: v2.0, v1.0*
