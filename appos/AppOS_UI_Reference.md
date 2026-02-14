# AppOS — UI Layer Reference

> **Version:** 1.0  
> **Created:** February 14, 2026  
> **Design Doc:** `AppOS_Design.md` §12 (L2766–L2896), §5.13–§5.15, §9 (L2218)  
> **Task Plan:** `AppOS_TaskPlan.md` Phase 4

---

## Architecture Overview

```
┌─────────────────────────────────────────────────────────────────────────────┐
│                        UI LAYER — RENDER PIPELINE                          │
├─────────────────────────────────────────────────────────────────────────────┤
│                                                                             │
│  @page(route="/customers", interface="CustomerList")                        │
│    │                                                                        │
│    └── reflex_bridge._add_reflex_page()                                     │
│          │                                                                  │
│          ├── 1. Resolve @interface from ObjectRegistry                      │
│          │     └── Lookup: fq_ref → name scan → match                       │
│          │                                                                  │
│          ├── 2. InterfaceRenderer.to_reflex()                               │
│          │     ├── a. Call @interface handler → ComponentDef tree            │
│          │     ├── b. Apply @interface.extend extensions (if any)            │
│          │     ├── c. Walk tree → render each ComponentDef → rx.Component   │
│          │     └── d. Apply per-app theme (colors, font, border-radius)     │
│          │                                                                  │
│          ├── 3. Wrap in SiteConfig sidebar layout                           │
│          │     ├── Navigation from @site decorator (explicit)               │
│          │     └── Or auto-generated nav from @page objects                 │
│          │                                                                  │
│          └── 4. Register with Reflex (add_page + auth guard)                │
│                                                                             │
└─────────────────────────────────────────────────────────────────────────────┘
```

---

## Component Hierarchy

```
Page → Interface → Component

@page(route="/customers", interface="CustomerList")
  │
  └── @interface(name="CustomerList", record="Customer", type="list")
        │
        └── DataTable(                          ← ComponentDef (dataclass)
              record="Customer",
              columns=["name", "email", "tier"],
              actions=[Button("Create", ...)],   ← nested ComponentDef
              row_actions=[Button("Edit", ...)]
            )
```

**Rule:** Components are plain functions returning `ComponentDef` dataclasses. The `InterfaceRenderer` converts them to `rx.Component` at render time. This separation means interface definitions can be built without importing Reflex.

---

## Component Library

| Component | Maps To | Purpose |
|-----------|---------|---------|
| `DataTable` | `rx.table` + pagination | Sortable, filterable, searchable record table |
| `Form` | `rx.form` | Validated form with auto-fields from @record |
| `Field` | `rx.input` / `rx.select` / `rx.checkbox` | Auto-detects widget from field type |
| `Button` | `rx.button` | Actions: navigate, submit, rule, delete, custom |
| `Layout` | `rx.box` (flex) | Flex/grid container |
| `Row` | `rx.hstack` | Horizontal stack |
| `Column` | `rx.vstack` | Vertical stack |
| `Card` | `rx.card` | Card with title + content |
| `Wizard` | Multi-step container | Progress indicator, step navigation |
| `WizardStep` | Single wizard panel | Title, description, child components |
| `Chart` | `rx.recharts` | Line, bar, area, pie charts |
| `Metric` | KPI card | Label, large value, trend arrow |
| `RawReflex` | Passthrough | Wrap any `rx.*` component for mixing |

**File:** `appos/ui/components.py`

### Field Type Auto-Detection

| Pydantic / Field Name | → AppOS Field Type | → Reflex Widget |
|----|----|----|
| `str` | `text` | `rx.input` |
| `int`, `float` | `number` | `rx.input(type="number")` |
| `bool` | `checkbox` | `rx.checkbox` |
| `datetime` | `datetime` | `rx.input(type="datetime-local")` |
| `date` | `date` | `rx.input(type="date")` |
| `Literal[...]` / choices | `select` | `rx.select` |
| `*email*` in name | `email` | `rx.input(type="email")` |
| `*password*` in name | `password` | `rx.input(type="password")` |
| long text / dict | `textarea` | `rx.text_area` |

