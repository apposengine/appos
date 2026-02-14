"""
AppOS Model Generator — Pydantic @record → SQLAlchemy model auto-generation.

Pipeline:
    1. Parse @record Pydantic model (fields, relationships, Meta)
    2. Map Pydantic types → SQLAlchemy columns
    3. Generate SQLAlchemy model class file
    4. Generate audit_log table if Meta.audit = True
    5. Write to .appos/generated/models/{record_name}.py

Also generates SQL DDL for direct execution against the app's Connected System DB.

Design refs: AppOS_Design.md §9 (Record System & Auto-Generation), §5.7 (Record)
"""

from __future__ import annotations

import logging
import os
import re
import textwrap
from datetime import date, datetime
from pathlib import Path
from typing import Any, Dict, List, Optional, Set, Tuple, Type, get_args, get_origin

from pydantic import BaseModel
from pydantic.fields import FieldInfo

logger = logging.getLogger("appos.generators.model_generator")


# ---------------------------------------------------------------------------
# Pydantic → SQLAlchemy type mapping
# ---------------------------------------------------------------------------

TYPE_MAPPING = {
    "str": "String",
    "int": "Integer",
    "float": "Numeric",
    "bool": "Boolean",
    "datetime": "DateTime",
    "date": "Date",
    "dict": "JSON",
    "list": "JSON",
    "List": "JSON",
    "Dict": "JSON",
    "bytes": "LargeBinary",
}

SQL_TYPE_MAPPING = {
    "str": "VARCHAR",
    "int": "INTEGER",
    "float": "NUMERIC",
    "bool": "BOOLEAN",
    "datetime": "TIMESTAMP WITH TIME ZONE",
    "date": "DATE",
    "dict": "JSONB",
    "list": "JSONB",
    "bytes": "BYTEA",
}


def _get_field_type_name(annotation: Any) -> str:
    """Extract the base type name from a possibly-Optional annotation."""
    origin = get_origin(annotation)

    # Optional[X] is Union[X, None]
    if origin is type(None):
        return "NoneType"

    args = get_args(annotation)
    if args:
        # Optional[str] → str, List[str] → list
        non_none = [a for a in args if a is not type(None)]
        if non_none:
            inner = non_none[0]
            origin_inner = get_origin(inner)
            if origin_inner is list or (hasattr(inner, "__name__") and inner.__name__ == "List"):
                return "list"
            if origin_inner is dict or (hasattr(inner, "__name__") and inner.__name__ == "Dict"):
                return "dict"
            if hasattr(inner, "__name__"):
                return inner.__name__
            return str(inner)

    if hasattr(annotation, "__name__"):
        return annotation.__name__

    return str(annotation)


def _is_optional(annotation: Any) -> bool:
    """Check if annotation is Optional[X]."""
    args = get_args(annotation)
    if args:
        return type(None) in args
    return False


def _is_relationship(field_info: FieldInfo) -> bool:
    """Check if a field represents a relationship (has_many, belongs_to, has_one)."""
    default = field_info.default
    if isinstance(default, dict) and "_relationship" in default:
        return True
    return False


def _get_max_length(field_info: FieldInfo) -> Optional[int]:
    """Extract max_length from Field metadata."""
    return getattr(field_info, "max_length", None)


def _get_decimal_places(field_info: FieldInfo) -> Optional[int]:
    """Extract decimal_places from Field json_schema_extra."""
    extra = getattr(field_info, "json_schema_extra", None) or {}
    if isinstance(extra, dict):
        return extra.get("decimal_places")
    return getattr(field_info, "decimal_places", None)


def _get_choices(field_info: FieldInfo) -> Optional[List[str]]:
    """Extract choices from Field json_schema_extra."""
    extra = getattr(field_info, "json_schema_extra", None) or {}
    if isinstance(extra, dict):
        return extra.get("choices")
    return None


def _get_ge(field_info: FieldInfo) -> Optional[float]:
    """Extract ge (>=) constraint."""
    for m in getattr(field_info, "metadata", []):
        if hasattr(m, "ge"):
            return m.ge
    return getattr(field_info, "ge", None)


