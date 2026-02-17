"""
Tests for Task Manager app — validates all AppOS object types and features.

Covers:
  1. Records: registration, Meta parsing, field validation, relationships
  2. Constants: env resolution, validators, object refs
  3. Expression Rules: inputs/outputs, scoring, validation, caching
  4. Connected Systems: registration, env overrides, pool config
  5. Integrations: config structure, connected_system ref, retry/error config
  6. Web APIs: registration, auth config, rate limiting, handler mapping
  7. Processes: step structure, parallel, fire_and_forget, variable visibility
  8. Interfaces: component tree, DataTable, Form, Layout
  9. Pages: route, title, interface ref, on_load
  10. Sites: page list, navigation, auth
  11. Translation Sets: multi-lang, fallback, parameterized
  12. External API Server: auth, CRUD, health check
"""

from __future__ import annotations

import pytest
from unittest.mock import MagicMock, patch

from appos.engine.registry import object_registry

# ---------------------------------------------------------------------------
# Module-level imports trigger @decorator registrations once for the session.
# These are read-only lookups so no per-test clearing is needed.
# ---------------------------------------------------------------------------
import apps.taskm.connected_systems  # noqa: F401
import apps.taskm.records            # noqa: F401
import apps.taskm.constants          # noqa: F401
import apps.taskm.rules              # noqa: F401
import apps.taskm.integrations       # noqa: F401
import apps.taskm.web_apis           # noqa: F401
import apps.taskm.processes          # noqa: F401
import apps.taskm.interfaces         # noqa: F401
import apps.taskm.pages              # noqa: F401
import apps.taskm.sites              # noqa: F401
import apps.taskm.translation_sets   # noqa: F401


# ===========================================================================
# 1. Records
# ===========================================================================

class TestRecords:
    """Test @record registration and Meta parsing."""

    def test_project_record_registers(self):
        from apps.taskm.records import Project

        obj = None
        for ref, o in object_registry._objects.items():
            if o.name == "Project" and o.object_type == "record":
                obj = o
                break
        assert obj is not None, "Project record should be registered"
        assert obj.metadata["table_name"] == "projects"
        assert obj.metadata["audit"] is True
        assert obj.metadata["soft_delete"] is True
        assert obj.metadata["display_field"] == "name"
        assert "name" in obj.metadata["search_fields"]
        assert obj.metadata["connected_system"] == "taskm_database"

    def test_project_permissions(self):
        from apps.taskm.records import Project

        obj = _find_obj("Project", "record")
        perms = obj.metadata["permissions"]
        assert "view" in perms
        assert "taskm_admins" in perms["delete"]
        assert "dev_team" in perms["view"]

    def test_project_on_create_hook(self):
        from apps.taskm.records import Project

        obj = _find_obj("Project", "record")
        assert "initialize_project" in obj.metadata["on_create"]

    def test_task_record_registers(self):
        from apps.taskm.records import Task

        obj = _find_obj("Task", "record")
        assert obj is not None
        assert obj.metadata["table_name"] == "tasks"
        assert obj.metadata["audit"] is True

    def test_task_on_update_hook(self):
        from apps.taskm.records import Task

        obj = _find_obj("Task", "record")
        assert "reassess_task_priority" in obj.metadata["on_update"]

    def test_comment_record_no_audit(self):
        from apps.taskm.records import Comment

        obj = _find_obj("Comment", "record")
        assert obj.metadata["audit"] is False
        assert obj.metadata["soft_delete"] is False

    def test_document_record_registers(self):
        from apps.taskm.records import Document

        obj = _find_obj("Document", "record")
        assert obj is not None
        assert obj.metadata["soft_delete"] is True

    def test_document_version_record(self):
        from apps.taskm.records import DocumentVersion

        obj = _find_obj("DocumentVersion", "record")
        assert obj is not None

    def test_folder_record_registers(self):
        from apps.taskm.records import Folder

        obj = _find_obj("Folder", "record")
        assert obj is not None

    def test_all_six_records_registered(self):
        from apps.taskm.records import (
            Project, Task, Comment, Document, DocumentVersion, Folder,
        )

        record_names = {
            o.name for o in object_registry._objects.values()
            if o.object_type == "record"
        }
        expected = {"Project", "Task", "Comment", "Document", "DocumentVersion", "Folder"}
        assert expected.issubset(record_names)

    def test_task_field_constraints(self):
        """Verify Pydantic field validation works on the Task record class."""
        from apps.taskm.records import Task

        # Valid task
        task = Task(
            title="Test task",
            project_id=1,
            status="todo",
            priority="high",
        )
        assert task.title == "Test task"
        assert task.priority == "high"
        assert task.is_active is True

    def test_project_field_defaults(self):
        from apps.taskm.records import Project

        proj = Project(name="Demo", code="DEM", owner_id=1)
        assert proj.status == "planning"
        assert proj.budget == 0.0
        assert proj.is_public is False


