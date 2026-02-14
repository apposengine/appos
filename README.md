# AppOS Design Philosophy

**Python Low-Code Platform — Quick Reference for Developers, AI Assistants, and Architects**

*Version 2.1 | February 2026*

---

## Core Philosophy

**AppOS accelerates Python development by 50%+ through organized structure, zero-import architecture, and AI-native observability. It's not a new language — it's Python with guardrails and wraps reflex dev.**

### Five Founding Principles

1. **Zero-Import Developer Experience** — Developers never write `import` statements. The platform auto-resolves all object references with security validation and dependency tracking.

2. **Security-First Architecture** — Every object access validated against user groups via unified 6-permission model. Three-tier inherited security reduces configuration burden. Redis-cached for performance (<5ms warm).

3. **AI-Native Debugging** — Pre-recorded logs, metrics, and dependency graphs in structured JSON. AI assistants can query runtime state for dependencies, performance bottlenecks, security violations, and impact analysis without human translation.

4. **Declarative Over Imperative** — Decorators define *what* objects do, the runtime handles *how*. Security, logging, metrics, error handling — all centralized in the Runtime Engine.

5. **Pydantic-Native Data Models** — Records use standard Pydantic `BaseModel`. Type hints drive auto-generation: SQLAlchemy models, migrations, CRUD services, REST APIs, and Reflex UI interfaces.

### What AppOS Provides

- **Centralized Runtime Engine** — Single dispatch point (`engine.dispatch()`) for all object access with security validation, execution tracking, and error handling
- **17 Object Types** — Comprehensive coverage: User, Group, App, Connected System, Constant, Record, Expression Rule, Step, Process, Integration, Web API, Interface, Page, Site, Document, Folder, Translation Set
- **Multi-App Architecture** — Shared users/groups, app-level isolation via group association. Cross-app references via `otherapp.object_name` syntax
- **Process Engine** — Multi-step workflows via Celery with process-level variables (`ctx.var`), parallel execution, fire-and-forget tracking, and monthly partitioning
- **Auto-Generation Pipeline** — Records auto-generate models, services, APIs, and UIs. Optional `audit_log` table per record
- **Admin Console** — Built-in Reflex app for user/group/app management, log viewing, metrics dashboards, platform settings, and theme editing
- **Structured Logging** — Per-object-type logs split into execution/performance/security categories. Differentiated retention (exec=90d, perf=30d, security=365d). Async queue for non-blocking writes

---

## Architecture Overview

### Request Flow

```
1. User action triggers decorated function
2. Runtime intercepts via SecureAutoImportNamespace
3. engine.dispatch() validates security (Redis cache)
4. Execution context created (execution_id, user, app)
5. Function executes with logging/metrics tracking
6. Logs queued async (execution/performance/security)
7. Dependencies recorded (for appos impact analysis)
```

### Technology Stack

| Component | Technology |
|-----------|------------|
| Database | PostgreSQL 16+ (partitioning, JSONB) |
| Cache | Redis 7+ (security cache, session store) |
| ORM | SQLAlchemy 2.0+ |
| Migrations | Alembic (auto-generated from Records) |
| Process Engine | Celery 5+ (Redis broker, partitioned tasks) |
| UI Framework | Reflex 0.5+ (single-port, per-app theming) |
| Validation | Pydantic 2.0+ (Records, config) |

---

## 17 Object Types — Quick Reference

*Each object type has a decorator, scope, and purpose. Security is three-tiered: Tier 1 (explicit), Tier 2 (inherits logic defaults), Tier 3 (inherits UI defaults).*

### Platform Objects (Scope: Platform)

| Type | Decorator | Purpose |
|------|-----------|---------|
| User | DB model | Authentication, user_type (basic/system_admin/service_account) |
| Group | DB model | Unified 6-permission model (view/use/create/update/delete/admin) |
| App | app.yaml | App-level config with security.defaults for logic/UI inheritance |
| Connected System | @connected_system | External system connections (DB, API, FTP, SMTP, IMAP) with pooling |

### Data Objects (Scope: Per-App)

| Type | Decorator | Purpose |
|------|-----------|---------|
| Constant | @constant | Static values (primitives/object refs), env overrides, Tier 2 security |
| Record | @record + Pydantic | Data models → auto-gen SQLAlchemy/CRUD/API/UI, Tier 1 security |
| Document | @record | Files with versioning/MIME validation, inherits parent Record security |
| Folder | @record | Runtime folder management with auto_cleanup |

### Logic Objects (Scope: Per-App)

