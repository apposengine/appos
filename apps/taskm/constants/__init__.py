"""
Task Manager — Constants.

Demonstrates all constant patterns from AppOS_Design.md §5.6:
  1. Primitive constant with environment overrides (TASKM_MAX_TASKS_PER_PROJECT)
  2. Simple primitive constant (TASKM_PAGE_SIZE, with validator)
  3. Object reference constant pointing to an expression rule (DEFAULT_SCORING_RULE)
  4. Object reference constant pointing to a process (DEFAULT_LIFECYCLE_PROCESS)
  5. Boolean constant (ENABLE_NOTIFICATIONS)
  6. String constant (DEFAULT_PRIORITY)

Security: inherits from app.yaml → security.defaults.logic
"""
import appos  # noqa: F401 — auto-injects decorators into builtins


# ---------------------------------------------------------------------------
# 1. Primitive with environment overrides — integer
# ---------------------------------------------------------------------------

@constant
def TASKM_MAX_TASKS_PER_PROJECT() -> int:
    """Maximum number of active tasks allowed per project.
    Lower in dev for easier testing, higher in prod."""
    return {
        "default": 100,
        "dev": 20,
        "staging": 100,
        "prod": 500,
    }


# ---------------------------------------------------------------------------
# 2. Primitive with validator — integer
# ---------------------------------------------------------------------------

@constant(validate=lambda x: isinstance(x, int) and x > 0)
def TASKM_PAGE_SIZE() -> int:
    """Default pagination page size. Must be a positive integer."""
    return 25


# ---------------------------------------------------------------------------
# 3. Object reference constant → expression rule (dynamic dispatch)
# ---------------------------------------------------------------------------

@constant
def DEFAULT_SCORING_RULE() -> str:
    """Points to the expression rule used for task priority scoring.
    Swappable per environment — simple scoring in dev, full model in prod."""
    return {
        "default": "taskm.rules.score_task_priority",
        "dev": "taskm.rules.score_task_priority",
        "prod": "taskm.rules.score_task_priority",
    }


# ---------------------------------------------------------------------------
# 4. Object reference constant → process (dynamic dispatch)
# ---------------------------------------------------------------------------

@constant
def DEFAULT_LIFECYCLE_PROCESS() -> str:
    """Points to the process that handles the full task lifecycle.
    Can be swapped without code deployment via admin console."""
    return {
        "default": "taskm.processes.task_lifecycle",
        "dev": "taskm.processes.task_lifecycle",
        "prod": "taskm.processes.task_lifecycle",
    }


# ---------------------------------------------------------------------------
# 5. Boolean constant with environment override
# ---------------------------------------------------------------------------

@constant
def ENABLE_NOTIFICATIONS() -> bool:
    """Whether to send external notifications (via integration).
    Disabled in dev to avoid noise."""
    return {
        "default": True,
        "dev": False,
        "staging": True,
        "prod": True,
    }


# ---------------------------------------------------------------------------
# 6. Simple string constant (no env overrides)
# ---------------------------------------------------------------------------

@constant
def DEFAULT_PRIORITY() -> str:
    """Default priority for new tasks."""
    return "medium"


# ---------------------------------------------------------------------------
# 7. Float constant with environment override
# ---------------------------------------------------------------------------

@constant
def TASKM_OVERDUE_THRESHOLD_HOURS() -> float:
    """Hours past due_date before a task is flagged as critically overdue."""
    return {
        "default": 24.0,
        "dev": 1.0,   # Fast feedback in dev
        "prod": 24.0,
    }
