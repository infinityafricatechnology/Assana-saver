# Copyright (c) 2023-present Plane Software, Inc. and contributors
# SPDX-License-Identifier: AGPL-3.0-only
# See the LICENSE file for details.

"""
The steering space (cahier des charges §6), read only: the portfolio the viewer's profile covers
(§10), a version stamp polled for the « temps réel » (§12) and the work item sheet (§6.6).
"""

# Python imports
import hashlib
import json
from typing import Any, Dict, List

# Django imports
from django.db.models import Count, Max

# Third party imports
from rest_framework import status
from rest_framework.response import Response

# Module imports
from plane.app.permissions import ROLE, allow_permission
from plane.db.models import (
    Branch,
    Entity,
    Issue,
    IssueActivity,
    IssueAssignee,
    IssueRelation,
    IssueSteering,
    PriorityRequalification,
    ProjectSteering,
    SteeringReminder,
    SteeringSubmission,
    User,
    Workspace,
)
from plane.utils.steering_dashboard import (
    Portfolio,
    Scope,
    days_late,
    effective_status,
    signal_of,
    today_in_abidjan,
    viewer_scope,
)
from plane.utils.steering_rules import blocked_by_graph, blocking_chain, is_closed

from ..base import BaseAPIView

# The history lines of the sheet (§9.4).
HISTORY_FIELDS = (
    "state",
    "target_date",
    "assignees",
    "priority",
    "blocked_by",
    "blocking",
    "steering",
    "steering_event",
)


def _no_access() -> Response:
    return Response(
        {"error": "You have no steering profile in this workspace.", "code": "no_steering_profile"},
        status=status.HTTP_403_FORBIDDEN,
    )


def dashboard_version(workspace_id) -> str:
    """Changes whenever something the steering space reads changes, so that it reloads within seconds."""
    steered = ProjectSteering.objects.filter(workspace_id=workspace_id).values("project_id")
    stamps: List[Any] = [today_in_abidjan()]
    for queryset in (
        Issue.issue_objects.filter(workspace_id=workspace_id, project_id__in=steered),
        IssueAssignee.objects.filter(workspace_id=workspace_id, project_id__in=steered),
        IssueSteering.objects.filter(workspace_id=workspace_id),
        IssueRelation.objects.filter(workspace_id=workspace_id, relation_type="blocked_by"),
        SteeringSubmission.objects.filter(workspace_id=workspace_id),
        PriorityRequalification.objects.filter(workspace_id=workspace_id),
        SteeringReminder.objects.filter(workspace_id=workspace_id),
        ProjectSteering.objects.filter(workspace_id=workspace_id),
        Entity.objects.filter(workspace_id=workspace_id),
        Branch.objects.filter(workspace_id=workspace_id),
    ):
        totals = queryset.aggregate(count=Count("id"), last=Max("updated_at"))
        stamps += [totals["count"], totals["last"]]
    return hashlib.sha1(json.dumps(stamps, default=str).encode()).hexdigest()[:16]


class SteeringDashboardEndpoint(BaseAPIView):
    """Everything the five tabs read, for the viewer's scope; ``?branch=`` narrows the Synthèse."""

    @allow_permission([ROLE.ADMIN, ROLE.MEMBER, ROLE.GUEST], level="WORKSPACE")
    def get(self, request, slug):
        workspace = Workspace.objects.get(slug=slug)
        scope = viewer_scope(request.user, workspace.id)
        if not scope:
            return _no_access()
        portfolio = Portfolio(workspace.id, scope)
        return Response(
            {
                "generated_at": portfolio.generated_at.isoformat(),
                "today": portfolio.today.isoformat(),
                "version": dashboard_version(workspace.id),
                "viewer": scope.as_payload(),
                **portfolio.referential_payload(),
                "tasks": portfolio.rows,
                "related": portfolio.related,
                "summary": portfolio.summary(request.query_params.get("branch") or None),
                "queue": [row["id"] for row in portfolio.queue()],
                "trend": [],
            },
            status=status.HTTP_200_OK,
        )