def _get_le(field_info: FieldInfo) -> Optional[float]:
    """Extract le (<=) constraint."""
    for m in getattr(field_info, "metadata", []):
        if hasattr(m, "le"):
            return m.le
    return getattr(field_info, "le", None)


def _to_snake(name: str) -> str:
    """CamelCase → snake_case."""
    s1 = re.sub(r"([A-Z]+)([A-Z][a-z])", r"\1_\2", name)
    return re.sub(r"([a-z0-9])([A-Z])", r"\1_\2", s1).lower()


# ---------------------------------------------------------------------------
# Record Parser
# ---------------------------------------------------------------------------

class ParsedField:
    """Parsed field from a Pydantic record."""

    def __init__(
        self,
        name: str,
        python_type: str,
        nullable: bool = False,
        max_length: Optional[int] = None,
        decimal_places: Optional[int] = None,
        default: Any = None,
        has_default: bool = False,
        choices: Optional[List[str]] = None,
        ge: Optional[float] = None,
        le: Optional[float] = None,
        unique: bool = False,
        index: bool = False,
        description: str = "",
    ):
        self.name = name
        self.python_type = python_type
        self.nullable = nullable
        self.max_length = max_length
        self.decimal_places = decimal_places
        self.default = default
        self.has_default = has_default
        self.choices = choices
        self.ge = ge
        self.le = le
        self.unique = unique
        self.index = index
        self.description = description


class ParsedRelationship:
    """Parsed relationship declaration."""

    def __init__(
        self,
        name: str,
        rel_type: str,  # "has_many" | "belongs_to" | "has_one"
        target: str,
        back_ref: Optional[str] = None,
        cascade: str = "save-update, merge",
        required: bool = False,
    ):
        self.name = name
        self.rel_type = rel_type
        self.target = target
        self.back_ref = back_ref
        self.cascade = cascade
        self.required = required


class ParsedRecord:
    """Fully parsed @record with fields, relationships, and Meta."""

    def __init__(
        self,
        class_name: str,
        app_name: str,
        table_name: str,
        fields: List[ParsedField],
        relationships: List[ParsedRelationship],
        audit: bool = False,
        soft_delete: bool = False,
        display_field: Optional[str] = None,
        search_fields: Optional[List[str]] = None,
        connected_system: Optional[str] = None,
        permissions: Optional[Dict[str, List[str]]] = None,
        on_create: Optional[List[str]] = None,
        on_update: Optional[List[str]] = None,
        on_delete: Optional[List[str]] = None,
        row_security_rule: Optional[str] = None,
    ):
        self.class_name = class_name
        self.app_name = app_name
        self.table_name = table_name
        self.fields = fields
        self.relationships = relationships
        self.audit = audit
        self.soft_delete = soft_delete
        self.display_field = display_field
        self.search_fields = search_fields or []
        self.connected_system = connected_system
        self.permissions = permissions or {}
        self.on_create = on_create or []
        self.on_update = on_update or []
        self.on_delete = on_delete or []
        self.row_security_rule = row_security_rule


