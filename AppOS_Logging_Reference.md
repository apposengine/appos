# AppOS — Logging & Monitoring Reference

> **Referenced from:** `AppOS_Design.md` §14 Logging  
> **Version:** 2.1 — February 12, 2026

---

## Log Architecture

### Per Object-Type Log Folders (Option A — Sub-Folder by Category)

Logs are organized by **object type**, then split into **category sub-folders** (execution, performance, security):

```
logs/
├── rules/
│   ├── execution/          # Rule call logs (input/output, success/failure)
│   ├── performance/        # Duration, p50/p95/p99, cache stats
│   └── security/           # Permission checks, denials
├── processes/
│   ├── execution/          # Process start/complete/fail events
│   ├── performance/        # Step durations, total duration
│   └── security/           # Process-level permission checks
├── steps/
│   ├── execution/          # Individual step execution
│   └── performance/        # Step duration, retry counts
├── integrations/
│   ├── execution/          # Outbound API call logs
│   ├── performance/        # Latency, response size
│   └── security/           # Auth failures, credential usage
├── web_apis/
│   ├── execution/          # Inbound API request logs
│   ├── performance/        # Response time, payload size
│   └── security/           # Auth checks, service account usage
├── records/
│   ├── execution/          # CRUD operation logs
│   ├── performance/        # Query duration, row count
│   └── security/           # Row-level security, permission checks
├── interfaces/
│   ├── execution/          # Render events
│   └── security/           # UI access checks
├── pages/
│   ├── execution/          # Page load events
│   └── security/           # Page access checks
├── constants/
│   └── execution/          # Constant resolution events
├── documents/
│   ├── execution/          # Upload/download events
│   └── security/           # Document access checks
├── folders/
│   ├── execution/          # Folder operations
│   └── security/           # Folder access checks
├── translation_sets/
│   └── execution/          # Translation lookups
├── connected_systems/
│   ├── execution/          # Connection pool events
│   └── security/           # Credential access logs
├── system/
│   ├── execution/          # Platform startup, shutdown, config changes
│   └── security/           # Admin login, system-level security events
└── admin/
    ├── execution/          # Admin console actions (user/group changes)
    └── security/           # Admin authentication, privilege escalation
```

Files rotate daily (e.g., `2026-02-12.jsonl`). Each line is a single JSON object.

**Retention by category:**
- `execution/` — 90 days
- `performance/` — 30 days  
- `security/` — 365 days (compliance)

---

## Log Entry Formats (Structured JSON)

### Expression Rule Execution

```json
{
    "timestamp": "2026-02-12T10:30:00.123Z",
    "level": "INFO",
    "event": "rule_executed",
    "execution_id": "exec_abc123",
    "object_ref": "crm.rules.calculate_discount",
    "app": "crm",
    "user_id": "user_42",
    "duration_ms": 12.5,
    "success": true,
    "process_instance_id": "proc_001",
    "step_name": "calc_step",
    "dependencies_accessed": ["crm.constants.discount_rate"],
    "cached": false
}
```

### Process Instance Event

```json
{
    "timestamp": "2026-02-12T10:30:00.000Z",
    "level": "INFO",
    "event": "process_started",
    "execution_id": "exec_def456",
    "object_ref": "crm.processes.onboard_customer",
    "app": "crm",
    "user_id": "user_42",
    "process_instance_id": "proc_002",
    "display_name": "Onboard Customer: Acme Corp",
    "inputs": {"customer_name": "Acme Corp"},
    "started_by": "web_api:crm.web_apis.customer_api"
}
```

### Integration / Web API Call

```json
{
    "timestamp": "2026-02-12T10:30:01.500Z",
    "level": "INFO",
    "event": "integration_called",
    "execution_id": "exec_ghi789",
    "object_ref": "crm.integrations.send_to_salesforce",
    "app": "crm",
    "user_id": "user_42",
    "connected_system": "salesforce_prod",
    "method": "POST",
    "url": "https://api.salesforce.com/v58/sobjects/Contact",
    "status_code": 201,
    "duration_ms": 450,
    "success": true,
    "log_payload": false,
    "request_size_bytes": 1024,
    "response_size_bytes": 512
}
```

**Payload logging:** By default, request/response bodies are NOT logged. Enable per-integration:

```python
@integration(connected_system="salesforce_prod", log_payload=True)
def send_to_salesforce(ctx):
    ...
```

### Record CRUD

```json
{
    "timestamp": "2026-02-12T10:30:02.000Z",
    "level": "INFO",
    "event": "record_updated",
    "execution_id": "exec_jkl012",
    "object_ref": "crm.records.customer",
    "app": "crm",
    "user_id": "user_42",
    "record_id": 12345,
    "operation": "update",
    "fields_changed": ["status", "last_contacted"],
    "process_instance_id": "proc_002"
}
```

### Security Event

```json
{
    "timestamp": "2026-02-12T10:30:03.000Z",
    "level": "WARNING",
    "event": "security_denied",
    "execution_id": "exec_mno345",
    "object_ref": "finance.records.salary",
    "object_type": "record",
    "permission_needed": "view",
    "app": "finance",
    "user_id": "user_42",
    "user_groups": ["sales", "support"],
    "source_object": "crm.rules.check_salary",
    "dependency_chain": ["crm.rules.check_salary → finance.records.salary"]
}
```

---

## Async Logging Pipeline

The auto-import layer blocks ONLY on the security check. All other logging is non-blocking:

```
Object Access
  ↓
[BLOCKING] Security Check → Redis permission cache → DB fallback
  ↓ (denied? → raise AppOSSecurityError)
[NON-BLOCKING] Push log entry to in-memory queue
  ↓
Background Flush Thread (every 100ms or 50 entries, whichever first)
  ↓
Write to log file
```

### Queue Configuration (appos.yaml)

```yaml
logging:
  async_queue:
    flush_interval_ms: 100
    flush_batch_size: 50
    max_queue_size: 10000    # drop oldest if exceeded
```

---

## Log Rotation & Cleanup

### Configuration (appos.yaml)

```yaml
logging:
  level: INFO
  format: json
  directory: logs
  rotation:
    strategy: daily          # daily | size
    max_file_size_mb: 100    # used when strategy=size
    compress_after_days: 7   # gzip files older than 7 days
  retention:
    execution_days: 90       # execution logs
    performance_days: 30     # performance logs
    security_days: 365       # security/access logs (compliance)
  cleanup_schedule: "0 2 * * *"  # nightly cleanup cron
  async_queue:
    flush_interval_ms: 100
    flush_batch_size: 50
    max_queue_size: 10000
```

### Admin Console Controls

| Setting | Admin Console Location | Effect |
|---|---|---|
| Log level | Settings → Logging | Change runtime level without restart |
| Retention days | Settings → Logging | How long to keep logs |
| Compression | Settings → Logging | When to compress old logs |
| Payload logging | Per-integration | Toggle log_payload default |
| View logs | Monitoring → Logs | Live tail, search, filter by type |

---

## Performance Logging

All object types record execution duration. This enables the Performance Dashboard:

| Metric | Source Folder | Aggregation |
|---|---|---|
| Rule execution time | rules/performance/ | P50, P95, P99 per rule |
| Process duration | processes/performance/ | Average per process type |
| Step duration | steps/performance/ | Per step, per process |
| Integration latency | integrations/performance/ | Per connected system |
| Web API response time | web_apis/performance/ | Per endpoint |
| Record query time | records/performance/ | Per record type, per operation |

---

*Reference document — see `AppOS_Design.md` §14 for integration context.*