---

## InterfaceRenderer — Node Resolution

The renderer's `_render_node()` handles any input type:

| Input Type | Action |
|------------|--------|
| `ComponentDef` subclass | Route to type-specific renderer (e.g., `_render_data_table`) |
| `rx.Component` | **Pass through** as-is (raw Reflex) |
| `list` / `tuple` | Render each child, wrap in `rx.fragment` |
| `str`, `int`, `float`, `bool` | Wrap in `rx.text` |
| `dict` with `_type: "translation_ref"` | Resolve translation label |
| `callable` | Invoke → render result |
| `None` | Empty `rx.fragment` |

**File:** `appos/ui/renderer.py`

---

## @interface.extend Mechanism

```python
# Auto-generated (from @record Customer):
@interface(name="CustomerList", record_name="Customer", type="list")
def customer_list():
    return DataTable(record="Customer", columns=["name", "email", "tier"], ...)

# Developer extension (in apps/crm/interfaces/customer.py):
@interface_extend("CustomerList")
def extend_customer_list(base):
    # base = DataTableDef returned by original handler
    base.columns.append("credit_limit")
    base.actions.append(Button("Export", action="rule", rule="export_customers"))
    return base
```

**Execution flow:**
1. Base `@interface` handler runs → returns `ComponentDef`
2. `InterfaceExtendRegistry.apply_extensions()` applies all registered extensions in order
3. Modified `ComponentDef` passed to `InterfaceRenderer` for Reflex conversion

**File:** `appos/decorators/interface.py`

---

## Interface Auto-Generation from @record

For each `@record` with `Meta.permissions`, the generator produces 4 interfaces:

| Generated Interface | Type | Components Used |
|---------------------|------|-----------------|
| `{Record}List` | `list` | `DataTable` with columns, search, pagination, row actions |
| `{Record}Create` | `create` | `Form` with all editable fields, submit → record create |
| `{Record}Edit` | `edit` | `Form` pre-populated, submit → record update |
| `{Record}View` | `view` | `Layout` + `Card` with read-only `Field`s |

**Output:** `.appos/generated/interfaces/{app}_{record}_interfaces.py`

**Override options:**
- Replace completely: define `@interface(name="CustomerList")` in app code
- Extend/modify: use `@interface_extend("CustomerList")`

**File:** `appos/generators/interface_generator.py`

---

## Site Navigation

### Explicit (@site decorator)

```python
@site(name="CRM")
def crm_site():
    return {
        "pages": ["dashboard_page", "customers_page"],
        "navigation": [
            {"label": "Dashboard", "route": "/dashboard", "icon": "home"},
            {"label": "Customers", "route": "/customers", "icon": "users"},
        ],
        "auth_required": True,
        "default_page": "/dashboard",
    }
```

### Auto-Generated (no @site)

If no `@site` exists for an app, `reflex_bridge._build_site_configs()` auto-generates navigation from all `@page` definitions:
- Label = `@page` title (or name → Title Case)
- Route = `/{app_name}/{page_route}`
- Default page = first page found

### Layout Structure

```
┌───────────────────────────────────────────────────────────────┐
│ ┌────────────┐ ┌──────────────────────────────────────────┐   │
│ │  Sidebar    │ │  Main Content                            │   │
│ │  (240px)    │ │  (page component from InterfaceRenderer) │   │
│ │             │ │                                          │   │
│ │  App Name   │ │  margin-left: 240px                      │   │
│ │  ─────────  │ │  padding: 24px                           │   │
│ │  🏠 Dash    │ │                                          │   │
│ │  👥 Users   │ │  ┌──────────────────────────────┐        │   │
│ │  📦 Orders  │ │  │  Rendered @interface output   │        │   │
│ │             │ │  │  (DataTable / Form / Layout)  │        │   │
│ │             │ │  └──────────────────────────────┘        │   │
│ │  fixed,     │ │                                          │   │
│ │  full-height│ │                                          │   │
│ └────────────┘ └──────────────────────────────────────────┘   │
│                    font-family from app theme                  │
└───────────────────────────────────────────────────────────────┘
```

