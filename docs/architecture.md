# AppOS Architecture Guide

> **Version:** 2.0  
> **Last Updated:** February 14, 2026

---

## 1. System Architecture

AppOS is organized as a layered architecture with clear separation of concerns.

### Layer Diagram

```
┌──────────────────────────────────────────────────────────────────────┐
│                        PRESENTATION LAYER                            │
│  Reflex UI (Admin Console + App Pages) + REST APIs (@web_api)        │
├──────────────────────────────────────────────────────────────────────┤
│                        APPLICATION LAYER                             │
│  Apps (crm, finance, ...)  →  Decorators (@record, @process, ...)   │
├──────────────────────────────────────────────────────────────────────┤
│                        ENGINE LAYER                                  │
│  Runtime │ Security │ Registry │ DependencyGraph │ Cache │ Logging   │
├──────────────────────────────────────────────────────────────────────┤
│                        INFRASTRUCTURE LAYER                          │
│  PostgreSQL │ Redis │ Celery │ File System │ NetworkX                │
└──────────────────────────────────────────────────────────────────────┘
```

### Four-State Model

1. **DEFINITION STATE** — Python source files in `apps/`
2. **COMPILED STATE** — Parsed objects in `ObjectRegistryManager` (memory)
3. **RUNTIME STATE** — `ExecutionContext` per request (contextvars, thread-safe)
4. **PROCESS STATE** — `ProcessContext` per process instance (DB-backed)

---

## 2. Request Lifecycle

```
Browser/API Client
       │
       ▼
┌─────────────────┐
│  Auth Middleware  │ → validate_session() → set_execution_context()
└────────┬────────┘
         │
         ▼
┌─────────────────┐
│  Reflex Handler  │ or @web_api handler
│  / rx.State      │
└────────┬────────┘
         │
         ▼
┌─────────────────┐
│  Auto-Import     │ ← SecureAutoImportNamespace
│  Namespace       │    1. Security check (blocking)
│                  │    2. Dependency tracking (non-blocking)
│                  │    3. Lazy module load + cache
└────────┬────────┘
         │
         ▼
┌─────────────────┐     ┌──────────────┐
│  runtime.dispatch│────▶│  Executor    │ (rule/process/integration/webapi)
│  (object_ref)   │     │              │
└────────┬────────┘     └──────────────┘
         │
         ▼
   ┌──────────┐
   │  Logging  │ → JSONL files + DB tables
   └──────────┘
```

---

## 3. Security Architecture

### Permission Model

Six permissions with hierarchy:

```
admin ⊃ {admin, delete, update, create, use, view}
delete ⊃ {delete, view}
update ⊃ {update, view}
create ⊃ {create, view}
use    ⊃ {use, view}
view   ⊃ {view}
```

### Three-Tier Inheritance

1. **App defaults** — `app.yaml` → `security.defaults` (all objects inherit unless overridden)
2. **Inheriting objects** — Objects without explicit `permissions` in Meta
3. **Always-explicit** — Objects with `permissions` in Meta (bypass defaults)

### Permission Resolution Flow

```
SecurityPolicy.check_access(groups, object_ref, permission)
    │
    ├── system_admin? → ALLOW
    │
    ├── Redis cache hit? → return cached
    │
    ├── DB query: object_permissions table
    │   ├── Match: crm.rules.calculate_discount  (most specific)
    │   ├── Match: crm.rules.*                    (wildcard)
    │   └── Match: crm.*                          (app-wide)
    │
    ├── Cache result (TTL=5min)
    │
    └── Return allowed/denied
```

### Session Management

- Sessions stored in Redis DB 4 (TTL = session_timeout)
- CSRF tokens generated per session
- Login audit: success/failure logged to `login_audit_log` table
- API key auth: header `X-Api-Key` → validate hash → `ExecutionContext`

---

## 4. Data Architecture

### PostgreSQL — 16 Platform Tables

```
apps ──────── groups ──────── users
  │              │               │
  │         user_groups ─────────┘
  │              │
  │        object_permissions
  │
  ├── connected_systems
  ├── object_registry
  ├── platform_config
  │
  ├── process_instances ──── process_step_log
  │
  ├── scheduled_triggers
  ├── dependency_changes
  ├── login_audit_log
  ├── event_log
  │
  └── document_meta ──── document_versions
```

