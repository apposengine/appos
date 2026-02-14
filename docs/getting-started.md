# AppOS Platform — Getting Started Guide

> **Version:** 2.0  
> **Last Updated:** February 14, 2026

---

## 1. What is AppOS?

AppOS is a **Python low-code platform** for building enterprise applications. It provides:

- **Decorator-based object model** — Define records, rules, processes, APIs, and UIs with Python decorators
- **Zero-import namespaces** — Auto-import with built-in security checks and dependency tracking
- **Process engine** — Multi-step workflows with Celery-backed async execution
- **Admin console** — Full Reflex-based admin UI for managing apps, users, permissions, and monitoring
- **Auto-generation** — Models, services, APIs, audit tables, and migrations generated from decorators

### Technology Stack

| Layer | Technology |
|-------|-----------|
| Web Framework | Reflex |
| Database | PostgreSQL + SQLAlchemy |
| Validation | Pydantic |
| Cache / Sessions | Redis |
| Task Queue | Celery + Redis |
| Dependency Graph | NetworkX |
| Security | bcrypt + Fernet encryption |
| Config | YAML + Pydantic |

---

## 2. Installation

### Prerequisites

- Python 3.11+
- PostgreSQL 15+
- Redis 7+

### Setup

```bash
# Clone the repository
git clone <repo-url> appOSDev
cd appOSDev

# Create virtual environment
python -m venv .venv
.venv\Scripts\activate     # Windows
# source .venv/bin/activate  # Linux/Mac

# Install dependencies
pip install -r requirements.txt

# Install AppOS in development mode
pip install -e .
```

### Initialize the Platform

```bash
# Bootstrap database, admin user, and groups
appos init

# Start the development server
appos run
```

The admin console is available at `http://localhost:3000/admin`.

---

## 3. Project Structure

```
appOSDev/
├── appos.yaml              # Platform configuration
├── requirements.txt        # Python dependencies
├── rxconfig.py             # Reflex configuration
├── appos/                  # Platform engine
│   ├── engine/             # Core engine (runtime, security, cache, etc.)
│   ├── decorators/         # Object decorators (@record, @process, etc.)
│   ├── generators/         # Auto-generators (models, services, APIs)
│   ├── db/                 # Database models and session management
│   ├── process/            # Process executor and scheduler
│   ├── admin/              # Admin console (Reflex pages)
│   ├── ui/                 # UI bridge for Reflex integration
│   └── cli.py              # CLI entry point
├── apps/                   # Application modules
│   └── crm/                # Example: CRM app
│       ├── app.yaml        # App configuration
│       ├── records/         # Data models
│       ├── rules/           # Business logic
│       ├── processes/       # Multi-step workflows
│       ├── constants/       # Configuration values
│       ├── integrations/    # External system calls
│       ├── web_apis/        # REST API endpoints
│       ├── interfaces/      # UI components
│       ├── pages/           # Routable pages
│       ├── translation_sets/# Internationalization
│       └── steps/           # Reusable process steps
├── migrations/             # Database migrations
└── tests/                  # Test suite
```

---

## 4. Configuration

### Platform Config (appos.yaml)

```yaml
platform:
  name: "My Platform"
  version: "2.0.0"
environment: dev    # dev | staging | prod

database:
  url: postgresql://user:pass@localhost:5432/appos_core
  pool_size: 10

redis:
  url: redis://localhost:6379/0

celery:
  broker: redis://localhost:6379/0
  result_backend: redis://localhost:6379/1
  concurrency: 4

security:
  session_timeout: 3600
  permission_cache_ttl: 300
  max_login_attempts: 5

logging:
  level: INFO
  directory: .appos/logs
  retention:
    execution_days: 90
    performance_days: 30
    security_days: 365

apps:
  - crm
  - finance
```

### App Config (apps/crm/app.yaml)

```yaml
app:
  name: "CRM Application"
  short_name: crm
  version: "1.0.0"
  description: "Customer Relationship Management"
  groups:
    - crm_users
    - crm_admins
  theme:
    primary_color: "#3B82F6"
    font_family: Inter
  features:
    audit: true
    soft_delete: true
```

---

## 5. CLI Commands

| Command | Description |
|---------|-------------|
| `appos init` | Bootstrap database, create admin user and groups |
| `appos run` | Start the Reflex development server |
| `appos new-app <name>` | Scaffold a new application module |
| `appos generate [--app <name>]` | Run auto-generators for all/specific apps |
| `appos migrate [--apply]` | Generate or apply database migrations |
| `appos check [--app <name>]` | Validate app code (syntax, imports, deps) |
| `appos impact <object_ref>` | Analyze impact of changing an object |
| `appos validate` | Validate platform configuration |