**File:** `appos/ui/reflex_bridge.py` — `_wrap_with_site_layout()`

---

## Per-App Theming

Each app defines its theme in `app.yaml`:

```yaml
app:
  theme:
    primary_color: "#3B82F6"
    secondary_color: "#1E40AF"
    accent_color: "#DBEAFE"
    font_family: "Inter"
    border_radius: "8px"
```

**Resolution chain:**
1. `reflex_bridge.get_app_theme(app_name)` → loads from `AppConfig`
2. Merges with defaults (`#3B82F6`, `Inter`, `8px`)
3. Applied at two levels:
   - `InterfaceRenderer._apply_theme()` → CSS variables on container
   - `_wrap_with_site_layout()` → `font-family` on outer wrapper

---

## UI Security — Three-Tier Inherited Model

| Tier | Source | Applies To | Override |
|------|--------|-----------|----------|
| **App defaults** | `app.yaml` → `security.defaults.ui.groups` | `@interface`, `@page`, `@translation_set` | Explicit `permissions=[...]` on decorator |
| **App defaults** | `app.yaml` → `security.defaults.logic.groups` | `@expression_rule`, `@constant` | Explicit `permissions=[...]` on decorator |
| **Always explicit** | Decorator / Meta | `@record`, `@process`, `@web_api`, `@integration`, `@connected_system` | REQUIRED — `appos check` errors if missing |

### Resolution Flow

```
UISecurityResolver.resolve_ui_permissions(app_name, explicit_permissions)
  │
  ├── explicit_permissions provided? → use those (Tier 2 override)
  │
  └── no explicit → inherit from app.yaml security.defaults.ui.groups (Tier 1)
        │
        └── no app.yaml defaults → empty list (open access)
```

### Access Check

```
UISecurityResolver.check_ui_access(app_name, user_groups, explicit_permissions)
  │
  ├── Resolve effective permissions
  ├── No permissions → open access (True)
  ├── Wildcard "*" → open access (True)
  └── Check: user_groups ∩ effective_permissions ≠ ∅
```

**File:** `appos/security/permissions.py`

---

## Form → Record Save Pipeline

```
rx.form(on_submit=RecordFormState.handle_record_submit)
  │
  └── RecordFormState.handle_record_submit(form_data)
        │
        ├── 1. Set save_status = "saving"
        ├── 2. Get runtime via get_runtime()
        ├── 3. Determine create vs update (from record_id)
        │     ├── No record_id → runtime.dispatch(record_type, action="create", data=form_data)
        │     └── Has record_id → runtime.dispatch(record_type, action="update", data={...form_data, id})
        ├── 4. On success → save_status = "success", optional redirect
        └── 5. On error → save_status = "error", error_message set
```

**File:** `appos/ui/renderer.py` — `RecordFormState`

---

## File Reference

| File | Purpose |
|------|---------|
| `appos/ui/components.py` | 12 ComponentDef dataclasses + constructor functions + `RawReflex` |
| `appos/ui/renderer.py` | `InterfaceRenderer` (ComponentDef → rx.Component) + `InterfaceState` + `RecordFormState` |
| `appos/ui/reflex_bridge.py` | `AppOSReflexApp`: routing, site nav, theme, auth guards, API routes |
| `appos/ui/__init__.py` | Public exports for all component constructors |
| `appos/generators/interface_generator.py` | Auto-gen List/Create/Edit/View from @record |
| `appos/decorators/interface.py` | `@interface_extend` + `InterfaceExtendRegistry` |
| `appos/decorators/core.py` | `@interface`, `@page`, `@site` decorators (registration only) |
| `appos/security/permissions.py` | `UISecurityResolver` — 3-tier inherited security |
| `appos/engine/config.py` | `AppConfig.theme`, `AppSecurity` models (app.yaml parsing) |

---

*Last updated: February 14, 2026*
