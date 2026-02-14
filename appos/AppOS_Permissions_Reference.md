# AppOS — Permissions & Security Reference

> **Referenced from:** `AppOS_Design.md` §6 Security Model  
> **Version:** 2.1 — February 12, 2026

---

## Unified Permission Model

Six generic permissions apply uniformly across all object types. No type-specific permission names.

### Permission Set

| Permission | Meaning |
|---|---|
| `view` | Can see the object exists, read its metadata/definition |
| `use` | Can execute/access (run a rule, start a process, call API, view page, read record data) |
| `create` | Can create new instances (records, documents) |
| `update` | Can modify instances (records, documents) |
| `delete` | Can remove instances (records, documents) |
| `admin` | Full control (modify security, override anything) |

### Permission Applicability by Object Type

| Object Type | `view` | `use` | `create` | `update` | `delete` | `admin` |
|---|---|---|---|---|---|---|
| Expression Rule | ✓ | ✓ | — | — | — | ✓ |
| Constant | ✓ | ✓ | — | — | — | ✓ |
| Process | ✓ | ✓ | — | — | — | ✓ |
| Integration | ✓ | ✓ | — | — | — | ✓ |
| Web API | ✓ | ✓ | — | — | — | ✓ |
| Interface | ✓ | ✓ | — | — | — | ✓ |
| Page | ✓ | ✓ | — | — | — | ✓ |
| Translation Set | ✓ | ✓ | — | — | — | ✓ |
| Record | ✓ | ✓ | ✓ | ✓ | ✓ | ✓ |
| Document | ✓ | ✓ | ✓ | ✓ | ✓ | ✓ |
| Connected System | ✓ | ✓ | — | — | — | ✓ |

