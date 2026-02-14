"""
AppOS Audit Log Generator — Auto-generates {app}_{record}_audit_log tables
for records with Meta.audit = True.

Generates:
    1. SQLAlchemy model for the audit_log table
    2. SQL DDL for direct DB creation
    3. Trigger hooks inserted into the RecordService

Output:
    .appos/generated/{app}/audits/{record}_audit_log.py

Design refs: AppOS_Design.md §9 (Record Processing Pipeline — Audit Log Table)
"""

from __future__ import annotations

import logging
import os
import textwrap
from pathlib import Path
from typing import Any, Dict, List, Optional, Type

from pydantic import BaseModel

logger = logging.getLogger("appos.generators.audit_generator")


class AuditGenerator:
    """
    Generates audit log tables and models for @record objects
    that have Meta.audit = True.

    Usage:
        gen = AuditGenerator(app_name="crm", app_dir="apps/crm",
                             output_dir=".appos/generated/crm/audits")
        count = gen.generate_all()
    """

    def __init__(
        self,
        app_name: str,
        app_dir: str,
        output_dir: str = "",
    ):
        self.app_name = app_name
        self.app_dir = Path(app_dir)
        self.output_dir = Path(output_dir) if output_dir else Path(f".appos/generated/{app_name}/audits")

    def generate_all(self) -> int:
        """
        Discover all @record objects in the app, generate audit log
        tables for those with audit=True.

        Returns:
            Number of audit tables generated.
        """
        from appos.generators.model_generator import parse_record

        records_dir = self.app_dir / "records"
        if not records_dir.exists():
            logger.info(f"No records/ directory in {self.app_dir}")
            return 0

        count = 0
        for py_file in sorted(records_dir.glob("*.py")):
            if py_file.name.startswith("_"):
                continue
            try:
                parsed = self._discover_records(py_file)
                for record in parsed:
                    if record.get("audit", False):
                        self._generate_audit_model(record)
                        count += 1
            except Exception as e:
                logger.warning(f"Failed to parse {py_file}: {e}")

        return count

    def _discover_records(self, py_file: Path) -> List[Dict[str, Any]]:
        """
        Discover @record-decorated Pydantic models in a Python file.

        Returns list of dicts with keys: name, table_name, fields, audit.
        """
        import ast

        records = []
        try:
            source = py_file.read_text(encoding="utf-8")
            tree = ast.parse(source)
        except (SyntaxError, OSError):
            return records

        for node in ast.walk(tree):
            if not isinstance(node, ast.ClassDef):
                continue

            # Check for @record decorator
            has_record_decorator = any(
                (isinstance(d, ast.Name) and d.id == "record")
                or (isinstance(d, ast.Call) and isinstance(d.func, ast.Name) and d.func.id == "record")
                for d in node.decorator_list
            )
            if not has_record_decorator:
                continue

            # Look for Meta inner class with audit=True
            audit = False
            table_name = _to_snake(node.name)
            for item in node.body:
                if isinstance(item, ast.ClassDef) and item.name == "Meta":
                    for meta_item in item.body:
                        if isinstance(meta_item, ast.Assign):
                            for target in meta_item.targets:
                                if isinstance(target, ast.Name) and target.id == "audit":
                                    if isinstance(meta_item.value, ast.Constant):
                                        audit = bool(meta_item.value.value)
                                if isinstance(target, ast.Name) and target.id == "table_name":
                                    if isinstance(meta_item.value, ast.Constant):
                                        table_name = str(meta_item.value.value)

            # Collect fields
            fields = []
            for item in node.body:
                if isinstance(item, ast.AnnAssign) and isinstance(item.target, ast.Name):
                    fields.append(item.target.id)

            records.append({
                "name": node.name,
                "table_name": table_name,
                "fields": fields,
                "audit": audit,
            })

        return records

    def _generate_audit_model(self, record: Dict[str, Any]) -> Path:
        """
        Generate a SQLAlchemy model file for the audit log table.

        Audit log schema:
            id              — Primary key
            record_id       — FK to the record being audited
            field           — Field name that changed
            old_value       — Previous value (JSON-serialized)
            new_value       — New value (JSON-serialized)
            changed_by      — User ID who made the change
            changed_at      — Timestamp of the change
            change_type     — 'create', 'update', 'delete'
        """
        record_name = record["name"]
        table_name = record["table_name"]
        audit_table = f"{self.app_name}_{table_name}_audit_log"

        snake_name = _to_snake(record_name)
        class_name = f"{record_name}AuditLog"

        code = textwrap.dedent(f'''\
            """
            Auto-generated audit log model for {self.app_name}.{record_name}.

            Table: {audit_table}
            Generated by AppOS AuditGenerator.
            """

            from datetime import datetime, timezone

            from sqlalchemy import Column, DateTime, Integer, String, Text
            from sqlalchemy import Index

            from appos.db.base import Base


            class {class_name}(Base):
                """Audit log for {record_name} — tracks field-level changes."""

                __tablename__ = "{audit_table}"

                id = Column(Integer, primary_key=True, autoincrement=True)
                record_id = Column(Integer, nullable=False, index=True)
                field = Column(String(100), nullable=False)
                old_value = Column(Text, nullable=True)
                new_value = Column(Text, nullable=True)
                changed_by = Column(Integer, nullable=True, index=True)
                changed_at = Column(
                    DateTime(timezone=True),
                    default=lambda: datetime.now(timezone.utc),
                    nullable=False,
                    index=True,
                )
                change_type = Column(String(20), nullable=False, default="update")

                __table_args__ = (
                    Index("idx_{audit_table}_record_field", "record_id", "field"),
                    Index("idx_{audit_table}_changed_at", "changed_at"),
                )

                def __repr__(self) -> str:
                    return (
                        f"<{class_name}(record_id={{self.record_id}}, "
                        f"field='{{self.field}}', change_type='{{self.change_type}}')>"
                    )
        ''')

        # Write file
        self.output_dir.mkdir(parents=True, exist_ok=True)
        output_path = self.output_dir / f"{snake_name}_audit_log.py"
        output_path.write_text(code, encoding="utf-8")
        logger.info(f"Generated audit model: {output_path}")

        # Also generate SQL DDL
        self._generate_sql_ddl(audit_table, record_name)

        return output_path

    def _generate_sql_ddl(self, audit_table: str, record_name: str) -> Path:
        """Generate raw SQL DDL for the audit log table."""
        sql = textwrap.dedent(f"""\
            -- Auto-generated audit log table for {self.app_name}.{record_name}
            -- Generated by AppOS AuditGenerator

            CREATE TABLE IF NOT EXISTS "{audit_table}" (
                id              SERIAL PRIMARY KEY,
                record_id       INTEGER NOT NULL,
                field           VARCHAR(100) NOT NULL,
                old_value       TEXT,
                new_value       TEXT,
                changed_by      INTEGER,
                changed_at      TIMESTAMPTZ NOT NULL DEFAULT NOW(),
                change_type     VARCHAR(20) NOT NULL DEFAULT 'update'
            );

            CREATE INDEX IF NOT EXISTS "idx_{audit_table}_record_id"
                ON "{audit_table}" (record_id);

            CREATE INDEX IF NOT EXISTS "idx_{audit_table}_record_field"
                ON "{audit_table}" (record_id, field);

            CREATE INDEX IF NOT EXISTS "idx_{audit_table}_changed_at"
                ON "{audit_table}" (changed_at);
        """)

        sql_dir = self.output_dir / "sql"
        sql_dir.mkdir(parents=True, exist_ok=True)
        sql_path = sql_dir / f"{audit_table}.sql"
        sql_path.write_text(sql, encoding="utf-8")
        logger.info(f"Generated audit SQL: {sql_path}")
        return sql_path


def _to_snake(name: str) -> str:
    """Convert CamelCase to snake_case."""
    import re
    s1 = re.sub(r"(.)([A-Z][a-z]+)", r"\1_\2", name)
    return re.sub(r"([a-z0-9])([A-Z])", r"\1_\2", s1).lower()
