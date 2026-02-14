"""
AppOS Component Library — Thin wrappers around Reflex components.

Components are plain functions (not object types). They map to Reflex components
with minimal abstraction. Developers can use raw Reflex components alongside
AppOS components inside Interfaces — no wrappers needed.

Hierarchy: Page → Interface → Component

Design refs:
    §12  UI Layer — Component library (L2766)
    §5.13 Interface — Component list, raw Reflex
    §9   Record System — Generated UIs use these components

Available components:
    DataTable      → rx.table with sorting, filtering, pagination
    Form           → rx.form with validation, submit handling
    Field          → rx.input / rx.select / rx.checkbox depending on type
    Button         → rx.button with action handlers
    Layout         → rx.box with flex/grid layout
    Row            → rx.hstack
    Column         → rx.vstack
    Card           → rx.card with header and content
    Wizard         → Multi-step form with progress indicator
    WizardStep     → Single wizard step
    Chart          → rx.recharts integration
    Metric         → KPI card with label, value, trend
"""

from __future__ import annotations

import logging
from dataclasses import dataclass, field as datafield
from typing import Any, Callable, Dict, List, Optional, Union

logger = logging.getLogger("appos.ui.components")


# ---------------------------------------------------------------------------
# Component Definition Classes
#
# These are intermediate representations. The InterfaceRenderer converts
# them to actual Reflex components at render time. This allows interface
# definitions to be built without importing reflex at module level.
# ---------------------------------------------------------------------------

@dataclass
class ComponentDef:
    """Base class for all AppOS component definitions."""
    _component_type: str = ""
    props: Dict[str, Any] = datafield(default_factory=dict)

    def to_dict(self) -> Dict[str, Any]:
        """Serialize to dict for interface definitions."""
        return {"type": self._component_type, **self.props}


@dataclass
class DataTableDef(ComponentDef):
    """
    Data table with sorting, filtering, and pagination.

    Maps to rx.table.root with AppOS enhancements:
    - Auto-columns from @record fields
    - Server-side sorting/filtering
    - Row actions (edit, delete, navigate)
    - Bulk actions toolbar
    """
    _component_type: str = "data_table"

    record: str = ""
    columns: List[str] = datafield(default_factory=list)
    searchable: bool = False
    filterable: bool = False
    sortable: bool = True
    page_size: int = 25
    selectable: bool = False
    actions: List["ButtonDef"] = datafield(default_factory=list)
    row_actions: List["ButtonDef"] = datafield(default_factory=list)
    empty_message: str = "No records found"
    on_row_click: Optional[str] = None

    def to_dict(self) -> Dict[str, Any]:
        return {
            "type": self._component_type,
            "record": self.record,
            "columns": self.columns,
            "searchable": self.searchable,
            "filterable": self.filterable,
            "sortable": self.sortable,
            "page_size": self.page_size,
            "selectable": self.selectable,
            "actions": [a.to_dict() for a in self.actions],
            "row_actions": [a.to_dict() for a in self.row_actions],
            "empty_message": self.empty_message,
            "on_row_click": self.on_row_click,
        }


@dataclass
class FormDef(ComponentDef):
    """
    Form with validation and submit handling.

    Maps to rx.form. Auto-generates fields from @record if record is specified.
    Supports custom field ordering, sections, and submit actions.
    """
    _component_type: str = "form"

    record: str = ""
    fields: List[Union[str, "FieldDef"]] = datafield(default_factory=list)
    submit_label: str = "Save"
    cancel_label: str = "Cancel"
    on_submit: Optional[str] = None
    on_cancel: Optional[str] = None
    layout: str = "vertical"  # vertical | horizontal | grid
    columns: int = 1  # for grid layout
    sections: List[Dict[str, Any]] = datafield(default_factory=list)

    def to_dict(self) -> Dict[str, Any]:
        fields_out = []
        for f in self.fields:
            if isinstance(f, str):
                fields_out.append(f)
            elif isinstance(f, FieldDef):
                fields_out.append(f.to_dict())
            else:
                fields_out.append(f)
        return {
            "type": self._component_type,
            "record": self.record,
            "fields": fields_out,
            "submit_label": self.submit_label,
            "cancel_label": self.cancel_label,
            "on_submit": self.on_submit,
            "on_cancel": self.on_cancel,
            "layout": self.layout,
            "columns": self.columns,
            "sections": self.sections,
        }


