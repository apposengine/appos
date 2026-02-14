"""Unit tests for appos.engine.context — ExecutionContext, ProcessContext, RuleContext."""

import pytest

from appos.engine.context import (
    ExecutionContext,
    ProcessContext,
    RuleContext,
    clear_execution_context,
    current_execution_context,
    get_execution_context,
    get_preferred_language,
    require_execution_context,
    resolve_translation,
    set_execution_context,
)
from appos.engine.errors import AppOSSecurityError


class TestExecutionContext:
    """Test ExecutionContext creation and properties."""

    def test_basic_creation(self):
        ctx = ExecutionContext(
            user_id=1,
            username="alice",
            user_type="basic",
            user_groups={"crm_users"},
        )
        assert ctx.user_id == 1
        assert ctx.username == "alice"
        assert ctx.user_type == "basic"
        assert "crm_users" in ctx.user_groups
        assert ctx.execution_id.startswith("exec_")
        assert len(ctx.execution_id) == 17  # "exec_" + 12 hex chars

    def test_system_admin_property(self):
        ctx = ExecutionContext(user_id=0, username="admin", user_type="system_admin", user_groups=set())
        assert ctx.is_system_admin is True
        assert ctx.is_service_account is False

    def test_service_account_property(self):
        ctx = ExecutionContext(user_id=99, username="svc", user_type="service_account", user_groups=set())
        assert ctx.is_service_account is True
        assert ctx.is_system_admin is False

    def test_basic_user_properties(self):
        ctx = ExecutionContext(user_id=1, username="u", user_type="basic", user_groups=set())
        assert ctx.is_system_admin is False
        assert ctx.is_service_account is False

    def test_defaults(self):
        ctx = ExecutionContext(user_id=1, username="u", user_type="basic", user_groups=set())
        assert ctx.preferred_language == "en"
        assert ctx.timezone == "UTC"
        assert ctx.full_name == ""
        assert ctx.app_name is None
        assert ctx.session_id is None
        assert ctx.process_instance_id is None
        assert ctx.step_name is None
        assert ctx.dependencies_accessed == []

    def test_to_dict(self):
        ctx = ExecutionContext(
            user_id=1, username="u", user_type="basic",
            user_groups={"b", "a"}, app_name="crm",
        )
        d = ctx.to_dict()
        assert d["user_id"] == 1
        assert d["username"] == "u"
        assert d["user_type"] == "basic"
        assert d["user_groups"] == ["a", "b"]  # sorted
        assert d["app_name"] == "crm"
        assert "execution_id" in d


class TestContextVarHelpers:
    """Test set/get/require/clear context functions."""

    def setup_method(self):
        clear_execution_context()

    def teardown_method(self):
        clear_execution_context()

    def test_set_and_get(self):
        ctx = ExecutionContext(user_id=1, username="u", user_type="basic", user_groups=set())
        set_execution_context(ctx)
        assert get_execution_context() is ctx

    def test_get_returns_none_when_empty(self):
        assert get_execution_context() is None

    def test_require_raises_when_empty(self):
        with pytest.raises(AppOSSecurityError, match="No execution context"):
            require_execution_context()

    def test_require_returns_context(self):
        ctx = ExecutionContext(user_id=1, username="u", user_type="basic", user_groups=set())
        set_execution_context(ctx)
        assert require_execution_context() is ctx

    def test_clear(self):
        ctx = ExecutionContext(user_id=1, username="u", user_type="basic", user_groups=set())
        set_execution_context(ctx)
        clear_execution_context()
        assert get_execution_context() is None


