"""
Integration tests — Cross-module workflows.

These tests verify that multiple AppOS subsystems work together correctly.
They use mocked infrastructure where possible but test real data flow.
"""

import json
import pytest
from pathlib import Path
from unittest.mock import MagicMock, patch

from appos.engine.config import PlatformConfig, load_platform_config, load_app_config
from appos.engine.context import (
    ExecutionContext,
    ProcessContext,
    set_execution_context,
    get_execution_context,
    clear_execution_context,
    resolve_translation,
)
from appos.engine.dependency import DependencyGraph
from appos.engine.registry import ObjectRegistryManager, RegisteredObject
from appos.engine.errors import AppOSSecurityError, AppOSObjectNotFoundError
from appos.engine.environment import EnvironmentResolver
from appos.decorators.record import RecordEventManager
from appos.process.scheduler import EventTriggerRegistry, ScheduleTriggerRegistry


@pytest.mark.integration
class TestConfigToEnvironmentFlow:
    """Test loading config and resolving environment overrides."""

    def test_load_and_resolve(self, integration_project, monkeypatch):
        monkeypatch.chdir(integration_project)

        # Load platform config
        cfg = load_platform_config(str(integration_project / "appos.yaml"))
        assert cfg.environment == "dev"

        # Load app config
        app_cfg = load_app_config("crm", str(integration_project / "apps"))
        assert app_cfg.short_name == "crm"

        # Resolve environment-specific values
        resolver = EnvironmentResolver(environment=cfg.environment)
        cs_config = {
            "default": {"host": "dev-db", "port": 5432},
            "environment_overrides": {
                "prod": {"host": "prod-db-cluster"},
            },
        }
        resolved = resolver.resolve(cs_config)
        assert resolved["host"] == "dev-db"  # dev environment


@pytest.mark.integration
class TestRegistryWithDependencyGraph:
    """Test registry + dependency graph working together."""

    def test_register_scan_and_track_deps(self, integration_project, tmp_path):
        registry = ObjectRegistryManager()
        graph = DependencyGraph(persistence_dir=str(tmp_path / "deps"))

        # Scan app directory
        app_path = integration_project / "apps" / "crm"
        count = registry.scan_app_directory("crm", app_path)
        assert count >= 3  # rule + constant + record + translation

        # Verify objects registered
        assert registry.contains("crm.rules.calculate_discount")
        assert registry.contains("crm.constants.tax_rate")
        assert registry.contains("crm.records.customer")

        # Simulate dependency tracking (as auto-import would do)
        graph.add_dependency("crm.rules.calculate_discount", "crm.constants.tax_rate", "read")
        graph.add_dependency("crm.processes.onboard", "crm.rules.calculate_discount", "execute")

        # Impact analysis
        impact = graph.impact_analysis("crm.constants.tax_rate")
        assert impact["total_impact"] >= 1
        assert "crm.rules.calculate_discount" in impact["transitive_dependents"]

        # Persist and reload
        graph.persist_all()
        graph2 = DependencyGraph(persistence_dir=str(tmp_path / "deps"))
        loaded = graph2.load()
        assert loaded >= 1
        assert graph2.has_dependency("crm.rules.calculate_discount", "crm.constants.tax_rate")


@pytest.mark.integration
class TestContextThroughProcess:
    """Test execution context flowing through process steps."""

    def setup_method(self):
        clear_execution_context()

    def teardown_method(self):
        clear_execution_context()

    def test_context_to_process_flow(self):
        # Set up execution context (as auth middleware would)
        ctx = ExecutionContext(
            user_id=1,
            username="alice",
            user_type="basic",
            user_groups={"crm_users"},
            app_name="crm",
            preferred_language="fr",
        )
        set_execution_context(ctx)

        # Create process context (as ProcessExecutor would)
        pc = ProcessContext(
            instance_id="pi_001",
            inputs={"customer_id": 42, "amount": 100.0},
        )

        # Step 1: Read input, compute, set variable
        customer_id = pc.input("customer_id")
        assert customer_id == 42

        pc.var("discount", 10.0)
        assert pc.var("discount") == 10.0
        assert pc.is_dirty is True

        # Step 2: Set sensitive variable
        pc.var("internal_score", 95, logged=False)
        assert pc.visibility["internal_score"] == "hidden"

        # Step 3: Produce output
        pc.output("final_amount", 90.0)

        # Verify outputs only include logged variables
        outputs = pc.outputs()
        assert "discount" in outputs
        assert "final_amount" in outputs
        assert "internal_score" not in outputs

        # Verify context is still available
        assert get_execution_context().preferred_language == "fr"


