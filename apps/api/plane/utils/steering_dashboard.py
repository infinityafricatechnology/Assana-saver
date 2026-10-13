# Copyright (c) 2023-present Plane Software, Inc. and contributors
# SPDX-License-Identifier: AGPL-3.0-only
# See the LICENSE file for details.

"""
The steering space's reading of the portfolio (cahier des charges §5, §6, §10): every work item of a
steered project with its signals, computed at the date of the day in Africa/Abidjan, and the totals
that the screens, the COMEX export and the weekly report share. Nothing here writes.
"""

# Python imports
from collections import defaultdict
from dataclasses import dataclass, field
from datetime import date, datetime
from typing import Any, Dict, Iterable, List, Optional, Set
from zoneinfo import ZoneInfo

# Django imports
from django.db.models import Count, Max
from django.utils import timezone

# Module imports
from plane.app.permissions import ROLE
from plane.db.models import (
    Branch,
    Entity,
    Issue,
    IssueAssignee,
    IssueSteering,
    PriorityRequalification,
    Project,
    ProjectSteering,
    SteeringCategory,
    SteeringProfile,
    SteeringReminder,
    SteeringSubmission,
    User,
    WorkspaceMember,
)
from plane.utils.steering_rules import CLOSED_STEERING_STATUSES, blocked_by_graph, is_closed

ABIDJAN = ZoneInfo("Africa/Abidjan")
CRITICAL_AFTER_DAYS = 30  # RG-03
SOON_WITHIN_DAYS = 14  # RG-03, §6.1 « échéances à 14 jours »
DORMANT_AFTER_DAYS = 14  # RG-09
RISK_SOON_WITHIN_DAYS = 7  # RG-13
PRIORITY_RANK = {"urgent": 0, "high": 1, "medium": 2}
SIGNAL_RANK = {"critical": 0, "late": 1, "soon": 2, "on_time": 3, "closed": 4}
# Work items without a steering record read their status from their column.
STATE_GROUP_STATUS = {
    "backlog": "to_start",
    "unstarted": "to_start",
    "started": "in_progress",
    "completed": "done",
    "cancelled": "cancelled",
}


# ---------------------------------------------------------------------------------------------------
# Rules (§5)
# ---------------------------------------------------------------------------------------------------


def today_in_abidjan() -> date:
    return timezone.now().astimezone(ABIDJAN).date()


def local_date(moment: Optional[datetime]) -> Optional[date]:
    return moment.astimezone(ABIDJAN).date() if moment else None


def effective_status(steering_status: Optional[str], state_group: str) -> str:
    """The steering status, or what the column says when the work item is closed there or has no record."""
    if steering_status in CLOSED_STEERING_STATUSES:
        return steering_status
    if state_group == "completed":
        return "done"
    if state_group == "cancelled":
        return "cancelled"
    return steering_status or STATE_GROUP_STATUS.get(state_group, "to_start")


def days_late(target_date: Optional[date], today: date, is_open: bool) -> int:
    """RG-02."""
    if not is_open or not target_date:
        return 0
    return max((today - target_date).days, 0)


def signal_of(target_date: Optional[date], today: date, is_open: bool) -> str:
    """RG-03: critical beyond 30 days late, late from 1 to 30, soon when due within 14 days."""
    if not is_open:
        return "closed"
    if not target_date:
        return "on_time"
    late = (today - target_date).days
    if late > CRITICAL_AFTER_DAYS:
        return "critical"
    if late >= 1:
        return "late"
    if late >= -SOON_WITHIN_DAYS:
        return "soon"
    return "on_time"


def inconsistencies(is_open: bool, status: str, progress: int, closure_date, target_date, today: date) -> List[str]:
    """RG-10, at least: 100 % without closure; deadline passed and still « À démarrer »."""
    if not is_open:
        return []
    reasons = []
    if progress >= 100 and not closure_date:
        reasons.append("progress_without_closure")
    if target_date and target_date < today and status == "to_start":
        reasons.append("late_not_started")
    return reasons


def entity_state(critical: int, blocked: int, late: int, queue: int) -> str:
    """RG-14."""
    if critical or blocked:
        return "alert"
    if late or queue:
        return "watch"
    return "ok"


