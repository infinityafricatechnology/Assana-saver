# Copyright (c) 2023-present Plane Software, Inc. and contributors
# SPDX-License-Identifier: AGPL-3.0-only
# See the LICENSE file for details.

"""
Rules of the steered projects, i.e. projects carried by an entity (cahier des charges §4, §9.4):
- « Une tâche ne peut pas être enregistrée tant qu'un champ obligatoire manque »: a work item is
  created with its assignee, deadline, category, supervisor and approver;
- « Un report de deadline sans commentaire est refusé ».
Other projects keep Plane's free creation.
"""

# Python imports
import uuid
from datetime import date
from typing import Any, Dict, List, Optional

# Module imports
from plane.db.models import (
    Entity,
    Issue,
    IssueSteering,
    Project,
    ProjectSteering,
    SteeringCategory,
    User,
    WorkspaceMember,
)
from plane.utils.steering import SteeringValueError, apply_steering_changes, clean_steering_changes
from plane.utils.steering_circuit import record_event

REQUIRED_STEERING = ("category_id", "supervisor_id", "approver_id")


class SteeringRuleError(ValueError):
    def __init__(self, message: str, code: str, missing: Optional[List[str]] = None):
        super().__init__(message)
        self.code = code
        self.missing = missing or []

    @property
    def payload(self) -> Dict[str, Any]:
        return {"error": str(self), "code": self.code, "missing": self.missing}


def is_steered(project_id) -> bool:
    return ProjectSteering.objects.filter(project_id=project_id).exists()


def _known_categories(workspace_id) -> str:
    """Named in the refusals, so that Claude and API clients can pick a valid one."""
    names = SteeringCategory.objects.filter(workspace_id=workspace_id).values_list("name", flat=True)
    return " Categories: " + ", ".join(names) + "." if names else ""


def _resolve_names(workspace_id, raw: Dict[str, Any]) -> Dict[str, Any]:
    """API v1 and Claude may name things: « category » and « entity » by name, people by e-mail."""
    resolved = dict(raw)
    for key, model in (("category", SteeringCategory), ("entity", Entity)):
        if key in resolved:
            name = str(resolved.pop(key) or "").strip()
            match = model.objects.filter(workspace_id=workspace_id, name__iexact=name).first() if name else None
            if name and not match:
                hint = _known_categories(workspace_id) if key == "category" else ""
                raise SteeringRuleError(f"Unknown {key}: {name}.{hint}", f"unknown_{key}")
            resolved[f"{key}_id"] = str(match.id) if match else None
    for key in ("supervisor", "approver"):
        if key in resolved:
            value = str(resolved.pop(key) or "").strip()
            user = None
            if value:
                try:
                    user = User.objects.filter(pk=uuid.UUID(value)).first()
                except ValueError:
                    user = User.objects.filter(email__iexact=value).first()
                if (
                    not user
                    or not WorkspaceMember.objects.filter(
                        workspace_id=workspace_id, member=user, is_active=True
                    ).exists()
                ):
                    raise SteeringRuleError(f"Unknown {key}: {value}.", f"unknown_{key}")
            resolved[f"{key}_id"] = str(user.id) if user else None
    return resolved


def prepare_steering_on_create(project: Project, data: Dict[str, Any]) -> Optional[Dict[str, Any]]:
    """
    For a steered project, check the work item about to be created and return its cleaned steering
    fields (``data["steering"]``); for any other project, return None and let Plane create freely.
    """
    if not is_steered(project.id):
        return None
    raw = data.get("steering") or {}
    if not isinstance(raw, dict):
        raise SteeringRuleError("'steering' must be an object.", "invalid_steering")
    try:
        changes = clean_steering_changes(_resolve_names(project.workspace_id, raw), project.workspace_id)
        # Dry run of the §4 rules (« En attente » needs its cause…) before anything is created.
        apply_steering_changes(IssueSteering(project_id=project.id, workspace_id=project.workspace_id), dict(changes))
    except SteeringValueError as error:
        raise SteeringRuleError(str(error), "invalid_steering")

    missing = []
    assignees = data.get("assignee_ids") or data.get("assignees") or []
    if not assignees and not project.default_assignee_id:
        missing.append("assignee")
    if not data.get("target_date"):
        missing.append("target_date")
    missing += [key.removesuffix("_id") for key in REQUIRED_STEERING if not changes.get(key)]
    if missing:
        hint = _known_categories(project.workspace_id) if "category" in missing else ""
        raise SteeringRuleError(
            "This project is steered: fill in " + ", ".join(missing) + "." + hint, "steering_required", missing
        )
    return changes


def attach_steering(issue: Issue, changes: Optional[Dict[str, Any]]) -> None:
    """Save the steering record of a work item just created in a steered project."""
    if changes is None:
        return
    steering = IssueSteering(issue=issue, project_id=issue.project_id, workspace_id=issue.workspace_id)
    apply_steering_changes(steering, dict(changes))
    steering.save()


def _as_date(value: Any) -> Optional[date]:
    if isinstance(value, date):
        return value
    try:
        return date.fromisoformat(str(value)) if value else None
    except ValueError:
        return None


def check_steered_update(issue: Issue, data: Dict[str, Any]) -> Optional[str]:
    """
    Updating a work item of a steered project: its deadline and assignees cannot be removed, and
    moving the deadline later needs a comment (``deadline_comment``, §9.4). Returns the comment to
    record for a postponement, or None.
    """
    if not is_steered(issue.project_id):
        return None
    for key in ("assignee_ids", "assignees"):
        if key in data and not data[key]:
            raise SteeringRuleError("A steered work item keeps an assignee.", "steering_required", ["assignee"])
    if "target_date" not in data:
        return None
    new_date = _as_date(data.get("target_date"))
    if new_date is None:
        raise SteeringRuleError("A steered work item keeps a deadline.", "steering_required", ["target_date"])
    if not issue.target_date or new_date <= issue.target_date:
        return None
    comment = str(data.get("deadline_comment") or "").strip()
    if not comment:
        raise SteeringRuleError(
            "Postponing the deadline of a steered work item needs a comment.", "deadline_comment_required"
        )
    return comment[:2000]


def check_steering_fields_kept(issue: Issue, changes: Dict[str, Any]) -> None:
    """In a steered project, the category, supervisor and approver cannot be cleared."""
    if not is_steered(issue.project_id):
        return
    cleared = [key.removesuffix("_id") for key in REQUIRED_STEERING if key in changes and not changes[key]]
    if cleared:
        raise SteeringRuleError("This project is steered: these fields are required.", "steering_required", cleared)


def record_postponement(issue: Issue, actor, old_date: Optional[date], comment: Optional[str]) -> None:
    """The postponement and its reason go to the history (« deadline_postponed »)."""
    if comment:
        old, new = _as_date(old_date), _as_date(issue.target_date)
        record_event(
            issue,
            actor,
            "deadline_postponed",
            comment,
            old=old.isoformat() if old else "",
            new=new.isoformat() if new else "",
        )
