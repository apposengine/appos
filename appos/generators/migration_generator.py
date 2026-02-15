"""
AppOS Migration Generator — Diffs current @record models vs live DB state
and generates Alembic-compatible migration scripts.

Pipeline:
    1. Parse all @record objects from the registry
    2. Build the "desired" schema from Pydantic → SQLAlchemy type mapping
    3. Introspect the live DB to get "current" schema
    4. Compute diff (new tables, new columns, type changes, dropped columns)
    5. Generate a numbered Alembic migration Python script

Output:
    migrations/{app}/versions/{sequence}_{slug}.py

Works with:
    - model_generator.py (uses same type mappings)
    - appos/db/session.py (gets DB session for introspection)
    - appos/engine/registry.py (discovers @record objects)

Design refs: AppOS_Design.md §9 (Record Processing Pipeline)
"""

from __future__ import annotations

import logging
import os
import re
import textwrap
from collections import OrderedDict
from dataclasses import dataclass, field
from datetime import datetime, timezone
from pathlib import Path
from typing import Any, Dict, List, Optional, Sequence, Set, Tuple

from appos.generators.model_generator import (
    SQL_TYPE_MAPPING,
    TYPE_MAPPING,
    ParsedField,
    ParsedRecord,
    _get_field_type_name,
    _is_optional,
    parse_record,
)
from appos.utilities.utils import to_snake

logger = logging.getLogger("appos.generators.migration_generator")


# ---------------------------------------------------------------------------
# Schema introspection data classes
# ---------------------------------------------------------------------------

@dataclass
class LiveColumn:
    """A column as it exists in the live database."""
    name: str
    data_type: str           # e.g., "VARCHAR", "INTEGER"
    is_nullable: bool
    column_default: Optional[str] = None
    character_maximum_length: Optional[int] = None
    numeric_precision: Optional[int] = None
    numeric_scale: Optional[int] = None

    @property
    def normalized_type(self) -> str:
        """Normalize DB type for comparison (uppercase, simplified)."""
        t = self.data_type.upper()
        # Normalize common aliases
        aliases = {
            "CHARACTER VARYING": "VARCHAR",
            "TIMESTAMP WITHOUT TIME ZONE": "TIMESTAMP",
            "TIMESTAMP WITH TIME ZONE": "TIMESTAMPTZ",
            "DOUBLE PRECISION": "FLOAT",
            "BIGINT": "BIGINT",
            "SMALLINT": "SMALLINT",
            "BOOLEAN": "BOOLEAN",
            "INTEGER": "INTEGER",
            "TEXT": "TEXT",
            "JSONB": "JSONB",
            "JSON": "JSON",
            "BYTEA": "BYTEA",
            "DATE": "DATE",
            "NUMERIC": "NUMERIC",
        }
        return aliases.get(t, t)


@dataclass
class LiveTable:
    """A table as it exists in the live database."""
    name: str
    schema_name: str
    columns: Dict[str, LiveColumn] = field(default_factory=dict)
    primary_key: Optional[str] = None


@dataclass
class DesiredColumn:
    """A column as desired based on @record definition."""
    name: str
    sql_type: str            # e.g., "VARCHAR(100)", "INTEGER"
    is_nullable: bool = True
    default: Optional[str] = None
    is_primary_key: bool = False
    is_unique: bool = False

    @property
    def normalized_type(self) -> str:
        """Base type without length/precision for comparison."""
        base = self.sql_type.split("(")[0].upper()
        # Map to the same normalized form as LiveColumn
        return base


@dataclass
class DesiredTable:
    """A table as desired based on @record definition."""
    name: str
    schema_name: str
    columns: Dict[str, DesiredColumn] = field(default_factory=OrderedDict)
    record_ref: Optional[str] = None  # object_ref back to the @record


# ---------------------------------------------------------------------------
# Diff types
# ---------------------------------------------------------------------------

@dataclass
class ColumnDiff:
    """Represents a change to a single column."""
    column_name: str
    change_type: str  # "add", "drop", "modify_type", "modify_nullable"
    old_value: Optional[str] = None
    new_value: Optional[str] = None
    desired: Optional[DesiredColumn] = None

    def __repr__(self) -> str:
        if self.change_type == "add":
            return f"+Column({self.column_name} {self.desired.sql_type if self.desired else ''})"
        if self.change_type == "drop":
            return f"-Column({self.column_name})"
        return f"~Column({self.column_name}: {self.old_value} → {self.new_value})"