| Type | Decorator | Purpose |
|------|-----------|---------|
| Expression Rule | @expression_rule | Business logic + queries + platform rules, Tier 2 security |
| Step | step() | Process building block, fire_and_forget tracking |
| Process | @process | Multi-step workflow with parallel() and ctx.var, Tier 1 security |

### External Objects (Scope: Per-App)

| Type | Decorator | Purpose |
|------|-----------|---------|
| Integration | @integration | Outbound API calls with log_payload opt-in, Tier 1 security |
| Web API | @web_api | Inbound REST endpoints with service account auth, Tier 1 security |

### UI Objects (Scope: Per-App)

| Type | Decorator | Purpose |
|------|-----------|---------|
| Interface | @interface | Reusable UI components (Reflex), Tier 3 security |
| Page | @page | Routable Reflex page, Tier 3 security |
| Site | @site | Collection of pages with navigation |
| Translation Set | @translation_set | i18n with ctx.user.preferred_language, Tier 3 security |

---

## Security Model

### Six-Permission Model

*Every object access requires one of six permissions. Groups grant permissions to users. Wildcards enable bulk assignment.*

| Permission | Scope |
|------------|-------|
| `view` | Read-only access to object or record data |
| `use` | Execute rules/processes/integrations |
| `create` | Create new record instances |
| `update` | Modify existing record instances |
| `delete` | Remove record instances |
| `admin` | Modify object definition or security settings |

### Three-Tier Security Inheritance

*Reduces configuration burden by letting lower-risk objects inherit permissions from app-level defaults.*

- **Tier 1 (Explicit)** — Record, Process, Web API, Integration → always require explicit permissions
- **Tier 2 (Logic Defaults)** — Expression Rule, Constant → inherit from `security.defaults.logic` in app.yaml
- **Tier 3 (UI Defaults)** — Interface, Page, Translation Set → inherit from `security.defaults.ui` in app.yaml
- **Special** — Document and Folder inherit from their parent Record's permissions

### Wildcard Permissions

Grant permissions to multiple objects at once using wildcard patterns:

- `crm.*` — All objects in the CRM app
- `crm.records.*` — All records in the CRM app
- `crm.customer*` — All objects starting with 'customer' in CRM

### Public Access

Objects can be marked `public_access: true` to bypass authentication (e.g., login pages, public APIs). Use sparingly for security reasons.

---

## State Management

### Four-State Model

1. **Request State** — Lives only during a single HTTP request/rule execution
2. **Session State** — Persists across requests for a logged-in user (Redis-backed)
3. **Process State** — Lives during multi-step process execution (`ctx.var` for cross-step variables)
4. **Database State** — Permanent storage in PostgreSQL (Records, business logs)

### Execution Context

Every function execution receives a `ctx` object with runtime information:

```python
ctx.user             # Current authenticated user
ctx.app              # Current app context
ctx.execution_id     # Unique execution ID (logging/tracing)
ctx.session          # Session state (Redis-backed)
ctx.var              # Process-level variables (multi-step)
ctx.request          # HTTP request object (if applicable)
```

---

## Logging & Observability

### Per-Object-Type Logging

*System logs organized by object type with three sub-folders per type. Async queue prevents blocking. Differentiated retention for compliance.*

```
.appos/logs/{object_type}/execution/{YYYY-MM-DD}.jsonl
.appos/logs/{object_type}/performance/{YYYY-MM-DD}.jsonl
.appos/logs/{object_type}/security/{YYYY-MM-DD}.jsonl
```

#### Log Categories

