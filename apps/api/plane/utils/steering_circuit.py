# Copyright (c) 2023-present Plane Software, Inc. and contributors
# SPDX-License-Identifier: AGPL-3.0-only
# See the LICENSE file for details.

"""
The CEO's validation circuit (cahier des charges §8): submission from the entity's space, decision
from the steering space, priority requalification by the Cabinet or the CEO, and the reminders the
Cabinet or the CEO send (§9.1). Every step is written in the work item's history.
"""

# Python imports
import json
import time
from typing import Any, Dict, Optional

# Django imports
from django.core.exceptions import ValidationError
from django.core.validators import URLValidator
from django.db import transaction
from django.utils import timezone

# Module imports
from plane.db.models import (
    FileAsset,
    Issue,
    IssueActivity,
    IssueAssignee,
    IssueSteering,
    PriorityRequalification,
    SteeringProfile,
    SteeringProfileRole,
    SteeringReminder,
    SteeringSubmission,
    SteeringSubmissionStatus,
    User,
)
from plane.utils.steering import (
    SteeringValueError,
    apply_steering_changes,
    clean_steering_changes,
    display_steering_value,
)
from plane.utils.steering_alerts import notify, profile_member_ids
from plane.utils.steering_rules import is_closed

THREE_PRIORITIES = ("urgent", "high", "medium")
STEERING_HISTORY_FIELDS = ("status", "approver_id", "risk_nature", "risk_effective_date", "risk_description")


class CircuitError(ValueError):
    def __init__(self, message: str, code: str):
        super().__init__(message)
        self.code = code


def has_profile(user: User, workspace_id, *roles: str) -> bool:
    return SteeringProfile.objects.filter(workspace_id=workspace_id, member=user, role__in=roles).exists()


def is_ceo(user: User, workspace_id) -> bool:
    return has_profile(user, workspace_id, SteeringProfileRole.CEO)


def is_cabinet_or_ceo(user: User, workspace_id) -> bool:
    """§10: the CEO holds every right of the Cabinet, on top of his own."""
    return has_profile(user, workspace_id, SteeringProfileRole.CEO, SteeringProfileRole.CABINET)


def assignee_ids(issue: Issue):
    return [str(user_id) for user_id in IssueAssignee.objects.filter(issue=issue).values_list("assignee_id", flat=True)]


def record_event(issue: Issue, actor: Optional[User], event: str, text: str = "", **extra: Any) -> None:
    """A history line for a circuit step: the event and its comment travel as JSON in ``comment``."""
    IssueActivity.objects.create(
        issue=issue,
        project_id=issue.project_id,
        workspace_id=issue.workspace_id,
        actor=actor,
        verb="updated",
        field="steering_event",
        old_value=extra.pop("old", "") or "",
        new_value=extra.pop("new", "") or "",
        comment=json.dumps({"event": event, "text": text, **extra}, ensure_ascii=False),
        epoch=int(time.time()),
    )


def _steering(issue: Issue) -> IssueSteering:
    return IssueSteering.objects.filter(issue=issue).first() or IssueSteering(
        issue=issue, project_id=issue.project_id, workspace_id=issue.workspace_id
    )


def _apply(issue: Issue, actor: User, steering: IssueSteering, data: Dict[str, Any]) -> None:
    """Change steering fields with the §4 rules, and write each change in the history."""
    try:
        changed = apply_steering_changes(steering, clean_steering_changes(data, issue.workspace_id))
    except SteeringValueError as error:
        raise CircuitError(str(error), "invalid_steering")
    steering.save()
    epoch = int(time.time())
    IssueActivity.objects.bulk_create(
        IssueActivity(
            issue=issue,
            project_id=issue.project_id,
            workspace_id=issue.workspace_id,
            actor=actor,
            verb="updated",
            field="steering",
            old_value=display_steering_value(key, old),
            new_value=display_steering_value(key, new),
            comment=key,
            epoch=epoch,
        )
        for key, old, new in changed
    )


