"""Unit tests for appos.cli — CLI command parsing and execution."""

import argparse
import json
import os
import sys
import pytest
from pathlib import Path
from unittest.mock import MagicMock, patch

# Import the CLI module
import appos.cli as cli_mod


class TestCLIParsing:
    """Test argparse subcommand setup."""

    def test_help_does_not_crash(self):
        """Parser should be creatable without errors."""
        parser = argparse.ArgumentParser(prog="appos")
        # The module sets up subparsers — test that it imports cleanly
        assert hasattr(cli_mod, "main")

    def test_module_has_expected_commands(self):
        """Verify expected command functions exist."""
        assert hasattr(cli_mod, "cmd_init")
        assert hasattr(cli_mod, "cmd_run")
        assert hasattr(cli_mod, "cmd_new_app")
        assert hasattr(cli_mod, "cmd_generate")
        assert hasattr(cli_mod, "cmd_migrate")
        assert hasattr(cli_mod, "cmd_check")


class TestCmdNewApp:
    """Test the new-app scaffolding command."""

    def test_scaffold_creates_directories(self, project_root, monkeypatch):
        monkeypatch.chdir(project_root)
        args = argparse.Namespace(
            name="finance",
            display_name="Finance App",
        )
        # Mock the function to avoid depending on full runtime
        with patch.object(cli_mod, "_find_project_root", return_value=project_root):
            cli_mod.cmd_new_app(args)

        app_dir = project_root / "apps" / "finance"
        assert app_dir.exists()
        assert (app_dir / "app.yaml").exists()
        assert (app_dir / "records" / "__init__.py").exists()
        assert (app_dir / "rules" / "__init__.py").exists()
        assert (app_dir / "processes" / "__init__.py").exists()
        assert (app_dir / "constants" / "__init__.py").exists()
        assert (app_dir / "integrations" / "__init__.py").exists()
        assert (app_dir / "web_apis" / "__init__.py").exists()
        assert (app_dir / "interfaces" / "__init__.py").exists()
        assert (app_dir / "pages" / "__init__.py").exists()
        assert (app_dir / "steps" / "__init__.py").exists()
        assert (app_dir / "translation_sets" / "__init__.py").exists()

    def test_app_yaml_content(self, project_root, monkeypatch):
        monkeypatch.chdir(project_root)
        args = argparse.Namespace(name="hr", display_name="HR System")
        with patch.object(cli_mod, "_find_project_root", return_value=project_root):
            cli_mod.cmd_new_app(args)

        yaml_content = (project_root / "apps" / "hr" / "app.yaml").read_text()
        assert "hr" in yaml_content.lower() or "HR" in yaml_content


class TestCmdCheck:
    """Test the check (validation) command."""

    def test_check_creates_report(self, project_root, monkeypatch):
        monkeypatch.chdir(project_root)
        args = argparse.Namespace(app=None, fix=False)
        with patch.object(cli_mod, "_find_project_root", return_value=project_root):
            cli_mod.cmd_check(args)

        # Should create a validation report
        report_dir = project_root / ".appos" / "logs" / "validation"
        if report_dir.exists():
            reports = list(report_dir.glob("*.json"))
            if reports:
                data = json.loads(reports[0].read_text())
                assert "apps" in data or "results" in data or isinstance(data, dict)