@dataclass
class TableDiff:
    """Represents changes to a single table."""
    table_name: str
    schema_name: str
    change_type: str  # "create", "drop", "alter"
    column_diffs: List[ColumnDiff] = field(default_factory=list)
    desired: Optional[DesiredTable] = None

    @property
    def has_changes(self) -> bool:
        return self.change_type in ("create", "drop") or bool(self.column_diffs)


@dataclass
class MigrationDiff:
    """Full diff between desired schema and live DB."""
    app_name: str
    table_diffs: List[TableDiff] = field(default_factory=list)
    timestamp: str = field(default_factory=lambda: datetime.now(timezone.utc).strftime("%Y%m%d_%H%M%S"))

    @property
    def has_changes(self) -> bool:
        return any(td.has_changes for td in self.table_diffs)

    @property
    def summary(self) -> str:
        creates = [td for td in self.table_diffs if td.change_type == "create"]
        alters = [td for td in self.table_diffs if td.change_type == "alter" and td.column_diffs]
        drops = [td for td in self.table_diffs if td.change_type == "drop"]
        parts = []
        if creates:
            parts.append(f"{len(creates)} new table(s)")
        if alters:
            total_cols = sum(len(td.column_diffs) for td in alters)
            parts.append(f"{total_cols} column change(s) in {len(alters)} table(s)")
        if drops:
            parts.append(f"{len(drops)} dropped table(s)")
        return ", ".join(parts) if parts else "no changes"


# ---------------------------------------------------------------------------
# Build desired schema from @record objects
# ---------------------------------------------------------------------------

def _pydantic_field_to_sql_type(parsed_field: ParsedField) -> str:
    """
    Convert a ParsedField to a SQL type string.

    Uses the same mapping as model_generator but outputs SQL type syntax.
    """
    type_name = parsed_field.python_type

    sql_type = SQL_TYPE_MAPPING.get(type_name, "TEXT")

    # Apply length/precision
    if type_name == "str" and parsed_field.max_length:
        sql_type = f"VARCHAR({parsed_field.max_length})"
    elif type_name == "str" and not parsed_field.max_length:
        sql_type = "VARCHAR(255)"  # Default length
    elif type_name == "float":
        precision = parsed_field.decimal_places or 2
        sql_type = f"NUMERIC(10, {precision})"

    return sql_type


def build_desired_table(parsed: ParsedRecord, schema_name: str = "public") -> DesiredTable:
    """
    Build a DesiredTable from a ParsedRecord.

    Args:
        parsed: Parsed @record with fields and metadata.
        schema_name: DB schema name (e.g., "public", app-specific schema).

    Returns:
        DesiredTable with all columns defined.
    """
    table_name = parsed.table_name
    table = DesiredTable(
        name=table_name,
        schema_name=schema_name,
        record_ref=f"{parsed.app_name}.records.{parsed.class_name}" if parsed.app_name else parsed.class_name,
    )

    # Primary key
    table.columns["id"] = DesiredColumn(
        name="id",
        sql_type="SERIAL",
        is_nullable=False,
        is_primary_key=True,
    )

    # Record fields
    for f in parsed.fields:
        col = DesiredColumn(
            name=f.name,
            sql_type=_pydantic_field_to_sql_type(f),
            is_nullable=f.nullable,
            default=repr(f.default) if f.default is not None else None,
            is_unique=f.unique,
        )
        table.columns[f.name] = col

    # Audit columns (if AuditMixin)
    if parsed.audit:
        for col_name, col_type, nullable in [
            ("created_at", "TIMESTAMP WITH TIME ZONE", False),
            ("updated_at", "TIMESTAMP WITH TIME ZONE", True),
            ("created_by", "VARCHAR(100)", True),
            ("updated_by", "VARCHAR(100)", True),
        ]:
            table.columns[col_name] = DesiredColumn(
                name=col_name, sql_type=col_type, is_nullable=nullable,
            )

    # Soft delete columns (if SoftDeleteMixin)
    if parsed.soft_delete:
        for col_name, col_type in [
            ("is_deleted", "BOOLEAN"),
            ("deleted_at", "TIMESTAMP WITH TIME ZONE"),
            ("deleted_by", "VARCHAR(100)"),
        ]:
            table.columns[col_name] = DesiredColumn(
                name=col_name, sql_type=col_type, is_nullable=True,
                default="false" if col_name == "is_deleted" else None,
            )

    # Foreign keys from relationships
    for rel in parsed.relationships:
        if rel.rel_type in ("belongs_to", "has_one"):
            fk_col = f"{to_snake(rel.target)}_id"
            if fk_col not in table.columns:
                table.columns[fk_col] = DesiredColumn(
                    name=fk_col, sql_type="INTEGER", is_nullable=True,
                )

    return table