# ===========================================================================
# 2. Constants
# ===========================================================================

class TestConstants:
    """Test @constant registration and resolution."""

    def test_max_tasks_registers(self):
        from apps.taskm.constants import TASKM_MAX_TASKS_PER_PROJECT

        obj = _find_obj("TASKM_MAX_TASKS_PER_PROJECT", "constant")
        assert obj is not None

    def test_max_tasks_returns_env_dict(self):
        from apps.taskm.constants import TASKM_MAX_TASKS_PER_PROJECT

        # The decorated function returns the env dict (engine resolves at runtime)
        result = TASKM_MAX_TASKS_PER_PROJECT()
        # It returns the resolved value — since env is not set, returns default
        assert isinstance(result, (int, dict))

    def test_page_size_with_validator(self):
        from apps.taskm.constants import TASKM_PAGE_SIZE

        obj = _find_obj("TASKM_PAGE_SIZE", "constant")
        assert obj is not None
        result = TASKM_PAGE_SIZE()
        assert result == 25

    def test_object_ref_constant_scoring(self):
        from apps.taskm.constants import DEFAULT_SCORING_RULE

        obj = _find_obj("DEFAULT_SCORING_RULE", "constant")
        assert obj is not None

    def test_object_ref_constant_lifecycle(self):
        from apps.taskm.constants import DEFAULT_LIFECYCLE_PROCESS

        obj = _find_obj("DEFAULT_LIFECYCLE_PROCESS", "constant")
        assert obj is not None

    def test_boolean_constant(self):
        from apps.taskm.constants import ENABLE_NOTIFICATIONS

        obj = _find_obj("ENABLE_NOTIFICATIONS", "constant")
        assert obj is not None

    def test_string_constant(self):
        from apps.taskm.constants import DEFAULT_PRIORITY

        result = DEFAULT_PRIORITY()
        assert result == "medium"

    def test_float_constant(self):
        from apps.taskm.constants import TASKM_OVERDUE_THRESHOLD_HOURS

        obj = _find_obj("TASKM_OVERDUE_THRESHOLD_HOURS", "constant")
        assert obj is not None

    def test_all_seven_constants_registered(self):
        from apps.taskm import constants as _  # noqa: F811

        const_names = {
            o.name for o in object_registry._objects.values()
            if o.object_type == "constant"
        }
        expected = {
            "TASKM_MAX_TASKS_PER_PROJECT", "TASKM_PAGE_SIZE",
            "DEFAULT_SCORING_RULE", "DEFAULT_LIFECYCLE_PROCESS",
            "ENABLE_NOTIFICATIONS", "DEFAULT_PRIORITY",
            "TASKM_OVERDUE_THRESHOLD_HOURS",
        }
        assert expected.issubset(const_names)


# ===========================================================================
# 3. Expression Rules
# ===========================================================================

