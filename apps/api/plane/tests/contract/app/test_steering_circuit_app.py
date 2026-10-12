# Copyright (c) 2023-present Plane Software, Inc. and contributors
# SPDX-License-Identifier: AGPL-3.0-only
# See the LICENSE file for details.

"""The CEO's validation circuit (cahier des charges §8), reminders (§9.1) and alerts (§9.2)."""

import json
from unittest import mock

import pytest
from rest_framework.test import APIClient

from plane.db.models import (
    Issue,
    IssueActivity,
    IssueAssignee,
    IssueSteering,
    Notification,
    PriorityRequalification,
    Project,
    ProjectMember,
    State,
    SteeringAlertLog,
    SteeringEmailPreference,
    SteeringProfile,
    SteeringReminder,
    SteeringSubmission,
    User,
    WorkspaceMember,
)
from plane.utils.steering_alerts import notify


@pytest.fixture(autouse=True)
def no_email():
    with mock.patch("plane.bgtasks.steering_alert_email_task.steering_alert_email.delay") as delay:
        yield delay


def _member(workspace, email, role=None):
    user = User.objects.create(email=email, username=email.split("@")[0], first_name=email.split("@")[0].title())
    WorkspaceMember.objects.create(workspace=workspace, member=user, role=15)
    if role:
        SteeringProfile.objects.create(workspace=workspace, member=user, role=role)
    client = APIClient()
    client.force_authenticate(user=user)
    return user, client


@pytest.fixture
def ceo(workspace):
    return _member(workspace, "pdg@infinity-africa.com", "ceo")


@pytest.fixture
def cabinet(workspace):
    return _member(workspace, "cabinet@infinity-africa.com", "cabinet")


@pytest.fixture
def issue(workspace, create_user):
    project = Project.objects.create(name="Agrément", identifier="AGR", workspace=workspace, created_by=create_user)
    ProjectMember.objects.create(workspace=workspace, project=project, member=create_user, role=20, is_active=True)
    state = State.objects.create(project=project, workspace=workspace, name="En cours", group="started", default=True)
    issue = Issue.objects.create(
        project=project, workspace=workspace, name="Dossier CREPMF", state=state, priority="urgent"
    )
    IssueAssignee.objects.create(issue=issue, assignee=create_user, project=project, workspace=workspace)
    return issue


def _submit(client, issue, **payload):
    url = f"/api/workspaces/{issue.workspace.slug}/projects/{issue.project_id}/issues/{issue.id}/steering/submission/"
    data = {"message": "Merci de valider le dossier", "link": "https://sharepoint.example/dossier.pdf", **payload}
    return client.post(url, data, format="json")


def _events(issue):
    return [
        json.loads(comment)["event"]
        for comment in IssueActivity.objects.filter(issue=issue, field="steering_event")
        .order_by("created_at")
        .values_list("comment", flat=True)
    ]


@pytest.mark.contract
@pytest.mark.django_db
class TestSubmission:
    def test_submit_to_the_ceo(self, session_client, issue, ceo, no_email):
        response = _submit(
            session_client,
            issue,
            risk_nature="regulatory",
            risk_effective_date="2026-12-01",
            risk_description="Perte de l'agrément",
        )
        assert response.status_code == 201
        assert response.json()["pending_submission_id"]
        steering = IssueSteering.objects.get(issue=issue)
        assert steering.status == "in_validation"
        assert steering.approver_id == ceo[0].id
        assert steering.risk_nature == "regulatory"
        assert _events(issue) == ["submitted"]
        alert = Notification.objects.get(receiver=ceo[0])
        assert alert.data["issue_activity"]["new_value"] == "submitted"
        no_email.assert_called_once()
        assert _submit(session_client, issue).json()["code"] == "already_submitted"

    @pytest.mark.parametrize(
        "payload, code",
        [
            ({"message": " "}, "missing_message"),
            ({"link": ""}, "missing_document"),
            ({"link": "pas-un-lien"}, "invalid_link"),
        ],
    )
    def test_submission_needs_a_message_and_a_document(self, session_client, issue, ceo, payload, code):
        assert _submit(session_client, issue, **payload).json()["code"] == code

    def test_only_the_assignee_submits_and_a_ceo_is_needed(self, session_client, issue, cabinet):
        assert _submit(cabinet[1], issue).status_code in (400, 403)
        assert _submit(session_client, issue).json()["code"] == "no_ceo"