@dataclass
class FieldDef(ComponentDef):
    """
    Form field — auto-detects Reflex component from field type.

    str → rx.input
    int/float → rx.input(type="number")
    bool → rx.checkbox
    List[str] (choices) → rx.select
    datetime → rx.input(type="datetime-local")
    text (long) → rx.text_area
    """
    _component_type: str = "field"

    name: str = ""
    label: Optional[str] = None
    field_type: str = "text"  # text | number | email | password | select | checkbox | textarea | date | datetime
    placeholder: str = ""
    required: bool = False
    read_only: bool = False
    default_value: Any = None
    choices: List[Any] = datafield(default_factory=list)
    help_text: str = ""
    validation: Optional[Dict[str, Any]] = None
    width: str = "100%"

    def to_dict(self) -> Dict[str, Any]:
        return {
            "type": self._component_type,
            "name": self.name,
            "label": self.label or self.name.replace("_", " ").title(),
            "field_type": self.field_type,
            "placeholder": self.placeholder,
            "required": self.required,
            "read_only": self.read_only,
            "default_value": self.default_value,
            "choices": self.choices,
            "help_text": self.help_text,
            "validation": self.validation,
            "width": self.width,
        }


@dataclass
class ButtonDef(ComponentDef):
    """
    Button with action handler.

    Actions:
    - "navigate" → navigate to a route (uses `to` prop)
    - "submit" → submit parent form
    - "rule" → execute an expression rule (uses `rule` prop)
    - "delete" → delete the record (uses `confirm` prop)
    - "custom" → call a custom handler (uses `handler` prop)
    """
    _component_type: str = "button"

    label: str = ""
    action: str = "custom"  # navigate | submit | rule | delete | custom
    to: Optional[str] = None  # for navigate action
    rule: Optional[str] = None  # for rule action
    handler: Optional[str] = None  # for custom action
    confirm: bool = False
    variant: str = "solid"  # solid | outline | ghost | soft
    color_scheme: str = "blue"
    size: str = "2"
    icon: Optional[str] = None
    disabled: bool = False

    def to_dict(self) -> Dict[str, Any]:
        return {
            "type": self._component_type,
            "label": self.label,
            "action": self.action,
            "to": self.to,
            "rule": self.rule,
            "handler": self.handler,
            "confirm": self.confirm,
            "variant": self.variant,
            "color_scheme": self.color_scheme,
            "size": self.size,
            "icon": self.icon,
            "disabled": self.disabled,
        }


@dataclass
class LayoutDef(ComponentDef):
    """
    Layout container — flex/grid arrangement of child components.

    Maps to rx.box with display flex or grid.
    """
    _component_type: str = "layout"

    children: List[Any] = datafield(default_factory=list)
    direction: str = "column"  # row | column
    gap: str = "4"
    padding: str = "4"
    align: str = "stretch"
    justify: str = "start"
    width: str = "100%"
    max_width: Optional[str] = None
    wrap: bool = False

    def to_dict(self) -> Dict[str, Any]:
        children_out = []
        for c in self.children:
            if isinstance(c, ComponentDef):
                children_out.append(c.to_dict())
            else:
                children_out.append(c)
        return {
            "type": self._component_type,
            "children": children_out,
            "direction": self.direction,
            "gap": self.gap,
            "padding": self.padding,
            "align": self.align,
            "justify": self.justify,
            "width": self.width,
            "max_width": self.max_width,
            "wrap": self.wrap,
        }