class TestExpressionRules:
    """Test @expression_rule registration and execution."""

    def test_score_task_priority_registers(self):
        from apps.taskm.rules import score_task_priority

        obj = _find_obj("score_task_priority", "expression_rule")
        assert obj is not None
        assert obj.metadata["cacheable"] is True
        assert obj.metadata["cache_ttl"] == 120
        assert "task_id" in obj.metadata["inputs"]
        assert "score" in obj.metadata["outputs"]

    def test_score_task_priority_execution(self):
        """Execute the scoring rule directly with a mock context."""
        from apps.taskm.rules import score_task_priority
        from appos.engine.context import RuleContext

        ctx = RuleContext(inputs={
            "task_id": 1,
            "priority": "critical",
            "is_overdue": True,
            "days_until_due": None,
            "has_assignee": True,
        })
        result = score_task_priority(ctx)
        assert "score" in result
        assert "urgency_label" in result
        assert result["score"] == 100  # 85 (critical) + 15 (overdue) = 100 (capped)
        assert result["urgency_label"] == "critical"

    def test_score_low_priority(self):
        from apps.taskm.rules import score_task_priority
        from appos.engine.context import RuleContext

        ctx = RuleContext(inputs={
            "task_id": 2,
            "priority": "low",
            "is_overdue": False,
            "days_until_due": 10,
            "has_assignee": False,
        })
        result = score_task_priority(ctx)
        assert result["score"] == 5  # 10 (low) - 5 (no assignee) = 5
        assert result["urgency_label"] == "low"

    def test_get_overdue_tasks_registers(self):
        from apps.taskm.rules import get_overdue_tasks

        obj = _find_obj("get_overdue_tasks", "expression_rule")
        assert obj is not None
        assert "project_id" in obj.metadata["inputs"]

    def test_reassess_task_priority_registers(self):
        from apps.taskm.rules import reassess_task_priority

        obj = _find_obj("reassess_task_priority", "expression_rule")
        assert "constants.DEFAULT_SCORING_RULE" in obj.metadata["depends_on"]

    def test_reassess_skips_irrelevant_changes(self):
        from apps.taskm.rules import reassess_task_priority
        from appos.engine.context import RuleContext

        ctx = RuleContext(inputs={
            "task_id": 1,
            "changes": {"description": "Updated desc"},  # Not a scoring field
        })
        result = reassess_task_priority(ctx)
        assert result["new_score"] is None
        assert result["notification_sent"] is False

    def test_initialize_project_registers(self):
        from apps.taskm.rules import initialize_project

        obj = _find_obj("initialize_project", "expression_rule")
        assert obj is not None

    def test_get_project_stats_registers(self):
        from apps.taskm.rules import get_project_stats

        obj = _find_obj("get_project_stats", "expression_rule")
        assert obj.metadata["cacheable"] is True
        assert "total_tasks" in obj.metadata["outputs"]

    def test_get_project_stats_execution(self):
        from apps.taskm.rules import get_project_stats
        from appos.engine.context import RuleContext

        ctx = RuleContext(inputs={"project_id": 1})
        result = get_project_stats(ctx)
        assert result["total_tasks"] == 12
        assert result["completion_pct"] == 41.7

    def test_validate_task_valid(self):
        from apps.taskm.rules import validate_task
        from appos.engine.context import RuleContext

        ctx = RuleContext(inputs={
            "title": "My Task",
            "priority": "high",
            "project_id": 1,
        })
        result = validate_task(ctx)
        assert result["is_valid"] is True
        assert result["errors"] == []

    def test_validate_task_invalid(self):
        from apps.taskm.rules import validate_task
        from appos.engine.context import RuleContext

        ctx = RuleContext(inputs={
            "title": "",
            "priority": "invalid_level",
            "project_id": None,
        })
        result = validate_task(ctx)
        assert result["is_valid"] is False
        assert len(result["errors"]) == 3

    def test_all_six_rules_registered(self):
        from apps.taskm import rules as _  # noqa: F811

        rule_names = {
            o.name for o in object_registry._objects.values()
            if o.object_type == "expression_rule"
        }
        expected = {
            "score_task_priority", "get_overdue_tasks",
            "reassess_task_priority", "initialize_project",
            "get_project_stats", "validate_task",
        }
        assert expected.issubset(rule_names)


# ===========================================================================
# 4. Connected Systems
# ===========================================================================

class TestConnectedSystems:
    """Test @connected_system registration."""

    def test_taskm_database_registers(self):
        from apps.taskm.connected_systems import taskm_database

        obj = _find_obj("taskm_database", "connected_system")
        assert obj is not None
        assert obj.metadata["type"] == "database"

    def test_taskm_database_config(self):
        from apps.taskm.connected_systems import taskm_database

        config = taskm_database()
        assert config["default"]["driver"] == "postgresql"
        assert config["default"]["pool_size"] == 5
        assert config["default"]["pool_pre_ping"] is True
        assert config["default"]["pool_reset_on_return"] == "rollback"

    def test_taskm_database_env_overrides(self):
        from apps.taskm.connected_systems import taskm_database

        config = taskm_database()
        assert "staging" in config["environment_overrides"]
        assert "prod" in config["environment_overrides"]
        assert config["environment_overrides"]["prod"]["pool_size"] == 25

    def test_notification_api_registers(self):
        from apps.taskm.connected_systems import notification_api

        obj = _find_obj("notification_api", "connected_system")
        assert obj is not None
        assert obj.metadata["type"] == "rest_api"

    def test_notification_api_config(self):
        from apps.taskm.connected_systems import notification_api

        config = notification_api()
        assert config["default"]["base_url"] == "http://localhost:9100"
        assert config["auth"]["type"] == "api_key"
        assert config["auth"]["header"] == "X-API-Key"

    def test_notification_api_health_check(self):
        from apps.taskm.connected_systems import notification_api

        config = notification_api()
        assert config["health_check"]["enabled"] is True


