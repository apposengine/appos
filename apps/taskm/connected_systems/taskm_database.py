"""Database Connected System — PostgreSQL with pool config."""
import appos  # noqa: F401 — auto-injects decorators into builtins


@connected_system(
    name="taskm_database",
    type="database",
    description="Task Manager PostgreSQL database",
)
def taskm_database():
    """
    Database connection with environment-aware overrides and pool tuning.
    Demonstrates: pool_size, max_overflow, pool_pre_ping, pool_reset_on_return,
    environment_overrides (dev/staging/prod), and health_check config.
    """
    return {
        "default": {
            "driver": "postgresql",
            "host": "localhost",
            "port": 5432,
            "database": "taskm_dev",
            "pool_size": 5,
            "max_overflow": 10,
            "pool_timeout": 30,
            "pool_recycle": 1800,
            "pool_pre_ping": True,
            "pool_reset_on_return": "rollback",
        },
        "auth": {
            "type": "basic",
        },
        "environment_overrides": {
            "staging": {
                "host": "staging-db.internal",
                "database": "taskm_staging",
                "pool_size": 10,
            },
            "prod": {
                "host": "prod-db.internal",
                "database": "taskm_prod",
                "pool_size": 25,
                "max_overflow": 50,
            },
        },
        "health_check": {
            "enabled": True,
            "interval_seconds": 60,
        },
    }