def build_desired_schema(
    app_name: str,
    schema_name: str = "public",
    registry=None,
) -> Dict[str, DesiredTable]:
    """
    Build desired schema for all @records in an app.

    Args:
        app_name: App short name (e.g., "crm").
        schema_name: DB schema name.
        registry: ObjectRegistryManager instance (defaults to global).

    Returns:
        Dict of table_name → DesiredTable.
    """
    from appos.engine.registry import object_registry
    reg = registry or object_registry

    records = reg.get_by_type("record", app_name=app_name)
    desired: Dict[str, DesiredTable] = {}

    for registered in records:
        handler = registered.handler
        if handler is None:
            continue

        try:
            parsed = parse_record(handler)
            table = build_desired_table(parsed, schema_name=schema_name)
            desired[table.name] = table
        except Exception as e:
            logger.warning(f"Failed to parse record {registered.object_ref}: {e}")

    return desired


# ---------------------------------------------------------------------------
# Live DB introspection
# ---------------------------------------------------------------------------

def introspect_live_tables(
    schema_name: str,
    engine=None,
    table_names: Optional[Set[str]] = None,
) -> Dict[str, LiveTable]:
    """
    Introspect live database tables using information_schema.

    Args:
        schema_name: DB schema to inspect.
        engine: SQLAlchemy engine (defaults to platform engine).
        table_names: Optional set of table names to filter. If None, all tables.

    Returns:
        Dict of table_name → LiveTable.
    """
    from sqlalchemy import text

    if engine is None:
        from appos.db.base import engine_registry
        engine = engine_registry.get("platform")
        if engine is None:
            logger.warning("No platform engine available — cannot introspect DB")
            return {}

    query = text("""
        SELECT
            c.table_name,
            c.column_name,
            c.data_type,
            c.is_nullable,
            c.column_default,
            c.character_maximum_length,
            c.numeric_precision,
            c.numeric_scale
        FROM information_schema.columns c
        WHERE c.table_schema = :schema
        ORDER BY c.table_name, c.ordinal_position
    """)

    tables: Dict[str, LiveTable] = {}

    try:
        with engine.connect() as conn:
            result = conn.execute(query, {"schema": schema_name})
            for row in result:
                t_name = row[0]

                # Filter if specific tables requested
                if table_names and t_name not in table_names:
                    continue

                if t_name not in tables:
                    tables[t_name] = LiveTable(name=t_name, schema_name=schema_name)

                col = LiveColumn(
                    name=row[1],
                    data_type=row[2],
                    is_nullable=row[3] == "YES",
                    column_default=row[4],
                    character_maximum_length=row[5],
                    numeric_precision=row[6],
                    numeric_scale=row[7],
                )
                tables[t_name].columns[col.name] = col

    except Exception as e:
        logger.error(f"Failed to introspect schema '{schema_name}': {e}")

    logger.debug(f"Introspected {len(tables)} tables in schema '{schema_name}'")
    return tables


# ---------------------------------------------------------------------------
# Diff computation
# ---------------------------------------------------------------------------

def compute_diff(
    desired: Dict[str, DesiredTable],
    live: Dict[str, LiveTable],
    app_name: str,
) -> MigrationDiff:
    """
    Compare desired schema (from @records) with live DB state.

    Returns a MigrationDiff describing all necessary changes.
    """
    diff = MigrationDiff(app_name=app_name)

    # 1. New tables (in desired but not in live)
    for table_name, desired_table in desired.items():
        if table_name not in live:
            diff.table_diffs.append(TableDiff(
                table_name=table_name,
                schema_name=desired_table.schema_name,
                change_type="create",
                desired=desired_table,
            ))
            continue

        # 2. Existing tables — compare columns
        live_table = live[table_name]
        col_diffs = _diff_columns(desired_table, live_table)
        if col_diffs:
            diff.table_diffs.append(TableDiff(
                table_name=table_name,
                schema_name=desired_table.schema_name,
                change_type="alter",
                column_diffs=col_diffs,
                desired=desired_table,
            ))

    # 3. Dropped tables — only flag tables that were previously generated
    # (Don't flag platform tables or tables from other apps)
    # This is conservative: we only detect drops for tables whose names
    # match expected @record table names that are no longer in desired.
    # Actual dropping is left to manual review.

    return diff