def pending_submission(issue: Issue) -> Optional[SteeringSubmission]:
    return SteeringSubmission.objects.filter(issue=issue, status=SteeringSubmissionStatus.PENDING).first()


@transaction.atomic
def submit_to_ceo(issue: Issue, actor: User, data: Dict[str, Any]) -> SteeringSubmission:
    """
    §8.1 « Soumettre »: by an assignee of the work item, with a message and the link or attachment to
    validate; the risk is optional. The work item goes « En validation » with the CEO as approver.
    """
    if str(actor.id) not in assignee_ids(issue):
        raise CircuitError("Only the assignee of the work item can submit it to the CEO.", "not_assignee")
    steering = _steering(issue)
    if is_closed(steering.status, issue.state.group if issue.state_id else ""):
        raise CircuitError("A closed work item cannot be submitted.", "closed")
    if pending_submission(issue):
        raise CircuitError("This work item is already waiting for the CEO's decision.", "already_submitted")
    message = str(data.get("message") or "").strip()
    if not message:
        raise CircuitError("A message is required.", "missing_message")
    link = str(data.get("link") or "").strip()
    attachment = None
    if link:
        try:
            URLValidator(schemes=["http", "https"])(link)
        except ValidationError:
            raise CircuitError("The link must be a web address.", "invalid_link")
    if data.get("attachment_id"):
        attachment = FileAsset.objects.filter(pk=data["attachment_id"], issue=issue).first()
        if not attachment:
            raise CircuitError("Unknown attachment.", "invalid_attachment")
    if not link and not attachment:
        raise CircuitError("Add the link or the attachment to validate.", "missing_document")
    ceo = SteeringProfile.objects.filter(workspace_id=issue.workspace_id, role=SteeringProfileRole.CEO).first()
    if not ceo:
        raise CircuitError("No CEO is set in the Group referential.", "no_ceo")

    changes: Dict[str, Any] = {"status": "in_validation", "approver_id": str(ceo.member_id)}
    for key in ("risk_nature", "risk_effective_date", "risk_description"):
        if key in data:
            changes[key] = data[key]
    _apply(issue, actor, steering, changes)
    submission = SteeringSubmission.objects.create(
        issue=issue,
        project_id=issue.project_id,
        workspace_id=issue.workspace_id,
        submitted_by=actor,
        submitted_at=timezone.now(),
        message=message[:5000],
        link=link,
        attachment=attachment,
    )
    record_event(issue, actor, "submitted", message, link=link, submission=str(submission.id))
    notify(issue, "submitted", profile_member_ids(issue.workspace_id, "ceo"), actor, message, key=str(submission.id))
    return submission


@transaction.atomic
def decide(submission: SteeringSubmission, actor: User, decision: str, comment: str) -> SteeringSubmission:
    """
    §8.1 « Valider » (comment optional) or « Renvoyer » (comment required), by the CEO. The work
    item goes back « En cours » to its assignee, who carries on, closes it or submits it again.
    """
    issue = submission.issue
    if not is_ceo(actor, issue.workspace_id):
        raise CircuitError("Only the CEO decides on the CEO queue.", "not_ceo")
    if submission.status != SteeringSubmissionStatus.PENDING:
        raise CircuitError("This submission has already been decided.", "already_decided")
    if decision not in (SteeringSubmissionStatus.VALIDATED, SteeringSubmissionStatus.RETURNED):
        raise CircuitError("Validate or return the work item.", "invalid_decision")
    comment = str(comment or "").strip()
    if decision == SteeringSubmissionStatus.RETURNED and not comment:
        raise CircuitError("A comment is required to return the work item.", "missing_comment")

    submission.status = decision
    submission.decided_by = actor
    submission.decided_at = timezone.now()
    submission.decision_comment = comment[:5000]
    submission.save(update_fields=["status", "decided_by", "decided_at", "decision_comment", "updated_at"])
    _apply(issue, actor, _steering(issue), {"status": "in_progress"})
    record_event(issue, actor, decision, comment, submission=str(submission.id))
    recipients = assignee_ids(issue) + profile_member_ids(issue.workspace_id, "cabinet")
    notify(issue, decision, recipients, actor, comment, key=str(submission.id))
    return submission


