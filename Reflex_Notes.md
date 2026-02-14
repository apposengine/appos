# Reflex Dev — Key Notes & Best Practices

## Frontend (Compile-Time) Rules

- Frontend compiles to **JavaScript**; backend stays Python on the server.
- You **can** use plain Python functions in components, but only if they are defined at **compile time** (no state var references).
  ```python
  def show_numbers():
      return rx.vstack(*[rx.hstack(i, check_even(i)) for i in range(10)])
  ```
- You **cannot** use arbitrary Python ops on state vars inside components (e.g., ternary `if`, `%`, string ops). They only work inside event handlers.
  ```python
  # ❌ Won't work
  rx.text("hello", color=("red" if State.count % 2 == 0 else "blue"))
  
  # ✅ Use rx.cond / rx.match / rx.foreach instead
  rx.cond(State.count % 2 == 0, rx.text("Even"), rx.text("Odd"))
  ```
- **Var operations** exist for manipulating state vars in the frontend: `%`, `==`, attribute access, etc.  
  Ref: https://reflex.dev/docs/vars/var-operations/

## `rx.foreach` Details

- Render function receives `(value: rx.Var[T], index: int)` automatically.
- **Type annotations required** — `foreach` passes value as a `Var` object.
  ```python
  def create_button(color: rx.Var[str], index: int):
      return rx.box(rx.button(f"{index + 1}. {color}"))
  ```
- Supports: simple lists, dataclasses, nested `foreach`, and `rx.cond` inside `foreach`.
- Lambda form: `rx.foreach(State.colors, lambda color, index: create_button(color, index))`

## `rx.el` — Base HTML Elements

- Use `rx.el.div`, `rx.el.p`, etc. for standard HTML elements outside Radix component set.

## Event System Internals

- **Event queue** per client. Each event = `{client_token, event_handler, arguments}`.
- **Client token**: unique per browser tab; identifies which state instance to update.
- **Processing flag**: only **one event at a time** per client (except `background=True` events).
- Handler args must match the event trigger's args count.

## State Manager

- Maps client tokens → state instances.
- Default: **in-memory dict**.
- Production: use **Redis**.
- On every handler return/yield, state is saved and **only dirty vars** (changed vars) are sent to the frontend.

## `get_state` API — Cross-Substate Access

- Any handler can access another substate: `settings = await self.get_state(SettingsState)`
- Avoids complex inheritance; call it **only where needed, inside the handler**.
- Shared states should live in a **separate module** (`my_app/state.py`) to avoid circular imports.

## Streaming with `yield`

- Event handlers can **`yield`** mid-execution to push partial state updates to the frontend.
- Useful for streaming responses (e.g., OpenAI chat streaming).
  ```python
  async def answer(self):
      self.chat_history.append((self.question, ""))
      yield  # push partial update
      async for chunk in stream:
          self.chat_history[-1] = (q, answer_so_far)
          yield
  ```

## `rx.Base` for Non-DB Models

- Use `rx.Base` (not `rx.Model`) for plain data objects that don't need a database table.
  ```python
  class User(rx.Base):
      name: str
      email: str
  ```

## Best Practices

### Component Design
- **Components = functions** returning component objects. Never pass State classes as args; import state and access vars directly.
- **`@lru_cache`** on component functions for performance in large apps.
  ```python
  from functools import lru_cache
  @lru_cache
  def sidebar():
      return rx.box(...)
  ```
- **Props**: use snake_case for CSS/HTML props (`border_radius`, `font_size`, `class_name`).

### Project Structure
```
my_app/
├── assets/                  # Static files (images, fonts) → rx.image(src="/img.png")
├── uploaded_files/          # Runtime uploads, served at /_upload/<path>
├── my_app/
│   ├── __init__.py          # Import all state, models, pages here
│   ├── my_app.py            # app = rx.App(); app.add_page(...)
│   ├── state.py             # Shared/common states & substates
│   ├── models.py            # All DB models (or a models/ package)
│   ├── template.py          # Page layout wrapper (navbar, menu, etc.)
│   ├── components/          # Reusable UI: header, footer, auth, etc.
│   │   └── __init__.py
│   └── pages/               # One module per page, decorated with @rx.page()
│       └── __init__.py
├── rxconfig.py
└── requirements.txt
```

### State Organization
- Page-specific vars go in **page-local substates**, not shared state.
- Common states in `state.py` — this module should **not import other app modules**.
- For large apps, create packages for states and modules.

### Template Pattern
```python
def template(page: Callable[[], rx.Component]) -> rx.Component:
    return rx.vstack(navbar(), rx.hstack(menu(), rx.container(page())), width="100%")

# Decorator order matters:
@rx.page(route="/posts", on_load=PostsState.on_load)
@template
def posts():
    ...
```

### Files & Assets
| Type | Location | Access | Refreshes at Runtime |
|------|----------|--------|---------------------|
| Static assets | `assets/` | `rx.image(src="/file.png")` (port 3000) | ❌ No |
| Uploaded files | `uploaded_files/` | `rx.get_upload_url(path)` (port 8000) | ✅ Yes |

- Configure upload dir: `REFLEX_UPLOADED_FILES_DIR` env var.
- Write uploads relative to `rx.get_upload_dir()`.

### Configuration (`rxconfig.py`)
```python
import reflex as rx
config = rx.Config(
    app_name="my_app",
    db_url="postgresql://user:pass@localhost:5432/db",
    frontend_port=3001,
)
```
- `REFLEX_DIR` env var controls where Bun/NodeJS are installed (default Windows: `C:/Users/<user>/AppData/Local/reflex`).
- Debug logging: `reflex run --loglevel debug`
- Env var overrides: `FRONTEND_PORT=3001 reflex run`

### Performance
- Use `@rx.event(background=True)` for long-running tasks (bypasses processing flag).
- Use `@lru_cache` on heavy component functions.
- Keep state granular — dirty var tracking only sends changed vars.
