"""
AppOS Interface Generator — Auto-generate List/Create/Edit/View interfaces from @record.

For each @record with Meta.permissions, generates:
    - {Record}List     → DataTable interface with columns, search, pagination
    - {Record}Create   → Form interface with all editable fields
    - {Record}Edit     → Form interface pre-populated, with update action
    - {Record}View     → Read-only detail interface

Generated code is written to: .appos/generated/interfaces/{app}_{record}_interfaces.py

These generated interfaces are registered in the ObjectRegistry and can be:
    - Used directly by @page decorators
    - Overridden completely via @interface with the same name
    - Extended via @interface.extend("{Record}List")

Design refs:
    §9   Record System — Interface auto-generation pipeline
    §12  UI Layer — Component library, Page→Interface→Component
    §5.13 Interface — Properties, auto-generated from Records
"""

from __future__ import annotations

import logging

from appos.utilities.utils import to_snake
from pathlib import Path
from typing import Any, Dict, List, Optional, Tuple

logger = logging.getLogger("appos.generators.interface_generator")


# ---------------------------------------------------------------------------
# Pydantic → Field Type Mapping
# ---------------------------------------------------------------------------

PYDANTIC_TO_FIELD_TYPE = {
    "str": "text",
    "int": "number",
    "float": "number",
    "bool": "checkbox",
    "datetime": "datetime",
    "date": "date",
    "Optional[str]": "text",
    "Optional[int]": "number",
    "Optional[float]": "number",
    "Optional[bool]": "checkbox",
    "Optional[datetime]": "datetime",
    "Optional[date]": "date",
    "List[str]": "text",
    "dict": "textarea",
}


def _infer_field_type(field_info: Dict[str, Any]) -> str:
    """Infer the AppOS field type from Pydantic field info."""
    annotation = field_info.get("annotation", "str")
    annotation_str = str(annotation)

    # Check for choices/enum
    if field_info.get("choices"):
        return "select"

    # Check for email pattern
    field_name = field_info.get("name", "")
    if "email" in field_name.lower():
        return "email"
    if "password" in field_name.lower():
        return "password"

    # Map annotation
    for key, ftype in PYDANTIC_TO_FIELD_TYPE.items():
        if key in annotation_str:
            return ftype

    return "text"


def _is_editable_field(field_name: str, field_info: Dict[str, Any]) -> bool:
    """Determine if a field should be included in create/edit forms."""
    # Skip auto-generated / system fields
    skip_fields = {
        "id", "created_at", "updated_at", "created_by", "updated_by",
        "is_deleted", "deleted_at", "deleted_by",
    }
    if field_name in skip_fields:
        return False
    return True


def _is_display_field(field_name: str, field_info: Dict[str, Any]) -> bool:
    """Determine if a field should be shown in list/view interfaces."""
    # Skip internal fields
    skip_fields = {"is_deleted", "deleted_at", "deleted_by"}
    if field_name in skip_fields:
        return False
    return True


def _to_title(name: str) -> str:
    """Convert snake_case to Title Case."""
    return name.replace("_", " ").title()


# ---------------------------------------------------------------------------
# Interface Code Generator
# ---------------------------------------------------------------------------

def generate_interfaces_for_record(
    record_def: Any,
    app_name: str,
    output_dir: Optional[Path] = None,
) -> Dict[str, str]:
    """
    Generate List/Create/Edit/View interface code for a @record.

    Args:
        record_def: RegisteredObject for the @record
        app_name: App short name
        output_dir: Where to write generated files (default: .appos/generated/interfaces/)

    Returns:
        Dict mapping interface name to generated Python code
    """
    record_name = record_def.metadata.get("name", record_def.name)
    record_class_name = record_name
    record_snake = to_snake(record_name)

    # Extract fields from the Pydantic model
    handler = record_def.handler
    fields = _extract_record_fields(handler)

    if not fields:
        logger.warning(f"No fields found for record {record_name} — skipping interface generation")
        return {}

    # Determine field categories
    list_columns = [f["name"] for f in fields if _is_display_field(f["name"], f)][:8]  # Max 8 columns
    editable_fields = [f for f in fields if _is_editable_field(f["name"], f)]
    display_field = record_def.metadata.get("display_field", list_columns[0] if list_columns else "id")

    # Get permissions
    permissions = record_def.metadata.get("permissions", {})
    view_perms = permissions.get("view", [])
    create_perms = permissions.get("create", [])
    update_perms = permissions.get("update", [])
    delete_perms = permissions.get("delete", [])

    # Generate code
    generated = {}

    # 1. List Interface
    generated[f"{record_class_name}List"] = _generate_list_interface(
        record_name=record_name,
        record_class_name=record_class_name,
        record_snake=record_snake,
        app_name=app_name,
        columns=list_columns,
        display_field=display_field,
        view_perms=view_perms,
        create_perms=create_perms,
        delete_perms=delete_perms,
    )

    # 2. Create Interface
    generated[f"{record_class_name}Create"] = _generate_create_interface(
        record_name=record_name,
        record_class_name=record_class_name,
        record_snake=record_snake,
        app_name=app_name,
        fields=editable_fields,
        create_perms=create_perms,
    )

    # 3. Edit Interface
    generated[f"{record_class_name}Edit"] = _generate_edit_interface(
        record_name=record_name,
        record_class_name=record_class_name,
        record_snake=record_snake,
        app_name=app_name,
        fields=editable_fields,
        update_perms=update_perms,
    )

    # 4. View Interface
    generated[f"{record_class_name}View"] = _generate_view_interface(
        record_name=record_name,
        record_class_name=record_class_name,
        record_snake=record_snake,
        app_name=app_name,
        fields=[f for f in fields if _is_display_field(f["name"], f)],
        view_perms=view_perms,
    )

    # Write to files if output_dir specified
    if output_dir:
        output_dir = Path(output_dir)
        output_dir.mkdir(parents=True, exist_ok=True)
        outfile = output_dir / f"{app_name}_{record_snake}_interfaces.py"

        combined_code = _generate_file_header(record_name, app_name)
        for name, code in generated.items():
            combined_code += f"\n\n{code}"

        outfile.write_text(combined_code)
        logger.info(f"Generated interfaces for {record_name} → {outfile}")

    return generated


