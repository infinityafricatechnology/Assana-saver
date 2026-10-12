"""Read tools: projects, tasks, the person's own work and project overviews."""

from collections import Counter
from datetime import timedelta
from typing import Annotated, Literal

from fastmcp import FastMCP
from mcp.types import ToolAnnotations
from pydantic import Field

from .. import formatting
from ..api import InfinityAPI, InfinityAPIError
from ..deps import Deps
from ..resolve import (
    find_people,
    find_project,
    find_task,
    pick,
    project_custom_fields,
    project_labels,
    project_members,
    project_states,
)
from ..resolve import (
    list_projects as fetch_projects,
)

READ_ONLY = ToolAnnotations(readOnlyHint=True, destructiveHint=False, idempotentHint=True, openWorldHint=False)

ProjectRef = Annotated[str, Field(description="Project identifier (e.g. IAT), name or id")]
TaskRef = Annotated[str, Field(description="Task identifier, e.g. IAT-12")]
IsoDate = Annotated[str, Field(description="Date as YYYY-MM-DD", pattern=r"^\d{4}-\d{2}-\d{2}$")]


async def _query_tasks(api: InfinityAPI, deps: Deps, **params) -> tuple[list[dict], bool]:
    items, truncated = await api.all_pages("work-items/", **params)
    return [formatting.compact_task(deps.settings, item) for item in items], truncated


