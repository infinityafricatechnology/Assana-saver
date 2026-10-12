"""Write tools on tasks: create, update, comment, delete."""

from collections import defaultdict
from typing import Annotated, Any, Literal

from fastmcp import FastMCP
from mcp.types import ToolAnnotations
from pydantic import BaseModel, Field

from .. import formatting
from ..api import InfinityAPI
from ..deps import Deps
from ..project_context import ProjectContext
from ..resolve import find_task

WRITE = ToolAnnotations(readOnlyHint=False, destructiveHint=False, idempotentHint=False, openWorldHint=False)
UPDATE = ToolAnnotations(readOnlyHint=False, destructiveHint=False, idempotentHint=True, openWorldHint=False)
DELETE = ToolAnnotations(readOnlyHint=False, destructiveHint=True, idempotentHint=True, openWorldHint=False)

MAX_BATCH = 100
# The Group keeps three priorities: urgent (Urgent), high (Important), medium (Normal).
Priority = Literal["urgent", "high", "medium"]
DATE_OR_NONE = r"^(\d{4}-\d{2}-\d{2}|none)$"
TaskRef = Annotated[str, Field(description="Task identifier, e.g. IAT-12")]


class NewTask(BaseModel):
    name: str = Field(min_length=1, max_length=255)
    description: str | None = Field(
        None, description="Plain text; blank lines separate paragraphs, lines starting with '- ' make a list"
    )
    section: str | None = Field(None, description="Section name; the project's default section otherwise")
    assignee: str | None = Field(None, description="'me' or a project member's name or email (one person)")
    start_date: str | None = Field(None, pattern=r"^\d{4}-\d{2}-\d{2}$", description="YYYY-MM-DD")
    due_date: str | None = Field(None, pattern=r"^\d{4}-\d{2}-\d{2}$", description="YYYY-MM-DD")
    priority: Priority | None = None
    labels: list[str] | None = Field(None, description="Label names of the project")
    parent: str | None = Field(None, description="Identifier of the parent task, to create a subtask")
    custom_fields: dict[str, Any] | None = Field(
        None,
        description=(
            "Custom field name → value: text, number, 'YYYY-MM-DD', option name, list of option names, "
            "or list of people (names or emails)"
        ),
    )


class TaskChanges(BaseModel):
    task: str = Field(description="Task identifier, e.g. IAT-12")
    name: str | None = Field(None, min_length=1, max_length=255)
    description: str | None = Field(None, description="Replaces the description; plain text as for create_tasks")
    section: str | None = Field(None, description="Move to this section")
    completed: bool | None = Field(None, description="true: mark as done (moves to the done section); false: reopen it")
    assignee: str | None = Field(None, description="'me', a project member's name or email, or 'none' to unassign")
    start_date: str | None = Field(None, pattern=DATE_OR_NONE, description="YYYY-MM-DD, or 'none' to clear")
    due_date: str | None = Field(None, pattern=DATE_OR_NONE, description="YYYY-MM-DD, or 'none' to clear")
    priority: Priority | None = None
    labels: list[str] | None = Field(None, description="Replaces the labels; [] removes them all")
    custom_fields: dict[str, Any] | None = Field(
        None, description="Custom field name → value, as for create_tasks; null clears a value"
    )


def _clear_or(value: str | None) -> str | None:
    return None if value == "none" else value


def _new_task_payload(context: ProjectContext, task: NewTask, parents: dict[str, str]) -> dict:
    payload: dict[str, Any] = {"name": task.name, "state": context.section_id(task.section) if task.section else None}
    if task.description:
        payload["description_html"] = formatting.text_to_html(task.description)
    if task.assignee:
        payload["assignees"] = [context.person_id(task.assignee)]
    if task.labels:
        payload["labels"] = context.label_ids(task.labels)
    if task.parent:
        payload["parent"] = parents[task.parent]
    for key, value in (("start_date", task.start_date), ("target_date", task.due_date), ("priority", task.priority)):
        if value:
            payload[key] = value
    if task.custom_fields:
        payload["custom_fields"] = context.custom_field_values(task.custom_fields)
    return {key: value for key, value in payload.items() if value is not None}


def _changes_payload(context: ProjectContext, issue: dict, changes: TaskChanges) -> dict:
    payload: dict[str, Any] = {"id": issue["id"]}
    if changes.name is not None:
        payload["name"] = changes.name
    if changes.description is not None:
        payload["description_html"] = formatting.text_to_html(changes.description)
    if changes.section is not None:
        payload["state"] = context.section_id(changes.section)
    if changes.completed is True and not context.is_completed_state(issue.get("state")):
        payload["state"] = context.completed_section_id()
    elif changes.completed is False and context.is_completed_state(issue.get("state")):
        payload["state"] = payload.get("state") or context.open_section_id()
    if changes.assignee is not None:
        payload["assignees"] = [] if changes.assignee == "none" else [context.person_id(changes.assignee)]
    if changes.start_date is not None:
        payload["start_date"] = _clear_or(changes.start_date)
    if changes.due_date is not None:
        payload["target_date"] = _clear_or(changes.due_date)
    if changes.priority is not None:
        payload["priority"] = changes.priority
    if changes.labels is not None:
        payload["labels"] = context.label_ids(changes.labels)
    if changes.custom_fields:
        payload["custom_fields"] = context.custom_field_values(changes.custom_fields)
    return payload