class SteeringDashboardVersionEndpoint(BaseAPIView):
    """Polled every few seconds; the screens reload only when the stamp changes (§12 « Temps réel »)."""

    @allow_permission([ROLE.ADMIN, ROLE.MEMBER, ROLE.GUEST], level="WORKSPACE")
    def get(self, request, slug):
        workspace = Workspace.objects.get(slug=slug)
        if not viewer_scope(request.user, workspace.id):
            return _no_access()
        return Response({"version": dashboard_version(workspace.id)}, status=status.HTTP_200_OK)


def _issue_scope(issue: Issue) -> Dict[str, Any]:
    steering = IssueSteering.objects.filter(issue=issue).values("entity_id", "status").first() or {}
    project_entity = ProjectSteering.objects.filter(project_id=issue.project_id).values_list("entity_id", flat=True)
    entity_id = steering.get("entity_id") or (project_entity[0] if project_entity else None)
    branch_id = Entity.objects.filter(pk=entity_id).values_list("branch_id", flat=True).first() if entity_id else None
    return {
        "entity_id": str(entity_id) if entity_id else None,
        "branch_id": str(branch_id) if branch_id else None,
        "steered": bool(project_entity),
    }


def _chain_item(issue: Dict[str, Any], today) -> Dict[str, Any]:
    status_ = effective_status(issue["steering__status"], issue["state__group"] or "")
    is_open = not is_closed(status_, issue["state__group"] or "")
    entity_id = issue["steering__entity_id"] or issue["project__steering__entity_id"]
    return {
        "id": str(issue["id"]),
        "key": f"{issue['project__identifier']}-{issue['sequence_id']}",
        "name": issue["name"],
        "entity_id": str(entity_id) if entity_id else None,
        "status": status_,
        "signal": signal_of(issue["target_date"], today, is_open),
        "days_late": days_late(issue["target_date"], today, is_open),
    }


class SteeringDashboardIssueEndpoint(BaseAPIView):
    """
    The sheet of a work item seen from the steering space (§6.6): the whole blocking chain (§7
    « Chaînes ») and the history (§9.4). The rest of the sheet comes with the dashboard.
    """

    @allow_permission([ROLE.ADMIN, ROLE.MEMBER, ROLE.GUEST], level="WORKSPACE")
    def get(self, request, slug, issue_id):
        workspace = Workspace.objects.get(slug=slug)
        scope: Scope = viewer_scope(request.user, workspace.id)
        if not scope:
            return _no_access()
        issue = Issue.issue_objects.filter(workspace=workspace, pk=issue_id).first()
        where = _issue_scope(issue) if issue else None
        if not issue or not where["steered"] or not scope.covers(where["entity_id"], where["branch_id"]):
            return Response({"error": "Work item not found."}, status=status.HTTP_404_NOT_FOUND)

        today = today_in_abidjan()
        levels = blocking_chain(blocked_by_graph(workspace.id), issue.id)
        ids = [item for level in levels for item in level]
        items = {
            str(item["id"]): _chain_item(item, today)
            for item in Issue.issue_objects.filter(pk__in=ids).values(
                "id",
                "name",
                "sequence_id",
                "target_date",
                "state__group",
                "project__identifier",
                "steering__status",
                "steering__entity_id",
                "project__steering__entity_id",
            )
        }
        for issue_id, name in IssueAssignee.objects.filter(issue_id__in=ids).values_list(
            "issue_id", "assignee__display_name"
        ):
            if str(issue_id) in items:
                items[str(issue_id)].setdefault("assignees", []).append(name)
        chain = [[items[item] for item in level if item in items] for level in levels]

        activities = list(
            IssueActivity.objects.filter(issue=issue, field__in=HISTORY_FIELDS)
            .order_by("created_at")
            .values("id", "field", "verb", "old_value", "new_value", "comment", "actor_id", "created_at")
        )
        actors = {
            str(user["id"]): user["display_name"]
            for user in User.objects.filter(pk__in={a["actor_id"] for a in activities if a["actor_id"]}).values(
                "id", "display_name"
            )
        }
        history = [
            {
                "id": str(activity["id"]),
                "field": activity["field"],
                "verb": activity["verb"],
                "old_value": activity["old_value"],
                "new_value": activity["new_value"],
                "comment": activity["comment"],
                "actor": actors.get(str(activity["actor_id"])) if activity["actor_id"] else None,
                "created_at": activity["created_at"].isoformat(),
            }
            for activity in activities
        ]
        return Response({"chain": chain, "history": history}, status=status.HTTP_200_OK)