def active_requalification(issue: Issue) -> Optional[PriorityRequalification]:
    return PriorityRequalification.objects.filter(issue=issue, cancelled_at__isnull=True).first()


@transaction.atomic
def requalify(issue: Issue, actor: User, priority: str, comment: str) -> PriorityRequalification:
    """
    §8.2: the Cabinet or the CEO retains another priority for a work item in the CEO queue, with a
    justification. The priority declared by the entity is left untouched.
    """
    if not is_cabinet_or_ceo(actor, issue.workspace_id):
        raise CircuitError("Only the Cabinet and the CEO requalify a priority.", "not_cabinet")
    if not pending_submission(issue):
        raise CircuitError("Only work items in the CEO queue can be requalified.", "not_in_queue")
    if priority not in THREE_PRIORITIES:
        raise CircuitError("Unknown priority.", "invalid_priority")
    comment = str(comment or "").strip()
    if not comment:
        raise CircuitError("A justification is required.", "missing_comment")
    previous = active_requalification(issue)
    retained_before = previous.priority if previous else issue.priority
    if previous:
        previous.cancelled_at, previous.cancelled_by = timezone.now(), actor
        previous.save(update_fields=["cancelled_at", "cancelled_by", "updated_at"])
    role = SteeringProfileRole.CEO if is_ceo(actor, issue.workspace_id) else SteeringProfileRole.CABINET
    requalification = PriorityRequalification.objects.create(
        issue=issue,
        project_id=issue.project_id,
        workspace_id=issue.workspace_id,
        priority=priority,
        declared_priority=issue.priority,
        comment=comment[:2000],
        requalified_by=actor,
        by_role=role,
    )
    record_event(issue, actor, "requalified", comment, old=retained_before, new=priority, role=role)
    steering = IssueSteering.objects.filter(issue=issue).first()
    recipients = assignee_ids(issue) + ([str(steering.supervisor_id)] if steering and steering.supervisor_id else [])
    notify(issue, "requalified", recipients, actor, comment, key=str(requalification.id))
    return requalification


@transaction.atomic
def cancel_requalification(issue: Issue, actor: User) -> None:
    """§8.2: the declared priority applies again."""
    if not is_cabinet_or_ceo(actor, issue.workspace_id):
        raise CircuitError("Only the Cabinet and the CEO requalify a priority.", "not_cabinet")
    current = active_requalification(issue)
    if not current:
        raise CircuitError("This work item has no requalified priority.", "not_requalified")
    current.cancelled_at, current.cancelled_by = timezone.now(), actor
    current.save(update_fields=["cancelled_at", "cancelled_by", "updated_at"])
    record_event(issue, actor, "requalification_cancelled", old=current.priority, new=issue.priority)


def remind(issue: Issue, actor: Optional[User], reason: str, message: str = "") -> SteeringReminder:
    """
    §9.1: remind the assignees (and the supervisor) of a work item. Manual reminders by the Cabinet
    or the CEO are unlimited; each one is written in the history with its author.
    """
    if actor is not None and not is_cabinet_or_ceo(actor, issue.workspace_id):
        raise CircuitError("Only the Cabinet and the CEO send reminders.", "not_cabinet")
    steering = IssueSteering.objects.filter(issue=issue).first()
    recipients = assignee_ids(issue) or ([str(steering.supervisor_id)] if steering and steering.supervisor_id else [])
    if not recipients:
        raise CircuitError("Nobody is in charge of this work item.", "no_recipient")
    message = str(message or "").strip()[:2000]
    reminder = SteeringReminder.objects.create(
        issue=issue,
        project_id=issue.project_id,
        workspace_id=issue.workspace_id,
        sent_by=actor,
        reason=reason,
        message=message,
        recipient_ids=recipients,
    )
    record_event(issue, actor, "reminded", message, reason=reason)
    notify(issue, "reminder" if actor else "reminder_auto", recipients, actor, message, once=False)
    return reminder
