"""
AppOS — Python Low-Code Platform Engine
Version: 2.1

Auto-injects all decorators into Python builtins so that app developers
never need to write ``from appos.decorators.core import …``.

After ``import appos`` (or after the platform boots), the following names
are available globally in every module without any import:

    @record, @expression_rule, @process, @step, @parallel, @event,
    @schedule, @integration, @web_api, @interface, @page, @site,
    @constant, @translation_set, @connected_system,
    has_many, belongs_to, has_one

Design ref: AppOS_Design.md §4 — Zero-Import Architecture
"""

__version__ = "2.1.0"
__all__ = ["engine", "decorators", "db", "admin", "ui", "generators", "process"]


def _inject_decorators_into_builtins() -> None:
    """
    Push every public decorator from ``appos.decorators`` into Python's
    ``builtins`` module so they are available in *all* modules without an
    explicit import.

    Safe to call multiple times — skips if already injected.
    """
    import builtins

    if getattr(builtins, "_appos_decorators_injected", False):
        return

    from appos.decorators import (  # noqa: F811
        belongs_to,
        connected_system,
        constant,
        event,
        expression_rule,
        has_many,
        has_one,
        integration,
        interface,
        page,
        parallel,
        process,
        record,
        schedule,
        site,
        step,
        translation_set,
        web_api,
    )

    _names = {
        "record": record,
        "expression_rule": expression_rule,
        "process": process,
        "step": step,
        "parallel": parallel,
        "event": event,
        "schedule": schedule,
        "integration": integration,
        "web_api": web_api,
        "interface": interface,
        "page": page,
        "site": site,
        "constant": constant,
        "translation_set": translation_set,
        "connected_system": connected_system,
        "has_many": has_many,
        "belongs_to": belongs_to,
        "has_one": has_one,
    }

    for name, obj in _names.items():
        setattr(builtins, name, obj)

    builtins._appos_decorators_injected = True


# Auto-inject on first import of appos
_inject_decorators_into_builtins()
