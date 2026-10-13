# Copyright (c) 2023-present Plane Software, Inc. and contributors
# SPDX-License-Identifier: AGPL-3.0-only
# See the LICENSE file for details.

"""
Alerts of the steering space (cahier des charges §9.2): a notification in the platform for every
recipient, an e-mail when the event calls for one and the recipient has not turned them off. An
alert goes out once per work item, event and key (the deadline, the submission…).
"""

# Python imports
import uuid
from dataclasses import dataclass
from typing import Iterable, List, Optional

# Django imports
from django.db import IntegrityError, transaction

# Module imports
from plane.db.models import (
    Issue,
    Notification,
    SteeringAlertLog,
    SteeringEmailPreference,
    SteeringProfile,
    User,
)


@dataclass(frozen=True)
class AlertEvent:
    title: str
    email: bool


EVENTS = {
    "deadline_soon": AlertEvent("Échéance dans 3 jours", True),
    "late": AlertEvent("Tâche en retard", True),
    "critical": AlertEvent("Tâche critique : plus de 30 jours de retard", True),
    "blocker_late": AlertEvent("Une tâche qui bloque la vôtre est en retard", False),
    "unblocked": AlertEvent("Blocage levé", True),
    "submitted": AlertEvent("Tâche soumise à votre validation", True),
    "validated": AlertEvent("Décision du PDG : tâche validée", True),
    "returned": AlertEvent("Décision du PDG : tâche renvoyée", True),
    "submission_overdue": AlertEvent("Soumission au PDG sans décision depuis 7 jours", False),
    "risk_soon": AlertEvent("Risque à 7 jours de sa date d'effet", True),
    "requalified": AlertEvent("Priorité requalifiée pour la File PDG", False),
    "reminder": AlertEvent("Relance : fiche à mettre à jour", True),
    "reminder_auto": AlertEvent("Relance automatique : fiche à mettre à jour", True),
}


def profile_member_ids(workspace_id, *roles: str) -> List[str]:
    return [
        str(member_id)
        for member_id in SteeringProfile.objects.filter(workspace_id=workspace_id, role__in=roles)
        .values_list("member_id", flat=True)
        .distinct()
    ]


def notify(
    issue: Issue,
    event: str,
    recipient_ids: Iterable,
    actor: Optional[User] = None,
    detail: str = "",
    key: str = "",
    once: bool = True,
) -> List[str]:
    """
    Alert people about a work item. With ``once``, a recipient already alerted for the same
    work item, event and key is skipped. The person who acted is never alerted. Returns the
    ids of the people alerted.
    """
    alert = EVENTS[event]
    wanted = {str(recipient) for recipient in recipient_ids if recipient}
    if actor:
        wanted.discard(str(actor.id))
    recipients = list(User.objects.filter(pk__in=wanted, is_active=True, is_bot=False))
    alerted = []
    for recipient in recipients:
        if once:
            try:
                with transaction.atomic():
                    SteeringAlertLog.objects.create(
                        workspace_id=issue.workspace_id, issue=issue, event=event, key=key, recipient=recipient
                    )
            except IntegrityError:
                continue
        alerted.append(recipient)

    Notification.objects.bulk_create(
        [
            Notification(
                workspace_id=issue.workspace_id,
                project_id=issue.project_id,
                receiver=recipient,
                triggered_by=actor,
                entity_identifier=issue.id,
                entity_name="issue",
                sender="in_app:steering",
                title=alert.title,
                data={
                    "issue": {
                        "id": str(issue.id),
                        "name": issue.name,
                        "identifier": issue.project.identifier,
                        "sequence_id": issue.sequence_id,
                        "state_name": issue.state.name if issue.state_id else "",
                        "state_group": issue.state.group if issue.state_id else "",
                    },
                    "issue_activity": {
                        "id": str(uuid.uuid4()),
                        "verb": "updated",
                        "field": "steering_alert",
                        "actor": str(actor.id) if actor else None,
                        "new_value": event,
                        "old_value": detail,
                        "issue_comment": "",
                        "old_identifier": None,
                        "new_identifier": None,
                    },
                },
            )
            for recipient in alerted
        ]
    )

    if alert.email and alerted:
        muted = set(
            SteeringEmailPreference.objects.filter(user__in=alerted, emails_enabled=False).values_list(
                "user_id", flat=True
            )
        )
        emailed = [str(recipient.id) for recipient in alerted if recipient.id not in muted]
        if emailed:
            from plane.bgtasks.steering_alert_email_task import steering_alert_email

            steering_alert_email.delay(str(issue.id), event, emailed, detail, actor.display_name if actor else "")
    return [str(recipient.id) for recipient in alerted]