def _diff_columns(desired: DesiredTable, live: LiveTable) -> List[ColumnDiff]:
    """Compare columns between desired and live table."""
    diffs: List[ColumnDiff] = []

    # New columns
    for col_name, desired_col in desired.columns.items():
        if col_name not in live.columns:
            diffs.append(ColumnDiff(
                column_name=col_name,
                change_type="add",
                new_value=desired_col.sql_type,
                desired=desired_col,
            ))
            continue

        # Type changes
        live_col = live.columns[col_name]
        desired_base = desired_col.normalized_type
        live_base = live_col.normalized_type

        if not _types_compatible(desired_base, live_base):
            diffs.append(ColumnDiff(
                column_name=col_name,
                change_type="modify_type",
                old_value=live_col.data_type,
                new_value=desired_col.sql_type,
                desired=desired_col,
            ))

        # Nullable changes
        if desired_col.is_nullable != live_col.is_nullable:
            diffs.append(ColumnDiff(
                column_name=col_name,
                change_type="modify_nullable",
                old_value=str(live_col.is_nullable),
                new_value=str(desired_col.is_nullable),
                desired=desired_col,
            ))

    # Dropped columns (conservative — just flag, don't auto-drop)
    for col_name in live.columns:
        if col_name not in desired.columns:
            # Only flag if it's not a system column
            system_cols = {"id", "created_at", "updated_at", "created_by",
                           "updated_by", "is_deleted", "deleted_at", "deleted_by"}
            if col_name not in system_cols:
                diffs.append(ColumnDiff(
                    column_name=col_name,
                    change_type="drop",
                    old_value=live.columns[col_name].data_type,
                ))

    return diffs


def _types_compatible(desired: str, live: str) -> bool:
    """
    Check if two normalized SQL types are compatible.

    Allows common aliases (e.g., SERIAL ↔ INTEGER, VARCHAR ↔ TEXT).
    """
    if desired == live:
        return True

    # Common compatible pairs
    compatible_pairs = {
        frozenset({"SERIAL", "INTEGER"}),
        frozenset({"BIGSERIAL", "BIGINT"}),
        frozenset({"VARCHAR", "TEXT"}),
        frozenset({"TIMESTAMPTZ", "TIMESTAMP"}),
        frozenset({"JSON", "JSONB"}),
        frozenset({"FLOAT", "NUMERIC"}),
        frozenset({"NUMERIC", "DOUBLE PRECISION"}),
    }

    return frozenset({desired, live}) in compatible_pairs


# ---------------------------------------------------------------------------
# Migration script generation
# ---------------------------------------------------------------------------