def parse_record(record_class: type, app_name: str = "") -> ParsedRecord:
    """
    Parse a @record-decorated Pydantic class into structured data.

    Args:
        record_class: The Pydantic BaseModel class decorated with @record.
        app_name: The app this record belongs to.

    Returns:
        ParsedRecord with fields, relationships, and Meta.
    """
    meta = getattr(record_class, "Meta", None)
    class_name = record_class.__name__

    # Meta config
    table_name = getattr(meta, "table_name", _to_snake(class_name) + "s")
    audit = getattr(meta, "audit", False)
    soft_delete = getattr(meta, "soft_delete", False)
    display_field = getattr(meta, "display_field", None)
    search_fields = getattr(meta, "search_fields", [])
    connected_system = getattr(meta, "connected_system", None)
    permissions = getattr(meta, "permissions", {})
    on_create = getattr(meta, "on_create", [])
    on_update = getattr(meta, "on_update", [])
    on_delete = getattr(meta, "on_delete", [])
    row_security_rule = getattr(meta, "row_security_rule", None)

    fields: List[ParsedField] = []
    relationships: List[ParsedRelationship] = []

    # Get Pydantic model fields
    model_fields = record_class.model_fields if hasattr(record_class, "model_fields") else {}

    for field_name, field_info in model_fields.items():
        # Check if it's a relationship
        if _is_relationship(field_info):
            rel_data = field_info.default
            relationships.append(ParsedRelationship(
                name=field_name,
                rel_type=rel_data["_relationship"],
                target=rel_data["target"],
                back_ref=rel_data.get("back_ref"),
                cascade=rel_data.get("cascade", "save-update, merge"),
                required=rel_data.get("required", False),
            ))
            continue

        # Regular field
        annotation = field_info.annotation or str
        type_name = _get_field_type_name(annotation)
        nullable = _is_optional(annotation)

        # Extract constraints
        max_length = _get_max_length(field_info)
        decimal_places = _get_decimal_places(field_info)
        choices = _get_choices(field_info)
        ge = _get_ge(field_info)
        le = _get_le(field_info)
        description = field_info.description or ""

        # Default value
        has_default = field_info.default is not None and not isinstance(field_info.default, type)
        default = field_info.default if has_default else None

        # Check for unique (via json_schema_extra or if field name is 'email')
        extra = getattr(field_info, "json_schema_extra", None) or {}
        unique = extra.get("unique", False) if isinstance(extra, dict) else False

        # Index search fields
        index = field_name in search_fields

        fields.append(ParsedField(
            name=field_name,
            python_type=type_name,
            nullable=nullable,
            max_length=max_length,
            decimal_places=decimal_places,
            default=default,
            has_default=has_default,
            choices=choices,
            ge=ge,
            le=le,
            unique=unique,
            index=index,
            description=description,
        ))

    return ParsedRecord(
        class_name=class_name,
        app_name=app_name,
        table_name=table_name,
        fields=fields,
        relationships=relationships,
        audit=audit,
        soft_delete=soft_delete,
        display_field=display_field,
        search_fields=search_fields,
        connected_system=connected_system,
        permissions=permissions,
        on_create=on_create,
        on_update=on_update,
        on_delete=on_delete,
        row_security_rule=row_security_rule,
    )


# ---------------------------------------------------------------------------
# SQLAlchemy Model Code Generator
# ---------------------------------------------------------------------------

