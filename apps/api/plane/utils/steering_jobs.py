# Copyright (c) 2023-present Plane Software, Inc. and contributors
# SPDX-License-Identifier: AGPL-3.0-only
# See the LICENSE file for details.

"""
The periodic work of the steering space (cahier des charges §9): the alerts that depend on the date,
the lifting of blocks, the weekly reminders and the weekly snapshot. Every alert goes once per work
item, event and key (§9.2), so running a job twice sends nothing twice.
"""

# Python imports
from collections import defaultdict
from datetime import date
from typing import Dict, Iterable, List, Optional

# Module imports
from plane.db.models import (
    Issue,
    IssueAssignee,
    IssueRelation,
    IssueSteering,
    ProjectSteering,
    SteeringSnapshot,
)
from plane.utils.steering_alerts import notify, profile_member_ids
from plane.utils.steering_circuit import CircuitError, remind
from plane.utils.exception_logger import log_exception
from plane.utils.steering_dashboard import RISK_SOON_WITHIN_DAYS, Portfolio, Scope
from plane.utils.steering_rules import CLOSED_STATE_GROUPS, CLOSED_STEERING_STATUSES

DEADLINE_SOON_DAYS = 3  # « Deadline à J-3 »
SUBMISSION_OVERDUE_DAYS = 7  # « Soumission au PDG sans décision depuis 7 jours »


def steered_workspace_ids() -> List:
    return list(ProjectSteering.objects.values_list("workspace_id", flat=True).distinct())


def _issues(ids: Iterable[str]) -> Dict[str, Issue]:
    return {
        str(issue.id): issue
        for issue in Issue.issue_objects.filter(pk__in=list(ids)).select_related("project", "state", "workspace")
    }


def _assignees(ids: Iterable[str]) -> Dict[str, List[str]]:
    assignees: Dict[str, List[str]] = defaultdict(list)
    for issue_id, user_id in IssueAssignee.objects.filter(issue_id__in=list(ids)).values_list(
        "issue_id", "assignee_id"
    ):
        assignees[str(issue_id)].append(str(user_id))
    return assignees


def daily_alerts(workspace_id, today: Optional[date] = None) -> Dict[str, int]:
    """
    §9.2, the alerts that follow the calendar: deadline in 3 days, late (J+1), critical (J+31), a
    blocker late, a submission waiting for 7 days, a risk 7 days from taking effect. Returns how many
    people each event reached.
    """
    portfolio = Portfolio(workspace_id, Scope(whole_group=True), today=today)
    rows = [row for row in portfolio.rows if row["is_open"]]
    blocked_ids = {item for row in rows if row["days_late"] > 0 for item in row["blocking"]}
    issues = _issues({row["id"] for row in rows} | blocked_ids)
    assignees = _assignees(blocked_ids)
    cabinet = profile_member_ids(workspace_id, "cabinet")
    ceo = profile_member_ids(workspace_id, "ceo")
    sent: Dict[str, int] = defaultdict(int)

    def alert(issue_id: str, event: str, recipients: Iterable, key: str, detail: str = "") -> None:
        issue = issues.get(issue_id)
        count = len(notify(issue, event, recipients, detail=detail, key=key)) if issue else 0
        if count:
            sent[event] += count

    for row in rows:
        people = row["assignee_ids"]
        supervisor = [row["supervisor_id"]] if row["supervisor_id"] else []
        deadline = row["target_date"] or ""
        if row["days_left"] == DEADLINE_SOON_DAYS:
            alert(row["id"], "deadline_soon", people, deadline)
        if 1 <= row["days_late"] <= 30:
            alert(row["id"], "late", people + supervisor, deadline, f"J+{row['days_late']}")
        if row["signal"] == "critical":
            alert(row["id"], "critical", people + supervisor + cabinet, deadline, f"J+{row['days_late']}")
        if row["days_late"] > 0:
            for blocked_id in row["blocking"]:
                blocked_people = next(
                    (other["assignee_ids"] for other in rows if other["id"] == blocked_id),
                    assignees.get(blocked_id, []),
                )
                alert(
                    blocked_id, "blocker_late", blocked_people, f"{row['id']}:{deadline}", f"{row['key']} {row['name']}"
                )
        submission = row["submission"]
        if submission and submission["waiting_days"] >= SUBMISSION_OVERDUE_DAYS:
            alert(row["id"], "submission_overdue", cabinet + ceo, submission["id"])
        risk = row["risk"]
        if (
            risk
            and risk["effective_date"]
            and risk["days"] is not None
            and 0 <= risk["days"] <= RISK_SOON_WITHIN_DAYS
            and (row["in_queue"] or row["blocked"] or row["status"] == "waiting")
        ):
            alert(
                row["id"],
                "risk_soon",
                (ceo if row["in_queue"] else []) + cabinet + people,
                risk["effective_date"],
                f"J-{risk['days']}",
            )
    return dict(sent)