@pytest.mark.integration
class TestEventTriggerChain:
    """Test event → trigger → process start chain."""

    def test_record_event_triggers_process(self):
        # Set up event triggers
        event_reg = EventTriggerRegistry()
        event_reg.register("customer.created", "crm.processes.onboard_customer")
        event_reg.register("customer.created", "crm.processes.send_welcome_email")

        # Simulate record creation event
        triggers = event_reg.get_triggers("customer.created")
        assert len(triggers) == 2

        process_refs = [t[0] for t in triggers]
        assert "crm.processes.onboard_customer" in process_refs
        assert "crm.processes.send_welcome_email" in process_refs

    def test_schedule_trigger_registration(self):
        sched_reg = ScheduleTriggerRegistry()
        sched_reg.register("crm.processes.nightly_cleanup", "0 2 * * *")
        sched_reg.register("crm.processes.weekly_report", "0 8 * * 1", enabled=True)
        sched_reg.register("crm.processes.disabled_job", "0 0 * * *", enabled=False)

        enabled = sched_reg.get_enabled_schedules()
        assert len(enabled) == 2  # nightly + weekly (not disabled)


@pytest.mark.integration
class TestRecordEventHooks:
    """Test record lifecycle hooks flowing to rules."""

    def test_register_and_fire_hooks(self):
        mgr = RecordEventManager()

        # Register hooks (as @record decorator would)
        mgr.register_hook("crm.records.customer", "on_create", "crm.rules.validate_customer")
        mgr.register_hook("crm.records.customer", "on_create", "crm.rules.assign_rep", priority=10)
        mgr.register_hook("crm.records.customer", "on_update", "crm.rules.update_cache")

        # Check registered hooks
        hooks = mgr.get_hooks_for_record("crm.records.customer")
        assert len(hooks) == 3
        assert mgr.hook_count == 3

        # Hooks for on_create should include both rules
        create_hooks = mgr._get_hooks("crm.records.customer", "on_create")
        assert len(create_hooks) == 2


@pytest.mark.integration
class TestTranslationResolution:
    """Test translation resolution through context."""

    def setup_method(self):
        clear_execution_context()

    def teardown_method(self):
        clear_execution_context()

    def test_full_translation_flow(self):
        translations = {
            "welcome": {
                "en": "Welcome, {name}!",
                "fr": "Bienvenue, {name} !",
                "es": "Bienvenido, {name}!",
            },
            "save": {"en": "Save"},
        }

        # No context → defaults to English
        result = resolve_translation(translations, "welcome", name="Alice")
        assert result == "Welcome, Alice!"

        # Set French context
        ctx = ExecutionContext(
            user_id=1, username="u", user_type="basic",
            user_groups=set(), preferred_language="fr",
        )
        set_execution_context(ctx)

        result = resolve_translation(translations, "welcome", name="Alice")
        assert result == "Bienvenue, Alice !"

        # Key without French → fallback to English
        result = resolve_translation(translations, "save")
        assert result == "Save"

        # Missing key → returns key name
        result = resolve_translation(translations, "nonexistent")
        assert result == "nonexistent"


@pytest.mark.integration
class TestDependencyGraphPersistence:
    """Test full persist → load cycle with complex graph."""

    def test_complex_graph_roundtrip(self, tmp_path):
        g = DependencyGraph(persistence_dir=str(tmp_path / "deps"))

        # Build a realistic graph
        g.add_dependency("crm.processes.onboard", "crm.rules.validate", "execute")
        g.add_dependency("crm.processes.onboard", "crm.rules.assign_rep", "execute")
        g.add_dependency("crm.rules.validate", "crm.constants.MAX_LENGTH", "read")
        g.add_dependency("crm.rules.assign_rep", "crm.records.customer", "write")
        g.add_dependency("crm.web_apis.create_customer", "crm.records.customer", "write")
        g.add_dependency("crm.web_apis.create_customer", "crm.rules.validate", "execute")

        # Persist all
        written = g.persist_all()
        assert written >= 4

        # Load into fresh graph
        g2 = DependencyGraph(persistence_dir=str(tmp_path / "deps"))
        loaded = g2.load()
        assert loaded >= 4

        # Verify relationships preserved
        assert g2.has_dependency("crm.processes.onboard", "crm.rules.validate")
        assert g2.has_dependency("crm.rules.validate", "crm.constants.MAX_LENGTH")

        # Impact analysis on fresh graph
        impact = g2.impact_analysis("crm.records.customer")
        assert impact["total_impact"] >= 2

        # Cycle detection
        cycles = g2.detect_cycles()
        assert cycles == []


@pytest.mark.integration
class TestGeneratorPipeline:
    """Test generators discovering and generating from app code."""

    def test_audit_and_api_generation(self, integration_project):
        from appos.generators.audit_generator import AuditGenerator
        from appos.generators.api_generator import ApiGenerator

        app_path = str(integration_project / "apps" / "crm")
        output = str(integration_project / "generated")

        # Run audit generator
        audit_gen = AuditGenerator(app_name="crm", app_path=app_path, output_dir=output)
        audit_count = audit_gen.generate_all()
        # customer.py has audit=True, should generate at least 1
        assert audit_count >= 1

        # Run API generator
        api_gen = ApiGenerator(app_name="crm", app_path=app_path, output_dir=output)
        api_count = api_gen.generate_all()
        # customer.py has generate_api=True, should generate at least 1
        assert api_count >= 1

        # Verify output directory has generated files
        gen_path = Path(output)
        assert gen_path.exists()
        generated = list(gen_path.rglob("*.py"))
        assert len(generated) >= 2