def generate_model_code(parsed: ParsedRecord) -> str:
    """
    Generate SQLAlchemy model Python code from a ParsedRecord.

    Returns:
        Python source code string for the generated model file.
    """
    model_name = f"{parsed.class_name}Model"
    imports: Set[str] = {"Column", "Integer"}
    sa_extras: Set[str] = set()
    base_classes = ["Base", "AuditMixin"]
    if parsed.soft_delete:
        base_classes.append("SoftDeleteMixin")

    lines: List[str] = []

    # Primary key
    lines.append(f"    id = Column(Integer, primary_key=True, autoincrement=True)")

    # Fields
    for f in parsed.fields:
        col_parts, field_imports = _build_column(f)
        imports.update(field_imports)
        lines.append(f"    {f.name} = {col_parts}")

    # Relationships
    rel_lines: List[str] = []
    for r in parsed.relationships:
        target_model = f"{r.target}Model"
        if r.rel_type == "has_many":
            imports.add("relationship")
            back_pop = f', back_populates="{r.back_ref}"' if r.back_ref else ""
            cascade_str = f', cascade="{r.cascade}"' if r.cascade != "save-update, merge" else ""
            rel_lines.append(f'    {r.name} = relationship("{target_model}"{back_pop}{cascade_str})')
        elif r.rel_type == "belongs_to":
            imports.update({"ForeignKey", "relationship"})
            fk_col = f"{r.name}_id" if not r.name.endswith("_id") else r.name
            nullable = "False" if r.required else "True"
            # FK column (only if not already in fields)
            field_names = {f.name for f in parsed.fields}
            if fk_col not in field_names:
                target_table = _to_snake(r.target) + "s"
                lines.append(
                    f'    {fk_col} = Column(Integer, ForeignKey("{target_table}.id"), '
                    f"nullable={nullable})"
                )
            rel_lines.append(f'    {r.name} = relationship("{target_model}")')
        elif r.rel_type == "has_one":
            imports.add("relationship")
            back_pop = f', back_populates="{r.back_ref}"' if r.back_ref else ""
            rel_lines.append(f'    {r.name} = relationship("{target_model}", uselist=False{back_pop})')

    # Check constraints
    check_lines: List[str] = []
    for f in parsed.fields:
        if f.choices:
            choice_str = ", ".join(f"'{c}'" for c in f.choices)
            imports.add("CheckConstraint")
            check_lines.append(
                f'        CheckConstraint("{f.name} IN ({choice_str})", name="ck_{parsed.table_name}_{f.name}"),'
            )
        if f.ge is not None:
            imports.add("CheckConstraint")
            check_lines.append(
                f'        CheckConstraint("{f.name} >= {f.ge}", name="ck_{parsed.table_name}_{f.name}_ge"),'
            )
        if f.le is not None:
            imports.add("CheckConstraint")
            check_lines.append(
                f'        CheckConstraint("{f.name} <= {f.le}", name="ck_{parsed.table_name}_{f.name}_le"),'
            )

    # Index lines
    index_lines: List[str] = []
    for f in parsed.fields:
        if f.index and not f.unique:
            imports.add("Index")
            index_lines.append(
                f'        Index("idx_{parsed.table_name}_{f.name}", "{f.name}"),'
            )
    if parsed.soft_delete:
        imports.add("Index")
        index_lines.append(
            f'        Index("idx_{parsed.table_name}_is_deleted", "is_deleted"),'
        )
    # is_active index
    field_names = {f.name for f in parsed.fields}
    if "is_active" in field_names:
        imports.add("Index")
        index_lines.append(
            f'        Index("idx_{parsed.table_name}_is_active", "is_active"),'
        )

    # Assemble imports
    sa_imports = sorted(imports - {"relationship"})
    orm_imports = []
    if "relationship" in imports:
        orm_imports.append("relationship")

    import_block = f"from sqlalchemy import {', '.join(sa_imports)}"
    if orm_imports:
        import_block += f"\nfrom sqlalchemy.orm import {', '.join(orm_imports)}"

    # Assemble class
    bases = ", ".join(base_classes)
    table_args_parts = check_lines + index_lines
    table_args_block = ""
    if table_args_parts:
        table_args_block = "\n    __table_args__ = (\n" + "\n".join(table_args_parts) + "\n    )\n"

    rel_block = ""
    if rel_lines:
        rel_block = "\n    # Relationships\n" + "\n".join(rel_lines) + "\n"

    code = f'''"""
Auto-generated SQLAlchemy model for @record {parsed.class_name}.
App: {parsed.app_name}
Table: {parsed.table_name}

DO NOT EDIT — regenerate with `appos generate`.
"""

from datetime import datetime, timezone

{import_block}
from appos.db.base import Base, AuditMixin{"" if not parsed.soft_delete else ", SoftDeleteMixin"}


class {model_name}({bases}):
    __tablename__ = "{parsed.table_name}"

{chr(10).join(lines)}
{rel_block}{table_args_block}
    def __repr__(self) -> str:
        return f"<{model_name}(id={{self.id}})"
'''

    return code


def _build_column(f: ParsedField) -> Tuple[str, Set[str]]:
    """Build a Column(...) expression for a ParsedField."""
    imports: Set[str] = set()
    parts: List[str] = []

    # Column type
    sa_type = TYPE_MAPPING.get(f.python_type, "String")
    imports.add(sa_type)

    if sa_type == "String" and f.max_length:
        parts.append(f"String({f.max_length})")
    elif sa_type == "Numeric" and f.decimal_places is not None:
        parts.append(f"Numeric(10, {f.decimal_places})")
    elif sa_type == "DateTime":
        parts.append("DateTime(timezone=True)")
    elif sa_type == "JSON":
        parts.append("JSON")
    else:
        parts.append(sa_type)

    # Nullable
    if f.unique:
        parts.append("unique=True")
    parts.append(f"nullable={f.nullable}")

    # Default
    if f.has_default:
        if isinstance(f.default, bool):
            parts.append(f"default={f.default}")
        elif isinstance(f.default, (int, float)):
            parts.append(f"default={f.default}")
        elif isinstance(f.default, str):
            parts.append(f'default="{f.default}"')

    col_expr = f"Column({', '.join(parts)})"
    return col_expr, imports