def unblock_alerts(workspace_id) -> int:
    """
    §7 « Levée automatique »: when a blocker is closed, the assignees of the work item it blocked are
    alerted, once per blocker. A relation added after its blocker was closed never blocked anyone.
    """
    relations = list(
        IssueRelation.objects.filter(
            workspace_id=workspace_id,
            relation_type="blocked_by",
            issue__deleted_at__isnull=True,
            related_issue__deleted_at__isnull=True,
        ).values_list("issue_id", "related_issue_id", "created_at")
    )
    if not relations:
        return 0
    involved = {str(item) for blocked, blocker, _ in relations for item in (blocked, blocker)}
    issues = _issues(involved)
    steerings = {
        str(steering["issue_id"]): steering
        for steering in IssueSteering.objects.filter(issue_id__in=involved).values("issue_id", "status", "updated_at")
    }

    def closed_at(issue: Issue):
        steering = steerings.get(str(issue.id)) or {}
        if steering.get("status") in CLOSED_STEERING_STATUSES:
            return steering["updated_at"]
        if issue.state_id and issue.state.group in CLOSED_STATE_GROUPS:
            return issue.completed_at or issue.updated_at
        return None

    assignees = _assignees(involved)
    count = 0
    for blocked_id, blocker_id, created_at in relations:
        blocked, blocker = issues.get(str(blocked_id)), issues.get(str(blocker_id))
        if not blocked or not blocker or closed_at(blocked):
            continue
        moment = closed_at(blocker)
        if not moment or moment < created_at:
            continue
        identifier = f"{blocker.project.identifier}-{blocker.sequence_id}"
        count += len(
            notify(
                blocked,
                "unblocked",
                assignees.get(str(blocked_id), []),
                detail=f"{identifier} {blocker.name}",
                key=str(blocker_id),
            )
        )
    return count


def weekly_reminders(workspace_id, today: Optional[date] = None) -> int:
    """§9.1 « Automatique »: every week, the assignees of dormant or inconsistent records are reminded."""
    portfolio = Portfolio(workspace_id, Scope(whole_group=True), today=today)
    rows = [row for row in portfolio.rows if row["dormant"] or row["inconsistencies"]]
    issues = _issues(row["id"] for row in rows)
    count = 0
    for row in rows:
        issue = issues.get(row["id"])
        if not issue:
            continue
        try:
            remind(issue, None, "inconsistent" if row["inconsistencies"] else "dormant")
            count += 1
        except CircuitError:
            continue
    return count


def take_snapshot(workspace_id, today: Optional[date] = None) -> SteeringSnapshot:
    """§9.3: the weekly picture, per entity, frozen on Fridays at noon whatever happens to the report."""
    portfolio = Portfolio(workspace_id, Scope(whole_group=True), today=today)
    entities: Dict[str, Dict[str, int]] = defaultdict(
        lambda: {"open": 0, "late": 0, "critical": 0, "blocked": 0, "queue": 0}
    )
    for row in portfolio.rows:
        if not row["is_open"]:
            continue
        counts = entities[row["entity_id"]]
        counts["open"] += 1
        counts["late"] += row["days_late"] > 0
        counts["critical"] += row["signal"] == "critical"
        counts["blocked"] += row["blocked"]
        counts["queue"] += row["in_queue"]
    snapshot, _ = SteeringSnapshot.objects.update_or_create(
        workspace_id=workspace_id, date=portfolio.today, defaults={"entities": dict(entities)}
    )
    return snapshot


def trend(
    workspace_id,
    scope: Scope,
    entity_branches: Dict[str, Optional[str]],
    branch_id: Optional[str] = None,
    weeks: int = 12,
):
    """§6.1 « Tendance hebdomadaire »: the snapshots summed over the entities the viewer reads."""
    points = []
    for snapshot in SteeringSnapshot.objects.filter(workspace_id=workspace_id).order_by("-date")[:weeks]:
        totals = {"open": 0, "late": 0, "critical": 0, "blocked": 0, "queue": 0}
        for entity_id, counts in snapshot.entities.items():
            entity_branch = entity_branches.get(entity_id)
            if not scope.covers(entity_id, entity_branch) or (branch_id and entity_branch != branch_id):
                continue
            for key in totals:
                totals[key] += counts.get(key, 0)
        points.append({"date": snapshot.date.isoformat(), **totals})
    return list(reversed(points))


def run_for_steered_workspaces(job, *args) -> Dict[str, object]:
    """Runs a job for every workspace that steers projects; one failing workspace does not stop the others."""
    results = {}
    for workspace_id in steered_workspace_ids():
        try:
            results[str(workspace_id)] = job(workspace_id, *args)
        except Exception as error:  # noqa: BLE001 - logged, the other workspaces go on
            log_exception(error)
    return results