`—` = not applicable (object doesn't support that operation)

> **Note:** Document, Folder, DocumentVersion, ProcessInstance, and ProcessStepLog are all implemented as Records internally. They follow the Record permission row above. Platform-internal records (Folder, DocumentVersion, ProcessInstance, ProcessStepLog) are restricted to `system_admin` by default.

### Object Permission Table (DB Schema)

```sql
CREATE TABLE object_permission (
    id          SERIAL PRIMARY KEY,
    group_name  VARCHAR(100) NOT NULL,
    object_ref  VARCHAR(255) NOT NULL,   -- e.g., "crm.rules.*" or "crm.records.customer"
    permission  VARCHAR(20) NOT NULL,    -- view | use | create | update | delete | admin
    UNIQUE(group_name, object_ref, permission)
);

-- Indexes
CREATE INDEX idx_perm_group ON object_permission(group_name);
CREATE INDEX idx_perm_obj ON object_permission(object_ref);
```

**Wildcard support:** `crm.rules.*` grants permission for all rules in the CRM app. `crm.*` grants permission for all objects in CRM.

### Examples

```
| group_name  | object_ref               | permission |
|-------------|---------------------------|------------|
| sales       | crm.rules.*               | use        |
| sales       | crm.constants.*           | use        |
| sales       | crm.records.customer      | view       |
| sales       | crm.records.customer      | create     |
| sales       | crm.records.customer      | update     |
| crm_admins  | crm.*                     | admin      |
| finance     | finance.records.*         | view       |
| finance     | finance.records.*         | create     |
| finance     | finance.records.*         | update     |
| finance     | finance.records.*         | delete     |
| api_consumers | crm.web_apis.*          | use        |
```

---

## Three-Tier Security Inheritance

### Tier 1 — App-Level Defaults (app.yaml)

Objects that don't declare explicit `permissions` inherit from their category default.

```yaml
# app.yaml
security:
  defaults:
    logic:     # applies to: rules, constants
      groups: ["sales", "support", "crm_admins"]
    ui:        # applies to: interfaces, pages, translation_sets
      groups: ["sales", "support", "crm_admins"]
```

### Tier 2 — Inheriting Objects

| Category | Objects | Inherits From | Override |
|---|---|---|---|
| Logic | Expression Rules, Constants | `security.defaults.logic` | Explicit `permissions=[...]` on decorator |
| UI | Interfaces, Pages, Translation Sets | `security.defaults.ui` | Explicit `permissions=[...]` on decorator |
| Data | Documents | Parent Record's security | Explicit `permissions` on Document record |

```python
# This rule inherits from security.defaults.logic
@expression_rule
def general_rule(ctx): ...

# This rule overrides — only crm_admins
@expression_rule(permissions=["crm_admins"])
def sensitive_rule(ctx): ...
```

### Tier 3 — Always-Explicit Objects

These objects MUST define their own permissions. `appos check` errors if omitted.

| Object | Why Explicit |
|---|---|
| Record | CRUD granularity matters per record type |
| Process | Represents distinct business actions |
| Web API | External-facing, needs auth config |
| Integration | Outbound calls, sensitive |
| Connected System | Credentials access |

```python
# REQUIRED — appos check will flag if missing
@record
class Customer(BaseModel):
    class Meta:
        permissions = {
            "view": ["sales", "support", "crm_admins"],
            "create": ["sales", "crm_admins"],
            "update": ["sales", "crm_admins"],
            "delete": ["crm_admins"],
        }

@process(permissions=["sales", "crm_admins"])
def onboard_customer(ctx): ...
```

---

## User Types

| Type | Can Login (UI) | Can Trigger API | In Groups | Admin Console Access |
|---|---|---|---|---|
| `basic` | Yes | Yes | Yes | No |
| `system_admin` | Yes | Yes | Yes (`system_admin` group) | Yes |
| `service_account` | No | Yes (via API key/OAuth) | Yes | No (managed from admin) |

### Default Groups (Bootstrapped on `appos init`)

| Group | Type | Purpose |
|---|---|---|
| `system_admin` | system | Full platform access, admin console, user/group management |
| `public_access` | system | For public Web APIs — service account user with limited permissions |

### Service Account Flow

1. System admin creates a service account user in admin console (type=`service_account`)
2. Service account is assigned to groups (e.g., `api_consumers`)
3. Web API `auth` config references a Connected System for authentication
4. API key/OAuth token resolves to the service account user
5. Service account's group permissions apply to all object access within the handler

### Public Access Pattern

For `auth_required: False` Web APIs:
- Internally executed as a `public_access` service account user
- This user belongs to the `public_access` group
- Only objects explicitly granted to `public_access` are accessible
- Security checks remain uniform (no special code paths)

---

## Error Types

```
AppOSError (base)
├── AppOSSecurityError      — permission denied (raised by auto-import layer)
├── AppOSDispatchError      — invalid dispatch target (raised by engine.dispatch)
├── AppOSValidationError    — input validation failed (raised by decorators)
├── AppOSTimeoutError       — execution timeout (raised by step/process engine)
├── AppOSIntegrationError   — outbound API failure (raised by integration decorator)
├── AppOSRecordError        — record CRUD failure (raised by record service)
└── AppOSObjectNotFoundError — object not found in registry
```

### Standard Error Format

All errors include:

```python
{
    "error_type": "AppOSSecurityError",
    "message": "Access denied: user 'user_123' cannot access 'crm.records.financial'",
    "execution_id": "exec_abc123",
    "object_ref": "crm.records.financial",
    "object_type": "record",
    "user_id": "user_123",
    "app": "crm",
    "timestamp": "2026-02-07T14:30:00Z",
    "process_instance_id": "proc_001",  // if within a process
    "step_name": "validate_data",       // if within a step
    "dependency_chain": ["crm.rules.pricing → crm.records.financial"],
    "stack_trace": "..."
}
```

---

## Session Management (Redis-Based)

| Setting | Default | Configurable In |
|---|---|---|
| Session timeout | 3600s (1 hour) | `appos.yaml` + Admin Console |
| Idle timeout | 1800s (30 min) | `appos.yaml` + Admin Console |
| Max concurrent sessions per user | 5 | `appos.yaml` + Admin Console |
| Session storage | Redis (DB 4) | `appos.yaml` |
| Permission cache TTL | 300s (5 min) | `appos.yaml` + Admin Console |

**Why sessions over JWT:** Instant revocation (delete from Redis), smaller cookies, server-controlled lifetime, Redis already in stack. JWT adds complexity for no benefit in this architecture.

---

*Reference document — see `AppOS_Design.md` §6 for integration context.*
