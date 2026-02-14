"""Unit tests for appos.engine.logging — FileLogger, AsyncLogQueue, LogRetentionManager."""

import json
import os
import time
import pytest
from pathlib import Path
from unittest.mock import patch, MagicMock

from appos.engine.logging import (
    FileLogger,
    LogEntry,
    LogRetentionManager,
    log_rule_execution,
    log_security_event,
    log_system_event,
    OBJECT_TYPE_CATEGORIES,
    DEFAULT_RETENTION,
)


class TestObjectTypeCategories:
    """Verify the category mapping is complete."""

    def test_all_14_types_have_categories(self):
        expected_types = {
            "expression_rule", "constant", "record", "process", "step",
            "integration", "web_api", "interface", "page", "site",
            "document", "folder", "translation_set", "connected_system",
        }
        assert set(OBJECT_TYPE_CATEGORIES.keys()) == expected_types

    def test_categories_are_lists(self):
        for obj_type, cats in OBJECT_TYPE_CATEGORIES.items():
            assert isinstance(cats, (list, tuple, set)), f"{obj_type} categories not iterable"


class TestLogEntry:
    def test_creation(self):
        entry = LogEntry(
            object_type="expression_rule",
            category="execution",
            data={"key": "value"},
        )
        assert entry.object_type == "expression_rule"
        assert entry.category == "execution"
        assert entry.data == {"key": "value"}

    def test_to_json(self):
        entry = LogEntry(
            object_type="expression_rule",
            category="execution",
            data={"rule": "calc"},
        )
        raw = entry.to_json()
        parsed = json.loads(raw)
        assert parsed["rule"] == "calc"


class TestFileLogger:
    """Test FileLogger file writing."""

    def test_write_creates_file(self, tmp_path):
        logger = FileLogger(log_dir=str(tmp_path / "logs"))
        entry = LogEntry(
            object_type="expression_rule",
            category="execution",
            data={"ts": "2026-02-14T00:00:00Z", "exec_id": "test", "status": "ok"},
        )
        logger.write(entry)

        # Check file was created under expression_rule/execution/
        log_dir = tmp_path / "logs" / "expression_rule" / "execution"
        assert log_dir.exists()
        files = list(log_dir.glob("*.jsonl"))
        assert len(files) == 1

        # Read and verify content
        content = files[0].read_text().strip()
        parsed = json.loads(content)
        assert parsed["exec_id"] == "test"

    def test_write_batch(self, tmp_path):
        logger = FileLogger(log_dir=str(tmp_path / "logs"))
        entries = [
            LogEntry("expression_rule", "execution", {"n": i})
            for i in range(5)
        ]
        logger.write_batch(entries)

        log_dir = tmp_path / "logs" / "expression_rule" / "execution"
        files = list(log_dir.glob("*.jsonl"))
        assert len(files) == 1
        lines = files[0].read_text().strip().split("\n")
        assert len(lines) == 5


class TestLogRetentionManager:
    """Test retention cleanup."""

    def test_creation(self, tmp_path):
        mgr = LogRetentionManager(
            log_dir=str(tmp_path / "logs"),
            retention_days={"execution": 90, "performance": 30},
        )
        assert mgr is not None

    def test_cleanup_empty_dir(self, tmp_path):
        log_dir = tmp_path / "logs"
        log_dir.mkdir()
        mgr = LogRetentionManager(log_dir=str(log_dir))
        result = mgr.cleanup()
        assert isinstance(result, dict)


class TestLogBuilders:
    """Test convenience log entry builder functions."""

    def test_log_rule_execution(self):
        entry = log_rule_execution(
            object_ref="crm.rules.calc",
            execution_id="exec_001",
            app_name="crm",
            status="success",
            duration_ms=15.5,
        )
        assert isinstance(entry, LogEntry)
        assert entry.object_type == "expression_rule"
        assert entry.category == "execution"
        assert entry.data["object_ref"] == "crm.rules.calc"
        assert entry.data["status"] == "success"

    def test_log_security_event(self):
        entry = log_security_event(
            event_type="access_denied",
            object_ref="crm.records.customer",
            user_id=1,
            username="test",
            details={"permission": "delete"},
        )
        assert isinstance(entry, LogEntry)
        assert entry.category == "security"

    def test_log_system_event(self):
        entry = log_system_event(
            event_type="startup",
            message="Platform started",
        )
        assert isinstance(entry, LogEntry)
        assert entry.category == "system"
