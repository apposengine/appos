"""
Integration tests — CLI end-to-end workflows.

Tests the CLI commands using a real (temp) project structure.
"""

import json
import argparse
import pytest
from pathlib import Path
from unittest.mock import patch

import appos.cli as cli_mod


@pytest.mark.integration
class TestCLINewAppIntegration:
    """Test appos new-app end-to-end."""

    def test_full_scaffold(self, integration_project, monkeypatch):
        monkeypatch.chdir(integration_project)
        args = argparse.Namespace(name="finance", display_name="Finance Module")
        with patch.object(cli_mod, "_find_project_root", return_value=integration_project):
            cli_mod.cmd_new_app(args)

        app_dir = integration_project / "apps" / "finance"
        assert app_dir.exists()

        # Verify all expected directories
        expected_dirs = [
            "records", "rules", "constants", "processes", "steps",
            "integrations", "web_apis", "interfaces", "pages",
            "translation_sets",
        ]
        for d in expected_dirs:
            assert (app_dir / d).is_dir(), f"Missing directory: {d}"
            assert (app_dir / d / "__init__.py").exists(), f"Missing __init__.py in {d}"

        # Verify app.yaml was created
        yaml_path = app_dir / "app.yaml"
        assert yaml_path.exists()
        content = yaml_path.read_text()
        assert "finance" in content.lower()

    def test_duplicate_app_handling(self, integration_project, monkeypatch):
        """Creating an app that already exists should handle gracefully."""
        monkeypatch.chdir(integration_project)
        args = argparse.Namespace(name="crm", display_name="CRM")
        with patch.object(cli_mod, "_find_project_root", return_value=integration_project):
            # Should not crash — existing app
            try:
                cli_mod.cmd_new_app(args)
            except (FileExistsError, SystemExit):
                pass  # Acceptable behavior


@pytest.mark.integration
class TestCLICheckIntegration:
    """Test appos check end-to-end."""

    def test_check_valid_project(self, integration_project, monkeypatch):
        monkeypatch.chdir(integration_project)
        args = argparse.Namespace(app=None, fix=False)
        with patch.object(cli_mod, "_find_project_root", return_value=integration_project):
            cli_mod.cmd_check(args)

    def test_check_specific_app(self, integration_project, monkeypatch):
        monkeypatch.chdir(integration_project)
        args = argparse.Namespace(app="crm", fix=False)
        with patch.object(cli_mod, "_find_project_root", return_value=integration_project):
            cli_mod.cmd_check(args)


@pytest.mark.integration
class TestCLIGenerateIntegration:
    """Test appos generate end-to-end."""

    def test_generate_all(self, integration_project, monkeypatch):
        monkeypatch.chdir(integration_project)
        args = argparse.Namespace(app=None, only=None)
        with patch.object(cli_mod, "_find_project_root", return_value=integration_project):
            cli_mod.cmd_generate(args)

    def test_generate_specific_app(self, integration_project, monkeypatch):
        monkeypatch.chdir(integration_project)
        args = argparse.Namespace(app="crm", only=None)
        with patch.object(cli_mod, "_find_project_root", return_value=integration_project):
            cli_mod.cmd_generate(args)