def generate_migration_script(
    diff: MigrationDiff,
    sequence: int = 1,
    description: Optional[str] = None,
) -> str:
    """
    Generate an Alembic-compatible migration Python script from a diff.

    Args:
        diff: MigrationDiff with all table changes.
        sequence: Migration sequence number.
        description: Human-readable description (auto-generated if None).

    Returns:
        String content of the migration .py file.
    """
    if not diff.has_changes:
        return ""

    desc = description or diff.summary
    slug = re.sub(r"[^a-z0-9]+", "_", desc.lower()).strip("_")[:50]
    revision = f"{diff.timestamp}_{sequence:03d}"

    # Collect all upgrade/downgrade operations
    upgrade_ops: List[str] = []
    downgrade_ops: List[str] = []

    for td in diff.table_diffs:
        if td.change_type == "create":
            upgrade_ops.append(_gen_create_table(td))
            downgrade_ops.append(f"    op.drop_table('{td.table_name}', schema='{td.schema_name}')")

        elif td.change_type == "alter":
            for cd in td.column_diffs:
                if cd.change_type == "add":
                    col_def = _gen_add_column(td.table_name, td.schema_name, cd)
                    upgrade_ops.append(col_def)
                    downgrade_ops.append(
                        f"    op.drop_column('{td.table_name}', '{cd.column_name}', "
                        f"schema='{td.schema_name}')"
                    )

                elif cd.change_type == "drop":
                    upgrade_ops.append(
                        f"    # WARNING: Dropping column '{cd.column_name}' — verify data migration\n"
                        f"    op.drop_column('{td.table_name}', '{cd.column_name}', "
                        f"schema='{td.schema_name}')"
                    )
                    downgrade_ops.append(
                        f"    # Cannot auto-restore dropped column '{cd.column_name}' — manual intervention required"
                    )

                elif cd.change_type == "modify_type":
                    upgrade_ops.append(
                        f"    op.alter_column(\n"
                        f"        '{td.table_name}', '{cd.column_name}',\n"
                        f"        type_=sa.{_sql_to_sa_type(cd.new_value)}(),\n"
                        f"        schema='{td.schema_name}'\n"
                        f"    )"
                    )
                    downgrade_ops.append(
                        f"    op.alter_column(\n"
                        f"        '{td.table_name}', '{cd.column_name}',\n"
                        f"        type_=sa.{_sql_to_sa_type(cd.old_value)}(),\n"
                        f"        schema='{td.schema_name}'\n"
                        f"    )"
                    )

                elif cd.change_type == "modify_nullable":
                    nullable = cd.new_value == "True"
                    upgrade_ops.append(
                        f"    op.alter_column(\n"
                        f"        '{td.table_name}', '{cd.column_name}',\n"
                        f"        nullable={nullable},\n"
                        f"        schema='{td.schema_name}'\n"
                        f"    )"
                    )
                    downgrade_ops.append(
                        f"    op.alter_column(\n"
                        f"        '{td.table_name}', '{cd.column_name}',\n"
                        f"        nullable={not nullable},\n"
                        f"        schema='{td.schema_name}'\n"
                        f"    )"
                    )

    upgrade_body = "\n\n".join(upgrade_ops) if upgrade_ops else "    pass"
    downgrade_body = "\n\n".join(downgrade_ops) if downgrade_ops else "    pass"

    script = textwrap.dedent(f'''\
        """
        {desc}

        Revision: {revision}
        App: {diff.app_name}
        Created: {datetime.now(timezone.utc).isoformat()}

        Auto-generated by AppOS Migration Generator.
        Review before applying — especially DROP operations.
        """

        from alembic import op
        import sqlalchemy as sa

        # Revision identifiers
        revision = "{revision}"
        down_revision = None  # Set manually or auto-chain
        branch_labels = None
        depends_on = None


        def upgrade() -> None:
        {upgrade_body}


        def downgrade() -> None:
        {downgrade_body}
    ''')

    return script


def _gen_create_table(td: TableDiff) -> str:
    """Generate op.create_table() call for a new table."""
    if td.desired is None:
        return f"    # Cannot generate CREATE TABLE for '{td.table_name}' — missing schema"

    lines = [f"    op.create_table(\n        '{td.table_name}',"]

    for col_name, col in td.desired.columns.items():
        sa_type = _sql_to_sa_type(col.sql_type)
        parts = [f"sa.Column('{col_name}', sa.{sa_type}()"]

        if col.is_primary_key:
            parts.append("primary_key=True")
            if col.sql_type.upper() == "SERIAL":
                parts.append("autoincrement=True")
        if not col.is_nullable:
            parts.append("nullable=False")
        if col.is_unique:
            parts.append("unique=True")
        if col.default is not None and not col.is_primary_key:
            parts.append(f"server_default=sa.text('{col.default}')")

        line = ", ".join(parts) + ")"
        lines.append(f"        {line},")

    lines.append(f"        schema='{td.schema_name}'")
    lines.append("    )")

    return "\n".join(lines)


def _gen_add_column(table_name: str, schema_name: str, cd: ColumnDiff) -> str:
    """Generate op.add_column() for a new column."""
    if cd.desired is None:
        return f"    # Cannot generate ADD COLUMN for '{cd.column_name}'"

    sa_type = _sql_to_sa_type(cd.desired.sql_type)
    parts = [f"sa.Column('{cd.column_name}', sa.{sa_type}()"]

    if not cd.desired.is_nullable:
        parts.append("nullable=False")

    col_def = ", ".join(parts) + ")"

    return (
        f"    op.add_column(\n"
        f"        '{table_name}',\n"
        f"        {col_def},\n"
        f"        schema='{schema_name}'\n"
        f"    )"
    )