def register_read_tools(mcp: FastMCP, deps: Deps) -> None:
    @mcp.tool(annotations=READ_ONLY)
    async def whoami() -> dict:
        """Who is connected, the organisation, and today's date.

        Call it first when the request depends on "me" or on relative dates ("this week", "overdue").
        """
        async with deps.api() as api:
            me = await api.me()
        return {
            "user": {"id": me["id"], "name": me.get("display_name"), "email": me.get("email")},
            "organisation": deps.settings.workspace_slug,
            "today": deps.today().isoformat(),
        }

    @mcp.tool(annotations=READ_ONLY)
    async def list_projects() -> list[dict]:
        """List the projects the connected person can access, with their identifier and link."""
        async with deps.api() as api:
            projects = await fetch_projects(api)
        return [formatting.compact_project(deps.settings, project) for project in projects]

    @mcp.tool(annotations=READ_ONLY)
    async def get_project(project: ProjectRef) -> dict:
        """Describe a project: its sections (in order), labels, members and custom fields.

        Use it before creating or updating tasks, to know the exact names of sections, labels,
        people and custom field options.
        """
        async with deps.api() as api:
            found = await find_project(api, project)
            states = await project_states(api, found["id"])
            labels = await project_labels(api, found["id"])
            members = await project_members(api, found["id"])
            fields = await project_custom_fields(api, found["id"])
        return {
            **formatting.compact_project(deps.settings, found),
            "sections": [{"id": state["id"], "name": state["name"], "kind": state["group"]} for state in states],
            "labels": [{"id": label["id"], "name": label["name"]} for label in labels],
            "members": [formatting.person(member) for member in members],
            "custom_fields": [formatting.custom_field(field) for field in fields],
        }

    @mcp.tool(annotations=READ_ONLY)
    async def search_tasks(
        project: Annotated[
            list[str] | None, Field(description="Projects (identifier, name or id); all by default")
        ] = None,
        assignee: Annotated[
            str | None, Field(description="'me', 'none', or a person's name or email (needs project)")
        ] = None,
        completed: Annotated[bool | None, Field(description="true: done only, false: open only")] = None,
        due_before: Annotated[IsoDate | None, Field(description="Due on or before this date")] = None,
        due_after: Annotated[IsoDate | None, Field(description="Due on or after this date")] = None,
        section: Annotated[str | None, Field(description="Section name (needs a single project)")] = None,
        label: Annotated[str | None, Field(description="Label name (needs a single project)")] = None,
        priority: Annotated[
            list[Literal["urgent", "high", "medium"]] | None,
            Field(description="Priorities: urgent (Urgent), high (Important), medium (Normal)"),
        ] = None,
        text: Annotated[str | None, Field(description="Words in the task name, or a task number")] = None,
        order_by: Annotated[
            Literal["due_date", "-due_date", "updated", "-updated", "created", "-created"],
            Field(description="Sort order; '-' for most recent / latest first"),
        ] = "due_date",
        limit: Annotated[int, Field(ge=1, le=100, description="Maximum number of tasks")] = 50,
    ) -> dict:
        """Find tasks across projects, by person, completion, due date, section, label, priority or text.

        Returns compact tasks with their identifier and link; use get_task for the details of one.
        """
        async with deps.api() as api:
            projects = [await find_project(api, reference) for reference in project or []]
            project_ids = [found["id"] for found in projects]
            params: dict = {
                "project": ",".join(project_ids) or None,
                "completed": None if completed is None else str(completed).lower(),
                "due_before": due_before,
                "due_after": due_after,
                "priority": ",".join(priority) if priority else None,
                "search": text,
                "order_by": {"due_date": "target_date", "updated": "updated_at", "created": "created_at"}[
                    order_by.lstrip("-")
                ],
                "per_page": limit,
            }
            if order_by.startswith("-"):
                params["order_by"] = f"-{params['order_by']}"
            if assignee in ("me", "none"):
                params["assignee"] = assignee
            elif assignee:
                params["assignee"] = ",".join(await find_people(api, project_ids, [assignee]))
            if section or label:
                if len(project_ids) != 1:
                    raise InfinityAPIError("Filtering by section or label needs exactly one project.")
                if section:
                    params["state"] = pick(await project_states(api, project_ids[0]), section, "section", "name")["id"]
                if label:
                    params["label"] = pick(await project_labels(api, project_ids[0]), label, "label", "name")["id"]
            page = await api.page("work-items/", **params)
        return {
            "tasks": [formatting.compact_task(deps.settings, item) for item in page["results"]],
            "total": page["total"],
            "more_results": page["has_more"],
        }

    @mcp.tool(annotations=READ_ONLY)
    async def my_tasks(
        days_ahead: Annotated[int, Field(ge=0, le=90, description="Include open tasks due within this many days")] = 7,
    ) -> dict:
        """The connected person's open tasks: overdue, due in the coming days, and without a due date."""
        today = deps.today()
        async with deps.api() as api:
            dated, truncated = await _query_tasks(
                api,
                deps,
                assignee="me",
                completed="false",
                due_before=(today + timedelta(days=days_ahead)).isoformat(),
            )
            undated_page = await api.page("work-items/", assignee="me", completed="false", per_page=100)
        undated = [
            formatting.compact_task(deps.settings, item) for item in undated_page["results"] if not item["target_date"]
        ]
        return {
            "today": today.isoformat(),
            "overdue": [task for task in dated if task["due_date"] < today.isoformat()],
            "due_soon": [task for task in dated if task["due_date"] >= today.isoformat()],
            "no_due_date": undated,
            "incomplete_list": truncated or undated_page["has_more"],
        }

    @mcp.tool(annotations=READ_ONLY)
    async def get_task(
        task: TaskRef,
        include_comments: Annotated[bool, Field(description="Include the comments")] = True,
        include_history: Annotated[bool, Field(description="Include the history of changes")] = False,
    ) -> dict:
        """Everything about one task: description, section, people, dates, custom fields, subtasks, comments."""
        async with deps.api() as api:
            issue = await find_task(api, task)
            project_id = issue["project"]
            project = await find_project(api, project_id)
            states = {state["id"]: state for state in await project_states(api, project_id)}
            members = {member["id"]: member.get("display_name") for member in await project_members(api, project_id)}
            fields = {field["id"]: field for field in await project_custom_fields(api, project_id)}
            values = await api.get(f"projects/{project_id}/custom-field-values/", work_item_id=issue["id"])
            subtasks, _ = await api.all_pages("work-items/", parent=issue["id"])
            comments = (
                (await api.all_pages(f"projects/{project_id}/work-items/{issue['id']}/comments/"))[0]
                if include_comments
                else []
            )
            history = (
                (await api.all_pages(f"projects/{project_id}/work-items/{issue['id']}/activities/"))[0]
                if include_history
                else []
            )
            parent = (
                await api.get(f"projects/{project_id}/work-items/{issue['parent']}/") if issue.get("parent") else None
            )

        identifier = f"{project['identifier']}-{issue['sequence_id']}"
        state = states.get(issue.get("state"), {})
        result = {
            "identifier": identifier,
            "name": issue["name"],
            "url": formatting.task_url(deps.settings, identifier),
            "project": project["name"],
            "section": state.get("name"),
            "completed": state.get("group") in formatting.COMPLETED_GROUPS,
            "assignees": [person.get("display_name") for person in issue.get("assignees", [])],
            "start_date": issue.get("start_date"),
            "due_date": issue.get("target_date"),
            "priority": issue.get("priority"),
            "labels": [label.get("name") for label in issue.get("labels", [])],
            "description": formatting.html_to_text(issue.get("description_html")),
            "custom_fields": {
                fields[value["custom_field_id"]]["name"]: formatting.custom_field_value(
                    fields[value["custom_field_id"]], value["value"], members
                )
                for value in values
                if value["custom_field_id"] in fields
            },
            "parent": f"{project['identifier']}-{parent['sequence_id']}" if parent else None,
            "subtasks": [formatting.compact_task(deps.settings, item) for item in subtasks],
            "created_at": issue.get("created_at"),
            "updated_at": issue.get("updated_at"),
        }
        if include_comments:
            result["comments"] = [
                {
                    "id": comment["id"],
                    "author": members.get(comment.get("actor"), comment.get("actor")),
                    "date": comment.get("created_at"),
                    "text": formatting.html_to_text(comment.get("comment_html")),
                }
                for comment in sorted(comments, key=lambda comment: comment.get("created_at") or "")
            ]
        if include_history:
            result["history"] = [
                {
                    "who": members.get(activity.get("actor"), activity.get("actor")),
                    "via": activity.get("via") or None,
                    "date": activity.get("created_at"),
                    "field": activity.get("field"),
                    "from": activity.get("old_value"),
                    "to": activity.get("new_value"),
                    "action": activity.get("verb"),
                }
                for activity in history
            ]
        return result

    @mcp.tool(annotations=READ_ONLY)
    async def project_overview(project: ProjectRef) -> dict:
        """Status of a project: open and done counts, overdue tasks, tasks due this week, workload and sections."""
        today = deps.today()
        week_end = today + timedelta(days=7)
        async with deps.api() as api:
            found = await find_project(api, project)
            tasks, truncated = await _query_tasks(api, deps, project=found["id"])
        open_tasks = [task for task in tasks if not task["completed"]]
        overdue = [task for task in open_tasks if task["due_date"] and task["due_date"] < today.isoformat()]
        due_this_week = [
            task
            for task in open_tasks
            if task["due_date"] and today.isoformat() <= task["due_date"] <= week_end.isoformat()
        ]
        workload = Counter(name for task in open_tasks for name in task["assignees"] or ["(unassigned)"])
        return {
            **formatting.compact_project(deps.settings, found),
            "today": today.isoformat(),
            "open": len(open_tasks),
            "completed": len(tasks) - len(open_tasks),
            "overdue": overdue,
            "due_this_week": due_this_week,
            "open_by_section": dict(Counter(task["section"] for task in open_tasks)),
            "open_by_person": dict(workload.most_common()),
            "incomplete_counts": truncated,
        }
