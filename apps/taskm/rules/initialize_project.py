"""Record event hook — initialize a newly created Project."""
import appos  # noqa: F401 — auto-injects decorators into builtins


@expression_rule(
    inputs=["project_id", "project_name", "owner_id"],
    outputs=["initialized"],
    permissions=["managers", "taskm_admins"],
)
def initialize_project(ctx):
    """
    Set up a newly created project: create default folder, initial task, etc.
    Triggered by Project.Meta.on_create = ["initialize_project"].
    """
    project_id = ctx.input("project_id")
    project_name = ctx.input("project_name")
    owner_id = ctx.input("owner_id")

    initialization_result = {
        "project_id": project_id,
        "folder_created": f"{project_name.lower().replace(' ', '_')}_docs",
        "welcome_task_created": True,
        "initialized_by": owner_id,
    }

    ctx.output("initialized", initialization_result)
    return ctx.outputs()
