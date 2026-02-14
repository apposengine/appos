"""
AppOS Configuration — Load and validate appos.yaml + app.yaml at startup.

Usage:
    from appos.engine.config import load_platform_config, load_app_config, get_platform_config
"""

from __future__ import annotations

import os
from pathlib import Path
from typing import Any, Dict, List, Optional

import yaml
from pydantic import BaseModel, Field, field_validator


# ---------------------------------------------------------------------------
# Pydantic models for appos.yaml
# ---------------------------------------------------------------------------

class DatabaseConfig(BaseModel):
    url: str = "postgresql://user:pass@localhost:5432/appos_core"
    pool_size: int = 10
    max_overflow: int = 20
    pool_timeout: int = 30
    pool_recycle: int = 1800
    pool_pre_ping: bool = True


class RedisConfig(BaseModel):
    url: str = "redis://localhost:6379/0"


class CeleryAutoscaleConfig(BaseModel):
    enabled: bool = True
    min: int = 4
    max: int = 16


class CeleryConfig(BaseModel):
    broker: str = "redis://localhost:6379/0"
    result_backend: str = "redis://localhost:6379/1"
    beat_schedule_check: int = 60
    concurrency: int = 4
    autoscale: CeleryAutoscaleConfig = CeleryAutoscaleConfig()
    queues: List[str] = Field(default_factory=lambda: ["celery", "process_steps", "scheduled"])


class SecurityConfig(BaseModel):
    session_timeout: int = 3600
    idle_timeout: int = 1800
    max_concurrent_sessions: int = 5
    password_min_length: int = 8
    permission_cache_ttl: int = 300
    max_login_attempts: int = 5


class LogRetentionConfig(BaseModel):
    execution_days: int = 90
    performance_days: int = 30
    security_days: int = 365


class LogAsyncQueueConfig(BaseModel):
    flush_interval_ms: int = 100
    flush_batch_size: int = 50
    max_queue_size: int = 10000


class LogRotationConfig(BaseModel):
    strategy: str = "daily"
    max_file_size_mb: int = 100
    compress_after_days: int = 7


class LoggingConfig(BaseModel):
    level: str = "INFO"
    format: str = "json"
    directory: str = ".appos/logs"
    rotation: LogRotationConfig = LogRotationConfig()
    retention: LogRetentionConfig = LogRetentionConfig()
    cleanup_schedule: str = "0 2 * * *"
    async_queue: LogAsyncQueueConfig = LogAsyncQueueConfig()


class ProcessInstancesConfig(BaseModel):
    archive_after_days: int = 90
    partition_range: str = "monthly"


class DocumentsConfig(BaseModel):
    max_upload_size_mb: int = 50


class UIAdminThemeConfig(BaseModel):
    primary_color: str = "#1F2937"
    font_family: str = "Inter"


class UIConfig(BaseModel):
    admin_theme: UIAdminThemeConfig = UIAdminThemeConfig()
    default_pagination: int = 25


class PlatformConfig(BaseModel):
    """Root model for appos.yaml."""
    name: str = "AppOS Platform"
    version: str = "2.0.0"
    environment: str = "dev"

    database: DatabaseConfig = DatabaseConfig()
    redis: RedisConfig = RedisConfig()
    celery: CeleryConfig = CeleryConfig()
    security: SecurityConfig = SecurityConfig()
    logging: LoggingConfig = LoggingConfig()
    process_instances: ProcessInstancesConfig = ProcessInstancesConfig()
    documents: DocumentsConfig = DocumentsConfig()
    ui: UIConfig = UIConfig()
    apps: List[str] = Field(default_factory=list)

    @field_validator("environment")
    @classmethod
    def validate_environment(cls, v: str) -> str:
        if v not in ("dev", "staging", "prod"):
            raise ValueError(f"environment must be dev/staging/prod, got '{v}'")
        return v


# ---------------------------------------------------------------------------
# Pydantic models for app.yaml
# ---------------------------------------------------------------------------

class AppSecurityDefaultsCategory(BaseModel):
    groups: List[str] = Field(default_factory=list)


class AppSecurityDefaults(BaseModel):
    logic: AppSecurityDefaultsCategory = AppSecurityDefaultsCategory()
    ui: AppSecurityDefaultsCategory = AppSecurityDefaultsCategory()


class AppSecurity(BaseModel):
    defaults: AppSecurityDefaults = AppSecurityDefaults()


class AppTheme(BaseModel):
    primary_color: str = "#3B82F6"
    secondary_color: str = "#1E40AF"
    accent_color: str = "#DBEAFE"
    font_family: str = "Inter"
    border_radius: str = "8px"


