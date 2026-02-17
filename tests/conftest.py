"""
AppOS Test Suite — Shared fixtures and configuration.

Run:  pytest tests/ -v
"""

from __future__ import annotations

import json
import os
import shutil
import tempfile
from pathlib import Path
from typing import Any, Dict
from unittest.mock import MagicMock, patch

import pytest


# ---------------------------------------------------------------------------
# Environment setup — avoid touching real Redis / Postgres in unit tests
# ---------------------------------------------------------------------------

@pytest.fixture(autouse=True)
def _isolate_config(monkeypatch):
    """Reset global singletons between tests."""
    import appos.engine.config as cfg_mod

    cfg_mod._platform_config = None
    cfg_mod._app_configs = {}


@pytest.fixture
def tmp_dir(tmp_path):
    """Provide a clean temp directory."""
    return tmp_path


@pytest.fixture
def project_root(tmp_path):
    """
    Create a minimal AppOS project tree with appos.yaml + one app.
    Returns the root Path.
    """
    root = tmp_path / "project"
    root.mkdir()

    # appos.yaml
    (root / "appos.yaml").write_text(
        "platform:\n"
        "  name: TestPlatform\n"
        "  version: '2.0.0'\n"
        "environment: dev\n"
        "database:\n"
        "  url: postgresql://test:test@localhost:5432/test_db\n"
        "redis:\n"
        "  url: redis://localhost:6379/0\n"
        "apps:\n"
        "  - crm\n",
        encoding="utf-8",
    )

    # apps/taskm/app.yaml
    taskm = root / "apps" / "taskm"
    taskm.mkdir(parents=True)
    (taskm / "app.yaml").write_text(
        "app:\n"
        "  name: Task Manager\n"
        "  short_name: taskm\n"
        "  version: '1.0.0'\n"
        "  description: Demo task management app\n"
        "  groups:\n"
        "    - dev_team\n"
        "    - managers\n"
        "    - taskm_admins\n",
        encoding="utf-8",
    )

    # App subdirectories
    for subdir in ("records", "rules", "constants", "processes", "steps",
                   "integrations", "web_apis", "interfaces", "pages",
                   "sites", "translation_sets", "connected_systems"):
        d = taskm / subdir
        d.mkdir()
        (d / "__init__.py").write_text("")

    # Runtime directory
    (taskm / "runtime" / "documents").mkdir(parents=True)

    return root


@pytest.fixture
def mock_db_session():
    """Return a mock SQLAlchemy session factory."""
    session = MagicMock()
    session.query.return_value = session
    session.filter.return_value = session
    session.all.return_value = []
    session.first.return_value = None
    session.commit.return_value = None
    session.rollback.return_value = None
    session.close.return_value = None

    factory = MagicMock(return_value=session)
    factory.__enter__ = MagicMock(return_value=session)
    factory.__exit__ = MagicMock(return_value=False)
    return factory


@pytest.fixture
def mock_redis():
    """Return a mock Redis client."""
    client = MagicMock()
    client.ping.return_value = True
    client.get.return_value = None
    client.set.return_value = True
    client.delete.return_value = 1
    client.scan_iter.return_value = iter([])
    return client


@pytest.fixture
def execution_context():
    """Create a standard ExecutionContext for tests."""
    from appos.engine.context import ExecutionContext

    return ExecutionContext(
        user_id=1,
        username="test_user",
        user_type="basic",
        user_groups={"dev_team", "managers", "taskm_admins"},
        app_name="taskm",
        preferred_language="en",
    )


@pytest.fixture
def admin_context():
    """Create a system_admin ExecutionContext."""
    from appos.engine.context import ExecutionContext

    return ExecutionContext(
        user_id=0,
        username="admin",
        user_type="system_admin",
        user_groups={"system_admins"},
        app_name=None,
    )