@dataclass
class RowDef(ComponentDef):
    """Horizontal stack — maps to rx.hstack."""
    _component_type: str = "row"

    children: List[Any] = datafield(default_factory=list)
    spacing: str = "4"
    align: str = "center"
    justify: str = "start"
    width: str = "100%"
    wrap: bool = False

    def to_dict(self) -> Dict[str, Any]:
        children_out = []
        for c in self.children:
            if isinstance(c, ComponentDef):
                children_out.append(c.to_dict())
            else:
                children_out.append(c)
        return {
            "type": self._component_type,
            "children": children_out,
            "spacing": self.spacing,
            "align": self.align,
            "justify": self.justify,
            "width": self.width,
            "wrap": self.wrap,
        }


@dataclass
class ColumnDef(ComponentDef):
    """Vertical stack — maps to rx.vstack."""
    _component_type: str = "column"

    children: List[Any] = datafield(default_factory=list)
    spacing: str = "4"
    align: str = "start"
    width: str = "100%"

    def to_dict(self) -> Dict[str, Any]:
        children_out = []
        for c in self.children:
            if isinstance(c, ComponentDef):
                children_out.append(c.to_dict())
            else:
                children_out.append(c)
        return {
            "type": self._component_type,
            "children": children_out,
            "spacing": self.spacing,
            "align": self.align,
            "width": self.width,
        }


@dataclass
class CardDef(ComponentDef):
    """
    Card with header and content area.

    Maps to rx.card with optional header text and content children.
    """
    _component_type: str = "card"

    title: str = ""
    content: Any = None
    children: List[Any] = datafield(default_factory=list)
    variant: str = "surface"  # surface | classic | ghost
    size: str = "3"
    width: str = "100%"

    def to_dict(self) -> Dict[str, Any]:
        children_out = []
        for c in self.children:
            if isinstance(c, ComponentDef):
                children_out.append(c.to_dict())
            else:
                children_out.append(c)
        return {
            "type": self._component_type,
            "title": self.title,
            "content": self.content,
            "children": children_out,
            "variant": self.variant,
            "size": self.size,
            "width": self.width,
        }


@dataclass
class WizardDef(ComponentDef):
    """
    Multi-step wizard form with progress indicator.

    Contains WizardStepDef children. Only one step visible at a time.
    """
    _component_type: str = "wizard"

    steps: List["WizardStepDef"] = datafield(default_factory=list)
    on_complete: Optional[str] = None
    on_cancel: Optional[str] = None
    show_progress: bool = True
    allow_skip: bool = False

    def to_dict(self) -> Dict[str, Any]:
        return {
            "type": self._component_type,
            "steps": [s.to_dict() for s in self.steps],
            "on_complete": self.on_complete,
            "on_cancel": self.on_cancel,
            "show_progress": self.show_progress,
            "allow_skip": self.allow_skip,
        }


@dataclass
class WizardStepDef(ComponentDef):
    """Single step in a wizard."""
    _component_type: str = "wizard_step"

    title: str = ""
    description: str = ""
    children: List[Any] = datafield(default_factory=list)
    validation: Optional[str] = None  # Rule to validate before proceeding

    def to_dict(self) -> Dict[str, Any]:
        children_out = []
        for c in self.children:
            if isinstance(c, ComponentDef):
                children_out.append(c.to_dict())
            else:
                children_out.append(c)
        return {
            "type": self._component_type,
            "title": self.title,
            "description": self.description,
            "children": children_out,
            "validation": self.validation,
        }


@dataclass
class ChartDef(ComponentDef):
    """
    Chart component — maps to rx.recharts.

    Supports: line, bar, area, pie, scatter chart types.
    """
    _component_type: str = "chart"

    chart_type: str = "line"  # line | bar | area | pie | scatter
    data_source: Optional[str] = None  # Rule or state var that returns data
    data: List[Dict[str, Any]] = datafield(default_factory=list)
    x_axis: str = ""
    y_axis: Union[str, List[str]] = ""
    title: str = ""
    width: str = "100%"
    height: str = "300px"
    colors: List[str] = datafield(default_factory=list)
    show_legend: bool = True
    show_grid: bool = True

    def to_dict(self) -> Dict[str, Any]:
        return {
            "type": self._component_type,
            "chart_type": self.chart_type,
            "data_source": self.data_source,
            "data": self.data,
            "x_axis": self.x_axis,
            "y_axis": self.y_axis,
            "title": self.title,
            "width": self.width,
            "height": self.height,
            "colors": self.colors,
            "show_legend": self.show_legend,
            "show_grid": self.show_grid,
        }


