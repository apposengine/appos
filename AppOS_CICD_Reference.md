# AppOS — CI/CD & Environment Promotion Reference

> **Referenced from:** `AppOS_Design.md` §16 Configuration  
> **Version:** 2.1 — February 12, 2026

---

## Overview

AppOS supports three environments: **dev**, **staging**, **prod**. Environment is set in `appos.yaml` under `platform.environment`. Connected Systems and Constants support per-environment overrides natively.

---

## Environment Promotion Flow

```
  dev  ──────►  staging  ──────►  prod
  (local)       (test)           (live)

  git push      merge to         merge to
  feature/*     staging          main
```

### What Changes Per Environment

| Artifact | Dev | Staging | Prod |
|----------|-----|---------|------|
| `appos.yaml` | Local DB/Redis URLs | Internal test URLs | Production URLs |
| Connected Systems | `environment_overrides.dev` | `environment_overrides.staging` | `environment_overrides.prod` |
| Constants | `environment_overrides.dev` | `environment_overrides.staging` | `environment_overrides.prod` |
| Credentials | Dev keys (admin console) | Test keys (admin console) | Prod keys (admin console) |
| Log level | `DEBUG` | `INFO` | `INFO` or `WARNING` |
| Celery concurrency | 2 | 4 | 8-16 (autoscale) |

### What Does NOT Change

- Application code (`apps/*/`)
- Record definitions, rules, processes, integrations
- Permission model and group definitions
- Decorator configurations

---

## CI/CD Pipeline (Example: GitHub Actions)

```yaml
# .github/workflows/appos-ci.yml
name: AppOS CI/CD

on:
  push:
    branches: [main, staging, "feature/*"]
  pull_request:
    branches: [main, staging]

jobs:
  validate:
    runs-on: ubuntu-latest
    steps:
      - uses: actions/checkout@v4

      - name: Set up Python
        uses: actions/setup-python@v5
        with:
          python-version: "3.12"

      - name: Install dependencies
        run: pip install -r requirements.txt

      - name: Run appos check
        run: appos check
        # Validates: object definitions, permissions, dependencies, imports

      - name: Run unit tests
        run: pytest tests/ -v --tb=short

      - name: Run integration tests
        run: pytest tests/integration/ -v --tb=short
        env:
          APPOS_ENV: test
          DATABASE_URL: postgresql://test:test@localhost:5432/appos_test
          REDIS_URL: redis://localhost:6379/0

  deploy-staging:
    needs: validate
    if: github.ref == 'refs/heads/staging'
    runs-on: ubuntu-latest
    steps:
      - uses: actions/checkout@v4

      - name: Deploy to staging
        run: |
          # 1. Run migrations
          APPOS_ENV=staging appos migrate

          # 2. Regenerate code
          APPOS_ENV=staging appos generate

          # 3. Validate
          APPOS_ENV=staging appos check

          # 4. Restart services (platform-specific)
          # docker-compose -f docker-compose.staging.yml up -d
          # OR: kubectl rollout restart deployment/appos -n staging

  deploy-prod:
    needs: validate
    if: github.ref == 'refs/heads/main'
    runs-on: ubuntu-latest
    environment: production  # requires manual approval
    steps:
      - uses: actions/checkout@v4

      - name: Backup production DB
        run: pg_dump -Fc -f backup_$(date +%Y%m%d_%H%M).dump $PROD_DB_URL

      - name: Deploy to production
        run: |
          APPOS_ENV=prod appos migrate
          APPOS_ENV=prod appos generate
          APPOS_ENV=prod appos check
          # Restart with zero-downtime (rolling restart)
```

---

## Deployment Checklist

| Step | Command | Purpose |
|------|---------|---------|
| 1 | `appos check` | Validate all objects, permissions, dependencies |
| 2 | `pg_dump` | Backup database before migration |
| 3 | `appos migrate` | Run Alembic migrations |
| 4 | `appos generate` | Regenerate SQLAlchemy models, services, UIs |
| 5 | `appos check` (again) | Post-generate validation |
| 6 | Restart services | Rolling restart for zero downtime |
| 7 | Verify `/ready` | Readiness probe confirms all dependencies healthy |
| 8 | Flush Redis caches | Optional — permission cache auto-expires (TTL=5min) |

---

## Environment-Specific Configuration

### Option A: Separate `appos.yaml` per environment

```
config/
├── appos.dev.yaml
├── appos.staging.yaml
└── appos.prod.yaml
```

Selected via `APPOS_ENV` environment variable or `--env` CLI flag.

### Option B: Single `appos.yaml` with env sections

Connected Systems and Constants already support `environment_overrides` natively — no duplicate config needed for those. Only platform-level settings (DB URLs, Redis URLs, Celery config) need env-specific values.

---

## Docker Compose (Development)

```yaml
# docker-compose.yml
version: "3.8"
services:
  appos:
    build: .
    ports:
      - "3000:3000"
    environment:
      - APPOS_ENV=dev
    depends_on:
      - db
      - redis
    volumes:
      - .:/app

  db:
    image: postgres:16
    environment:
      POSTGRES_DB: appos_core
      POSTGRES_USER: appos
      POSTGRES_PASSWORD: devpass
    ports:
      - "5432:5432"

  redis:
    image: redis:7-alpine
    ports:
      - "6379:6379"

  celery-worker:
    build: .
    command: celery -A appos.celery worker -l info -Q celery,process_steps,scheduled
    depends_on:
      - db
      - redis

  celery-beat:
    build: .
    command: celery -A appos.celery beat -l info
    depends_on:
      - db
      - redis
```

---

*Reference document — see `AppOS_Design.md` §16 for configuration context.*
