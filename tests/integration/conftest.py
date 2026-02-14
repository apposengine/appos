"""
Integration test fixtures — heavier fixtures requiring DB/Redis/filesystem.
These tests require running infrastructure (PostgreSQL, Redis).
Mark with @pytest.mark.integration to skip in unit-only runs.

Run: pytest tests/integration/ -v -m integration
"""

from __future__ import annotations

import os
import pytest
from pathlib import Path
from unittest.mock import MagicMock, patch


# Custom marker for integration tests
def pytest_configure(config):
    config.addinivalue_line("markers", "integration: requires live infrastructure (DB/Redis)")


@pytest.fixture
def integration_project(tmp_path):
    """
    Create a full AppOS project tree for integration testing.
    Includes sample app with records, rules, processes.
    """
    root = tmp_path / "project"
    root.mkdir()

    # appos.yaml
    (root / "appos.yaml").write_text(
        "platform:\n"
        "  name: IntegrationTestPlatform\n"
        "  version: '2.0.0'\n"
        "environment: dev\n"
        "database:\n"
        "  url: postgresql://test:test@localhost:5432/appos_test\n"
        "redis:\n"
        "  url: redis://localhost:6379/0\n"
        "logging:\n"
        "  directory: " + str(root / ".appos" / "logs") + "\n"
        "apps:\n"
        "  - crm\n",
        encoding="utf-8",
    )

    # Create .appos dirs
    (root / ".appos" / "logs").mkdir(parents=True)
    (root / ".appos" / "runtime" / "dependencies").mkdir(parents=True)

    # apps/crm structure
    crm = root / "apps" / "crm"
    for d in ("records", "rules", "constants", "processes", "steps",
              "integrations", "web_apis", "interfaces", "pages",
              "translation_sets"):
        (crm / d).mkdir(parents=True)
        (crm / d / "__init__.py").write_text("")

    (crm / "__init__.py").write_text("")
    (crm / "app.yaml").write_text(
        "app:\n"
        "  name: CRM App\n"
        "  short_name: crm\n"
        "  version: '1.0.0'\n"
        "  groups:\n"
        "    - crm_users\n"
        "    - crm_admins\n",
        encoding="utf-8",
    )

    # Sample rule
    (crm / "rules" / "calculate_discount.py").write_text(
        "from appos.decorators.core import expression_rule\n\n"
        "@expression_rule(\n"
        "    name='calculate_discount',\n"
        "    inputs={'amount': float, 'tier': str},\n"
        "    outputs={'discount': float},\n"
        ")\n"
        "def calculate_discount(ctx):\n"
        "    amount = ctx.input('amount')\n"
        "    tier = ctx.input('tier')\n"
        "    rate = 0.1 if tier == 'gold' else 0.05\n"
        "    ctx.output('discount', amount * rate)\n",
        encoding="utf-8",
    )

    # Sample constant
    (crm / "constants" / "tax_rate.py").write_text(
        "from appos.decorators.core import constant\n\n"
        "@constant(name='TAX_RATE')\n"
        "def TAX_RATE():\n"
        "    return {'default': 0.08, 'prod': 0.0825}\n",
        encoding="utf-8",
    )

    # Sample record
    (crm / "records" / "customer.py").write_text(
        "from appos.decorators.core import record\n\n"
        "@record\n"
        "class Customer:\n"
        "    class Meta:\n"
        "        table_name = 'customers'\n"
        "        audit = True\n"
        "        soft_delete = True\n"
        "        display_field = 'email'\n"
        "        search_fields = ['first_name', 'last_name', 'email']\n"
        "        generate_api = True\n"
        "    first_name: str\n"
        "    last_name: str\n"
        "    email: str\n"
        "    tier: str = 'standard'\n",
        encoding="utf-8",
    )

    # Sample translation set
    (crm / "translation_sets" / "labels.py").write_text(
        "from appos.decorators.core import translation_set\n\n"
        "@translation_set(name='labels')\n"
        "def labels():\n"
        "    return {\n"
        "        'greeting': {'en': 'Hello', 'fr': 'Bonjour', 'es': 'Hola'},\n"
        "        'farewell': {'en': 'Goodbye', 'fr': 'Au revoir'},\n"
        "    }\n",
        encoding="utf-8",
    )

    return root