### Redis — 6 Databases

| DB | Purpose | Key Pattern | TTL |
|----|---------|-------------|-----|
| 0 | Celery broker | celery internal | — |
| 1 | Celery results | celery-task-meta-* | — |
| 2 | Permission cache | `appos:perms:{hash}:{ref}:{perm}` | 5 min |
| 3 | Object cache | `appos:obj:{ref}` | 10 min |
| 4 | Session store | `appos:session:{session_id}` | Configurable |
| 5 | Rate limiting | `appos:rate:{key}` | Per-window |

### File System — Log Structure

```
.appos/
├── logs/                           # Tier 1: JSONL system logs
│   ├── expression_rule/execution/  # Rule execution traces
│   ├── expression_rule/performance/# Rule timing metrics
│   ├── process/execution/          # Process lifecycle events
│   ├── integration/execution/      # Integration API calls
│   ├── web_api/execution/          # Web API request logs
│   ├── record/execution/           # Record CRUD operations
│   └── security/                   # Access denied, login events
│
└── runtime/
    └── dependencies/               # JSON dependency graph files
        ├── crm.rules.calc.json
        ├── crm.constants.TAX.json
        └── ...
```

---

## 5. Process Engine

### Execution Flow

```
start_process(ref, inputs)
    │
    ├── Create ProcessInstance (DB, status=running)
    ├── Create ProcessContext (inputs → variables)
    │
    ├── For each step:
    │   ├── Evaluate condition (skip if false)
    │   ├── Apply input_mapping
    │   ├── Dispatch rule via runtime.dispatch()
    │   ├── Apply output_mapping → process variables
    │   ├── Log to process_step_log (DB)
    │   ├── Retry on failure (up to retry_count)
    │   └── If error + on_error_step → branch
    │
    ├── Parallel groups: Celery group → concurrent steps
    │
    └── Complete → update ProcessInstance (status=completed)
```

### Triggers

| Type | Mechanism | Example |
|------|-----------|---------|
| Manual | `ProcessExecutor.start_process()` | Button click, API call |
| Event | `EventTriggerRegistry` | Record created/updated |
| Schedule | `ScheduleTriggerRegistry` + Celery Beat | Cron expression |

### Step Definition

```python
step(
    name="validate",              # Step name
    rule="crm.rules.validate",   # Rule to execute
    input_mapping={"id": "customer_id"},  # Map process vars → rule inputs
    output_mapping={"valid": "is_valid"}, # Map rule outputs → process vars
    retry_count=3,                # Retry on failure
    retry_delay=5,                # Delay between retries (seconds)
    timeout=30,                   # Step timeout
    condition="is_valid == True", # Skip if condition is false
    on_error="error_handler",     # Branch step on error
)
```

---

## 6. Generator Pipeline

Generators read `@record` definitions (via AST parsing) and produce:

```
@record class Customer          @record class Order
    │                               │
    ▼                               ▼
┌─────────────┐            ┌─────────────┐
│ ModelGenerator│            │ Same pipeline│
│ → SQLAlchemy │            │ per record   │
├─────────────┤            └─────────────┘
│ ServiceGen   │
│ → CRUD class │
├─────────────┤
│ ApiGenerator │
│ → @web_api   │
├─────────────┤
│ AuditGenerator│
│ → audit_log  │
├─────────────┤
│ MigrationGen │
│ → SQL DDL    │
└─────────────┘
```

---

## 7. Multi-App Architecture

### App Isolation

- Each app has its own namespace: `crm.*`, `finance.*`
- Users/groups are shared platform-wide
- App access controlled via group → app association
- Cross-app access via `CrossAppNamespace`: `finance.rules.calc_tax()`

### URL Routing

Single-port Reflex with URL-prefix routing:
- `/admin` — Admin console
- `/crm` — CRM app pages
- `/finance` — Finance app pages

### Shared vs. App-Specific

| Shared (Platform) | App-Specific |
|-------------------|--------------|
| Users, Groups | Records, Rules |
| Connected Systems | Processes, Steps |
| Platform Config | Constants, Pages |
| Login Audit | Integrations, APIs |
| Session Store | Translation Sets |