class TestProcessContext:
    """Test ProcessContext variable management."""

    def test_creation(self):
        pc = ProcessContext(instance_id="pi_001")
        assert pc.instance_id == "pi_001"
        assert pc.inputs == {}
        assert pc.variables == {}
        assert pc.is_dirty is False

    def test_set_and_get_variable(self):
        pc = ProcessContext(instance_id="pi_001")
        pc.var("total", 100)
        assert pc.var("total") == 100
        assert pc.is_dirty is True

    def test_get_missing_variable(self):
        pc = ProcessContext(instance_id="pi_001")
        assert pc.var("nonexistent") is None

    def test_input_access(self):
        pc = ProcessContext(instance_id="pi_001", inputs={"customer_id": 42})
        assert pc.input("customer_id") == 42
        assert pc.input("missing") is None

    def test_visibility_logged(self):
        pc = ProcessContext(instance_id="pi_001")
        pc.var("total", 100, logged=True)
        assert pc.visibility["total"] == "logged"

    def test_visibility_hidden(self):
        pc = ProcessContext(instance_id="pi_001")
        pc.var("secret_val", "abc", logged=False)
        assert pc.visibility["secret_val"] == "hidden"

    def test_visibility_sensitive(self):
        pc = ProcessContext(instance_id="pi_001")
        pc.var("password", "p@ss", sensitive=True)
        assert pc.visibility["password"] == "sensitive"

    def test_output_shortcut(self):
        pc = ProcessContext(instance_id="pi_001")
        pc.output("result", 42)
        assert pc.var("result") == 42
        assert pc.visibility["result"] == "logged"

    def test_outputs_filter(self):
        pc = ProcessContext(instance_id="pi_001")
        pc.var("visible", "yes", logged=True)
        pc.var("hidden", "no", logged=False)
        pc.var("secret", "x", sensitive=True)
        outs = pc.outputs()
        assert "visible" in outs
        assert "hidden" not in outs
        assert "secret" not in outs

    def test_mark_clean(self):
        pc = ProcessContext(instance_id="pi_001")
        pc.var("x", 1)
        assert pc.is_dirty is True
        pc.mark_clean()
        assert pc.is_dirty is False

    def test_inputs_immutable(self):
        pc = ProcessContext(instance_id="pi_001", inputs={"a": 1})
        inputs = pc.inputs
        inputs["b"] = 2
        assert "b" not in pc.inputs  # original not mutated


class TestPreferredLanguage:
    """Test get_preferred_language() resolution."""

    def setup_method(self):
        clear_execution_context()

    def teardown_method(self):
        clear_execution_context()

    def test_default_english(self):
        assert get_preferred_language() == "en"

    def test_from_context(self):
        ctx = ExecutionContext(
            user_id=1, username="u", user_type="basic",
            user_groups=set(), preferred_language="fr",
        )
        set_execution_context(ctx)
        assert get_preferred_language() == "fr"


class TestResolveTranslation:
    """Test resolve_translation() with fallback chain."""

    TRANSLATIONS = {
        "greeting": {
            "en": "Hello {name}",
            "fr": "Bonjour {name}",
            "es": "Hola {name}",
        },
        "farewell": {
            "en": "Goodbye",
        },
    }

    def setup_method(self):
        clear_execution_context()

    def teardown_method(self):
        clear_execution_context()

    def test_resolve_explicit_language(self):
        result = resolve_translation(self.TRANSLATIONS, "greeting", lang="fr", name="Alice")
        assert result == "Bonjour Alice"

    def test_resolve_fallback_to_english(self):
        result = resolve_translation(self.TRANSLATIONS, "greeting", lang="de", name="Bob")
        assert result == "Hello Bob"

    def test_resolve_missing_key_returns_key(self):
        result = resolve_translation(self.TRANSLATIONS, "unknown_key")
        assert result == "unknown_key"

    def test_resolve_uses_context_language(self):
        ctx = ExecutionContext(
            user_id=1, username="u", user_type="basic",
            user_groups=set(), preferred_language="es",
        )
        set_execution_context(ctx)
        result = resolve_translation(self.TRANSLATIONS, "greeting", name="Carlos")
        assert result == "Hola Carlos"

    def test_resolve_bad_format_params(self):
        # Should not crash, returns unformatted
        result = resolve_translation(self.TRANSLATIONS, "greeting", lang="en", wrong="x")
        assert "Hello" in result
