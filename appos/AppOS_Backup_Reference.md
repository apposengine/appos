# AppOS — Backup & Restore Reference

> **Referenced from:** `AppOS_Design.md` §16 Configuration  
> **Version:** 2.1 — February 12, 2026

---

## Overview

AppOS backup strategy covers three data categories: the platform database (PostgreSQL), app databases (Connected System DBs), and file-system artifacts (logs, uploaded documents, dependency graphs).

---

## What to Back Up

| Category | Location | Method | Frequency |
|----------|----------|--------|-----------|
| **Platform DB** | PostgreSQL (`appos_core`) | `pg_dump` | Daily + before migrations |
| **App databases** | Per-Connected System DBs | `pg_dump` per DB | Daily |
| **Uploaded documents** | `apps/*/runtime/documents/` | File copy / rsync | Daily |
| **Log files** | `.appos/logs/` | Optional — rotated + compressed by retention policy | Weekly (archive) |
| **Dependency graphs** | `.appos/runtime/dependencies/` | File copy | After each `appos check` |
| **Configuration** | `appos.yaml`, `apps/*/app.yaml` | Version control (git) | Every commit |
| **Alembic migrations** | `migrations/versions/` | Version control (git) | Every commit |
| **Generated code** | `.appos/generated/` | NOT backed up — regenerated from source | — |

---

## Backup Procedure

### 1. Platform Database

```bash
# Full dump (compressed, custom format)
pg_dump -Fc -f appos_core_$(date +%Y%m%d).dump appos_core

# Include roles (if needed for full restore)
pg_dumpall --roles-only -f roles_$(date +%Y%m%d).sql
```

### 2. App Databases

```bash
# For each Connected System of type "database"
pg_dump -Fc -f crm_$(date +%Y%m%d).dump crm_prod
pg_dump -Fc -f finance_$(date +%Y%m%d).dump finance_prod
```

### 3. File Artifacts

```bash
# Documents
rsync -a apps/*/runtime/documents/ /backup/documents/

# Dependency graphs (small, but useful for audit)
rsync -a .appos/runtime/dependencies/ /backup/dependencies/
```

---

## Restore Procedure

### 1. Database Restore

```bash
# Drop and recreate
dropdb appos_core
createdb appos_core
pg_restore -d appos_core appos_core_20260212.dump

# Run pending migrations
appos migrate
```

### 2. File Restore

```bash
rsync -a /backup/documents/ apps/*/runtime/documents/
```

### 3. Post-Restore Steps

1. `appos migrate` — ensure DB schema is current
2. `appos generate` — regenerate SQLAlchemy models, services, interfaces
3. `appos check` — validate all objects, permissions, dependencies
4. Flush Redis caches (permission cache, object cache) via Admin Console or CLI
5. Verify Connected System health via `/ready` endpoint

---

## Redis Data

Redis is **not backed up** — it contains only ephemeral data:

| DB | Content | Recovery |
|----|---------|----------|
| 0 | Celery broker queue | Tasks re-queued on restart |
| 1 | Celery results | Regenerated on task completion |
| 2 | Permission cache | Auto-populated from DB on cache miss |
| 3 | Object cache | Auto-populated from filesystem on cache miss |
| 4 | Sessions | Users re-login after restore |

---

## Retention Policy

| Data | Retention | Rationale |
|------|-----------|-----------|
| DB backups | 30 days rolling | Point-in-time recovery |
| Document backups | 30 days rolling | Match DB backup window |
| Log archives | Per `logging.retention` in appos.yaml | Compliance-driven |
| Git history | Indefinite | Source of truth for config + code |

---

## Automation

Recommended: Schedule backups via cron or CI/CD pipeline:

```bash
# /etc/cron.d/appos-backup
0 3 * * * /opt/appos/scripts/backup.sh >> /var/log/appos-backup.log 2>&1
```

---

*Reference document — see `AppOS_Design.md` §16 for configuration context.*
