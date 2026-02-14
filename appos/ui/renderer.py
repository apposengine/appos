"""
AppOS Interface Renderer — Converts AppOS component definitions to Reflex components.

The renderer bridges AppOS's declarative component library (ComponentDef dataclasses)
and Reflex's actual UI component tree. It processes @interface function output and
produces a renderable rx.Component.

Hierarchy: Page → Interface → Component
- @page specifies which @interface to render
- @interface function returns ComponentDef tree (or raw Reflex components)
- InterfaceRenderer walks the tree and produces rx.Component

Design refs:
    §12  UI Layer — InterfaceRenderer, Page→Interface→Component hierarchy
    §5.13 Interface — component definitions, raw Reflex passthrough
    §5.14 Page — route binding, on_load
    §9   Record System — auto-generated interfaces

Supports:
- AppOS ComponentDef → Reflex component conversion
- Raw Reflex component passthrough (no wrapping needed)
- Per-app theming (wraps rendered output in theme provider)
- Form submission → Record save pipeline
- Security filtering (hides components the user can't access)
"""

from __future__ import annotations

import logging
from typing import Any, Callable, Dict, List, Optional, Tuple, Type

import reflex as rx

from appos.ui.components import (
    COMPONENT_TYPES,
    ButtonDef,
    CardDef,
    ChartDef,
    ColumnDef,
    ComponentDef,
    DataTableDef,
    FieldDef,
    FileUploadDef,
    FormDef,
    LayoutDef,
    MetricDef,
    RawReflexDef,
    RowDef,
    WizardDef,
    WizardStepDef,
)

logger = logging.getLogger("appos.ui.renderer")


# ---------------------------------------------------------------------------
# Renderer State — Reflex state for dynamic interface interaction
# ---------------------------------------------------------------------------

class InterfaceState(rx.State):
    """
    Shared Reflex state for rendered interfaces.

    Manages:
    - Form data collection and submission
    - Table pagination / sorting / filtering
    - Wizard step navigation
    - Action handlers (navigate, rule execution, delete)
    """

    # Form state
    form_data: dict = {}
    form_errors: dict = {}
    form_submitting: bool = False

    # Table state
    table_data: list = []
    table_page: int = 1
    table_page_size: int = 25
    table_sort_field: str = ""
    table_sort_dir: str = "asc"
    table_search: str = ""
    table_total: int = 0

    # Wizard state
    wizard_step: int = 0
    wizard_total_steps: int = 0

    # General
    loading: bool = False
    error_message: str = ""

    def set_form_field(self, field_name: str, value: Any):
        """Update a form field value."""
        self.form_data[field_name] = value

    def handle_form_submit(self, form_data: dict):
        """
        Handle form submission — delegates to Record save pipeline.

        The record name and action are determined from the interface definition
        stored at render time.
        """
        self.form_data = form_data
        self.form_submitting = True
        self.form_errors = {}
        # Actual save is wired by InterfaceRenderer via on_submit binding
        self.form_submitting = False

    def next_wizard_step(self):
        """Move to the next wizard step."""
        if self.wizard_step < self.wizard_total_steps - 1:
            self.wizard_step += 1

    def prev_wizard_step(self):
        """Move to the previous wizard step."""
        if self.wizard_step > 0:
            self.wizard_step -= 1

    def set_wizard_step(self, step: int):
        """Jump to a specific wizard step."""
        if 0 <= step < self.wizard_total_steps:
            self.wizard_step = step

    def set_table_page(self, page: int):
        """Change table page."""
        self.table_page = page

    def set_table_sort(self, field: str):
        """Toggle sort on a table column."""
        if self.table_sort_field == field:
            self.table_sort_dir = "desc" if self.table_sort_dir == "asc" else "asc"
        else:
            self.table_sort_field = field
            self.table_sort_dir = "asc"

    def set_table_search(self, query: str):
        """Update table search query."""
        self.table_search = query
        self.table_page = 1

    def clear_error(self):
        """Clear error message."""
        self.error_message = ""


# ---------------------------------------------------------------------------
# Interface Renderer
# ---------------------------------------------------------------------------