def _sql_to_sa_type(sql_type: str) -> str:
    """
    Convert SQL type string to SQLAlchemy type name.

    Examples: "VARCHAR(100)" → "String", "INTEGER" → "Integer"
    """
    base = sql_type.split("(")[0].upper().strip()

    mapping = {
        "VARCHAR": "String",
        "TEXT": "Text",
        "INTEGER": "Integer",
        "INT": "Integer",
        "SERIAL": "Integer",
        "BIGINT": "BigInteger",
        "BIGSERIAL": "BigInteger",
        "SMALLINT": "SmallInteger",
        "NUMERIC": "Numeric",
        "FLOAT": "Float",
        "DOUBLE PRECISION": "Float",
        "BOOLEAN": "Boolean",
        "DATE": "Date",
        "TIMESTAMP": "DateTime",
        "TIMESTAMP WITH TIME ZONE": "DateTime",
        "TIMESTAMPTZ": "DateTime",
        "JSON": "JSON",
        "JSONB": "JSON",
        "BYTEA": "LargeBinary",
    }

    return mapping.get(base, "String")


# ---------------------------------------------------------------------------
# High-level API
# ---------------------------------------------------------------------------

def generate_migration(
    app_name: str,
    schema_name: str = "public",
    output_dir: Optional[str] = None,
    engine=None,
    registry=None,
    description: Optional[str] = None,
    dry_run: bool = False,
) -> Optional[str]:
    """
    Full pipeline: parse records → introspect DB → diff → generate migration.

    Args:
        app_name: App short name (e.g., "crm").
        schema_name: DB schema where app tables live.
        output_dir: Output directory. Defaults to migrations/{app}/versions/.
        engine: SQLAlchemy engine for DB introspection.
        registry: ObjectRegistryManager (defaults to global).
        description: Migration description.
        dry_run: If True, return the script string without writing to disk.

    Returns:
        File path of generated migration (or script string if dry_run),
        or None if no changes detected.
    """
    logger.info(f"Generating migration for app '{app_name}' in schema '{schema_name}'")

    # 1. Build desired schema from @records
    desired = build_desired_schema(app_name, schema_name, registry)
    if not desired:
        logger.info(f"No @record objects found for app '{app_name}'")
        return None

    # 2. Introspect live DB
    live = introspect_live_tables(
        schema_name=schema_name,
        engine=engine,
        table_names=set(desired.keys()),
    )

    # 3. Compute diff
    diff = compute_diff(desired, live, app_name)

    if not diff.has_changes:
        logger.info(f"No migration needed for app '{app_name}' — schema is in sync")
        return None

    logger.info(f"Migration diff for '{app_name}': {diff.summary}")

    # 4. Determine sequence number
    out_dir = output_dir or f"migrations/{app_name}/versions"
    sequence = _next_sequence_number(out_dir)

    # 5. Generate script
    script = generate_migration_script(diff, sequence, description)

    if dry_run:
        return script

    # 6. Write to file
    out_path = Path(out_dir)
    out_path.mkdir(parents=True, exist_ok=True)

    slug = re.sub(r"[^a-z0-9]+", "_", (description or diff.summary).lower()).strip("_")[:50]
    filename = f"{sequence:03d}_{slug}.py"
    filepath = out_path / filename

    filepath.write_text(script, encoding="utf-8")
    logger.info(f"Migration written: {filepath}")

    return str(filepath)


def generate_all_migrations(
    schema_name: str = "public",
    output_base: str = "migrations",
    engine=None,
    registry=None,
    dry_run: bool = False,
) -> Dict[str, Optional[str]]:
    """
    Generate migrations for ALL apps that have @record objects.

    Returns:
        Dict of app_name → migration file path (or None if no changes).
    """
    from appos.engine.registry import object_registry
    reg = registry or object_registry

    # Discover all apps with records
    all_records = reg.get_by_type("record")
    apps = set()
    for r in all_records:
        if r.app_name:
            apps.add(r.app_name)

    results: Dict[str, Optional[str]] = {}
    for app_name in sorted(apps):
        result = generate_migration(
            app_name=app_name,
            schema_name=schema_name,
            output_dir=f"{output_base}/{app_name}/versions",
            engine=engine,
            registry=reg,
            dry_run=dry_run,
        )
        results[app_name] = result

    return results


def _next_sequence_number(versions_dir: str) -> int:
    """Determine the next migration sequence number."""
    path = Path(versions_dir)
    if not path.exists():
        return 1

    max_seq = 0
    for py_file in path.glob("*.py"):
        match = re.match(r"^(\d+)_", py_file.name)
        if match:
            seq = int(match.group(1))
            max_seq = max(max_seq, seq)

    return max_seq + 1