@pytest.mark.contract
@pytest.mark.django_db
class TestDecision:
    def _decide(self, client, submission_id, decision, comment=""):
        url = f"/api/workspaces/test-workspace/steering/submissions/{submission_id}/decision/"
        return client.post(url, {"decision": decision, "comment": comment}, format="json")

    def test_return_then_validate(self, session_client, issue, ceo, cabinet, create_user):
        submission_id = _submit(session_client, issue).json()["pending_submission_id"]
        assert self._decide(cabinet[1], submission_id, "returned", "Non").json()["code"] == "not_ceo"
        assert self._decide(ceo[1], submission_id, "returned").json()["code"] == "missing_comment"
        response = self._decide(ceo[1], submission_id, "returned", "Joindre l'avis juridique")
        assert response.status_code == 200
        assert IssueSteering.objects.get(issue=issue).status == "in_progress"
        assert SteeringSubmission.objects.get(pk=submission_id).decision_comment == "Joindre l'avis juridique"
        assert Notification.objects.filter(receiver=create_user, data__issue_activity__new_value="returned").exists()
        assert Notification.objects.filter(receiver=cabinet[0], data__issue_activity__new_value="returned").exists()
        assert self._decide(ceo[1], submission_id, "validated").json()["code"] == "already_decided"

        second = _submit(session_client, issue).json()["pending_submission_id"]
        assert self._decide(ceo[1], second, "validated").status_code == 200
        assert _events(issue) == ["submitted", "returned", "submitted", "validated"]


@pytest.mark.contract
@pytest.mark.django_db
class TestRequalification:
    def _url(self, issue):
        return f"/api/workspaces/{issue.workspace.slug}/steering/issues/{issue.id}/requalification/"

    def test_requalify_then_cancel(self, session_client, issue, ceo, cabinet, create_user):
        payload = {"priority": "high", "comment": "Pas d'échéance réglementaire avant décembre"}
        assert cabinet[1].post(self._url(issue), payload, format="json").json()["code"] == "not_in_queue"
        _submit(session_client, issue)
        assert session_client.post(self._url(issue), payload, format="json").json()["code"] == "not_cabinet"
        assert (
            cabinet[1].post(self._url(issue), {"priority": "high"}, format="json").json()["code"] == "missing_comment"
        )

        body = cabinet[1].post(self._url(issue), payload, format="json").json()
        assert body["requalification"]["priority"] == "high"
        assert body["requalification"]["declared_priority"] == "urgent"
        assert body["requalification"]["by_role"] == "cabinet"
        issue.refresh_from_db()
        assert issue.priority == "urgent"
        assert Notification.objects.filter(receiver=create_user, data__issue_activity__new_value="requalified").exists()

        body = ceo[1].post(self._url(issue), {"priority": "medium", "comment": "Arbitrage"}, format="json").json()
        assert body["requalification"]["by_role"] == "ceo"
        assert PriorityRequalification.objects.filter(issue=issue, cancelled_at__isnull=True).count() == 1

        assert cabinet[1].delete(self._url(issue)).json()["requalification"] is None
        assert _events(issue)[-3:] == ["requalified", "requalified", "requalification_cancelled"]


@pytest.mark.contract
@pytest.mark.django_db
class TestReminders:
    def test_unlimited_manual_reminders(self, session_client, issue, cabinet, create_user, no_email):
        url = f"/api/workspaces/{issue.workspace.slug}/steering/issues/{issue.id}/reminders/"
        assert session_client.post(url, {}, format="json").json()["code"] == "not_cabinet"
        first = cabinet[1].post(url, {"message": "Merci de mettre la fiche à jour"}, format="json")
        assert first.status_code == 201
        second = cabinet[1].post(url, {}, format="json").json()
        assert second["reminders"]["count"] == 2
        assert SteeringReminder.objects.filter(issue=issue, sent_by=cabinet[0]).count() == 2
        assert (
            Notification.objects.filter(receiver=create_user, data__issue_activity__new_value="reminder").count() == 2
        )
        assert _events(issue) == ["reminded", "reminded"]

    def test_alerts_go_once_and_e_mails_can_be_turned_off(self, issue, create_user, no_email):
        assert notify(issue, "late", [create_user.id], key="2026-10-01") == [str(create_user.id)]
        assert notify(issue, "late", [create_user.id], key="2026-10-01") == []
        assert SteeringAlertLog.objects.filter(issue=issue, event="late").count() == 1
        assert no_email.call_count == 1
        SteeringEmailPreference.objects.create(user=create_user, emails_enabled=False)
        notify(issue, "late", [create_user.id], key="2026-10-08")
        assert no_email.call_count == 1
        assert Notification.objects.filter(receiver=create_user).count() == 2


@pytest.mark.contract
@pytest.mark.django_db
def test_each_person_turns_the_steering_e_mails_off(session_client, create_user):
    url = "/api/users/me/steering-emails/"
    assert session_client.get(url).json() == {"emails_enabled": True}
    assert session_client.patch(url, {"emails_enabled": "non"}, format="json").status_code == 400
    assert session_client.patch(url, {"emails_enabled": False}, format="json").json() == {"emails_enabled": False}
    assert SteeringEmailPreference.objects.get(user=create_user).emails_enabled is False
    assert session_client.get(url).json() == {"emails_enabled": False}