@dataclass
class MetricDef(ComponentDef):
    """
    KPI metric card — label, value, and optional trend indicator.

    Renders as a card with large value text and trend arrow/percentage.
    """
    _component_type: str = "metric"

    label: str = ""
    value: Any = None
    value_source: Optional[str] = None  # Rule that returns the value
    trend: Optional[float] = None  # Positive = up, negative = down
    trend_label: str = ""
    format: str = ""  # "currency", "percent", "number", or format string
    color_scheme: str = "blue"
    size: str = "3"
    icon: Optional[str] = None

    def to_dict(self) -> Dict[str, Any]:
        return {
            "type": self._component_type,
            "label": self.label,
            "value": self.value,
            "value_source": self.value_source,
            "trend": self.trend,
            "trend_label": self.trend_label,
            "format": self.format,
            "color_scheme": self.color_scheme,
            "size": self.size,
            "icon": self.icon,
        }


@dataclass
class FileUploadDef(ComponentDef):
    """
    File upload component — wraps rx.upload.

    Integrates with AppOS DocumentService for MIME validation,
    size limits, folder targeting, and versioning.

    Design ref: §5.16 Document (rx.upload integration)
    """
    _component_type: str = "file_upload"

    folder: str = ""  # Target folder name or path
    accept: List[str] = datafield(default_factory=list)  # Accepted MIME types (overrides folder config)
    max_size_mb: Optional[int] = None  # Override platform max_upload_size_mb
    multiple: bool = False  # Allow multiple file selection
    on_upload: Optional[str] = None  # Handler name after upload completes
    label: str = "Upload File"
    help_text: str = ""
    show_preview: bool = True  # Show file list before upload
    auto_upload: bool = False  # Upload immediately on selection
    record_field: Optional[str] = None  # If set, links uploaded doc to this record field
    tags: List[str] = datafield(default_factory=list)  # Default tags for uploaded docs

    def to_dict(self) -> Dict[str, Any]:
        return {
            "type": self._component_type,
            "folder": self.folder,
            "accept": self.accept,
            "max_size_mb": self.max_size_mb,
            "multiple": self.multiple,
            "on_upload": self.on_upload,
            "label": self.label,
            "help_text": self.help_text,
            "show_preview": self.show_preview,
            "auto_upload": self.auto_upload,
            "record_field": self.record_field,
            "tags": self.tags,
        }


# ---------------------------------------------------------------------------
# Public API — Constructor functions matching design §12
#
# These are the functions developers use inside @interface definitions.
# They return ComponentDef instances that the InterfaceRenderer processes.
# ---------------------------------------------------------------------------

def DataTable(
    record: str = "",
    columns: Optional[List[str]] = None,
    searchable: bool = False,
    filterable: bool = False,
    sortable: bool = True,
    page_size: int = 25,
    selectable: bool = False,
    actions: Optional[List[Any]] = None,
    row_actions: Optional[List[Any]] = None,
    empty_message: str = "No records found",
    on_row_click: Optional[str] = None,
) -> DataTableDef:
    """Create a DataTable component definition."""
    return DataTableDef(
        record=record,
        columns=columns or [],
        searchable=searchable,
        filterable=filterable,
        sortable=sortable,
        page_size=page_size,
        selectable=selectable,
        actions=actions or [],
        row_actions=row_actions or [],
        empty_message=empty_message,
        on_row_click=on_row_click,
    )


def Form(
    record: str = "",
    fields: Optional[List[Any]] = None,
    submit_label: str = "Save",
    cancel_label: str = "Cancel",
    on_submit: Optional[str] = None,
    on_cancel: Optional[str] = None,
    layout: str = "vertical",
    columns: int = 1,
    sections: Optional[List[Dict[str, Any]]] = None,
) -> FormDef:
    """Create a Form component definition."""
    return FormDef(
        record=record,
        fields=fields or [],
        submit_label=submit_label,
        cancel_label=cancel_label,
        on_submit=on_submit,
        on_cancel=on_cancel,
        layout=layout,
        columns=columns,
        sections=sections or [],
    )


