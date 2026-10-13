# Copyright (c) 2023-present Plane Software, Inc. and contributors
# SPDX-License-Identifier: AGPL-3.0-only
# See the LICENSE file for details.

"""The CEO's validation circuit (§8) and the reminders (§9.1)."""

# Python imports
from typing import Any, Dict, Optional

# Third party imports
from rest_framework import status
from rest_framework.response import Response

# Module imports
from plane.app.permissions import ROLE, allow_permission
from plane.db.models import Issue, SteeringEmailPreference, SteeringReminder, SteeringSubmission, User
from plane.utils.steering_circuit import (
    CircuitError,
    active_requalification,
    cancel_requalification,
    decide,
    remind,
    requalify,
    submit_to_ceo,
)

from ..base import BaseAPIView


def _error(error: CircuitError) -> Response:
    return Response({"error": str(error), "code": error.code}, status=status.HTTP_400_BAD_REQUEST)


def _person(user: Optional[User]) -> Optional[Dict[str, str]]:
    return {"id": str(user.id), "display_name": user.display_name} if user else None


def submission_payload(submission: SteeringSubmission) -> Dict[str, Any]:
    return {
        "id": str(submission.id),
        "status": submission.status,
        "message": submission.message,
        "link": submission.link,
        "attachment_id": str(submission.attachment_id) if submission.attachment_id else None,
        "submitted_by": _person(submission.submitted_by),
        "submitted_at": submission.submitted_at,
        "decided_by": _person(submission.decided_by),
        "decided_at": submission.decided_at,
        "decision_comment": submission.decision_comment,
    }


def circuit_payload(issue: Issue) -> Dict[str, Any]:
    """Where the work item stands in the CEO circuit: submissions, retained priority, reminders."""
    submissions = list(SteeringSubmission.objects.filter(issue=issue).select_related("submitted_by", "decided_by")[:10])
    requalification = active_requalification(issue)
    reminders = SteeringReminder.objects.filter(issue=issue)
    last_reminder = reminders.first()
    return {
        "submissions": [submission_payload(submission) for submission in submissions],
        "pending_submission_id": next(
            (str(submission.id) for submission in submissions if submission.status == "pending"), None
        ),
        "requalification": (
            {
                "priority": requalification.priority,
                "declared_priority": requalification.declared_priority,
                "comment": requalification.comment,
                "by_role": requalification.by_role,
                "by": _person(requalification.requalified_by),
                "at": requalification.created_at,
            }
            if requalification
            else None
        ),
        "reminders": {"count": reminders.count(), "last_at": last_reminder.created_at if last_reminder else None},
    }


class IssueSubmissionEndpoint(BaseAPIView):
    """« Soumettre au PDG », from the work item in the entity's space."""

    @allow_permission([ROLE.ADMIN, ROLE.MEMBER])
    def post(self, request, slug, project_id, issue_id):
        issue = Issue.issue_objects.select_related("state").get(project_id=project_id, pk=issue_id)
        try:
            submit_to_ceo(issue, request.user, request.data)
        except CircuitError as error:
            return _error(error)
        return Response(circuit_payload(issue), status=status.HTTP_201_CREATED)


class SubmissionDecisionEndpoint(BaseAPIView):
    """« Valider » or « Renvoyer », by the CEO from the steering space."""

    def post(self, request, slug, submission_id):
        submission = SteeringSubmission.objects.select_related("issue").get(workspace__slug=slug, pk=submission_id)
        try:
            decide(submission, request.user, request.data.get("decision"), request.data.get("comment", ""))
        except CircuitError as error:
            return _error(error)
        return Response(circuit_payload(submission.issue), status=status.HTTP_200_OK)


class IssueRequalificationEndpoint(BaseAPIView):
    """The priority retained by the Cabinet or the CEO for the CEO queue (§8.2)."""

    def post(self, request, slug, issue_id):
        issue = Issue.issue_objects.get(workspace__slug=slug, pk=issue_id)
        try:
            requalify(issue, request.user, request.data.get("priority"), request.data.get("comment", ""))
        except CircuitError as error:
            return _error(error)
        return Response(circuit_payload(issue), status=status.HTTP_200_OK)

    def delete(self, request, slug, issue_id):
        issue = Issue.issue_objects.get(workspace__slug=slug, pk=issue_id)
        try:
            cancel_requalification(issue, request.user)
        except CircuitError as error:
            return _error(error)
        return Response(circuit_payload(issue), status=status.HTTP_200_OK)


class IssueReminderEndpoint(BaseAPIView):
    """« Relancer le responsable », by the Cabinet or the CEO, as often as needed (§9.1)."""

    def post(self, request, slug, issue_id):
        issue = Issue.issue_objects.get(workspace__slug=slug, pk=issue_id)
        try:
            remind(issue, request.user, "manual", request.data.get("message", ""))
        except CircuitError as error:
            return _error(error)
        return Response(circuit_payload(issue), status=status.HTTP_201_CREATED)


class SteeringEmailPreferenceEndpoint(BaseAPIView):
    """§9.2: each person can turn the steering e-mails off; the alerts stay in the platform."""

    def get(self, request):
        preference = SteeringEmailPreference.objects.filter(user=request.user).first()
        return Response({"emails_enabled": preference.emails_enabled if preference else True})

    def patch(self, request):
        enabled = request.data.get("emails_enabled")
        if not isinstance(enabled, bool):
            return Response(
                {"error": "'emails_enabled' must be true or false.", "code": "invalid_value"},
                status=status.HTTP_400_BAD_REQUEST,
            )
        SteeringEmailPreference.objects.update_or_create(user=request.user, defaults={"emails_enabled": enabled})
        return Response({"emails_enabled": enabled})