# ---------------------------------------------------------------------------
# SQL DDL Generator
# ---------------------------------------------------------------------------

def generate_sql_ddl(parsed: ParsedRecord) -> str:
    """
    Generate CREATE TABLE SQL for a ParsedRecord.

    Returns PostgreSQL DDL including indexes and check constraints.
    """
    lines: List[str] = []
    lines.append(f"-- Auto-generated from @record {parsed.class_name}")
    lines.append(f"CREATE TABLE IF NOT EXISTS {parsed.table_name} (")

    # Primary key
    col_lines: List[str] = []
    col_lines.append("    id              SERIAL PRIMARY KEY")

    # Fields
    for f in parsed.fields:
        sql_type = _sql_type(f)
        nullable = "" if f.nullable else " NOT NULL"
        default = _sql_default(f)
        unique = " UNIQUE" if f.unique else ""
        check = ""
        if f.choices:
            choice_str = ", ".join(f"'{c}'" for c in f.choices)
            check = f"\n                    CHECK ({f.name} IN ({choice_str}))"
        if f.ge is not None:
            check += f"\n                    CHECK ({f.name} >= {f.ge})"

        col_lines.append(f"    {f.name:<16}{sql_type}{nullable}{default}{unique}{check}")

    # Audit columns (always)
    col_lines.append("    created_at      TIMESTAMP WITH TIME ZONE NOT NULL DEFAULT NOW()")
    col_lines.append("    updated_at      TIMESTAMP WITH TIME ZONE NOT NULL DEFAULT NOW()")
    col_lines.append("    created_by      INTEGER")
    col_lines.append("    updated_by      INTEGER")

    # Soft delete columns
    if parsed.soft_delete:
        col_lines.append("    is_deleted      BOOLEAN NOT NULL DEFAULT FALSE")
        col_lines.append("    deleted_at      TIMESTAMP WITH TIME ZONE")
        col_lines.append("    deleted_by      INTEGER")

    lines.append(",\n".join(col_lines))
    lines.append(");")
    lines.append("")

    # Indexes
    for f in parsed.fields:
        if f.index:
            lines.append(
                f"CREATE INDEX IF NOT EXISTS idx_{parsed.table_name}_{f.name} "
                f"ON {parsed.table_name}({f.name});"
            )
    if parsed.soft_delete:
        lines.append(
            f"CREATE INDEX IF NOT EXISTS idx_{parsed.table_name}_is_deleted "
            f"ON {parsed.table_name}(is_deleted);"
        )
    field_names = {f.name for f in parsed.fields}
    if "is_active" in field_names:
        lines.append(
            f"CREATE INDEX IF NOT EXISTS idx_{parsed.table_name}_is_active "
            f"ON {parsed.table_name}(is_active);"
        )

    return "\n".join(lines)


def _sql_type(f: ParsedField) -> str:
    """Map a ParsedField to a PostgreSQL type string."""
    base = SQL_TYPE_MAPPING.get(f.python_type, "TEXT")
    if f.python_type == "str" and f.max_length:
        return f"VARCHAR({f.max_length})"
    if f.python_type == "float" and f.decimal_places is not None:
        return f"NUMERIC(10,{f.decimal_places})"
    return base


def _sql_default(f: ParsedField) -> str:
    """Generate DEFAULT clause for SQL."""
    if not f.has_default:
        return ""
    if isinstance(f.default, bool):
        return f" DEFAULT {'TRUE' if f.default else 'FALSE'}"
    if isinstance(f.default, (int, float)):
        return f" DEFAULT {f.default}"
    if isinstance(f.default, str):
        return f" DEFAULT '{f.default}'"
    return ""


# ---------------------------------------------------------------------------
# Audit Log Table Generator
# ---------------------------------------------------------------------------