def Field(
    name: str,
    label: Optional[str] = None,
    field_type: str = "text",
    placeholder: str = "",
    required: bool = False,
    read_only: bool = False,
    default_value: Any = None,
    choices: Optional[List[Any]] = None,
    help_text: str = "",
    validation: Optional[Dict[str, Any]] = None,
    width: str = "100%",
) -> FieldDef:
    """Create a Field component definition."""
    return FieldDef(
        name=name,
        label=label,
        field_type=field_type,
        placeholder=placeholder,
        required=required,
        read_only=read_only,
        default_value=default_value,
        choices=choices or [],
        help_text=help_text,
        validation=validation,
        width=width,
    )


def Button(
    label: str,
    action: str = "custom",
    to: Optional[str] = None,
    rule: Optional[str] = None,
    handler: Optional[str] = None,
    confirm: bool = False,
    variant: str = "solid",
    color_scheme: str = "blue",
    size: str = "2",
    icon: Optional[str] = None,
    disabled: bool = False,
) -> ButtonDef:
    """Create a Button component definition."""
    return ButtonDef(
        label=label,
        action=action,
        to=to,
        rule=rule,
        handler=handler,
        confirm=confirm,
        variant=variant,
        color_scheme=color_scheme,
        size=size,
        icon=icon,
        disabled=disabled,
    )


def Layout(
    children: Optional[List[Any]] = None,
    direction: str = "column",
    gap: str = "4",
    padding: str = "4",
    align: str = "stretch",
    justify: str = "start",
    width: str = "100%",
    max_width: Optional[str] = None,
    wrap: bool = False,
) -> LayoutDef:
    """Create a Layout component definition."""
    return LayoutDef(
        children=children or [],
        direction=direction,
        gap=gap,
        padding=padding,
        align=align,
        justify=justify,
        width=width,
        max_width=max_width,
        wrap=wrap,
    )


def Row(
    children: Optional[List[Any]] = None,
    spacing: str = "4",
    align: str = "center",
    justify: str = "start",
    width: str = "100%",
    wrap: bool = False,
) -> RowDef:
    """Create a Row (horizontal stack) component definition."""
    return RowDef(
        children=children or [],
        spacing=spacing,
        align=align,
        justify=justify,
        width=width,
        wrap=wrap,
    )


def Column(
    children: Optional[List[Any]] = None,
    spacing: str = "4",
    align: str = "start",
    width: str = "100%",
) -> ColumnDef:
    """Create a Column (vertical stack) component definition."""
    return ColumnDef(
        children=children or [],
        spacing=spacing,
        align=align,
        width=width,
    )


def Card(
    title: str = "",
    content: Any = None,
    children: Optional[List[Any]] = None,
    variant: str = "surface",
    size: str = "3",
    width: str = "100%",
) -> CardDef:
    """Create a Card component definition."""
    return CardDef(
        title=title,
        content=content,
        children=children or [],
        variant=variant,
        size=size,
        width=width,
    )


def Wizard(
    steps: Optional[List["WizardStepDef"]] = None,
    on_complete: Optional[str] = None,
    on_cancel: Optional[str] = None,
    show_progress: bool = True,
    allow_skip: bool = False,
) -> WizardDef:
    """Create a Wizard component definition."""
    return WizardDef(
        steps=steps or [],
        on_complete=on_complete,
        on_cancel=on_cancel,
        show_progress=show_progress,
        allow_skip=allow_skip,
    )


def WizardStep(
    title: str = "",
    description: str = "",
    children: Optional[List[Any]] = None,
    validation: Optional[str] = None,
) -> WizardStepDef:
    """Create a WizardStep component definition."""
    return WizardStepDef(
        title=title,
        description=description,
        children=children or [],
        validation=validation,
    )


