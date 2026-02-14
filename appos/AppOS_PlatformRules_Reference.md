# AppOS — Platform Rules Reference

> **Referenced from:** `AppOS_Design.md` §5.8, §15  
> **Version:** 2.1 — February 12, 2026

---

## Overview

Platform rules are prebuilt expression rules provided by AppOS itself. They live in `appos/platform_rules/` and are available to all apps without import via the `platform` namespace:

```python
user = platform.rules.get_current_user(ctx)
```

---

## Available Platform Rules

### User Management

| Rule | Signature | Returns | Description |
|---|---|---|---|
| `get_current_user` | `(ctx)` | `User` dict | Returns the currently authenticated user's profile |
| `get_user` | `(ctx, user_id)` | `User` dict | Returns any user's profile by ID |
| `create_user` | `(ctx, username, email, display_name, user_type="basic")` | `User` dict | Creates a new user. Requires `system_admin` group. |
| `update_user` | `(ctx, user_id, **fields)` | `User` dict | Updates user profile fields. Requires `system_admin` group. |
| `change_password` | `(ctx, user_id, old_password, new_password)` | `bool` | Self-service password change. Requires `old_password` for verification. |
| `reset_password` | `(ctx, user_id, new_password)` | `bool` | Admin password reset — no `old_password` required. Requires `system_admin` group. |
| `deactivate_user` | `(ctx, user_id)` | `bool` | Soft-deactivates user (sets `is_active=False`). Requires `system_admin` group. No hard deletes. |

### Group Management

| Rule | Signature | Returns | Description |
|---|---|---|---|
| `get_user_groups` | `(ctx, user_id=None)` | `list[Group]` | Returns groups for user (defaults to current user) |
| `get_group_members` | `(ctx, group_name)` | `list[User]` | Returns all members of a group |
| `create_group` | `(ctx, group_name, description=None)` | `Group` dict | Creates a new group. Requires `system_admin` group. |
| `add_user_to_group` | `(ctx, user_id, group_name)` | `bool` | Adds user to group. Requires `admin` permission on the group or `system_admin` group. |
| `remove_user_from_group` | `(ctx, user_id, group_name)` | `bool` | Removes user from group. Requires `admin` permission on the group or `system_admin` group. |
| `deactivate_group` | `(ctx, group_name)` | `bool` | Soft-deactivates group (sets `is_active=False`). Members are NOT removed. Requires `system_admin` group. No hard deletes. |

### Utility

| Rule | Signature | Returns | Description |
|---|---|---|---|
| `get_environment` | `(ctx)` | `str` | Returns current environment name (`dev`, `staging`, `prod`) |
| `get_app_config` | `(ctx, key)` | `Any` | Returns app-level configuration value from `app.yaml` |

---

## Usage Examples

### In Expression Rules

```python
@expression_rule
def get_my_team(ctx):
    current_user = platform.rules.get_current_user(ctx)
    groups = platform.rules.get_user_groups(ctx, current_user["id"])
    
    team_members = []
    for group in groups:
        members = platform.rules.get_group_members(ctx, group["name"])
        team_members.extend(members)
    
    return list({m["id"]: m for m in team_members}.values())
```

### In Process Steps

```python
@process
def provision_user(ctx):
    new_user = platform.rules.create_user(
        ctx,
        username=ctx.var("username"),
        email=ctx.var("email"),
        display_name=ctx.var("display_name"),
        user_type="basic"
    )
    platform.rules.add_user_to_group(ctx, new_user["id"], "sales")
    ctx.var("new_user_id", new_user["id"])
```

### In Web API Handlers

```python
@web_api(method="GET", path="/api/me", auth_required=True)
def get_me(ctx):
    user = platform.rules.get_current_user(ctx)
    groups = platform.rules.get_user_groups(ctx)
    return {"user": user, "groups": groups}
```

---

## Security

- All platform rules go through the same auto-import security layer
- User management rules (`create_user`, `update_user`, `add_user_to_group`, `remove_user_from_group`, `reset_password`, `deactivate_user`, `deactivate_group`) require `system_admin` group or explicit `admin` permission
- Read-only rules (`get_current_user`, `get_user`, `get_user_groups`, `get_group_members`) available to all authenticated users
- `change_password` is self-service — any authenticated user can change their own password (requires `old_password` verification)
- **No hard deletes:** Users and groups are never physically deleted. Use `deactivate_user` / `deactivate_group` for removal. Deactivated entities retain audit history and can be reactivated by `system_admin`.
- All platform rule invocations are logged to `logs/rules/`

---

## File Location

```
appos/
├── platform_rules/
│   ├── __init__.py          # Registers all platform rules
│   ├── user_rules.py        # get_current_user, get_user, create_user, update_user, change_password, reset_password, deactivate_user
│   └── group_rules.py       # get_user_groups, get_group_members, create_group, add_user_to_group, remove_user_from_group, deactivate_group
```

---

*Reference document — see `AppOS_Design.md` §5.8 and §15 for integration context.*