def _extract_record_fields(handler: Any) -> List[Dict[str, Any]]:
    """Extract field information from a Pydantic record class."""
    fields = []

    if handler is None:
        return fields

    # Try Pydantic v2 model_fields
    if hasattr(handler, "model_fields"):
        for name, field_info in handler.model_fields.items():
            field_data = {
                "name": name,
                "annotation": str(field_info.annotation) if hasattr(field_info, "annotation") else "str",
                "required": field_info.is_required() if hasattr(field_info, "is_required") else True,
                "default": field_info.default if hasattr(field_info, "default") else None,
                "max_length": None,
                "choices": [],
            }

            # Extract metadata from Pydantic Field
            if hasattr(field_info, "metadata"):
                for meta in field_info.metadata:
                    if hasattr(meta, "max_length"):
                        field_data["max_length"] = meta.max_length

            # Check for literal/enum choices
            annotation_str = str(field_info.annotation) if hasattr(field_info, "annotation") else ""
            if "Literal" in annotation_str:
                # Extract literal values
                import re
                match = re.findall(r"'([^']+)'", annotation_str)
                if match:
                    field_data["choices"] = match

            fields.append(field_data)
        return fields

    # Try Pydantic v1 __fields__
    if hasattr(handler, "__fields__"):
        for name, field_info in handler.__fields__.items():
            field_data = {
                "name": name,
                "annotation": str(field_info.outer_type_) if hasattr(field_info, "outer_type_") else "str",
                "required": field_info.required,
                "default": field_info.default,
                "max_length": getattr(field_info.field_info, "max_length", None) if hasattr(field_info, "field_info") else None,
                "choices": [],
            }
            fields.append(field_data)
        return fields

    return fields


# ---------------------------------------------------------------------------
# Code Generators
# ---------------------------------------------------------------------------

def _generate_file_header(record_name: str, app_name: str) -> str:
    """Generate the file header for generated interface code."""
    return f'''"""
Auto-generated interfaces for {record_name} record ({app_name} app).

Generated by AppOS Interface Generator.
DO NOT EDIT — changes will be overwritten on next generation.
Override via @interface or @interface.extend in your app code.
"""

from appos.decorators.core import interface
from appos.ui.components import (
    Button, Card, Column, DataTable, Field, Form,
    Layout, Metric, Row,
)
'''


def _generate_list_interface(
    record_name: str,
    record_class_name: str,
    record_snake: str,
    app_name: str,
    columns: List[str],
    display_field: str,
    view_perms: List[str],
    create_perms: List[str],
    delete_perms: List[str],
) -> str:
    """Generate a list/table interface for a record."""
    columns_str = ", ".join(f'"{c}"' for c in columns)
    perms_str = ", ".join(f'"{p}"' for p in view_perms) if view_perms else ""

    return f'''
@interface(
    name="{record_class_name}List",
    record_name="{record_name}",
    type="list",
    permissions=[{perms_str}],
)
def {record_snake}_list():
    """Auto-generated list interface for {record_name}."""
    return DataTable(
        record="{record_name}",
        columns=[{columns_str}],
        searchable=True,
        filterable=True,
        page_size=25,
        actions=[
            Button(
                "Create {_to_title(record_snake)}",
                action="navigate",
                to="/{app_name}/{record_snake}s/new",
            ),
        ],
        row_actions=[
            Button("Edit", action="navigate", to="/{app_name}/{record_snake}s/{{id}}/edit", size="1"),
            Button("Delete", action="delete", confirm=True, color_scheme="red", variant="ghost", size="1"),
        ],
    )
'''


