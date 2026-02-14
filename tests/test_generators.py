"""Unit tests for appos.generators — AuditGenerator, ApiGenerator."""

import os
import pytest
from pathlib import Path
from unittest.mock import patch, MagicMock

from appos.generators.audit_generator import AuditGenerator
from appos.generators.api_generator import ApiGenerator


class TestAuditGenerator:
    """Test AuditGenerator discovery and generation."""

    def test_creation(self, project_root):
        gen = AuditGenerator(
            app_name="crm",
            app_path=str(project_root / "apps" / "crm"),
            output_dir=str(project_root / "generated"),
        )
        assert gen is not None

    def test_generate_all_empty(self, project_root):
        """No records → no audit tables generated."""
        gen = AuditGenerator(
            app_name="crm",
            app_path=str(project_root / "apps" / "crm"),
            output_dir=str(project_root / "generated"),
        )
        count = gen.generate_all()
        assert count == 0

    def test_generate_all_with_auditable_record(self, project_root):
        """Record with Meta.audit=True should generate audit table."""
        records_dir = project_root / "apps" / "crm" / "records"
        (records_dir / "customer.py").write_text(
            "from appos.decorators.core import record\n\n"
            "@record\n"
            "class Customer:\n"
            "    class Meta:\n"
            "        table_name = 'customers'\n"
            "        audit = True\n"
            "    first_name: str\n"
            "    last_name: str\n"
            "    email: str\n",
            encoding="utf-8",
        )
        output = project_root / "generated"
        gen = AuditGenerator(
            app_name="crm",
            app_path=str(project_root / "apps" / "crm"),
            output_dir=str(output),
        )
        count = gen.generate_all()
        assert count >= 1

        # Check output files exist
        generated_files = list(output.rglob("*audit*"))
        assert len(generated_files) >= 1

    def test_generate_all_skips_non_audit(self, project_root):
        """Record without Meta.audit=True should be skipped."""
        records_dir = project_root / "apps" / "crm" / "records"
        (records_dir / "note.py").write_text(
            "from appos.decorators.core import record\n\n"
            "@record\n"
            "class Note:\n"
            "    class Meta:\n"
            "        table_name = 'notes'\n"
            "        audit = False\n"
            "    text: str\n",
            encoding="utf-8",
        )
        output = project_root / "generated"
        gen = AuditGenerator(
            app_name="crm",
            app_path=str(project_root / "apps" / "crm"),
            output_dir=str(output),
        )
        count = gen.generate_all()
        assert count == 0


class TestApiGenerator:
    """Test ApiGenerator discovery and generation."""

    def test_creation(self, project_root):
        gen = ApiGenerator(
            app_name="crm",
            app_path=str(project_root / "apps" / "crm"),
            output_dir=str(project_root / "generated"),
        )
        assert gen is not None

    def test_generate_all_empty(self, project_root):
        """No records → no API endpoints generated."""
        gen = ApiGenerator(
            app_name="crm",
            app_path=str(project_root / "apps" / "crm"),
            output_dir=str(project_root / "generated"),
        )
        count = gen.generate_all()
        assert count == 0

    def test_generate_all_with_record(self, project_root):
        """Record with generate_api should produce CRUD endpoints."""
        records_dir = project_root / "apps" / "crm" / "records"
        (records_dir / "customer.py").write_text(
            "from appos.decorators.core import record\n\n"
            "@record\n"
            "class Customer:\n"
            "    class Meta:\n"
            "        table_name = 'customers'\n"
            "        generate_api = True\n"
            "    first_name: str\n"
            "    last_name: str\n",
            encoding="utf-8",
        )
        output = project_root / "generated"
        gen = ApiGenerator(
            app_name="crm",
            app_path=str(project_root / "apps" / "crm"),
            output_dir=str(output),
        )
        count = gen.generate_all()
        assert count >= 1

        # Check generated file exists
        generated_files = list(output.rglob("*customer*api*"))
        assert len(generated_files) >= 1