class AppFeatures(BaseModel):
    audit: bool = True
    soft_delete: bool = True
    document_versioning: bool = True


class AppLogging(BaseModel):
    process_logging: bool = True
    audit_logging: bool = True
    event_logging: bool = True


class AppConfig(BaseModel):
    """Root model for app.yaml."""
    name: str
    short_name: str
    version: str = "1.0.0"
    description: str = ""
    groups: List[str] = Field(default_factory=list)
    db_connected_system: Optional[str] = None
    theme: AppTheme = AppTheme()
    environment: str = "dev"
    security: AppSecurity = AppSecurity()
    features: AppFeatures = AppFeatures()
    logging: AppLogging = AppLogging()

    @field_validator("environment")
    @classmethod
    def validate_environment(cls, v: str) -> str:
        if v not in ("dev", "staging", "prod"):
            raise ValueError(f"environment must be dev/staging/prod, got '{v}'")
        return v


# ---------------------------------------------------------------------------
# Config Loading Functions
# ---------------------------------------------------------------------------

_platform_config: Optional[PlatformConfig] = None
_app_configs: Dict[str, AppConfig] = {}


def _find_project_root() -> Path:
    """Find the project root by looking for appos.yaml."""
    # Start from CWD and walk up
    current = Path.cwd()
    for parent in [current, *current.parents]:
        if (parent / "appos.yaml").exists():
            return parent
    return current


def get_project_root() -> Path:
    """Return the project root directory."""
    return _find_project_root()


def load_platform_config(config_path: Optional[str] = None) -> PlatformConfig:
    """
    Load and validate appos.yaml.

    Args:
        config_path: Explicit path to appos.yaml. If None, auto-discovers.

    Returns:
        Validated PlatformConfig instance.
    """
    global _platform_config

    if config_path is None:
        root = _find_project_root()
        config_path = str(root / "appos.yaml")

    path = Path(config_path)
    if not path.exists():
        # Return defaults if no config file
        _platform_config = PlatformConfig()
        return _platform_config

    with open(path, "r", encoding="utf-8") as f:
        raw = yaml.safe_load(f) or {}

    # appos.yaml has nested structure: platform.name, database.url, etc.
    # Flatten the top-level "platform" key if present
    platform_data = raw.get("platform", {})
    config_data = {
        "name": platform_data.get("name", raw.get("name", "AppOS Platform")),
        "version": platform_data.get("version", raw.get("version", "2.0.0")),
        "environment": platform_data.get("environment", raw.get("environment", "dev")),
        "database": raw.get("database", {}),
        "redis": raw.get("redis", {}),
        "celery": raw.get("celery", {}),
        "security": raw.get("security", {}),
        "logging": raw.get("logging", {}),
        "process_instances": raw.get("process_instances", {}),
        "documents": raw.get("documents", {}),
        "ui": raw.get("ui", {}),
        "apps": raw.get("apps", []),
    }

    _platform_config = PlatformConfig(**config_data)
    return _platform_config


def load_app_config(app_short_name: str, apps_dir: Optional[str] = None) -> AppConfig:
    """
    Load and validate an app.yaml for a specific app.

    Args:
        app_short_name: The app short name (e.g., 'crm').
        apps_dir: Base path to apps/ directory. If None, auto-discovers.

    Returns:
        Validated AppConfig instance.
    """
    if apps_dir is None:
        root = _find_project_root()
        apps_dir = str(root / "apps")

    config_path = Path(apps_dir) / app_short_name / "app.yaml"
    if not config_path.exists():
        raise FileNotFoundError(f"App config not found: {config_path}")

    with open(config_path, "r", encoding="utf-8") as f:
        raw = yaml.safe_load(f) or {}

    # app.yaml wraps under "app:" key
    app_data = raw.get("app", raw)

    # Map groups from top-level if present
    if "groups" in raw and "groups" not in app_data:
        app_data["groups"] = raw["groups"]

    config = AppConfig(**app_data)
    _app_configs[app_short_name] = config
    return config


def get_platform_config() -> PlatformConfig:
    """Get the currently loaded platform config, loading if necessary."""
    global _platform_config
    if _platform_config is None:
        _platform_config = load_platform_config()
    return _platform_config


def get_app_config(app_short_name: str) -> AppConfig:
    """Get a loaded app config by short name."""
    if app_short_name not in _app_configs:
        load_app_config(app_short_name)
    return _app_configs[app_short_name]


def get_all_app_configs() -> Dict[str, AppConfig]:
    """Get all loaded app configs."""
    return dict(_app_configs)


def get_environment() -> str:
    """Get the current platform environment."""
    return get_platform_config().environment
