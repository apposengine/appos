# AppOS API Reference

> **Version:** 2.0  
> **Last Updated:** February 14, 2026

---

## Table of Contents

1. [Engine — Runtime](#1-engine--runtime)
2. [Engine — Config](#2-engine--config)
3. [Engine — Context](#3-engine--context)
4. [Engine — Security](#4-engine--security)
5. [Engine — Cache](#5-engine--cache)
6. [Engine — Registry](#6-engine--registry)
7. [Engine — Dependency Graph](#7-engine--dependency-graph)
8. [Engine — Environment](#8-engine--environment)
9. [Engine — Credentials](#9-engine--credentials)
10. [Engine — Health](#10-engine--health)
11. [Engine — Logging](#11-engine--logging)
12. [Engine — Errors](#12-engine--errors)
13. [Decorators — Core](#13-decorators--core)
14. [Decorators — Record Events](#14-decorators--record-events)
15. [Decorators — Constants](#15-decorators--constants)
16. [Decorators — Connected Systems](#16-decorators--connected-systems)
17. [Decorators — Interface Extend](#17-decorators--interface-extend)
18. [Process — Executor](#18-process--executor)
19. [Process — Scheduler](#19-process--scheduler)
20. [Generators](#20-generators)
21. [Database — Models](#21-database--models)
22. [Database — Session](#22-database--session)

---

## 1. Engine — Runtime

**Module:** `appos.engine.runtime`

### CentralizedRuntime

The single entry point for all AppOS operations.

```python
from appos.engine.runtime import get_runtime, init_runtime
```

#### `init_runtime(**kwargs) → CentralizedRuntime`

Initialize the runtime engine. Call once at platform startup.

| Parameter | Type | Default | Description |
|-----------|------|---------|-------------|
| `log_dir` | `str` | `.appos/logs` | Base log directory |
| `dependency_dir` | `str` | `.appos/runtime/dependencies` | Dependency JSON dir |
| `redis_url` | `str` | `redis://localhost:6379/0` | Redis connection URL |
| `db_session_factory` | `callable` | `None` | SQLAlchemy session factory |
| `flush_interval_ms` | `int` | `100` | Log flush interval |
| `flush_batch_size` | `int` | `50` | Log flush batch size |

#### `get_runtime() → CentralizedRuntime`

Get the initialized runtime singleton.

#### `CentralizedRuntime.startup()`

Initialize all subsystems: registry, dependency graph, security, caching, logging.

#### `CentralizedRuntime.shutdown()`

Graceful shutdown: persist dependency graph, flush logs, close connections.

#### `CentralizedRuntime.dispatch(object_ref, inputs, **kwargs) → Any`

Dispatch execution to any object type.

| Parameter | Type | Description |
|-----------|------|-------------|
| `object_ref` | `str` | Fully-qualified object reference |
| `inputs` | `dict` | Input parameters |
| `**kwargs` | `Any` | Additional dispatch options |

Supported types: `expression_rule`, `process`, `integration`, `web_api`, `constant`.

#### `CentralizedRuntime.build_namespaces(app_name) → Dict`

Build auto-import namespaces for an app (used by the namespace system).

#### `CentralizedRuntime.query_for_ai(question) → Dict`

AI-friendly query interface for dependencies, impact analysis, and status.

#### Maintenance Methods

| Method | Description |
|--------|-------------|
| `cleanup_logs(config)` | Delete JSONL files past retention periods |
| `create_monthly_partitions(months_ahead, schema)` | Create PostgreSQL range partitions |
| `archive_completed_instances(days, batch)` | Archive old completed process instances |

---

## 2. Engine — Config

**Module:** `appos.engine.config`

### PlatformConfig

Pydantic model for `appos.yaml`.

```python
from appos.engine.config import (
    PlatformConfig,
    AppConfig,
    load_platform_config,
    load_app_config,
    get_platform_config,
    get_app_config,
    get_environment,
)
```

#### `load_platform_config(config_path=None) → PlatformConfig`

Load and validate `appos.yaml`. Returns defaults if file not found.

#### `load_app_config(app_short_name, apps_dir=None) → AppConfig`

Load and validate an app's `app.yaml`.

#### `get_platform_config() → PlatformConfig`

Lazy-loading singleton for platform config.

#### `get_app_config(app_short_name) → AppConfig`

Get a cached app config by short name.

#### `get_environment() → str`

Get current environment (`dev` | `staging` | `prod`).

### Key Config Models

| Model | Fields |
|-------|--------|
| `DatabaseConfig` | `url`, `pool_size`, `max_overflow`, `pool_timeout`, `pool_recycle` |
| `RedisConfig` | `url` |
| `CeleryConfig` | `broker`, `result_backend`, `concurrency`, `autoscale` |
| `SecurityConfig` | `session_timeout`, `idle_timeout`, `permission_cache_ttl`, `max_login_attempts` |
| `LoggingConfig` | `level`, `format`, `directory`, `retention`, `rotation` |

---

## 3. Engine — Context

**Module:** `appos.engine.context`

### ExecutionContext

Thread-safe per-request context (via `contextvars`).

```python
from appos.engine.context import (
    ExecutionContext,
    set_execution_context,
    get_execution_context,
    require_execution_context,
    clear_execution_context,
)
```

| Field | Type | Description |
|-------|------|-------------|
| `user_id` | `int` | Authenticated user ID |
| `username` | `str` | Username |
| `user_type` | `str` | `basic` / `system_admin` / `service_account` |
| `user_groups` | `Set[str]` | Group memberships |
| `execution_id` | `str` | Auto-generated trace ID (`exec_xxxx`) |
| `app_name` | `str?` | Current app context |
| `preferred_language` | `str` | Language code (default: `en`) |

**Properties:** `is_system_admin`, `is_service_account`

### ProcessContext

Process-level variable store, persisted to DB.

```python
from appos.engine.context import ProcessContext
```

| Method | Description |
|--------|-------------|
| `var(name, value?, logged?, sensitive?)` | Get/set a process variable |
| `input(name)` | Get a process input |
| `output(name, value)` | Set a named output |
| `outputs()` | Get all logged variables |
| `is_dirty` | Whether variables changed since last persist |

**Variable Visibility:**
- `logged=True` (default): Visible in logs, admin, AI queries
- `logged=False`: Hidden from logs/UI, stored as hash
- `sensitive=True`: Encrypted, never shown

### Translation Resolution

```python
from appos.engine.context import resolve_translation, get_preferred_language
```

#### `resolve_translation(translations_data, key, lang=None, **format_params) → str`

Resolve a translation key with fallback chain: user language → `en` → key name.

---

## 4. Engine — Security

**Module:** `appos.engine.security`

### SecurityPolicy

Cache-first permission checking.

```python
from appos.engine.security import SecurityPolicy
```

#### `SecurityPolicy.check_access(user_groups, object_ref, permission, user_type) → bool`

Check if any group has the required permission. `system_admin` bypasses all checks.

#### `SecurityPolicy.check_permission(object_ref, permission, raise_on_deny) → bool`

Check permission using current `ExecutionContext`.

### AuthService

Session-based authentication.

| Method | Description |
|--------|-------------|
| `authenticate(username, password, ip, user_agent)` | Login → session |
| `validate_session(session_id)` | Validate → `ExecutionContext` |
| `logout(session_id)` | End session |
| `authenticate_api_key(api_key)` | API key → `ExecutionContext` |

### Password Utilities

```python
from appos.engine.security import hash_password, verify_password, generate_api_key
```

| Function | Description |
|----------|-------------|
| `hash_password(password) → str` | bcrypt hash |
| `verify_password(password, hash) → bool` | Verify against hash |
| `generate_api_key() → (key, hash)` | Generate API key + hash |

### RowSecurityPolicy

Row-level security (placeholder for future expansion).

```python
from appos.engine.security import RowSecurityPolicy
```

| Method | Description |
|--------|-------------|
| `register_policy(record_name, filter_fn)` | Register row filter |
| `apply_filter(record_name, query, ctx) → query` | Apply filter to query |
| `has_policy(record_name) → bool` | Check if policy exists |

---

## 5. Engine — Cache

**Module:** `appos.engine.cache`

### RedisCache

Redis wrapper with circuit breaker.

```python
from appos.engine.cache import RedisCache, PermissionCache
```

| Method | Description |
|--------|-------------|
| `connect() → bool` | Initialize connection |
| `get(key) → str?` | Get string value |
| `set(key, value, ttl?) → bool` | Set with TTL |
| `delete(key) → bool` | Delete key |
| `get_json(key) → Any?` | Get + JSON deserialize |
| `set_json(key, value, ttl?) → bool` | JSON serialize + set |
| `ping() → bool` | Health check |

**Circuit Breaker:** After 5 failures within 30s, circuit opens. All operations gracefully return defaults. Auto-recovers after window expires.

### Redis DB Allocation

| DB | Purpose | TTL |
|----|---------|-----|
| 0 | Celery broker | — |
| 1 | Celery results | — |
| 2 | Permission cache | 5 min |
| 3 | Object cache | 10 min |
| 4 | Session store | Session timeout |
| 5 | Rate limiting | Per-window |

---

## 6. Engine — Registry

**Module:** `appos.engine.registry`

### ObjectRegistryManager

In-memory object registry.

```python
from appos.engine.registry import object_registry, RegisteredObject
```

| Method | Description |
|--------|-------------|
| `register(obj)` | Register an object |
| `resolve(object_ref) → RegisteredObject?` | Lookup by ref |
| `resolve_or_raise(object_ref)` | Lookup or raise `AppOSObjectNotFoundError` |
| `get_by_type(type, app?) → List` | Get all of a type |
| `get_by_app(app) → List` | Get all in an app |
| `scan_app_directory(app, path) → int` | Scan and register |
| `count` | Total registered objects |

---

## 7. Engine — Dependency Graph

**Module:** `appos.engine.dependency`

### DependencyGraph

NetworkX-based dependency tracking with JSON persistence.

```python
from appos.engine.dependency import DependencyGraph
```

| Method | Description |
|--------|-------------|
| `add_dependency(caller, target, access)` | Record dependency |
| `get_direct_dependencies(ref) → List` | What ref depends on |
| `get_direct_dependents(ref) → List` | What depends on ref |
| `get_transitive_dependents(ref) → Set` | Full impact set |
| `impact_analysis(ref) → Dict` | Impact report with breakdown |
| `detect_cycles() → List[List]` | Find circular dependencies |
| `persist_all() → int` | Write to JSON files |
| `load() → int` | Load from JSON files |

---

## 8. Engine — Environment

**Module:** `appos.engine.environment`

### EnvironmentResolver

Resolves environment-specific config overrides.

```python
from appos.engine.environment import EnvironmentResolver
```

| Method | Description |
|--------|-------------|
| `resolve(config, env?) → Dict` | Apply env overrides |
| `resolve_value(values, env?) → Any` | Resolve simple value map |
| `resolve_connected_system(config) → Dict` | Full CS resolution |

---

## 9. Engine — Credentials

**Module:** `appos.engine.credentials`

### CredentialManager

Fernet-encrypted credential storage.

```python
from appos.engine.credentials import CredentialManager
```

| Method | Description |
|--------|-------------|
| `encrypt(credentials) → bytes` | Encrypt credential dict |
| `decrypt(encrypted) → Dict` | Decrypt credentials |
| `set_credentials(name, creds)` | Store in DB (encrypted) |
| `get_credentials(name) → Dict?` | Retrieve and decrypt |
| `rotate_key(new_key) → int` | Re-encrypt all with new key |
| `get_auth_headers(name, config) → Dict` | Build auth headers |

**Auth types:** `basic`, `api_key`, `oauth2`, `certificate`

---

## 10. Engine — Health

**Module:** `appos.engine.health`

### HealthCheckService

Health monitoring for all subsystems.

```python
from appos.engine.health import get_health_service, HealthStatus
```

| Method | Description |
|--------|-------------|
| `register_check(name, fn, config?)` | Register health check |
| `register_database_check(name, engine)` | DB health check |
| `register_redis_check(name, url)` | Redis health check |
| `check(name) → HealthCheckResult` | Run single check (async) |
| `check_all() → Dict` | Run all checks (async) |
| `get_platform_health() → Dict` | Aggregated health status |

**Statuses:** `healthy`, `degraded`, `unhealthy`, `unknown`

---

## 11. Engine — Logging

**Module:** `appos.engine.logging`

### Two-Tier Logging

- **Tier 1:** JSONL files in `.appos/logs/` (system logs, not in DB)
- **Tier 2:** PostgreSQL tables (app data: process instances, step logs)

### File Structure

```
.appos/logs/
├── expression_rule/
│   ├── execution/          # Rule execution logs
│   └── performance/        # Timing metrics
├── process/
│   ├── execution/          # Process events
│   └── performance/
├── integration/
│   ├── execution/
│   └── performance/
├── web_api/
│   └── execution/
├── record/
│   └── execution/
└── security/               # Access denied, login events
```

### Key Functions

```python
from appos.engine.logging import init_logging, log, shutdown_logging
```

| Function | Description |
|----------|-------------|
| `init_logging(log_dir, ...) → AsyncLogQueue` | Initialize logging |
| `log(entry) → bool` | Push log entry to async queue |
| `shutdown_logging()` | Flush and close |

### Log Entry Builders

| Builder | Object Type |
|---------|------------|
| `log_rule_execution(...)` | Expression rule execution |
| `log_rule_performance(...)` | Rule performance metrics |
| `log_process_event(...)` | Process lifecycle events |
| `log_integration_call(...)` | Integration API calls |
| `log_record_operation(...)` | Record CRUD operations |
| `log_security_event(...)` | Security events |
| `log_web_api_request(...)` | Web API requests |
| `log_system_event(...)` | Platform system events |

---

## 12. Engine — Errors

**Module:** `appos.engine.errors`

### Error Hierarchy

```
AppOSError
├── AppOSSecurityError        # Access denied
├── AppOSDispatchError        # Cannot dispatch object
├── AppOSValidationError      # Input validation failed
├── AppOSTimeoutError         # Execution timeout
├── AppOSIntegrationError     # External system failure
├── AppOSRecordError          # Record operation failure
├── AppOSObjectNotFoundError  # Object ref not in registry
├── AppOSConfigError          # Configuration error
└── AppOSSessionError         # Session/auth error
```

All errors include: `message`, `execution_id`, `object_ref`, `timestamp`, `to_dict()`, `to_json()`.

---

## 13. Decorators — Core

**Module:** `appos.decorators.core`

See [Getting Started §7](getting-started.md#7-quick-reference--decorators) for usage examples.

| Decorator | Object Type | Key Parameters |
|-----------|------------|----------------|
| `@expression_rule` | Rule | `name`, `inputs`, `outputs`, `cacheable` |
| `@constant` | Constant | `name`, `validate` |
| `@record` | Record | Class with `Meta` inner class |
| `@process` | Process | `name`, `inputs`, `triggers`, `timeout` |
| `@integration` | Integration | `name`, `connected_system` |
| `@web_api` | Web API | `name`, `method`, `path`, `auth` |
| `@interface` | Interface | `name`, `record_name`, `type` |
| `@page` | Page | `route`, `title`, `interface_name` |
| `@site` | Site | `name` |
| `@translation_set` | Translation | `name`, `app` |
| `@connected_system` | Conn. System | `name`, `type`, `description` |

### Helper Functions

| Function | Description |
|----------|-------------|
| `step(name, rule, ...)` | Build a process step |
| `parallel(*steps)` | Parallel step group |
| `event(event_name)` | Event trigger builder |
| `schedule(cron)` | Cron trigger builder |
| `has_many(target, ...)` | One-to-many relationship |
| `belongs_to(target, ...)` | Many-to-one relationship |
| `has_one(target, ...)` | One-to-one relationship |

---

## 14-17. Decorators — Subsystems

### Record Events (`appos.decorators.record`)

```python
from appos.decorators.record import RecordEventManager, get_record_event_manager
```

Events: `on_create`, `on_update`, `on_delete`, `on_view`, `before_create`, `before_update`, `before_delete`

### Constants (`appos.decorators.constant`)

```python
from appos.decorators.constant import ConstantManager, get_constant_manager
```

Resolves constants with environment awareness. Dispatches `object_ref` constants to target rules.

### Connected Systems (`appos.decorators.connected_system`)

```python
from appos.decorators.connected_system import ConnectedSystemManager
```

Manages connection pooling, environment resolution, health checks, and credential injection.

### Interface Extend (`appos.decorators.interface`)

```python
from appos.decorators.interface import interface_extend
```

Override auto-generated interfaces with custom extensions.

---

## 18. Process — Executor

**Module:** `appos.process.executor`

### ProcessExecutor

Celery-backed process execution engine.

```python
from appos.process.executor import get_process_executor
```

| Method | Description |
|--------|-------------|
| `start_process(ref, inputs, user_id, async?) → Dict` | Start a process |
| `get_instance(id) → Dict?` | Get process instance status |
| `get_step_history(id) → List[Dict]` | Get step execution log |

---

## 19. Process — Scheduler

**Module:** `appos.process.scheduler`

### ProcessScheduler

Event + cron trigger management.

```python
from appos.process.scheduler import get_scheduler
```

| Method | Description |
|--------|-------------|
| `fire_event(event, data, user_id) → List[Dict]` | Fire event → start matching processes |
| `configure_celery_beat() → Dict` | Generate Celery Beat schedule |

---

## 20. Generators

**Module:** `appos.generators`

| Generator | Output |
|-----------|--------|
| `ModelGenerator` | SQLAlchemy models from `@record` |
| `ServiceGenerator` | CRUD service classes |
| `ApiGenerator` | REST API `@web_api` endpoints |
| `AuditGenerator` | Audit log tables for `@record(audit=True)` |
| `MigrationGenerator` | SQL migration scripts |

All generators follow the same pattern:

```python
gen = Generator(app_name="crm", app_path="apps/crm", output_dir="generated/")
count = gen.generate_all()  # Returns number of files generated
```

---

## 21. Database — Models

**Module:** `appos.db.platform_models`

### 16 Platform Tables

| # | Model | Table | Purpose |
|---|-------|-------|---------|
| 1 | `App` | `apps` | Registered applications |
| 2 | `User` | `users` | Platform users |
| 3 | `Group` | `groups` | Permission groups |
| 4 | `UserGroup` | `user_groups` | User↔Group junction |
| 5 | `ConnectedSystem` | `connected_systems` | External connections |
| 6 | `ObjectPermission` | `object_permissions` | Permission grants |
| 7 | `ObjectRegistry` | `object_registry` | Registered objects |
| 8 | `LoginAuditLog` | `login_audit_log` | Login attempts |
| 9 | `PlatformConfigEntry` | `platform_config` | Key-value settings |
| 10 | `ProcessInstance` | `process_instances` | Running/completed processes |
| 11 | `ProcessStepLog` | `process_step_log` | Step execution history |
| 12 | `DependencyChange` | `dependency_changes` | Dependency audit trail |
| 13 | `ScheduledTrigger` | `scheduled_triggers` | Cron job definitions |
| 14 | `DocumentMeta` | `document_meta` | File metadata |
| 15 | `DocumentVersion` | `document_versions` | File version history |
| 16 | `EventLog` | `event_log` | Application events |

---

## 22. Database — Session

**Module:** `appos.db.session`

```python
from appos.db.session import init_platform_db, platform_session_scope
```

| Function | Description |
|----------|-------------|
| `init_platform_db(url)` | Initialize DB engine and create tables |
| `platform_session_scope()` | Context manager for DB sessions |
| `app_session_scope(cs_name)` | Context manager for app DB sessions |
| `close_all_sessions()` | Cleanup all connections |