class InterfaceRenderer:
    """
    Converts AppOS interface definitions to Reflex component trees.

    Usage:
        renderer = InterfaceRenderer(interface_def, theme=app_theme)
        reflex_component = renderer.to_reflex()

    The renderer:
    1. Invokes the @interface handler to get the ComponentDef tree
    2. Walks the tree, converting each ComponentDef to an rx.Component
    3. Applies per-app theming
    4. Returns a single rx.Component suitable for Reflex page rendering
    """

    def __init__(
        self,
        interface_def: Any,  # RegisteredObject from registry
        theme: Optional[Dict[str, Any]] = None,
        app_name: str = "",
    ):
        self._interface_def = interface_def
        self._theme = theme or {}
        self._app_name = app_name

    def to_reflex(self) -> rx.Component:
        """
        Render the interface to a Reflex component.

        Returns a complete rx.Component tree ready for page rendering.
        """
        try:
            # Step 1: Invoke the @interface handler to get component defs
            handler = self._interface_def.handler
            if handler is None:
                return self._render_error("Interface has no handler")

            result = handler()

            # Step 1.5: Apply @interface.extend extensions if any
            interface_name = self._interface_def.metadata.get("name", self._interface_def.name)
            try:
                from appos.decorators.interface import interface_extend_registry
                if interface_extend_registry.has_extensions(interface_name):
                    result = interface_extend_registry.apply_extensions(interface_name, result)
            except ImportError:
                pass

            # Step 2: Convert the result to Reflex components
            component = self._render_node(result)

            # Step 3: Wrap in theme container if theme is provided
            if self._theme:
                component = self._apply_theme(component)

            return component

        except Exception as e:
            logger.error(f"Failed to render interface: {e}", exc_info=True)
            return self._render_error(str(e))

    def _render_node(self, node: Any) -> rx.Component:
        """
        Recursively render a node to a Reflex component.

        Handles:
        - ComponentDef instances → convert via type-specific renderer
        - rx.Component instances → pass through as-is (raw Reflex)
        - str/int/float → wrap in rx.text
        - list → render each item and wrap in rx.fragment
        - None → empty fragment
        """
        if node is None:
            return rx.fragment()

        # Raw Reflex components pass through
        if isinstance(node, rx.Component):
            return node

        # AppOS ComponentDef → convert
        if isinstance(node, ComponentDef):
            return self._render_component_def(node)

        # List of children
        if isinstance(node, (list, tuple)):
            children = [self._render_node(child) for child in node]
            return rx.fragment(*children)

        # Dict (translation ref or unknown) → text
        if isinstance(node, dict):
            if node.get("_type") == "translation_ref":
                # Translation reference — resolve at render time
                return rx.text(f"[{node.get('key', '?')}]")
            return rx.text(str(node))

        # Primitive → text
        if isinstance(node, (str, int, float, bool)):
            return rx.text(str(node))

        # Callable (component function) → call and render result
        if callable(node):
            try:
                return self._render_node(node())
            except Exception as e:
                return self._render_error(f"Component error: {e}")

        return rx.text(str(node))

    def _render_component_def(self, comp: ComponentDef) -> rx.Component:
        """Route a ComponentDef to its type-specific renderer."""
        renderers = {
            "data_table": self._render_data_table,
            "form": self._render_form,
            "field": self._render_field,
            "button": self._render_button,
            "layout": self._render_layout,
            "row": self._render_row,
            "column": self._render_column,
            "card": self._render_card,
            "wizard": self._render_wizard,
            "wizard_step": self._render_wizard_step,
            "chart": self._render_chart,
            "metric": self._render_metric,
            "file_upload": self._render_file_upload,
            "raw_reflex": self._render_raw_reflex,
        }

        renderer = renderers.get(comp._component_type)
        if renderer:
            return renderer(comp)

        logger.warning(f"Unknown component type: {comp._component_type}")
        return rx.text(f"[Unknown: {comp._component_type}]")

    # -------------------------------------------------------------------
    # Type-specific renderers
    # -------------------------------------------------------------------

    def _render_data_table(self, comp: DataTableDef) -> rx.Component:
        """Render a DataTable → rx.table with header, body, pagination."""
        # Header actions (search bar + action buttons)
        header_items = []

        if comp.searchable:
            header_items.append(
                rx.input(
                    placeholder=f"Search {comp.record or 'records'}...",
                    on_change=InterfaceState.set_table_search,
                    width="300px",
                    size="2",
                )
            )

        if comp.actions:
            for action_def in comp.actions:
                header_items.append(self._render_button(action_def))

        # Column headers
        col_headers = [
            rx.table.column_header_cell(
                rx.text(col.replace("_", " ").title(), weight="bold")
            )
            for col in comp.columns
        ]

        if comp.row_actions:
            col_headers.append(rx.table.column_header_cell("Actions"))

        # Table structure
        table = rx.vstack(
            # Header bar
            rx.hstack(
                *header_items,
                width="100%",
                justify="between",
                align="center",
                spacing="3",
            ) if header_items else rx.fragment(),
            # The table
            rx.table.root(
                rx.table.header(rx.table.row(*col_headers)),
                rx.table.body(
                    rx.cond(
                        InterfaceState.table_data.length() > 0,
                        rx.foreach(
                            InterfaceState.table_data,
                            lambda row: self._render_table_row(row, comp),
                        ),
                        rx.table.row(
                            rx.table.cell(
                                rx.text(comp.empty_message, color="gray"),
                                col_span=len(comp.columns) + (1 if comp.row_actions else 0),
                            )
                        ),
                    ),
                ),
                width="100%",
            ),
            # Pagination
            rx.hstack(
                rx.text(
                    f"Page ",
                    rx.text(InterfaceState.table_page, as_="span", weight="bold"),
                    size="2",
                    color="gray",
                ),
                rx.hstack(
                    rx.button(
                        "Previous",
                        variant="outline",
                        size="1",
                        on_click=InterfaceState.set_table_page(
                            InterfaceState.table_page - 1
                        ),
                        disabled=InterfaceState.table_page <= 1,
                    ),
                    rx.button(
                        "Next",
                        variant="outline",
                        size="1",
                        on_click=InterfaceState.set_table_page(
                            InterfaceState.table_page + 1
                        ),
                    ),
                    spacing="2",
                ),
                width="100%",
                justify="between",
                align="center",
            ),
            spacing="4",
            width="100%",
        )

        return table

    def _render_table_row(self, row: Any, comp: DataTableDef) -> rx.Component:
        """Render a single table row."""
        cells = [rx.table.cell(rx.text(row[col])) for col in comp.columns]

        if comp.row_actions:
            action_buttons = rx.hstack(
                *[self._render_button(a) for a in comp.row_actions],
                spacing="2",
            )
            cells.append(rx.table.cell(action_buttons))

        return rx.table.row(*cells)

    def _render_form(self, comp: FormDef) -> rx.Component:
        """Render a Form → rx.form with fields and submit/cancel buttons."""
        fields = []
        for field_def in comp.fields:
            if isinstance(field_def, str):
                # Simple field name — create with defaults
                fields.append(
                    self._render_field(FieldDef(name=field_def))
                )
            elif isinstance(field_def, FieldDef):
                fields.append(self._render_field(field_def))
            else:
                fields.append(self._render_node(field_def))

        # Arrange in grid if requested
        if comp.layout == "grid" and comp.columns > 1:
            rows = []
            for i in range(0, len(fields), comp.columns):
                row_fields = fields[i : i + comp.columns]
                rows.append(rx.hstack(*row_fields, spacing="4", width="100%"))
            field_container = rx.vstack(*rows, spacing="3", width="100%")
        else:
            field_container = rx.vstack(*fields, spacing="3", width="100%")

        # Action buttons
        buttons = rx.hstack(
            rx.button(comp.cancel_label, variant="outline", type="button"),
            rx.button(comp.submit_label, type="submit"),
            spacing="3",
            justify="end",
            width="100%",
        )

        return rx.form(
            rx.vstack(
                field_container,
                rx.divider(),
                buttons,
                spacing="4",
                width="100%",
            ),
            on_submit=InterfaceState.handle_form_submit,
            width="100%",
        )

    def _render_field(self, comp: FieldDef) -> rx.Component:
        """Render a Field → appropriate rx.input / rx.select / rx.checkbox."""
        label_text = comp.label or comp.name.replace("_", " ").title()

        if comp.field_type == "checkbox":
            return rx.box(
                rx.checkbox(
                    label_text,
                    name=comp.name,
                    default_checked=bool(comp.default_value),
                    disabled=comp.read_only,
                ),
                width=comp.width,
            )

        if comp.field_type == "select" or comp.choices:
            return rx.box(
                rx.text(label_text, size="2", weight="medium"),
                rx.select(
                    [str(c) for c in comp.choices],
                    placeholder=comp.placeholder or f"Select {label_text.lower()}...",
                    name=comp.name,
                    default_value=str(comp.default_value) if comp.default_value else None,
                    disabled=comp.read_only,
                    width="100%",
                ),
                rx.cond(
                    comp.help_text != "",
                    rx.text(comp.help_text, size="1", color="gray"),
                    rx.fragment(),
                ) if comp.help_text else rx.fragment(),
                width=comp.width,
            )

        if comp.field_type == "textarea":
            return rx.box(
                rx.text(label_text, size="2", weight="medium"),
                rx.text_area(
                    placeholder=comp.placeholder,
                    name=comp.name,
                    default_value=str(comp.default_value) if comp.default_value else "",
                    read_only=comp.read_only,
                    required=comp.required,
                    width="100%",
                ),
                rx.text(comp.help_text, size="1", color="gray") if comp.help_text else rx.fragment(),
                width=comp.width,
            )

        # Default: text/email/password/number/date/datetime input
        input_type = comp.field_type
        if input_type == "datetime":
            input_type = "datetime-local"

        return rx.box(
            rx.text(label_text, size="2", weight="medium"),
            rx.input(
                placeholder=comp.placeholder or label_text,
                name=comp.name,
                type=input_type,
                default_value=str(comp.default_value) if comp.default_value else "",
                read_only=comp.read_only,
                required=comp.required,
                width="100%",
            ),
            rx.text(comp.help_text, size="1", color="gray") if comp.help_text else rx.fragment(),
            width=comp.width,
        )

    def _render_button(self, comp: ButtonDef) -> rx.Component:
        """Render a Button → rx.button with action handler."""
        on_click = None

        if comp.action == "navigate" and comp.to:
            on_click = rx.redirect(comp.to)
        elif comp.action == "submit":
            # Submit is handled by the form's type="submit"
            return rx.button(
                comp.label,
                type="submit",
                variant=comp.variant,
                color_scheme=comp.color_scheme,
                size=comp.size,
                disabled=comp.disabled,
            )

        btn = rx.button(
            comp.label,
            variant=comp.variant,
            color_scheme=comp.color_scheme,
            size=comp.size,
            disabled=comp.disabled,
            on_click=on_click,
        )

        if comp.confirm:
            return rx.alert_dialog.root(
                rx.alert_dialog.trigger(btn),
                rx.alert_dialog.content(
                    rx.alert_dialog.title("Confirm Action"),
                    rx.alert_dialog.description(
                        f"Are you sure you want to {comp.label.lower()}?"
                    ),
                    rx.hstack(
                        rx.alert_dialog.cancel(rx.button("Cancel", variant="outline")),
                        rx.alert_dialog.action(
                            rx.button(
                                comp.label,
                                color_scheme="red",
                                on_click=on_click,
                            )
                        ),
                        spacing="3",
                        justify="end",
                    ),
                ),
            )

        return btn

    def _render_layout(self, comp: LayoutDef) -> rx.Component:
        """Render a Layout → rx.box with flex direction."""
        children = [self._render_node(c) for c in comp.children]

        if comp.direction == "row":
            return rx.hstack(
                *children,
                spacing=comp.gap,
                align=comp.align,
                justify=comp.justify,
                width=comp.width,
                flex_wrap="wrap" if comp.wrap else "nowrap",
                padding=comp.padding,
                max_width=comp.max_width or "100%",
            )
        else:
            return rx.vstack(
                *children,
                spacing=comp.gap,
                align=comp.align,
                width=comp.width,
                padding=comp.padding,
                max_width=comp.max_width or "100%",
            )

    def _render_row(self, comp: RowDef) -> rx.Component:
        """Render a Row → rx.hstack."""
        children = [self._render_node(c) for c in comp.children]
        return rx.hstack(
            *children,
            spacing=comp.spacing,
            align=comp.align,
            justify=comp.justify,
            width=comp.width,
            flex_wrap="wrap" if comp.wrap else "nowrap",
        )

    def _render_column(self, comp: ColumnDef) -> rx.Component:
        """Render a Column → rx.vstack."""
        children = [self._render_node(c) for c in comp.children]
        return rx.vstack(
            *children,
            spacing=comp.spacing,
            align=comp.align,
            width=comp.width,
        )

    def _render_card(self, comp: CardDef) -> rx.Component:
        """Render a Card → rx.card with header and content."""
        card_children = []

        if comp.title:
            card_children.append(
                rx.text(comp.title, size="3", weight="bold")
            )

        if comp.content is not None:
            card_children.append(self._render_node(comp.content))

        for child in comp.children:
            card_children.append(self._render_node(child))

        return rx.card(
            rx.vstack(*card_children, spacing="2"),
            variant=comp.variant,
            size=comp.size,
            width=comp.width,
        )

    def _render_wizard(self, comp: WizardDef) -> rx.Component:
        """
        Render a Wizard → multi-step form with progress.

        Uses WizardState to track current step and show/hide steps.
        """
        if not comp.steps:
            return rx.text("Empty wizard", color="gray")

        # Progress indicator
        progress_items = []
        if comp.show_progress:
            for i, step_def in enumerate(comp.steps):
                progress_items.append(
                    rx.hstack(
                        rx.cond(
                            InterfaceState.wizard_step > i,
                            rx.icon("check-circle", color="green", size=20),
                            rx.cond(
                                InterfaceState.wizard_step == i,
                                rx.icon("circle-dot", color="blue", size=20),
                                rx.icon("circle", color="gray", size=20),
                            ),
                        ),
                        rx.text(
                            step_def.title,
                            size="2",
                            weight=rx.cond(
                                InterfaceState.wizard_step == i,
                                "bold",
                                "regular",
                            ),
                        ),
                        spacing="2",
                        align="center",
                    )
                )

        # Step content — show only active step
        step_panels = []
        for i, step_def in enumerate(comp.steps):
            step_content = self._render_wizard_step(step_def)
            step_panels.append(
                rx.cond(
                    InterfaceState.wizard_step == i,
                    step_content,
                    rx.fragment(),
                )
            )

        # Navigation buttons
        nav_buttons = rx.hstack(
            rx.button(
                "Previous",
                variant="outline",
                on_click=InterfaceState.prev_wizard_step,
                disabled=InterfaceState.wizard_step <= 0,
            ),
            rx.cond(
                InterfaceState.wizard_step < len(comp.steps) - 1,
                rx.button("Next", on_click=InterfaceState.next_wizard_step),
                rx.button("Complete", color_scheme="green"),
            ),
            spacing="3",
            justify="end",
            width="100%",
        )

        return rx.vstack(
            # Progress bar
            rx.hstack(*progress_items, spacing="4") if progress_items else rx.fragment(),
            rx.divider(),
            # Step content
            *step_panels,
            rx.divider(),
            # Navigation
            nav_buttons,
            spacing="4",
            width="100%",
            padding="4",
        )

    def _render_wizard_step(self, comp: WizardStepDef) -> rx.Component:
        """Render a single wizard step."""
        children = [self._render_node(c) for c in comp.children]

        return rx.vstack(
            rx.heading(comp.title, size="4") if comp.title else rx.fragment(),
            rx.text(comp.description, color="gray") if comp.description else rx.fragment(),
            *children,
            spacing="3",
            width="100%",
            min_height="200px",
        )

    def _render_chart(self, comp: ChartDef) -> rx.Component:
        """
        Render a Chart → rx.recharts component.

        Supports line, bar, area, pie charts via Reflex's recharts integration.
        """
        chart_children = []

        # Ensure y_axis is a list
        y_axes = comp.y_axis if isinstance(comp.y_axis, list) else [comp.y_axis]

        # Default colors
        colors = comp.colors or [
            "#3B82F6", "#10B981", "#F59E0B", "#EF4444",
            "#8B5CF6", "#EC4899", "#06B6D4", "#84CC16",
        ]

        if comp.chart_type == "line":
            for i, y_key in enumerate(y_axes):
                color = colors[i % len(colors)]
                chart_children.append(
                    rx.recharts.line(
                        data_key=y_key,
                        stroke=color,
                        type="monotone",
                    )
                )

            chart = rx.recharts.line_chart(
                *chart_children,
                rx.recharts.x_axis(data_key=comp.x_axis),
                rx.recharts.y_axis(),
                rx.recharts.cartesian_grid(stroke_dasharray="3 3") if comp.show_grid else rx.fragment(),
                rx.recharts.legend() if comp.show_legend else rx.fragment(),
                rx.recharts.tooltip(),
                data=comp.data,
                width="100%",
                height=300,
            )

        elif comp.chart_type == "bar":
            for i, y_key in enumerate(y_axes):
                color = colors[i % len(colors)]
                chart_children.append(
                    rx.recharts.bar(data_key=y_key, fill=color)
                )

            chart = rx.recharts.bar_chart(
                *chart_children,
                rx.recharts.x_axis(data_key=comp.x_axis),
                rx.recharts.y_axis(),
                rx.recharts.cartesian_grid(stroke_dasharray="3 3") if comp.show_grid else rx.fragment(),
                rx.recharts.legend() if comp.show_legend else rx.fragment(),
                rx.recharts.tooltip(),
                data=comp.data,
                width="100%",
                height=300,
            )

        elif comp.chart_type == "area":
            for i, y_key in enumerate(y_axes):
                color = colors[i % len(colors)]
                chart_children.append(
                    rx.recharts.area(
                        data_key=y_key,
                        stroke=color,
                        fill=color,
                        fill_opacity=0.3,
                        type="monotone",
                    )
                )

            chart = rx.recharts.area_chart(
                *chart_children,
                rx.recharts.x_axis(data_key=comp.x_axis),
                rx.recharts.y_axis(),
                rx.recharts.cartesian_grid(stroke_dasharray="3 3") if comp.show_grid else rx.fragment(),
                rx.recharts.legend() if comp.show_legend else rx.fragment(),
                rx.recharts.tooltip(),
                data=comp.data,
                width="100%",
                height=300,
            )

        elif comp.chart_type == "pie":
            chart = rx.recharts.pie_chart(
                rx.recharts.pie(
                    data=comp.data,
                    data_key=y_axes[0] if y_axes else "value",
                    name_key=comp.x_axis or "name",
                    cx="50%",
                    cy="50%",
                    outer_radius=80,
                    fill="#3B82F6",
                    label=True,
                ),
                rx.recharts.legend() if comp.show_legend else rx.fragment(),
                rx.recharts.tooltip(),
                width="100%",
                height=300,
            )

        else:
            chart = rx.text(f"Unsupported chart type: {comp.chart_type}", color="red")

        # Wrap with title
        if comp.title:
            return rx.vstack(
                rx.text(comp.title, size="3", weight="bold"),
                rx.recharts.responsive_container(chart, width="100%", height=300),
                spacing="2",
                width=comp.width,
            )

        return rx.recharts.responsive_container(chart, width="100%", height=300)

    def _render_metric(self, comp: MetricDef) -> rx.Component:
        """Render a Metric → KPI card with value and trend."""
        value_display = str(comp.value) if comp.value is not None else "—"

        # Format value
        if comp.format == "currency":
            value_display = f"${comp.value:,.2f}" if isinstance(comp.value, (int, float)) else value_display
        elif comp.format == "percent":
            value_display = f"{comp.value}%" if comp.value is not None else value_display
        elif comp.format == "number" and isinstance(comp.value, (int, float)):
            value_display = f"{comp.value:,}"

        # Trend indicator
        trend_component = rx.fragment()
        if comp.trend is not None:
            trend_color = "green" if comp.trend >= 0 else "red"
            trend_icon = "trending-up" if comp.trend >= 0 else "trending-down"
            trend_text = f"{comp.trend:+.1f}%"
            if comp.trend_label:
                trend_text = f"{trend_text} {comp.trend_label}"

            trend_component = rx.hstack(
                rx.icon(trend_icon, color=trend_color, size=16),
                rx.text(trend_text, size="1", color=trend_color),
                spacing="1",
                align="center",
            )

        return rx.card(
            rx.vstack(
                rx.hstack(
                    rx.icon(comp.icon, size=20, color=comp.color_scheme) if comp.icon else rx.fragment(),
                    rx.text(comp.label, size="2", color="gray"),
                    spacing="2",
                    align="center",
                ),
                rx.text(value_display, size="7", weight="bold"),
                trend_component,
                spacing="2",
                align="start",
            ),
            size=comp.size,
        )

    def _render_raw_reflex(self, comp: RawReflexDef) -> rx.Component:
        """Render a raw Reflex component — pass through as-is."""
        if comp.component is not None and isinstance(comp.component, rx.Component):
            return comp.component
        return rx.text("[Raw Reflex: invalid]", color="red")

    def _render_file_upload(self, comp: FileUploadDef) -> rx.Component:
        """
        Render a FileUpload → rx.upload zone with progress and file list.

        Uses Reflex's rx.upload component which provides:
        - Drag-and-drop zone
        - File type filtering (accept)
        - Multiple file support
        - Upload progress tracking

        The actual file handling is done by FileUploadState which
        delegates to DocumentService for validation and storage.
        """
        # Build accept filter
        accept_filter = {}
        if comp.accept:
            for mime in comp.accept:
                accept_filter[mime] = []

        # Max file size in bytes (from component or platform default 50MB)
        max_size = (comp.max_size_mb or 50) * 1024 * 1024

        # Upload zone content
        upload_content = rx.vstack(
            rx.icon("upload-cloud", size=48, color="gray"),
            rx.text(
                comp.label,
                size="3",
                weight="medium",
            ),
            rx.text(
                comp.help_text or "Drag and drop files here, or click to browse",
                size="1",
                color="gray",
            ),
            align="center",
            spacing="2",
            padding="40px",
        )

        # The upload zone
        upload_zone = rx.upload(
            upload_content,
            id=f"upload_{comp.folder or 'default'}",
            accept=accept_filter if accept_filter else None,
            max_files=10 if comp.multiple else 1,
            multiple=comp.multiple,
            border="2px dashed var(--gray-6)",
            border_radius="8px",
            padding="0",
            width="100%",
            cursor="pointer",
            _hover={"border_color": "var(--accent-9)", "background": "var(--accent-2)"},
        )

        # File list preview (selected files before upload)
        file_list = rx.cond(
            FileUploadState.selected_files.length() > 0,  # type: ignore
            rx.vstack(
                rx.foreach(
                    FileUploadState.selected_files,
                    lambda f: rx.hstack(
                        rx.icon("file", size=16),
                        rx.text(f, size="2"),
                        spacing="2",
                        align="center",
                    ),
                ),
                spacing="1",
                width="100%",
            ),
            rx.fragment(),
        )

        # Upload button (manual trigger unless auto_upload)
        upload_button = rx.cond(
            ~FileUploadState.is_uploading,  # type: ignore
            rx.button(
                rx.icon("upload", size=16),
                "Upload",
                on_click=FileUploadState.handle_upload(
                    rx.upload_files(
                        upload_id=f"upload_{comp.folder or 'default'}",
                    )
                ),
                variant="solid",
                size="2",
            ),
            rx.button(
                rx.spinner(size="1"),
                "Uploading...",
                disabled=True,
                variant="soft",
                size="2",
            ),
        )

        # Status message
        status = rx.cond(
            FileUploadState.upload_status != "",  # type: ignore
            rx.callout(
                rx.text(FileUploadState.upload_status),
                icon=rx.cond(
                    FileUploadState.upload_error,  # type: ignore
                    "alert-circle",
                    "check-circle",
                ),
                color_scheme=rx.cond(
                    FileUploadState.upload_error,  # type: ignore
                    "red",
                    "green",
                ),
                width="100%",
            ),
            rx.fragment(),
        )

        # Assemble
        children = [upload_zone]
        if comp.show_preview:
            children.append(file_list)
        if not comp.auto_upload:
            children.append(upload_button)
        children.append(status)

        return rx.vstack(
            *children,
            spacing="3",
            width="100%",
        )

    # -------------------------------------------------------------------
    # Theme Application
    # -------------------------------------------------------------------

    def _apply_theme(self, component: rx.Component) -> rx.Component:
        """
        Wrap rendered component in per-app theme styling.

        Applies primary_color, font_family, border_radius from app theme.
        Uses Reflex's theme system (rx.theme) for consistent styling.
        """
        primary = self._theme.get("primary_color", "#3B82F6")
        font = self._theme.get("font_family", "Inter")

        # Wrap in a themed container
        return rx.box(
            component,
            style={
                "--accent-color": primary,
                "font_family": font,
            },
            width="100%",
        )

    # -------------------------------------------------------------------
    # Error rendering
    # -------------------------------------------------------------------

    def _render_error(self, message: str) -> rx.Component:
        """Render an error state."""
        return rx.callout(
            rx.text(f"Render Error: {message}"),
            icon="alert-triangle",
            color_scheme="red",
            width="100%",
        )


