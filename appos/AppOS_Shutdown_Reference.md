# AppOS — Graceful Shutdown Reference

> **Referenced from:** `AppOS_Design.md` §8 CentralizedRuntime  
> **Version:** 2.1 — February 12, 2026

---

## Overview

AppOS performs a coordinated graceful shutdown to avoid data loss, orphaned processes, and incomplete log writes. Shutdown is triggered by `SIGTERM` (container orchestrators), `SIGINT` (Ctrl+C), or the Admin Console "Shutdown" action.

---

## Shutdown Sequence

```
Signal received (SIGTERM / SIGINT)
  │
  ├─ 1. Stop accepting new requests
  │     └─ Reflex HTTP server stops accepting connections
  │     └─ Web API endpoints return 503 Service Unavailable
  │
  ├─ 2. Drain in-flight requests (grace period: 30s default)
  │     └─ Active HTTP requests allowed to complete
  │     └─ Active rule executions allowed to finish
  │
  ├─ 3. Stop Celery workers gracefully
  │     └─ Send SIGTERM to Celery worker processes
  │     └─ Running tasks allowed to complete (up to task soft_time_limit)
  │     └─ No new tasks consumed from queues
  │     └─ In-progress process steps marked as "interrupted" in process_step_log
  │
  ├─ 4. Flush all log queues
  │     └─ AsyncLogQueue.flush() called for every (type, category) queue
  │     └─ Remaining entries written to disk synchronously
  │     └─ Log "platform_shutdown" event to system/execution/
  │
  ├─ 5. Close database connections
  │     └─ SQLAlchemy engine.dispose() for each Connected System engine
  │     └─ Platform DB connection pool disposed
  │
  ├─ 6. Close Redis connections
  │     └─ Redis connection pool closed (sessions, cache, Celery broker)
  │
  └─ 7. Exit
        └─ Exit code 0 (clean) or 1 (forced after timeout)
```

---

## Configuration

```yaml
# appos.yaml
shutdown:
  grace_period_seconds: 30      # time to drain in-flight requests
  celery_shutdown_timeout: 60   # max wait for Celery tasks to finish
  force_kill_after: 90          # SIGKILL after this many seconds
```

---

## Process Instance Handling

- **Running processes** continue their current step until completion
- **Pending steps** are NOT started — process instance status set to `"interrupted"`
- On next startup, interrupted processes can be resumed (configurable: `auto_resume: true` in appos.yaml)
- `process_step_log` records interruption with `error_info: {"reason": "platform_shutdown"}`

---

## Celery Worker Shutdown

Celery workers use the **warm shutdown** strategy:

1. Worker stops consuming new tasks from the queue
2. Currently executing tasks are allowed to finish (up to `soft_time_limit`)
3. If a task exceeds `soft_time_limit`, it receives `SoftTimeLimitExceeded` and should clean up
4. After `celery_shutdown_timeout`, remaining tasks are force-terminated (`SIGKILL`)

---

## Admin Console Trigger

System admins can initiate shutdown from **Admin > System > Shutdown**:

- Confirmation dialog with "Drain active requests" option
- Broadcasts shutdown event to all connected admin sessions
- Logs admin-initiated shutdown to `system/security/`

---

*Reference document — see `AppOS_Design.md` §8 for CentralizedRuntime context.*