# ===========================================================================
# 5. Integrations
# ===========================================================================

class TestIntegrations:
    """Test @integration registration."""

    def test_send_notification_registers(self):
        from apps.taskm.integrations import send_task_notification

        obj = _find_obj("send_task_notification", "integration")
        assert obj is not None
        assert obj.metadata["connected_system"] == "notification_api"
        assert obj.metadata["log_payload"] is True

    def test_send_notification_config(self):
        from apps.taskm.integrations import send_task_notification

        config = send_task_notification()
        assert config["method"] == "POST"
        assert config["path"] == "/api/v1/notifications"
        assert "event" in config["body"]
        assert "notification_id" in config["response_mapping"]
        assert config["retry"]["count"] == 3
        assert config["retry"]["backoff"] == "exponential"

    def test_send_notification_error_handling(self):
        from apps.taskm.integrations import send_task_notification

        config = send_task_notification()
        assert config["error_handling"]["400"] == "fail"
        assert config["error_handling"]["429"] == "retry"
        assert config["error_handling"]["5xx"] == "retry"

    def test_fetch_status_registers(self):
        from apps.taskm.integrations import fetch_notification_status

        obj = _find_obj("fetch_notification_status", "integration")
        assert obj is not None
        assert obj.metadata["log_payload"] is False

    def test_fetch_status_config(self):
        from apps.taskm.integrations import fetch_notification_status

        config = fetch_notification_status()
        assert config["method"] == "GET"
        assert "{notification_id}" in config["path"]


# ===========================================================================
# 6. Web APIs
# ===========================================================================

class TestWebAPIs:
    """Test @web_api registration."""

    def test_get_task_api_registers(self):
        from apps.taskm.web_apis import get_task

        obj = _find_obj("get_task", "web_api")
        assert obj is not None
        assert obj.metadata["method"] == "GET"
        assert "/tasks/{task_id}" in obj.metadata["path"]
        assert obj.metadata["auth"]["type"] == "api_key"
        assert obj.metadata["version"] == "v1"

    def test_get_task_rate_limit(self):
        from apps.taskm.web_apis import get_task

        obj = _find_obj("get_task", "web_api")
        assert obj.metadata["rate_limit"]["requests"] == 100
        assert obj.metadata["rate_limit"]["window"] == 60

    def test_create_task_api_registers(self):
        from apps.taskm.web_apis import create_task

        obj = _find_obj("create_task", "web_api")
        assert obj.metadata["method"] == "POST"
        assert obj.metadata["auth"]["type"] == "oauth2"
        assert obj.metadata["log_payload"] is True

    def test_create_task_handler_is_process(self):
        from apps.taskm.web_apis import create_task

        config = create_task()
        assert config["handler"] == "processes.task_lifecycle"

    def test_get_project_stats_api_registers(self):
        from apps.taskm.web_apis import get_project_stats_api

        obj = _find_obj("get_project_stats", "web_api")
        assert obj is not None
        assert "/projects/{project_id}/stats" in obj.metadata["path"]

    def test_webhook_receiver_registers(self):
        from apps.taskm.web_apis import webhook_receiver

        obj = _find_obj("webhook_receiver", "web_api")
        assert obj.metadata["method"] == "POST"
        assert obj.metadata["log_payload"] is True

    def test_all_four_web_apis_registered(self):
        from apps.taskm import web_apis as _  # noqa: F811

        api_names = {
            o.name for o in object_registry._objects.values()
            if o.object_type == "web_api"
        }
        expected = {"get_task", "create_task", "get_project_stats", "webhook_receiver"}
        assert expected.issubset(api_names)


# ===========================================================================
# 7. Processes
# ===========================================================================

