# AppOS — Monitoring Reference

> **Referenced from:** `AppOS_Design.md` §14 Logging, §13 Admin Console  
> **Version:** 2.1 — February 12, 2026

---

## Overview

AppOS exposes health and readiness endpoints for container orchestration (Kubernetes, Docker Compose) and monitoring systems (Prometheus, Grafana, uptime checks).

---

## Health Endpoints

### `/health` — Liveness Probe

Returns `200 OK` if the platform process is alive. Does NOT check dependencies.

```json
{
  "status": "ok",
  "version": "2.1.0",
  "environment": "prod",
  "uptime_seconds": 86400
}
```

- **Use:** Kubernetes `livenessProbe`, basic uptime monitoring
- **Auth:** None required (public endpoint)
- **Response time target:** < 10ms

### `/ready` — Readiness Probe

Returns `200 OK` only if all critical dependencies are healthy:

```json
{
  "status": "ready",
  "checks": {
    "database": {"status": "ok", "latency_ms": 2.3},
    "redis": {"status": "ok", "latency_ms": 0.8},
    "celery": {"status": "ok", "workers": 4},
    "connected_systems": {
      "crm_database": {"status": "ok", "pool_active": 3, "pool_available": 7},
      "stripe_api": {"status": "ok", "last_health_check": "2026-02-12T10:30:00Z"}
    }
  }
}
```

Returns `503 Service Unavailable` if any critical check fails:

```json
{
  "status": "not_ready",
  "checks": {
    "database": {"status": "ok", "latency_ms": 2.3},
    "redis": {"status": "error", "error": "Connection refused"},
    "celery": {"status": "ok", "workers": 4}
  }
}
```

- **Use:** Kubernetes `readinessProbe`, load balancer health checks
- **Auth:** None required (public endpoint)
- **Response time target:** < 500ms

---

## Connected System Health Checks

Each Connected System with `health_check.enabled: True` is periodically probed:

| Type | Health Check Method |
|------|-------------------|
| `database` | `SELECT 1` query via connection pool |
| `rest_api` | HTTP GET to configured health endpoint |
| `ftp` | FTP `NOOP` command |
| `smtp` | SMTP `EHLO` handshake |
| `imap` | IMAP `NOOP` command |

Results are cached and included in the `/ready` response.

---

## Metrics (Admin Console)

The Admin Console **Monitoring** section provides:

| Metric | Source | Refresh |
|--------|--------|---------|
| Active sessions | Redis DB 4 | Real-time |
| Cache hit rate | Redis DB 2 (permissions) | 1 min |
| Process instances (running/completed/failed) | Platform DB | 1 min |
| Rule execution P50/P95/P99 | `rules/performance/` logs | 5 min |
| Celery queue depth | Redis DB 0 (broker) | Real-time |
| Connected System pool utilization | SQLAlchemy pool stats | 1 min |
| Disk usage (.appos/logs/) | Filesystem | 15 min |

---

## Configuration

```yaml
# appos.yaml
monitoring:
  health_endpoint: "/health"      # liveness probe path
  ready_endpoint: "/ready"        # readiness probe path
  connected_system_check_interval: 60  # seconds between health checks
```

---

## Integration with External Monitoring

| Tool | Integration |
|------|-------------|
| Prometheus | Scrape `/ready` endpoint; parse JSON for metrics |
| Grafana | Dashboard over Prometheus data source |
| Kubernetes | `livenessProbe` → `/health`, `readinessProbe` → `/ready` |
| Docker Compose | `healthcheck: curl -f http://localhost:8000/health` |
| Uptime monitoring | Poll `/health` endpoint |

---

*Reference document — see `AppOS_Design.md` §13 and §14 for Admin Console and Logging context.*