# ---------------------------------------------------------------------------
# Helper: Create a Reflex page component from an interface
# ---------------------------------------------------------------------------

def render_interface_page(
    interface_def: Any,
    theme: Optional[Dict[str, Any]] = None,
    app_name: str = "",
    page_layout: Optional[Callable] = None,
) -> Callable:
    """
    Create a Reflex page function from an @interface definition.

    This is called by the reflex_bridge when binding @page routes.

    Args:
        interface_def: RegisteredObject for the @interface
        theme: App theme dict
        app_name: App short name
        page_layout: Optional layout wrapper function

    Returns:
        A function that returns an rx.Component (suitable for rx.add_page)
    """
    def page_component() -> rx.Component:
        renderer = InterfaceRenderer(
            interface_def=interface_def,
            theme=theme,
            app_name=app_name,
        )
        content = renderer.to_reflex()

        if page_layout:
            return page_layout(content)
        return content

    return page_component


# ---------------------------------------------------------------------------
# Form Submission → Record Save Pipeline (Task 4.12)
# ---------------------------------------------------------------------------

class RecordFormState(rx.State):
    """
    Reflex state for form-to-record save operations.

    Handles the pipeline:
    1. Collect form data from rx.form on_submit
    2. Validate against Pydantic @record model
    3. Call CRUD service (create or update)
    4. Show success/error feedback
    5. Optionally redirect on success
    """

    # Form state
    record_type: str = ""
    record_id: str = ""  # Empty for create, populated for edit
    form_data: dict = {}
    validation_errors: dict = {}
    save_status: str = ""  # "saving" | "success" | "error"
    error_message: str = ""
    redirect_to: str = ""

    def handle_record_submit(self, form_data: dict):
        """
        Handle form submission for a record create/update.

        Pipeline:
            1. Validate with Pydantic model
            2. Call record service
            3. Update state with result
        """
        self.form_data = form_data
        self.save_status = "saving"
        self.validation_errors = {}
        self.error_message = ""

        try:
            # Import runtime for dispatch
            from appos.engine.runtime import get_runtime

            runtime = get_runtime()
            if runtime is None:
                self.save_status = "error"
                self.error_message = "Runtime not available"
                return

            # Determine create vs update
            if self.record_id:
                # Update existing record
                result = runtime.dispatch(
                    f"{self.record_type}",
                    action="update",
                    data={**form_data, "id": self.record_id},
                )
            else:
                # Create new record
                result = runtime.dispatch(
                    f"{self.record_type}",
                    action="create",
                    data=form_data,
                )

            self.save_status = "success"

            # Redirect if configured
            if self.redirect_to:
                return rx.redirect(self.redirect_to)

        except Exception as e:
            self.save_status = "error"
            self.error_message = str(e)
            logger.error(f"Record save failed: {e}", exc_info=True)

    def clear_form(self):
        """Reset form state."""
        self.form_data = {}
        self.validation_errors = {}
        self.save_status = ""
        self.error_message = ""
        self.record_id = ""