class TestProcesses:
    """Test @process registration and step structure."""

    def test_task_lifecycle_registers(self):
        from apps.taskm.processes import task_lifecycle

        obj = _find_obj("task_lifecycle", "process")
        assert obj is not None
        assert obj.metadata["timeout"] == 300
        assert "title" in obj.metadata["inputs"]

    def test_task_lifecycle_permissions(self):
        from apps.taskm.processes import task_lifecycle

        obj = _find_obj("task_lifecycle", "process")
        assert "dev_team" in obj.metadata["permissions"]
        assert "managers" in obj.metadata["permissions"]

    def test_task_lifecycle_display_name(self):
        from apps.taskm.processes import task_lifecycle

        obj = _find_obj("task_lifecycle", "process")
        assert obj.metadata["display_name"] == "Task: {title}"

    def test_task_lifecycle_triggers(self):
        from apps.taskm.processes import task_lifecycle

        obj = _find_obj("task_lifecycle", "process")
        triggers = obj.metadata["triggers"]
        assert len(triggers) >= 1
        assert triggers[0]["type"] == "event"

    def test_task_lifecycle_steps(self):
        """Execute the process function to get the step list."""
        from apps.taskm.processes import task_lifecycle
        from appos.engine.context import ProcessContext

        ctx = ProcessContext(
            instance_id="test_001",
            inputs={
                "title": "Test Task",
                "description": "Test",
                "project_id": 1,
                "priority": "high",
                "assignee_id": 42,
            },
        )
        steps = task_lifecycle(ctx)
        assert isinstance(steps, list)
        assert len(steps) == 5  # validate, score, init_project, parallel, external_notify

        # Step 1: validate
        assert steps[0]["name"] == "validate"
        assert steps[0]["rule"] == "validate_task"
        assert steps[0]["on_error"] == "fail"

        # Step 2: score (conditional)
        assert steps[1]["name"] == "score"
        assert steps[1]["condition"] == "ctx.var.is_valid"
        assert steps[1]["retry_count"] == 2

        # Step 3: init_project
        assert steps[2]["name"] == "init_project"
        assert steps[2]["on_error"] == "skip"

        # Step 4: parallel group
        assert steps[3]["type"] == "parallel"
        assert len(steps[3]["steps"]) == 2

        # Step 5: fire_and_forget
        assert steps[4]["fire_and_forget"] is True

    def test_process_variable_visibility(self):
        """Verify process variables have correct visibility flags."""
        from apps.taskm.processes import task_lifecycle
        from appos.engine.context import ProcessContext

        ctx = ProcessContext(
            instance_id="test_002",
            inputs={"title": "T", "description": "D", "project_id": 1,
                    "priority": "low", "assignee_id": 1},
        )
        task_lifecycle(ctx)

        # logged=True (default)
        assert ctx.visibility.get("title") == "logged"
        # logged=False
        assert ctx.visibility.get("internal_trace_id") == "hidden"
        # sensitive=True
        assert ctx.visibility.get("api_token_snapshot") == "sensitive"

    def test_daily_overdue_check_registers(self):
        from apps.taskm.processes import daily_overdue_check

        obj = _find_obj("daily_overdue_check", "process")
        assert obj is not None
        triggers = obj.metadata["triggers"]
        assert any(t.get("type") == "schedule" for t in triggers)


# ===========================================================================
# 8. Interfaces
# ===========================================================================

class TestInterfaces:
    """Test @interface registration and component tree."""

    def test_task_list_registers(self):
        from apps.taskm.interfaces import task_list

        obj = _find_obj("TaskList", "interface")
        assert obj is not None
        assert obj.metadata["record"] == "Task"
        assert obj.metadata["type"] == "list"

    def test_task_list_components(self):
        from apps.taskm.interfaces import task_list

        tree = task_list()
        assert tree["_component"] == "DataTable"
        assert tree["searchable"] is True
        assert tree["filterable"] is True
        assert "title" in tree["columns"]

    def test_task_dashboard_registers(self):
        from apps.taskm.interfaces import task_dashboard

        obj = _find_obj("TaskDashboard", "interface")
        assert obj is not None
        assert obj.metadata["type"] == "custom"

    def test_task_dashboard_layout(self):
        from apps.taskm.interfaces import task_dashboard

        tree = task_dashboard()
        assert tree["_component"] == "Layout"
        assert len(tree["children"]) == 2  # Two rows

    def test_task_create_form_registers(self):
        from apps.taskm.interfaces import task_create_form

        obj = _find_obj("TaskCreateForm", "interface")
        assert obj is not None
        assert obj.metadata["type"] == "create"

    def test_task_create_form_fields(self):
        from apps.taskm.interfaces import task_create_form

        tree = task_create_form()
        assert tree["_component"] == "Form"
        fields = tree["fields"]
        field_names = [f["name"] for f in fields]
        assert "title" in field_names
        assert "priority" in field_names
        assert "tags" in field_names


