"""Prebuilt platform rules for user/group management."""

from appos.platform_rules.user_rules import (  # noqa: F401
    add_user_to_group,
    change_password,
    create_group,
    create_user,
    get_current_user,
    get_group_members,
    get_user,
    get_user_groups,
    remove_user_from_group,
    update_user,
)