### Examples

```bash
# Create a new app
appos new-app finance --display-name "Finance Module"

# Generate models, services, APIs for all apps
appos generate

# Generate only for CRM
appos generate --app crm --only model,service

# Check all apps for issues
appos check

# See what depends on a rule
appos impact crm.rules.calculate_discount

# Apply pending migrations
appos migrate --apply
```

---

## 6. Core Concepts

### 6.1 Object Types

AppOS has **14 object types**, each defined by a Python decorator:

| Type | Decorator | Purpose |
|------|-----------|---------|
| Record | `@record` | Data model (Pydantic → SQLAlchemy) |
| Expression Rule | `@expression_rule` | Business logic function |
| Constant | `@constant` | Configuration value (env-aware) |
| Process | `@process` | Multi-step workflow |
| Step | `step()` | Process step builder |
| Integration | `@integration` | Outbound API call |
| Web API | `@web_api` | REST endpoint |
| Interface | `@interface` | UI component definition |
| Page | `@page` | Routable page |
| Site | `@site` | Collection of pages |
| Translation Set | `@translation_set` | i18n labels |
| Connected System | `@connected_system` | External connection config |
| Document | (runtime) | File/attachment |
| Folder | (runtime) | Document container |

### 6.2 Object References

Every object has a unique reference: `{app}.{category}.{name}`

Examples:
- `crm.rules.calculate_discount`
- `crm.records.customer`
- `crm.constants.TAX_RATE`
- `crm.processes.onboard_customer`

### 6.3 Security Model

AppOS uses a **6-permission model**: `view | use | create | update | delete | admin`

Permissions are granted to **groups** on **object patterns**:
- `crm.rules.calculate_discount` — exact object
- `crm.rules.*` — all rules in CRM
- `crm.*` — all objects in CRM

`admin` implies all permissions. `system_admin` users bypass all checks.

---

## 7. Quick Reference — Decorators

### @record

```python
from appos.decorators.core import record, has_many, belongs_to

@record
class Customer:
    class Meta:
        table_name = "customers"
        audit = True
        soft_delete = True
        display_field = "email"
        search_fields = ["first_name", "last_name", "email"]
        permissions = {"view": ["crm_users"], "update": ["crm_admins"]}
        on_create = "crm.rules.validate_customer"
        on_update = "crm.rules.update_cache"

    first_name: str
    last_name: str
    email: str
    tier: str = "standard"
    orders = has_many("Order", back_ref="customer")
```

### @expression_rule

```python
from appos.decorators.core import expression_rule

@expression_rule(
    name="calculate_discount",
    inputs={"amount": float, "tier": str},
    outputs={"discount": float},
    permissions={"use": ["crm_users"]},
    cacheable=True,
    cache_ttl=300,
)
def calculate_discount(ctx):
    amount = ctx.input("amount")
    tier = ctx.input("tier")
    rate = 0.1 if tier == "gold" else 0.05
    ctx.output("discount", amount * rate)
```

### @constant

```python
from appos.decorators.core import constant

@constant(name="TAX_RATE")
def TAX_RATE():
    return {"default": 0.08, "prod": 0.0825}

# Object-ref constant (dispatches to a rule)
@constant(name="PRICING_RULE")
def PRICING_RULE() -> str:
    return "crm.rules.calculate_discount"
```

### @process

```python
from appos.decorators.core import process, step, parallel, event, schedule

@process(
    name="onboard_customer",
    inputs={"customer_id": int},
    triggers=[
        event("customer.created"),
        schedule("0 2 * * *"),
    ],
    timeout=600,
)
def onboard_customer():
    return [
        step("validate", rule="crm.rules.validate_customer",
             input_mapping={"id": "customer_id"}),
        parallel(
            step("assign_rep", rule="crm.rules.assign_rep"),
            step("create_account", rule="crm.rules.create_account"),
        ),
        step("send_welcome", rule="crm.rules.send_welcome_email"),
    ]
```

### @integration

```python
from appos.decorators.core import integration

@integration(
    name="fetch_credit_score",
    connected_system="credit_bureau",
    permissions={"use": ["crm_admins"]},
)
async def fetch_credit_score(ctx, http):
    response = await http.post("/api/score", json={"ssn": ctx.input("ssn")})
    ctx.output("score", response.json()["score"])
```

### @web_api