# ===========================================================================
# 9. Pages
# ===========================================================================

class TestPages:
    """Test @page registration."""

    def test_dashboard_page_registers(self):
        from apps.taskm.pages import dashboard_page

        obj = _find_obj("dashboard_page", "page")
        assert obj is not None
        assert obj.metadata["route"] == "/dashboard"
        assert obj.metadata["title"] == "Task Dashboard"
        assert obj.metadata["interface"] == "TaskDashboard"
        assert obj.metadata["on_load"] == "rules.get_project_stats"

    def test_tasks_page_registers(self):
        from apps.taskm.pages import tasks_page

        obj = _find_obj("tasks_page", "page")
        assert obj.metadata["route"] == "/tasks"
        assert obj.metadata["interface"] == "TaskList"

    def test_task_create_page_registers(self):
        from apps.taskm.pages import task_create_page

        obj = _find_obj("task_create_page", "page")
        assert obj.metadata["route"] == "/tasks/new"

    def test_task_detail_page_dynamic_route(self):
        from apps.taskm.pages import task_detail_page

        obj = _find_obj("task_detail_page", "page")
        assert "/tasks/detail" in obj.metadata["route"]


# ===========================================================================
# 10. Sites
# ===========================================================================

class TestSites:
    """Test @site registration."""

    def test_site_registers(self):
        from apps.taskm.sites import taskm_site

        obj = _find_obj("TaskManager", "site")
        assert obj is not None

    def test_site_config(self):
        from apps.taskm.sites import taskm_site

        config = taskm_site()
        assert "dashboard_page" in config["pages"]
        assert config["auth_required"] is True
        assert config["default_page"] == "/dashboard"

    def test_site_navigation(self):
        from apps.taskm.sites import taskm_site

        config = taskm_site()
        nav = config["navigation"]
        assert len(nav) == 3
        routes = [n["route"] for n in nav]
        assert "/dashboard" in routes
        assert "/tasks" in routes


# ===========================================================================
# 11. Translation Sets
# ===========================================================================

class TestTranslationSets:
    """Test @translation_set registration and resolution."""

    def test_translation_set_registers(self):
        from apps.taskm.translation_sets import taskm_translations

        obj = _find_obj("taskm_labels", "translation_set")
        assert obj is not None
        assert obj.metadata["app"] == "taskm"

    def test_translations_data(self):
        from apps.taskm.translation_sets import taskm_translations

        data = taskm_translations()
        assert "task_title" in data
        assert "en" in data["task_title"]
        assert "fr" in data["task_title"]
        assert "es" in data["task_title"]

    def test_translation_get_english(self):
        """Test .get() method resolves English by default."""
        from apps.taskm.translation_sets import taskm_translations

        result = taskm_translations.get("task_title", lang="en")
        assert result == "Task Title"

    def test_translation_get_french(self):
        from apps.taskm.translation_sets import taskm_translations

        result = taskm_translations.get("task_title", lang="fr")
        assert result == "Titre de la Tâche"

    def test_translation_get_spanish(self):
        from apps.taskm.translation_sets import taskm_translations

        result = taskm_translations.get("task_title", lang="es")
        assert result == "Título de Tarea"

    def test_translation_parameterized(self):
        from apps.taskm.translation_sets import taskm_translations

        result = taskm_translations.get("welcome_msg", lang="en", name="Alice")
        assert result == "Welcome, Alice!"

    def test_translation_parameterized_french(self):
        from apps.taskm.translation_sets import taskm_translations

        result = taskm_translations.get("welcome_msg", lang="fr", name="Alice")
        assert result == "Bienvenue, Alice !"

    def test_translation_fallback_to_en(self):
        """Unknown language falls back to English."""
        from apps.taskm.translation_sets import taskm_translations

        result = taskm_translations.get("task_title", lang="ja")
        assert result == "Task Title"  # Falls back to "en"

    def test_translation_missing_key_returns_key(self):
        from apps.taskm.translation_sets import taskm_translations

        result = taskm_translations.get("nonexistent_key", lang="en")
        assert result == "nonexistent_key"

    def test_translation_ref(self):
        """Test .ref() returns a lazy reference dict."""
        from apps.taskm.translation_sets import taskm_translations

        ref = taskm_translations.ref("task_title")
        assert ref["_type"] == "translation_ref"
        assert ref["set"] == "taskm_labels"
        assert ref["key"] == "task_title"