# ---------------------------------------------------------------------------------------------------
# Who sees what (§10)
# ---------------------------------------------------------------------------------------------------


@dataclass
class Scope:
    """The part of the Group a person reads: everything, branches, entities, or a mix of the last two."""

    whole_group: bool = False
    branch_ids: Set[str] = field(default_factory=set)
    entity_ids: Set[str] = field(default_factory=set)
    is_ceo: bool = False
    is_cabinet: bool = False

    def covers(self, entity_id: Optional[str], branch_id: Optional[str]) -> bool:
        return self.whole_group or (branch_id in self.branch_ids) or (entity_id in self.entity_ids)

    def as_payload(self) -> Dict[str, Any]:
        return {
            "whole_group": self.whole_group,
            "branch_ids": sorted(self.branch_ids),
            "entity_ids": sorted(self.entity_ids),
            "is_ceo": self.is_ceo,
            # The CEO holds every right of the Cabinet (§10).
            "can_requalify": self.is_ceo or self.is_cabinet,
            "can_remind": self.is_ceo or self.is_cabinet,
            "can_decide": self.is_ceo,
        }


def viewer_scope(user: User, workspace_id) -> Optional[Scope]:
    """
    CEO, Cabinet and workspace admins read the whole Group; a branch director reads the branch, an
    entity manager the entity. None: the person has no access to the steering space.
    """
    scope = Scope()
    for role, branch_id, entity_id in SteeringProfile.objects.filter(
        workspace_id=workspace_id, member=user
    ).values_list("role", "branch_id", "entity_id"):
        if role == "ceo":
            scope.is_ceo = scope.whole_group = True
        elif role == "cabinet":
            scope.is_cabinet = scope.whole_group = True
        elif role == "branch_director" and branch_id:
            scope.branch_ids.add(str(branch_id))
        elif role == "entity_manager" and entity_id:
            scope.entity_ids.add(str(entity_id))
    if WorkspaceMember.objects.filter(
        workspace_id=workspace_id, member=user, role=ROLE.ADMIN.value, is_active=True
    ).exists():
        scope.whole_group = True
    if not (scope.whole_group or scope.branch_ids or scope.entity_ids):
        return None
    return scope


# ---------------------------------------------------------------------------------------------------
# The portfolio
# ---------------------------------------------------------------------------------------------------


def _iso(value) -> Optional[str]:
    return value.isoformat() if value else None


def _name(person: Dict[str, Any]) -> str:
    full = f"{person.get('first_name') or ''} {person.get('last_name') or ''}".strip()
    return full or person.get("display_name") or person.get("email") or ""