def _generate_create_interface(
    record_name: str,
    record_class_name: str,
    record_snake: str,
    app_name: str,
    fields: List[Dict[str, Any]],
    create_perms: List[str],
) -> str:
    """Generate a create form interface for a record."""
    perms_str = ", ".join(f'"{p}"' for p in create_perms) if create_perms else ""

    # Build field definitions
    field_lines = []
    for f in fields:
        ftype = _infer_field_type(f)
        required = f.get("required", False)
        choices_str = ""
        if f.get("choices"):
            choices_list = ", ".join(f'"{c}"' for c in f["choices"])
            choices_str = f', choices=[{choices_list}]'

        field_lines.append(
            f'        Field("{f["name"]}", field_type="{ftype}", '
            f'required={required}{choices_str}),'
        )

    fields_str = "\n".join(field_lines)

    return f'''
@interface(
    name="{record_class_name}Create",
    record_name="{record_name}",
    type="create",
    permissions=[{perms_str}],
)
def {record_snake}_create():
    """Auto-generated create interface for {record_name}."""
    return Form(
        record="{record_name}",
        fields=[
{fields_str}
        ],
        submit_label="Create {_to_title(record_snake)}",
        on_submit="{app_name}.records.{record_name}.create",
        on_cancel="navigate:/{app_name}/{record_snake}s",
    )
'''


def _generate_edit_interface(
    record_name: str,
    record_class_name: str,
    record_snake: str,
    app_name: str,
    fields: List[Dict[str, Any]],
    update_perms: List[str],
) -> str:
    """Generate an edit form interface for a record."""
    perms_str = ", ".join(f'"{p}"' for p in update_perms) if update_perms else ""

    field_lines = []
    for f in fields:
        ftype = _infer_field_type(f)
        choices_str = ""
        if f.get("choices"):
            choices_list = ", ".join(f'"{c}"' for c in f["choices"])
            choices_str = f', choices=[{choices_list}]'

        field_lines.append(
            f'        Field("{f["name"]}", field_type="{ftype}"{choices_str}),'
        )

    fields_str = "\n".join(field_lines)

    return f'''
@interface(
    name="{record_class_name}Edit",
    record_name="{record_name}",
    type="edit",
    permissions=[{perms_str}],
)
def {record_snake}_edit():
    """Auto-generated edit interface for {record_name}."""
    return Form(
        record="{record_name}",
        fields=[
{fields_str}
        ],
        submit_label="Save Changes",
        on_submit="{app_name}.records.{record_name}.update",
        on_cancel="navigate:/{app_name}/{record_snake}s",
    )
'''


def _generate_view_interface(
    record_name: str,
    record_class_name: str,
    record_snake: str,
    app_name: str,
    fields: List[Dict[str, Any]],
    view_perms: List[str],
) -> str:
    """Generate a read-only view interface for a record."""
    perms_str = ", ".join(f'"{p}"' for p in view_perms) if view_perms else ""

    field_lines = []
    for f in fields:
        ftype = _infer_field_type(f)
        field_lines.append(
            f'        Field("{f["name"]}", field_type="{ftype}", read_only=True),'
        )

    fields_str = "\n".join(field_lines)

    return f'''
@interface(
    name="{record_class_name}View",
    record_name="{record_name}",
    type="view",
    permissions=[{perms_str}],
)
def {record_snake}_view():
    """Auto-generated view interface for {record_name}."""
    return Layout(children=[
        Row(children=[
            Button("Edit", action="navigate", to="/{app_name}/{record_snake}s/{{id}}/edit"),
            Button("Back", action="navigate", to="/{app_name}/{record_snake}s", variant="outline"),
        ]),
        Card(
            title="{_to_title(record_snake)} Details",
            children=[
                Column(children=[
{fields_str}
                ]),
            ],
        ),
    ])
'''


# ---------------------------------------------------------------------------
# Batch Generator — Generate interfaces for all records in an app
# ---------------------------------------------------------------------------

def generate_all_interfaces(
    app_name: str,
    output_dir: Optional[Path] = None,
) -> Dict[str, Dict[str, str]]:
    """
    Generate interfaces for all @record objects in an app.

    Args:
        app_name: App short name
        output_dir: Output directory (default: .appos/generated/interfaces/)

    Returns:
        Dict mapping record name to generated interface code dict
    """
    from appos.engine.registry import object_registry

    if output_dir is None:
        output_dir = Path(".appos/generated/interfaces")

    results = {}
    record_defs = object_registry.get_by_type("record", app_name=app_name)

    for record_def in record_defs:
        record_name = record_def.metadata.get("name", record_def.name)
        try:
            generated = generate_interfaces_for_record(
                record_def=record_def,
                app_name=app_name,
                output_dir=output_dir,
            )
            results[record_name] = generated
            logger.info(f"Generated {len(generated)} interfaces for {record_name}")
        except Exception as e:
            logger.error(f"Failed to generate interfaces for {record_name}: {e}")

    logger.info(
        f"Interface generation complete for {app_name}: "
        f"{sum(len(v) for v in results.values())} interfaces from {len(results)} records"
    )
    return results



