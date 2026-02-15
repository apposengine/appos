"""
AppOS Shared Utilities — common helpers used across the platform.

Centralises functions that were previously duplicated in multiple modules.
"""

from __future__ import annotations

import re


def to_snake(name: str) -> str:
    """
    Convert CamelCase (or PascalCase) to snake_case.

    Examples:
        to_snake("CustomerAddress")  → "customer_address"
        to_snake("HTTPSConnection")  → "https_connection"
        to_snake("simpleTest")       → "simple_test"
    """
    s1 = re.sub(r"([A-Z]+)([A-Z][a-z])", r"\1_\2", name)
    return re.sub(r"([a-z0-9])([A-Z])", r"\1_\2", s1).lower()