class Portfolio:
    """
    Loads the steered work items of a workspace in a fixed number of queries and computes their
    signals. ``rows`` holds the work items the scope covers; ``related`` the few facts shown about
    work items outside it that block or wait on them (§6.2 « la tâche qui la bloque, son entité »).
    """

    def __init__(self, workspace_id, scope: Scope, today: Optional[date] = None):
        self.workspace_id = workspace_id
        self.scope = scope
        self.today = today or today_in_abidjan()
        self.generated_at = timezone.now()
        self._load()

    # -- loading ----------------------------------------------------------------------------------

    def _load(self) -> None:
        workspace_id = self.workspace_id
        self.branches = {
            str(branch["id"]): branch
            for branch in Branch.objects.filter(workspace_id=workspace_id).values("id", "name", "sort_order")
        }
        self.entities = {
            str(entity["id"]): {**entity, "branch_id": str(entity["branch_id"])}
            for entity in Entity.objects.filter(workspace_id=workspace_id).values(
                "id", "name", "branch_id", "sort_order"
            )
        }
        self.categories = {
            str(category["id"]): category["name"]
            for category in SteeringCategory.objects.filter(workspace_id=workspace_id).values("id", "name")
        }
        project_entities = {
            str(project_id): str(entity_id)
            for project_id, entity_id in ProjectSteering.objects.filter(workspace_id=workspace_id).values_list(
                "project_id", "entity_id"
            )
        }
        self.projects = {
            str(project["id"]): {**project, "entity_id": project_entities[str(project["id"])]}
            for project in Project.objects.filter(pk__in=project_entities.keys()).values("id", "name", "identifier")
        }

        issues = list(
            Issue.issue_objects.filter(workspace_id=workspace_id, project_id__in=self.projects.keys()).values(
                "id",
                "name",
                "sequence_id",
                "project_id",
                "priority",
                "target_date",
                "state__group",
                "updated_at",
            )
        )
        ids = [issue["id"] for issue in issues]
        steerings = {
            str(steering["issue_id"]): steering
            for steering in IssueSteering.objects.filter(issue_id__in=ids).values(
                "issue_id",
                "entity_id",
                "category_id",
                "supervisor_id",
                "approver_id",
                "status",
                "progress",
                "waiting_for",
                "waiting_since",
                "risk_nature",
                "risk_effective_date",
                "risk_description",
                "closure_date",
                "closure_comment",
                "situation",
                "situation_updated_at",
                "updated_at",
            )
        }
        assignees: Dict[str, List[str]] = defaultdict(list)
        for issue_id, assignee_id in IssueAssignee.objects.filter(issue_id__in=ids).values_list(
            "issue_id", "assignee_id"
        ):
            assignees[str(issue_id)].append(str(assignee_id))
        submissions = {
            str(submission["issue_id"]): submission
            for submission in SteeringSubmission.objects.filter(
                workspace_id=workspace_id, status="pending", issue_id__in=ids
            ).values("id", "issue_id", "submitted_at", "message", "link", "submitted_by_id")
        }
        requalifications = {
            str(requalification["issue_id"]): requalification
            for requalification in PriorityRequalification.objects.filter(
                workspace_id=workspace_id, cancelled_at__isnull=True, issue_id__in=ids
            ).values("issue_id", "priority", "declared_priority", "by_role", "comment")
        }
        reminders = {
            str(reminder["issue_id"]): reminder
            for reminder in SteeringReminder.objects.filter(workspace_id=workspace_id, issue_id__in=ids)
            .values("issue_id")
            .annotate(count=Count("id"), last_at=Max("created_at"))
        }
        graph = blocked_by_graph(workspace_id)

        # Facts on every steered work item: the dependencies need them across the scope's edge.
        facts: Dict[str, Dict[str, Any]] = {}
        for issue in issues:
            issue_id = str(issue["id"])
            steering = steerings.get(issue_id) or {}
            project = self.projects[str(issue["project_id"])]
            entity_id = str(steering["entity_id"]) if steering.get("entity_id") else project["entity_id"]
            status = effective_status(steering.get("status"), issue["state__group"] or "")
            is_open = not is_closed(status, issue["state__group"] or "")
            facts[issue_id] = {
                "issue": issue,
                "steering": steering,
                "project": project,
                "entity_id": entity_id,
                "branch_id": (self.entities.get(entity_id) or {}).get("branch_id"),
                "status": status,
                "is_open": is_open,
                "signal": signal_of(issue["target_date"], self.today, is_open),
                "days_late": days_late(issue["target_date"], self.today, is_open),
            }

        blocks: Dict[str, Set[str]] = defaultdict(set)
        for blocked, blockers in graph.items():
            for blocker in blockers:
                blocks[blocker].add(blocked)
        outside = {item for pair in graph.items() for item in (pair[0], *pair[1])} - facts.keys()
        others = {
            str(issue["id"]): issue
            for issue in Issue.issue_objects.filter(pk__in=outside).values(
                "id", "name", "sequence_id", "project__identifier", "target_date", "state__group"
            )
        }

        def open_item(item_id: str) -> bool:
            if item_id in facts:
                return facts[item_id]["is_open"]
            other = others.get(item_id)
            return bool(other) and other["state__group"] not in ("completed", "cancelled")

        self.rows: List[Dict[str, Any]] = []
        people_ids: Set[str] = set()
        for issue_id, fact in facts.items():
            if not self.scope.covers(fact["entity_id"], fact["branch_id"]):
                continue
            issue, steering, is_open = fact["issue"], fact["steering"], fact["is_open"]
            submission = submissions.get(issue_id) if is_open else None
            requalification = requalifications.get(issue_id)
            blocked_by = sorted(b for b in graph.get(issue_id, ()) if open_item(b)) if is_open else []
            blocking = sorted(b for b in blocks.get(issue_id, ()) if open_item(b)) if is_open else []
            waiting_since = local_date(steering.get("waiting_since"))
            last_update = max(
                moment for moment in (issue["updated_at"], steering.get("updated_at")) if moment is not None
            )
            dormant_days = (self.today - local_date(last_update)).days
            dormant = is_open and fact["status"] != "waiting" and not submission and dormant_days > DORMANT_AFTER_DAYS
            risk_date = steering.get("risk_effective_date")
            risk_days = (risk_date - self.today).days if risk_date else None
            reminder = reminders.get(issue_id) or {}
            row = {
                "id": issue_id,
                "key": f"{fact['project']['identifier']}-{issue['sequence_id']}",
                "name": issue["name"],
                "project_id": str(issue["project_id"]),
                "entity_id": fact["entity_id"],
                "branch_id": fact["branch_id"],
                "category_id": str(steering["category_id"]) if steering.get("category_id") else None,
                "assignee_ids": assignees.get(issue_id, []),
                "supervisor_id": str(steering["supervisor_id"]) if steering.get("supervisor_id") else None,
                "approver_id": str(steering["approver_id"]) if steering.get("approver_id") else None,
                "priority": issue["priority"],
                "retained_priority": requalification["priority"] if requalification else issue["priority"],
                "requalification": (
                    {
                        "priority": requalification["priority"],
                        "by_role": requalification["by_role"],
                        "comment": requalification["comment"],
                    }
                    if requalification
                    else None
                ),
                "status": fact["status"],
                "is_open": is_open,
                "progress": steering.get("progress") or 0,
                "target_date": _iso(issue["target_date"]),
                "days_late": fact["days_late"],
                "days_left": (issue["target_date"] - self.today).days
                if is_open and issue["target_date"] and issue["target_date"] >= self.today
                else None,
                "signal": fact["signal"],
                "waiting_for": steering.get("waiting_for") or None,
                "waiting_since": _iso(waiting_since),
                "waiting_days": (self.today - waiting_since).days
                if is_open and fact["status"] == "waiting" and waiting_since
                else None,
                "risk": (
                    {
                        "nature": steering.get("risk_nature") or None,
                        "effective_date": _iso(risk_date),
                        "description": steering.get("risk_description") or "",
                        "days": risk_days,
                        "soon": is_open and risk_days is not None and risk_days <= RISK_SOON_WITHIN_DAYS,
                    }
                    if steering.get("risk_nature") or risk_date or steering.get("risk_description")
                    else None
                ),
                "in_queue": bool(submission),
                "submission": (
                    {
                        "id": str(submission["id"]),
                        "submitted_at": _iso(submission["submitted_at"]),
                        "submitted_by_id": str(submission["submitted_by_id"])
                        if submission["submitted_by_id"]
                        else None,
                        "message": submission["message"],
                        "link": submission["link"],
                        "waiting_days": (self.today - local_date(submission["submitted_at"])).days,
                    }
                    if submission
                    else None
                ),
                "blocked_by": blocked_by,
                "blocking": blocking,
                "blocked": bool(blocked_by),
                "dormant": dormant,
                "dormant_days": dormant_days,
                "inconsistencies": inconsistencies(
                    is_open,
                    fact["status"],
                    steering.get("progress") or 0,
                    steering.get("closure_date"),
                    issue["target_date"],
                    self.today,
                ),
                "closure_date": _iso(steering.get("closure_date")),
                "situation": steering.get("situation") or "",
                "situation_updated_at": _iso(steering.get("situation_updated_at")),
                "reminders": {"count": reminder.get("count", 0), "last_at": _iso(reminder.get("last_at"))},
                "updated_at": _iso(last_update),
            }
            self.rows.append(row)
            people_ids.update(row["assignee_ids"])
            people_ids.update(filter(None, (row["supervisor_id"], row["approver_id"])))
            if row["submission"] and row["submission"]["submitted_by_id"]:
                people_ids.add(row["submission"]["submitted_by_id"])

        in_rows = {row["id"] for row in self.rows}
        self.related: Dict[str, Dict[str, Any]] = {}
        for row in self.rows:
            for item_id in (*row["blocked_by"], *row["blocking"]):
                if item_id in in_rows or item_id in self.related:
                    continue
                if item_id in facts:
                    fact = facts[item_id]
                    self.related[item_id] = {
                        "id": item_id,
                        "key": f"{fact['project']['identifier']}-{fact['issue']['sequence_id']}",
                        "name": fact["issue"]["name"],
                        "entity_id": fact["entity_id"],
                        "status": fact["status"],
                        "signal": fact["signal"],
                        "days_late": fact["days_late"],
                    }
                elif item_id in others:
                    other = others[item_id]
                    is_open = open_item(item_id)
                    self.related[item_id] = {
                        "id": item_id,
                        "key": f"{other['project__identifier']}-{other['sequence_id']}",
                        "name": other["name"],
                        "entity_id": None,
                        "status": STATE_GROUP_STATUS.get(other["state__group"], "to_start"),
                        "signal": signal_of(other["target_date"], self.today, is_open),
                        "days_late": days_late(other["target_date"], self.today, is_open),
                    }

        self.people = {
            str(person["id"]): {"id": str(person["id"]), "name": _name(person)}
            for person in User.objects.filter(pk__in=people_ids).values(
                "id", "display_name", "first_name", "last_name", "email"
            )
        }
        self.rows.sort(key=lambda row: (SIGNAL_RANK[row["signal"]], -row["days_late"], row["key"]))

    # -- totals -------------------------------------------------------------------------------------

    def rows_for(self, branch_id: Optional[str] = None) -> List[Dict[str, Any]]:
        return [row for row in self.rows if not branch_id or row["branch_id"] == branch_id]

    def summary(self, branch_id: Optional[str] = None) -> Dict[str, Any]:
        """The Synthèse (§6.1), optionally on one branch, as the header's filter and the export ask."""
        rows = self.rows_for(branch_id)
        open_rows = [row for row in rows if row["is_open"]]
        late = [row for row in open_rows if row["days_late"] > 0]
        kpis = {
            "open": len(open_rows),
            "late": len(late),
            "late_share": round(100 * len(late) / len(open_rows)) if open_rows else 0,
            "critical": sum(row["signal"] == "critical" for row in open_rows),
            "blocked": sum(row["blocked"] for row in open_rows),
            "queue": sum(row["in_queue"] for row in open_rows),
            "due_soon": sum(row["signal"] == "soon" for row in open_rows),
            # RG-11
            "average_progress": round(sum(row["progress"] for row in open_rows) / len(open_rows)) if open_rows else 0,
        }
        return {
            "kpis": kpis,
            "branches": self._situation(open_rows, branch_id),
            "priority_delays": [row["id"] for row in self._priority_delays(late)[:8]],
            "blocking": self._blocking(open_rows),
            "load": self._load_by_person(open_rows),
        }

    def _situation(self, open_rows: List[Dict[str, Any]], branch_id: Optional[str]) -> List[Dict[str, Any]]:
        """§3.2: branches, then entities, sorted by late then critical work items; RG-14 per entity."""
        counts: Dict[str, Dict[str, int]] = defaultdict(lambda: defaultdict(int))
        for row in open_rows:
            entity = counts[row["entity_id"]]
            entity["open"] += 1
            entity["late"] += row["days_late"] > 0
            entity["critical"] += row["signal"] == "critical"
            entity["blocked"] += row["blocked"]
            entity["queue"] += row["in_queue"]
        branches = []
        for current_id, branch in self.branches.items():
            if branch_id and current_id != branch_id:
                continue
            entities = []
            for entity_id, entity in self.entities.items():
                if entity["branch_id"] != current_id or not self.scope.covers(entity_id, current_id):
                    continue
                count = counts.get(entity_id, {})
                totals = {key: count.get(key, 0) for key in ("open", "late", "critical", "blocked", "queue")}
                entities.append(
                    {
                        "id": entity_id,
                        "name": entity["name"],
                        "project_ids": [
                            project_id
                            for project_id, project in self.projects.items()
                            if project["entity_id"] == entity_id
                        ],
                        **totals,
                        "state": entity_state(totals["critical"], totals["blocked"], totals["late"], totals["queue"]),
                    }
                )
            if not entities:
                continue
            entities.sort(key=lambda item: (-item["late"], -item["critical"], item["name"]))
            totals = {
                key: sum(item[key] for item in entities) for key in ("open", "late", "critical", "blocked", "queue")
            }
            branches.append(
                {
                    "id": current_id,
                    "name": branch["name"],
                    **totals,
                    "has_alert": any(item["state"] == "alert" for item in entities),
                    "entities": entities,
                }
            )
        branches.sort(key=lambda item: (-item["late"], -item["critical"], item["name"]))
        return branches

    @staticmethod
    def _priority_delays(late_rows: Iterable[Dict[str, Any]]) -> List[Dict[str, Any]]:
        """RG-12: Urgent, then Important, then Normal, then the longest delay first."""
        return sorted(late_rows, key=lambda row: (PRIORITY_RANK.get(row["priority"], 2), -row["days_late"]))

    @staticmethod
    def _blocking(open_rows: List[Dict[str, Any]]) -> List[Dict[str, Any]]:
        """§7 « Vue d'ensemble »: the work items others wait on, late ones (or in the CEO queue) first."""
        blocking = [row for row in open_rows if row["blocking"]]
        blocking.sort(
            key=lambda row: (
                not (row["days_late"] > 0 or row["in_queue"]),
                -len(row["blocking"]),
                -row["days_late"],
            )
        )
        return [
            {"id": row["id"], "count": len(row["blocking"]), "highlighted": row["days_late"] > 0 or row["in_queue"]}
            for row in blocking
        ]

    def _load_by_person(self, open_rows: List[Dict[str, Any]]) -> List[Dict[str, Any]]:
        """§6.1 « Charge par responsable »: open, late and critical work items per assignee."""
        load: Dict[str, Dict[str, int]] = defaultdict(lambda: {"open": 0, "late": 0, "critical": 0})
        for row in open_rows:
            for person_id in row["assignee_ids"]:
                load[person_id]["open"] += 1
                load[person_id]["late"] += row["days_late"] > 0
                load[person_id]["critical"] += row["signal"] == "critical"
        people = [{"person_id": person_id, **counts} for person_id, counts in load.items()]
        people.sort(key=lambda item: (-item["late"], -item["critical"], -item["open"]))
        return people

    def queue(self) -> List[Dict[str, Any]]:
        """RG-04: the retained priority, then the oldest deadline."""
        rows = [row for row in self.rows if row["in_queue"]]
        return sorted(
            rows,
            key=lambda row: (PRIORITY_RANK.get(row["retained_priority"], 2), row["target_date"] or "9999-12-31"),
        )

    # -- payload ------------------------------------------------------------------------------------

    def referential_payload(self) -> Dict[str, Any]:
        projects_with_rows = {row["project_id"] for row in self.rows}
        return {
            "branches": [
                {"id": branch_id, "name": branch["name"], "sort_order": branch["sort_order"]}
                for branch_id, branch in self.branches.items()
                if self.scope.whole_group
                or branch_id in self.scope.branch_ids
                or any(
                    entity["branch_id"] == branch_id and entity_id in self.scope.entity_ids
                    for entity_id, entity in self.entities.items()
                )
            ],
            "entities": [
                {"id": entity_id, "name": entity["name"], "branch_id": entity["branch_id"]}
                for entity_id, entity in self.entities.items()
            ],
            # A project shows when its entity is covered, or when it holds a work item that is (§3.3).
            "projects": [
                {
                    "id": project_id,
                    "name": project["name"],
                    "identifier": project["identifier"],
                    "entity_id": project["entity_id"],
                }
                for project_id, project in self.projects.items()
                if project_id in projects_with_rows
                or self.scope.covers(project["entity_id"], self.entities.get(project["entity_id"], {}).get("branch_id"))
            ],
            "categories": [{"id": category_id, "name": name} for category_id, name in self.categories.items()],
            "people": list(self.people.values()),
        }