def generate_audit_table_sql(parsed: ParsedRecord) -> Optional[str]:
    """
    Generate the audit_log table DDL for records with Meta.audit = True.

    Table name: {app}_{table}_audit_log
    """
    if not parsed.audit:
        return None

    table_name = f"{parsed.app_name}_{parsed.table_name}_audit_log"

    return f"""-- Auto-generated audit log for @record {parsed.class_name}
CREATE TABLE IF NOT EXISTS {table_name} (
    id                  SERIAL PRIMARY KEY,
    record_id           INTEGER NOT NULL,
    field_name          VARCHAR(100) NOT NULL,
    old_value           TEXT,
    new_value           TEXT,
    operation           VARCHAR(20) NOT NULL CHECK (operation IN ('create', 'update', 'delete')),
    changed_by          INTEGER NOT NULL,
    changed_at          TIMESTAMP WITH TIME ZONE NOT NULL DEFAULT NOW(),
    execution_id        VARCHAR(50),
    process_instance_id VARCHAR(50)
);

CREATE INDEX IF NOT EXISTS idx_{table_name}_record ON {table_name}(record_id);
CREATE INDEX IF NOT EXISTS idx_{table_name}_field ON {table_name}(field_name);
CREATE INDEX IF NOT EXISTS idx_{table_name}_changed ON {table_name}(changed_at);
CREATE INDEX IF NOT EXISTS idx_{table_name}_user ON {table_name}(changed_by);
CREATE INDEX IF NOT EXISTS idx_{table_name}_op ON {table_name}(operation);"""


# ---------------------------------------------------------------------------
# File writer
# ---------------------------------------------------------------------------

def generate_and_write(
    record_class: type,
    app_name: str,
    output_dir: Optional[str] = None,
) -> Dict[str, str]:
    """
    Full generation pipeline: parse → generate model + SQL → write files.

    Args:
        record_class: The @record Pydantic class.
        app_name: App short name (e.g., "crm").
        output_dir: Base output directory. Defaults to .appos/generated/.

    Returns:
        Dict of {filepath: content} that was written.
    """
    if output_dir is None:
        from appos.engine.config import get_project_root
        output_dir = str(get_project_root() / ".appos" / "generated")

    parsed = parse_record(record_class, app_name)
    written: Dict[str, str] = {}

    # Model code
    model_code = generate_model_code(parsed)
    model_path = os.path.join(output_dir, "models", f"{_to_snake(parsed.class_name)}.py")
    _write_file(model_path, model_code)
    written[model_path] = model_code

    # SQL DDL
    sql_ddl = generate_sql_ddl(parsed)
    sql_path = os.path.join(output_dir, "sql", f"{parsed.table_name}.sql")
    _write_file(sql_path, sql_ddl)
    written[sql_path] = sql_ddl

    # Audit log SQL (if enabled)
    audit_sql = generate_audit_table_sql(parsed)
    if audit_sql:
        audit_path = os.path.join(output_dir, "sql", f"{parsed.app_name}_{parsed.table_name}_audit_log.sql")
        _write_file(audit_path, audit_sql)
        written[audit_path] = audit_sql

    logger.info(
        f"Generated model for {parsed.class_name}: "
        f"{len(parsed.fields)} fields, {len(parsed.relationships)} relationships"
    )
    return written


def _write_file(path: str, content: str) -> None:
    """Write content to a file, creating directories as needed."""
    os.makedirs(os.path.dirname(path), exist_ok=True)
    with open(path, "w", encoding="utf-8") as f:
        f.write(content)


# ---------------------------------------------------------------------------
# Batch generation utility
# ---------------------------------------------------------------------------

def generate_all_for_app(app_name: str, output_dir: Optional[str] = None) -> Dict[str, str]:
    """
    Generate SQLAlchemy models for ALL @record objects in an app.

    Scans the object registry for records belonging to the app,
    then generates model + SQL for each.

    Args:
        app_name: App short name (e.g., "crm").
        output_dir: Base output directory.

    Returns:
        Dict of all {filepath: content} written.
    """
    from appos.engine.registry import object_registry

    all_written: Dict[str, str] = {}
    records = object_registry.get_by_type("record", app_name=app_name)

    for reg_obj in records:
        handler = reg_obj.handler
        if handler and isinstance(handler, type) and issubclass(handler, BaseModel):
            written = generate_and_write(handler, app_name, output_dir)
            all_written.update(written)

    logger.info(f"Generated {len(records)} record models for app '{app_name}'")
    return all_written