# ===========================================================================
# 12. External API Server (FastAPI)
# ===========================================================================

class TestExternalAPIServer:
    """Test the standalone notification API server."""

    @pytest.fixture
    def client(self):
        from fastapi.testclient import TestClient
        from apps.taskm.external_api_server import app
        return TestClient(app)

    def test_health_check_no_auth(self, client):
        """Health check should work without API key."""
        resp = client.get("/health")
        assert resp.status_code == 200
        data = resp.json()
        assert data["status"] == "healthy"
        assert "version" in data

    def test_create_notification_requires_auth(self, client):
        """POST without API key should return 401."""
        resp = client.post("/api/v1/notifications", json={
            "event": "test",
            "message": "Hello",
        })
        assert resp.status_code == 401

    def test_create_notification_invalid_key(self, client):
        """POST with wrong API key should return 401."""
        resp = client.post(
            "/api/v1/notifications",
            json={"event": "test", "message": "Hello"},
            headers={"X-API-Key": "wrong_key"},
        )
        assert resp.status_code == 401

    def test_create_notification_success(self, client):
        """POST with valid API key creates notification."""
        resp = client.post(
            "/api/v1/notifications",
            json={
                "event": "task_created",
                "task_id": "42",
                "task_title": "Fix bug",
                "project": "Demo",
                "assignee": "Alice",
                "message": "New task created",
                "severity": "info",
            },
            headers={"X-API-Key": "taskm_key_001"},
        )
        assert resp.status_code == 201
        data = resp.json()
        assert data["status"] == "delivered"
        assert data["event"] == "task_created"
        assert "id" in data

    def test_get_notification(self, client):
        """Create and then retrieve a notification."""
        # Create
        create_resp = client.post(
            "/api/v1/notifications",
            json={"event": "test_get", "message": "Retrieve me"},
            headers={"X-API-Key": "taskm_key_001"},
        )
        notif_id = create_resp.json()["id"]

        # Get
        get_resp = client.get(
            f"/api/v1/notifications/{notif_id}",
            headers={"X-API-Key": "taskm_key_001"},
        )
        assert get_resp.status_code == 200
        assert get_resp.json()["id"] == notif_id

    def test_get_nonexistent_notification(self, client):
        resp = client.get(
            "/api/v1/notifications/notif_doesntexist",
            headers={"X-API-Key": "taskm_key_001"},
        )
        assert resp.status_code == 404

    def test_list_notifications(self, client):
        resp = client.get(
            "/api/v1/notifications",
            headers={"X-API-Key": "taskm_key_001"},
        )
        assert resp.status_code == 200
        assert "notifications" in resp.json()

    def test_delete_notification(self, client):
        # Create
        create_resp = client.post(
            "/api/v1/notifications",
            json={"event": "test_delete", "message": "Delete me"},
            headers={"X-API-Key": "taskm_key_001"},
        )
        notif_id = create_resp.json()["id"]

        # Delete
        del_resp = client.delete(
            f"/api/v1/notifications/{notif_id}",
            headers={"X-API-Key": "taskm_key_001"},
        )
        assert del_resp.status_code == 200
        assert del_resp.json()["deleted"] is True

    def test_api_key_constant_time_comparison(self, client):
        """Verify the server uses HMAC compare for API keys (timing-safe)."""
        # This is a structural test — make sure the endpoint handler uses hmac.compare_digest
        import inspect
        from apps.taskm.external_api_server import verify_api_key

        source = inspect.getsource(verify_api_key)
        assert "hmac.compare_digest" in source


# ===========================================================================
# Helpers
# ===========================================================================

def _find_obj(name: str, obj_type: str):
    """Find a registered object by name and type."""
    for ref, obj in object_registry._objects.items():
        if obj.name == name and obj.object_type == obj_type:
            return obj
    return None