```python
from appos.decorators.core import web_api

@web_api(
    name="create_customer",
    method="POST",
    path="/api/crm/customers",
    auth="api_key",
    rate_limit=100,
)
def create_customer(request, ctx):
    # Validate and create
    customer = ctx.input("body")
    ctx.output("id", created.id)
    ctx.output("status", 201)
```

### @translation_set

```python
from appos.decorators.core import translation_set

@translation_set(name="labels")
def labels():
    return {
        "greeting": {"en": "Hello, {name}!", "fr": "Bonjour, {name} !"},
        "save": {"en": "Save", "fr": "Enregistrer", "es": "Guardar"},
    }
```

---

## 8. Auto-Import Namespaces

Inside any rule or process step, objects are available without imports:

```python
@expression_rule(name="calculate_total")
def calculate_total(ctx):
    # Auto-imported — security checked, dependency tracked
    tax_rate = constants.TAX_RATE
    discount = rules.calculate_discount(amount=ctx.input("amount"), tier="gold")
    label = translations.labels.get("greeting", name="Alice")

    # Cross-app access
    finance_rule = finance.rules.calculate_tax(amount=100)
```

The auto-import layer:
1. Checks permissions (blocking) via `SecurityPolicy`
2. Tracks dependencies (non-blocking) via `DependencyGraph`
3. Lazy-loads and caches the object module

---

## 9. Testing

```bash
# Run all unit tests
pytest tests/ -v

# Run only unit tests (skip integration)
pytest tests/ -v -m "not integration"

# Run integration tests
pytest tests/integration/ -v -m integration

# Run specific test file
pytest tests/test_errors.py -v

# Run with coverage
pytest tests/ --cov=appos --cov-report=html
```

### Test Categories

| Directory | What | Requirements |
|-----------|------|--------------|
| `tests/test_*.py` | Unit tests | None (all mocked) |
| `tests/integration/` | Integration tests | PostgreSQL + Redis |

---

## 10. Admin Console

Access at `http://localhost:3000/admin` (requires `system_admin` login).

### Available Pages

| Page | Path | Description |
|------|------|-------------|
| Dashboard | `/admin` | Overview metrics and health |
| Apps | `/admin/apps` | Registered applications |
| Users | `/admin/users` | User management |
| Groups | `/admin/groups` | Group and permission management |
| Connections | `/admin/connections` | Connected system management |
| Processes | `/admin/processes` | Process instance monitoring |
| Object Browser | `/admin/object-browser` | Browse all registered objects |
| Records Browser | `/admin/records-browser` | Query record data |
| Settings | `/admin/settings` | Platform configuration |
| Sessions | `/admin/sessions` | Active session management |
| Themes | `/admin/themes` | Per-app theme editor |
| Logs | `/admin/logs` | System log viewer |
| Metrics | `/admin/metrics` | Performance metrics dashboard |
| Workers | `/admin/workers` | Celery worker management |

---

## 11. Troubleshooting

### Common Issues

**Redis connection failed**
```
Redis connection failed (DB 2): Connection refused
```
→ Start Redis: `redis-server` or check `redis.url` in `appos.yaml`.

**Database connection failed**
→ Ensure PostgreSQL is running and `database.url` is correct in `appos.yaml`.

**Permission denied errors**
→ Check group membership and object permissions in Admin → Groups.

**Missing object reference**
→ Run `appos check` to validate all object references and imports.

---

## 12. Architecture Overview

```
┌─────────────┐     ┌──────────────┐     ┌─────────────┐
│  Reflex UI  │────▶│  Admin State  │────▶│  Runtime    │
│  (Pages)    │     │  (rx.State)   │     │  Engine     │
└─────────────┘     └──────────────┘     └──────┬──────┘
                                                 │
                    ┌────────────────────────────┼────────────────────┐
                    │                            │                    │
              ┌─────▼──────┐  ┌─────────────┐  ┌▼────────────┐  ┌──▼──────┐
              │  Security  │  │  Registry    │  │  Dependency  │  │  Cache  │
              │  Policy    │  │  (Objects)   │  │  Graph       │  │  Redis  │
              └────────────┘  └─────────────┘  └─────────────┘  └─────────┘
                    │                            │
              ┌─────▼──────┐              ┌─────▼──────────┐
              │  PostgreSQL │              │  Log Files     │
              │  (16 tables)│              │  (.appos/logs) │
              └────────────┘              └────────────────┘
```

The `CentralizedRuntime` is the single entry point, tying together all subsystems:
security, registry, dependency graph, logging, caching, process execution, and dispatch.