- **execution/** — Function calls, parameters, results, errors (retention: 90 days)
- **performance/** — Execution time, query counts, cache hit rates (retention: 30 days)
- **security/** — Permission checks, auth failures, suspicious activity (retention: 365 days)

### Structured Error Hierarchy

All errors extend `AppOSError` with `execution_id`, `object_ref`, and `object_type` for AI-friendly debugging:

- `AppOSSecurityError` — Permission/auth failures
- `AppOSDispatchError` — Object resolution failures
- `AppOSValidationError` — Input/schema/MIME violations
- `AppOSTimeoutError` — Step/integration timeouts
- `AppOSIntegrationError` — External system failures

### Business Logs vs. System Logs

- **System logs** — File-based JSONL in `.appos/logs/`, async queue, not user-queryable
- **Business logs** — Database tables (e.g., `audit_log` for Records), queryable by users with proper permissions

---

## Code Examples

### Record Definition

```python
from pydantic import BaseModel

@record(
    audit_log=True,  # Auto-generate audit_log table
    view=["crm_users"],
    create=["crm_admins"],
    update=["crm_admins"]
)
class Customer(BaseModel):
    name: str
    email: str
    status: Literal["active", "inactive"]
```

*Auto-generates: SQLAlchemy model, Alembic migration, CRUD service, REST API endpoints, Reflex UI interface*

### Expression Rule

```python
@expression_rule(  # Inherits security.defaults.logic
    description="Calculate customer lifetime value"
)
def customer_ltv(customer_id: int) -> float:
    orders = records.orders.query(
        customer_id=customer_id,
        status="completed"
    )
    return sum(o.total for o in orders)
```

### Process with Parallel Steps

```python
@process(
    display_name="Customer Onboarding",
    use=["crm_users"]
)
def onboard_customer(customer_id: int):
    ctx.var.customer_id = customer_id  # Process-level variable
    
    step(create_account)()
    
    # Run three steps in parallel
    parallel(
        step(send_welcome_email),
        step(provision_trial),
        step(notify_sales_team)
    )
    
    step(log_completion)()
```

### Cross-App Reference

```python
# In CRM app, reference Billing app's Invoice record
@expression_rule()
def get_customer_invoices(customer_id: int):
    return billing.records.invoice.query(
        customer_id=customer_id
    )
```

*The prefix 'billing.' tells the runtime to resolve the object in the Billing app instead of the current app.*

---

## CLI Commands

| Command | Purpose |
|---------|---------|
| `appos init` | Scaffold a new AppOS platform project |
| `appos check` | Validate all imports are AppOS-only (no external imports) |
| `appos impact {obj}` | Show what depends on an object (AI-queryable dependency graph) |
| `appos migrate` | Run database migrations (auto-generated from Record changes) |

---

## Configuration Files

### Platform Config (appos.yaml)

*Located at project root. Controls platform-wide settings:*

```yaml
database:
  host: localhost
  port: 5432
  name: appos_platform

redis:
  host: localhost
  port: 6379

session:
  timeout: 3600  # 1 hour

logging:
  retention:
    execution: 90    # days
    performance: 30
    security: 365

process:
  partition: monthly  # ProcessInstance partitioning
  archive_after_months: 6
```

### App Config (app.yaml)

*Located in each app folder (e.g., `apps/crm/app.yaml`). Controls app-level settings:*

```yaml
name: crm
display_name: Customer Relationship Management

security:
  defaults:
    logic:  # Tier 2 (Rules, Constants)
      view: ["crm_users"]
      use: ["crm_users"]
    ui:  # Tier 3 (Interfaces, Pages, Translations)
      view: ["crm_users"]
```

---

## Key Constraints & Design Decisions

### What AppOS Enforces

- **Zero external imports** — All object access goes through `engine.dispatch()`. The `appos check` command validates this.
- **Decorator-driven** — All object types require a decorator. No decorator = not an AppOS object = cannot be referenced by other objects.
- **Explicit Tier 1 security** — Record, Process, Web API, Integration always require explicit permission configuration. No inheritance allowed.
- **Pydantic-only Records** — Records must extend `BaseModel`. Type hints are mandatory for auto-generation.
- **Async logging only** — All system logs go through async queue. No blocking `file.write()` allowed.

### What AppOS Does NOT Enforce

- **Code style** — Use any Python style (PEP 8, Black, etc.). AppOS doesn't care.
- **Naming conventions** — Object names can be snake_case, camelCase, or PascalCase. Consistency recommended but not required.
- **Testing framework** — Use pytest, unittest, or any other. AppOS provides helpers but doesn't mandate a framework.
- **Deployment method** — Docker, K8s, bare metal — all work. AppOS is deployment-agnostic.

---

## When to Use AppOS

### Good Fit

- **Internal tools and admin panels** — Fast development, auto-generated UIs, built-in security
- **Multi-tenant B2B SaaS** — Group-based permissions, app isolation, audit logging
- **Workflow automation** — Process engine with parallel steps, fire-and-forget, Celery-backed
- **Data-heavy applications** — Pydantic → SQLAlchemy pipeline, auto-generated CRUD, REST APIs
- **Compliance-heavy industries** — 365-day security log retention, audit_log tables, structured errors

### Poor Fit

- **Public-facing consumer apps** — AppOS adds overhead for simple CRUD apps with no complex permissions
- **Microservices architectures** — AppOS assumes monolithic multi-app structure; cross-service calls not optimized
- **Real-time gaming or streaming** — `engine.dispatch()` overhead (100-200ms cold, <5ms warm) too high for sub-10ms latency requirements
- **Highly customized data models** — If your ORM needs custom SQL, triggers, or stored procedures, AppOS auto-generation may feel constraining

---

## Success Metrics

*AppOS aims for 50%+ development acceleration. Here's how to measure it:*

### Developer Productivity

- **Lines of boilerplate avoided** — Compare AppOS Record (10 lines) vs. Django model + serializer + viewset + router (50+ lines)
- **Time to CRUD endpoint** — From zero to working REST API: AppOS = 5 minutes, FastAPI = 30 minutes
- **Security config burden** — Tier 2/3 inheritance means 70% fewer security declarations vs. explicit-everywhere

### AI Assistant Effectiveness

- **Debugging time** — AI can query `execution_id` in logs without human translation; target: 50% faster root cause identification
- **Impact analysis accuracy** — `appos impact` provides complete dependency graph; target: 100% accuracy vs. 60% with manual grep

### System Performance

- **Cache hit rate** — Redis security cache should hit >95% in production
- **Dispatch latency** — Cold: <200ms, Warm: <5ms (p99)
- **Log write lag** — Async queue should flush logs within 1 second under normal load

---

## Quick Reference: All Decorators & Syntax

### Platform Objects
```python
# User, Group - DB models, no decorator
# App - app.yaml configuration file

@connected_system(
    name="stripe_api",
    type="api",
    base_url="https://api.stripe.com",
    pool_size=10,
    pool_reset_on_return=True
)
def stripe():
    return {"api_key": env.STRIPE_API_KEY}
```

### Data Objects
```python
@constant(name="max_retries", value=3)
def max_retries(): return 3

@record(audit_log=True, view=["users"], create=["admins"])
class Customer(BaseModel):
    name: str
    email: str
```

### Logic Objects
```python
@expression_rule(description="Calculate total")
def calculate_total(items: list) -> float:
    return sum(item.price for item in items)

@process(display_name="Onboarding", use=["users"])
def onboard():
    step(send_email)()
    parallel(step(a), step(b), step(c))
```

### External Objects
```python
@integration(
    name="create_charge",
    system="stripe_api",
    log_payload=True,
    use=["billing_users"]
)
def create_charge():
    return {
        "method": "POST",
        "path": "/charges",
        "body": {...}
    }

@web_api(
    method="POST",
    path="/webhook",
    auth="service_account"
)
def webhook():
    return {"handler": "rules.handle_hook"}
```

### UI Objects
```python
@interface(name="Dashboard")
def dashboard():
    return rx.vstack(...)

@page(route="/home", interface="Dashboard")
def home_page():
    return {...}

@site(name="CRM")
def crm_site():
    return {"pages": [...], "navigation": [...]}

@translation_set(name="labels", app="crm")
def labels():
    return {
        "save": {"en": "Save", "fr": "Enregistrer"}
    }
```

---

## Summary

**AppOS v2.1** is a Python-first low-code platform that:

1. **Zero-Import DX** — Developers never write imports. Auto-import layer resolves everything with security checks and dependency tracking.
2. **Security-First** — Every object access validated against user groups via unified 6-permission model. Cached in Redis for performance. Three-tier inherited security.
3. **AI-Native Debugging** — Pre-recorded logs, metrics, and dependency graphs in structured JSON. AI can query runtime state for dependencies, performance, security violations, and impact analysis.
4. **Multi-App Architecture** — Shared users/groups, app-level isolation via group association. Single-port Reflex routing.
5. **17 Object Types** — Comprehensive coverage from platform management to UI components.
6. **Auto-Generation** — Records auto-generate SQLAlchemy models, migrations, CRUD services, REST APIs, and Reflex UI interfaces.
7. **Pydantic-Native** — Records use standard Pydantic BaseModel. Type hints drive everything.
8. **Process Engine** — Multi-step workflows via Celery with process-level variables, parallel execution, and fire-and-forget tracking.
9. **Per-Category Logging** — System logs split into execution/performance/security sub-folders per object type. Differentiated retention for compliance.
10. **Admin Console** — Built-in Reflex app for user/group/app management, log viewing, metrics dashboards, and platform settings.
11. **Connected Systems** — Unified external connection management with admin-managed credentials and connection pool tuning.
12. **Error Hierarchy** — Structured `AppOSError` with 5 subtypes, each carrying `execution_id`, `object_ref`, and `object_type` for AI-friendly debugging.
13. **Reflex Integration** — Single Reflex instance, per-app theming, auto-generated UI, single-port routing.

**Goal:** Python developers + AI assistants get 50%+ acceleration through organized structure, zero-import DX, auto-generation, centralized observability, and AI-queryable runtime — without learning a new language.

---

*This document is a quick reference extract from the full AppOS Design Document v2.1.*  
*For complete implementation details, see AppOS_Design.md and reference documentation.*

**February 2026 | AppOS v2.1**