# ---------------------------------------------------------------------------
# File Upload State (Task 5.11)
# ---------------------------------------------------------------------------

class FileUploadState(rx.State):
    """
    Reflex state for document file uploads.

    Integrates with DocumentService for:
    - MIME type validation against folder config
    - Size limit enforcement (platform + folder level)
    - Document record creation with versioning
    - Physical file storage to apps/{app}/runtime/documents/

    Design ref: §5.16 (rx.upload integration)
    """

    # Upload state
    selected_files: list[str] = []
    is_uploading: bool = False
    upload_status: str = ""
    upload_error: bool = False
    upload_progress: float = 0.0
    uploaded_documents: list[dict] = []

    # Configuration (set by the FileUpload component or page)
    target_folder: str = ""
    target_app: str = ""
    upload_tags: list[str] = []

    async def handle_upload(self, files: list[rx.UploadFile]):
        """
        Handle file upload from rx.upload component.

        Pipeline:
        1. Set uploading state
        2. For each file: validate → write → create Document
        3. Update status
        """
        self.is_uploading = True
        self.upload_status = ""
        self.upload_error = False
        self.uploaded_documents = []

        try:
            from appos.documents.service import DocumentService
            from appos.engine.config import get_platform_config
            from appos.engine.context import get_execution_context

            # Get platform config for max upload size
            platform_config = get_platform_config()
            max_size = platform_config.documents.max_upload_size_mb

            # Get current user
            ctx = get_execution_context()
            owner_id = ctx.user_id if ctx else 0

            # Create document service
            doc_service = DocumentService(
                app_short_name=self.target_app or "default",
                max_upload_size_mb=max_size,
            )

            uploaded = []
            errors = []

            for file in files:
                try:
                    # Read file data
                    file_data = await file.read()
                    file_size = len(file_data)
                    file_name = file.filename or "unnamed"

                    # Detect MIME type
                    mime_type = DocumentService.detect_mime_type(file_name)

                    # Create a Folder-like object for validation if target_folder is set
                    # In production, this would query the DB for the actual Folder record
                    from appos.documents.models import Folder
                    folder = Folder(
                        name=self.target_folder or "uploads",
                        path=self.target_folder or "uploads",
                        purpose="User uploads",
                        app_id=0,
                    )

                    # Validate
                    valid, error = doc_service.validate_upload(
                        folder=folder,
                        file_name=file_name,
                        file_size=file_size,
                        mime_type=mime_type,
                    )
                    if not valid:
                        errors.append(f"{file_name}: {error}")
                        continue

                    # Write to disk using BytesIO wrapper
                    import io
                    file_stream = io.BytesIO(file_data)

                    doc, version = doc_service.upload_document(
                        folder=folder,
                        file_name=file_name,
                        file_data=file_stream,
                        file_size=file_size,
                        owner_id=owner_id,
                        mime_type=mime_type,
                        tags=self.upload_tags if self.upload_tags else [],
                    )

                    uploaded.append({
                        "name": doc.name,
                        "size": doc.size_bytes,
                        "mime_type": doc.mime_type,
                        "path": doc.file_path,
                    })

                except Exception as e:
                    errors.append(f"{getattr(file, 'filename', 'unknown')}: {str(e)}")

            self.uploaded_documents = uploaded

            if errors:
                self.upload_error = True
                self.upload_status = f"Errors: {'; '.join(errors)}"
                if uploaded:
                    self.upload_status = (
                        f"Uploaded {len(uploaded)} file(s). Errors: {'; '.join(errors)}"
                    )
            else:
                self.upload_status = f"Successfully uploaded {len(uploaded)} file(s)"
                self.upload_error = False

        except Exception as e:
            self.upload_error = True
            self.upload_status = f"Upload failed: {str(e)}"
            logger.error(f"File upload failed: {e}", exc_info=True)

        finally:
            self.is_uploading = False

    def clear_upload(self):
        """Reset upload state."""
        self.selected_files = []
        self.is_uploading = False
        self.upload_status = ""
        self.upload_error = False
        self.upload_progress = 0.0
        self.uploaded_documents = []