def _summary(deps: Deps, context: ProjectContext, issue: dict) -> dict:
    identifier = f"{context.project['identifier']}-{issue['sequence_id']}"
    return {"identifier": identifier, "name": issue["name"], "url": formatting.task_url(deps.settings, identifier)}


async def _me_id(api: InfinityAPI) -> str:
    return (await api.me())["id"]


def register_write_tools(mcp: FastMCP, deps: Deps) -> None:
    @mcp.tool(annotations=WRITE)
    async def create_tasks(
        project: Annotated[str, Field(description="Project identifier (e.g. IAT), name or id")],
        tasks: Annotated[list[NewTask], Field(min_length=1, max_length=MAX_BATCH)],
    ) -> dict:
        """Create up to 100 tasks in a project in one go, with section, assignee, dates, labels and custom fields.

        All or nothing: if one task is invalid, none is created. Call get_project first for the exact
        names of sections, labels, people and custom field options. Subtasks: set `parent`.
        """
        async with deps.api() as api:
            context = await ProjectContext.load(api, project, await _me_id(api))
            parents = {}
            for reference in {task.parent for task in tasks if task.parent}:
                parent = await find_task(api, reference)
                parents[reference] = parent["id"]
            payload = [_new_task_payload(context, task, parents) for task in tasks]
            created = await api.request(
                "POST", api.workspace_path(f"projects/{context.id}/work-items/bulk/"), json={"work_items": payload}
            )
        return {"created": [_summary(deps, context, issue) for issue in created["work_items"]]}

    @mcp.tool(annotations=UPDATE)
    async def update_tasks(changes: Annotated[list[TaskChanges], Field(min_length=1, max_length=MAX_BATCH)]) -> dict:
        """Change up to 100 tasks at once: name, description, section, completion, assignee, dates, priority,
        labels and custom fields. Only the given fields change.

        Each project's tasks are updated all or nothing.
        """
        updated = []
        async with deps.api() as api:
            me_id = await _me_id(api)
            issues = [(change, await find_task(api, change.task)) for change in changes]
            by_project: dict[str, list] = defaultdict(list)
            for change, issue in issues:
                by_project[issue["project"]].append((change, issue))
            for project_id, items in by_project.items():
                context = await ProjectContext.load(api, project_id, me_id)
                payload = [_changes_payload(context, issue, change) for change, issue in items]
                result = await api.request(
                    "PATCH", api.workspace_path(f"projects/{project_id}/work-items/bulk/"), json={"work_items": payload}
                )
                updated.extend(_summary(deps, context, issue) for issue in result["work_items"])
        return {"updated": updated}

    @mcp.tool(annotations=WRITE)
    async def add_comment(
        task: TaskRef,
        text: Annotated[str, Field(min_length=1, description="Comment text; blank lines separate paragraphs")],
    ) -> dict:
        """Add a comment to a task, as the connected person."""
        async with deps.api() as api:
            issue = await find_task(api, task)
            comment = await api.request(
                "POST",
                api.workspace_path(f"projects/{issue['project']}/work-items/{issue['id']}/comments/"),
                json={"comment_html": formatting.text_to_html(text)},
            )
        return {"comment_id": comment["id"], "task": task.upper()}

    @mcp.tool(annotations=DELETE)
    async def delete_comment(
        task: TaskRef, comment_id: Annotated[str, Field(description="Comment id, as given by get_task")]
    ) -> dict:
        """Delete a comment of a task. Ask the user to confirm first: this cannot be undone."""
        async with deps.api() as api:
            issue = await find_task(api, task)
            await api.request(
                "DELETE",
                api.workspace_path(f"projects/{issue['project']}/work-items/{issue['id']}/comments/{comment_id}/"),
            )
        return {"deleted_comment": comment_id}

    @mcp.tool(annotations=DELETE)
    async def delete_task(task: TaskRef) -> dict:
        """Delete a task. Ask the user to confirm first; prefer completing it (update_tasks completed=true)
        unless they really want it gone. Only project admins and the task's creator can delete it.
        """
        async with deps.api() as api:
            issue = await find_task(api, task)
            await api.request("DELETE", api.workspace_path(f"projects/{issue['project']}/work-items/{issue['id']}/"))
        return {"deleted": task.upper(), "name": issue["name"]}