def Chart(
    chart_type: str = "line",
    data_source: Optional[str] = None,
    data: Optional[List[Dict[str, Any]]] = None,
    x_axis: str = "",
    y_axis: Union[str, List[str]] = "",
    title: str = "",
    width: str = "100%",
    height: str = "300px",
    colors: Optional[List[str]] = None,
    show_legend: bool = True,
    show_grid: bool = True,
) -> ChartDef:
    """Create a Chart component definition."""
    return ChartDef(
        chart_type=chart_type,
        data_source=data_source,
        data=data or [],
        x_axis=x_axis,
        y_axis=y_axis if isinstance(y_axis, (list, str)) else [y_axis],
        title=title,
        width=width,
        height=height,
        colors=colors or [],
        show_legend=show_legend,
        show_grid=show_grid,
    )


def Metric(
    label: str,
    value: Any = None,
    value_source: Optional[str] = None,
    trend: Optional[float] = None,
    trend_label: str = "",
    format: str = "",
    color_scheme: str = "blue",
    size: str = "3",
    icon: Optional[str] = None,
) -> MetricDef:
    """Create a Metric (KPI card) component definition."""
    return MetricDef(
        label=label,
        value=value,
        value_source=value_source,
        trend=trend,
        trend_label=trend_label,
        format=format,
        color_scheme=color_scheme,
        size=size,
        icon=icon,
    )


# ---------------------------------------------------------------------------
# Raw Reflex Passthrough (Task 4.3)
#
# Developers can use rx.* components directly inside @interface functions.
# The InterfaceRenderer detects non-ComponentDef items and passes them
# through as-is. This function wraps a raw Reflex component for explicit
# declaration if desired, but it's not required.
# ---------------------------------------------------------------------------

@dataclass
class RawReflexDef(ComponentDef):
    """
    Wrapper for raw Reflex components used alongside AppOS components.

    Usage:
        @interface(name="MyDashboard")
        def my_dashboard():
            return Layout([
                Card("Stats", content=Metric(label="Users", value=42)),
                RawReflex(rx.text("This is raw Reflex!", size="3")),
            ])

    Not required — the renderer auto-detects Reflex components.
    This wrapper is for explicit declaration when mixing component types.
    """
    _component_type: str = "raw_reflex"

    component: Any = None

    def to_dict(self) -> Dict[str, Any]:
        return {"type": self._component_type, "component": str(self.component)}


def RawReflex(component: Any) -> RawReflexDef:
    """Wrap a raw Reflex component for use in AppOS interfaces."""
    return RawReflexDef(component=component)


def FileUpload(
    folder: str = "",
    accept: Optional[List[str]] = None,
    max_size_mb: Optional[int] = None,
    multiple: bool = False,
    on_upload: Optional[str] = None,
    label: str = "Upload File",
    help_text: str = "",
    show_preview: bool = True,
    auto_upload: bool = False,
    record_field: Optional[str] = None,
    tags: Optional[List[str]] = None,
) -> FileUploadDef:
    """Create a FileUpload component definition for document uploads."""
    return FileUploadDef(
        folder=folder,
        accept=accept or [],
        max_size_mb=max_size_mb,
        multiple=multiple,
        on_upload=on_upload,
        label=label,
        help_text=help_text,
        show_preview=show_preview,
        auto_upload=auto_upload,
        record_field=record_field,
        tags=tags or [],
    )


# ---------------------------------------------------------------------------
# Component type registry — used by InterfaceRenderer
# ---------------------------------------------------------------------------

COMPONENT_TYPES = {
    "data_table": DataTableDef,
    "form": FormDef,
    "field": FieldDef,
    "button": ButtonDef,
    "layout": LayoutDef,
    "row": RowDef,
    "column": ColumnDef,
    "card": CardDef,
    "wizard": WizardDef,
    "wizard_step": WizardStepDef,
    "chart": ChartDef,
    "metric": MetricDef,
    "file_upload": FileUploadDef,
    "raw_reflex": RawReflexDef,
}
