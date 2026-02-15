"""Unit tests for appos.engine.config — PlatformConfig, AppConfig, loading."""

import os
import pytest
from pathlib import Path
from unittest.mock import patch

from appos.engine.config import (
    AppConfig,
    DatabaseConfig,
    LoggingConfig,
    PlatformConfig,
    RedisConfig,
    SecurityConfig,
    load_app_config,
    load_platform_config,
)


class TestPlatformConfig:
    """Test PlatformConfig Pydantic model."""

    def test_defaults(self):
        cfg = PlatformConfig()
        assert cfg.name == "AppOS Platform"
        assert cfg.version == "2.0.0"
        assert cfg.environment == "dev"
        assert cfg.database.pool_size == 10
        assert cfg.redis.url == "redis://localhost:6379/0"
        assert cfg.security.session_timeout == 3600
        assert cfg.logging.level == "INFO"

    def test_valid_environments(self):
        for env in ("dev", "staging", "prod"):
            cfg = PlatformConfig(environment=env)
            assert cfg.environment == env

    def test_invalid_environment(self):
        with pytest.raises(ValueError, match="dev/staging/prod"):
            PlatformConfig(environment="test")

    def test_custom_database(self):
        cfg = PlatformConfig(
            database=DatabaseConfig(host="host", user="a", password="b", name="db", pool_size=20)
        )
        assert cfg.database.url == "postgresql://a:b@host:5432/db"
        assert cfg.database.pool_size == 20

    def test_custom_security(self):
        cfg = PlatformConfig(
            security=SecurityConfig(session_timeout=7200, max_login_attempts=10)
        )
        assert cfg.security.session_timeout == 7200
        assert cfg.security.max_login_attempts == 10

    def test_apps_list(self):
        cfg = PlatformConfig(apps=["crm", "finance"])
        assert cfg.apps == ["crm", "finance"]


class TestAppConfig:
    """Test AppConfig Pydantic model."""

    def test_minimal(self):
        cfg = AppConfig(name="CRM App", short_name="crm")
        assert cfg.name == "CRM App"
        assert cfg.short_name == "crm"
        assert cfg.version == "1.0.0"
        assert cfg.groups == []
        assert cfg.features.audit is True

    def test_invalid_environment(self):
        with pytest.raises(ValueError, match="dev/staging/prod"):
            AppConfig(name="X", short_name="x", environment="local")

    def test_with_groups(self):
        cfg = AppConfig(name="CRM", short_name="crm", groups=["crm_users", "crm_admins"])
        assert len(cfg.groups) == 2

    def test_theme_defaults(self):
        cfg = AppConfig(name="X", short_name="x")
        assert cfg.theme.primary_color == "#3B82F6"
        assert cfg.theme.font_family == "Inter"


class TestLoadPlatformConfig:
    """Test load_platform_config() from file."""

    def test_load_from_file(self, project_root, monkeypatch):
        monkeypatch.chdir(project_root)
        cfg = load_platform_config(str(project_root / "appos.yaml"))
        assert cfg.environment == "dev"

    def test_missing_file_returns_defaults(self, tmp_path):
        cfg = load_platform_config(str(tmp_path / "nonexistent.yaml"))
        assert cfg.name == "AppOS Platform"

    def test_load_app_config(self, project_root, monkeypatch):
        monkeypatch.chdir(project_root)
        cfg = load_app_config("crm", apps_dir=str(project_root / "apps"))
        assert cfg.short_name == "crm"
        assert cfg.name == "CRM App"

    def test_load_missing_app_raises(self, project_root):
        with pytest.raises(FileNotFoundError):
            load_app_config("nonexistent", apps_dir=str(project_root / "apps"))
