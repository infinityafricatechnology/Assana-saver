# Copyright (c) 2023-present Plane Software, Inc. and contributors
# SPDX-License-Identifier: AGPL-3.0-only
# See the LICENSE file for details.

"""Steered projects through the public API and Claude (cahier des charges §4, §9.4): names and e-mails are accepted."""

import pytest

from plane.celery import app as celery_app
from plane.db.models import (
    Branch,
    Entity,
    Issue,
    IssueActivity,
    IssueAssignee,
    IssueSteering,
    Project,
    ProjectMember,
    ProjectSteering,
    State,
    SteeringCategory,
    User,
    WorkspaceMember,
)


@pytest.fixture(autouse=True)
def celery_eager():
    """Run the activity tasks in-process: there is no broker in the test stack."""
    original = (celery_app.conf.task_always_eager, celery_app.conf.task_eager_propagates)
    celery_app.conf.task_always_eager, celery_app.conf.task_eager_propagates = True, False
    yield
    celery_app.conf.task_always_eager, celery_app.conf.task_eager_propagates = original


@pytest.fixture
def referential(workspace):
    branch = Branch.objects.create(workspace=workspace, name="Finance")
    return {
        "entity": Entity.objects.create(workspace=workspace, branch=branch, name="Infinity Africa Finance"),
        "other_entity": Entity.objects.create(workspace=workspace, branch=branch, name="Infinity Africa Capital"),
        "category": SteeringCategory.objects.create(workspace=workspace, name="Réglementaire"),
    }


@pytest.fixture
def supervisor(workspace):
    user = User.objects.create(email="superviseur@infinity-africa.com", username="superviseur")
    WorkspaceMember.objects.create(workspace=workspace, member=user, role=15)
    return user


@pytest.fixture
def project(workspace, create_user, referential):
    project = Project.objects.create(name="IAF", identifier="IAF", workspace=workspace, created_by=create_user)
    ProjectMember.objects.create(workspace=workspace, project=project, member=create_user, role=20, is_active=True)
    State.objects.create(project=project, workspace=workspace, name="À faire", group="unstarted", default=True)
    ProjectSteering.objects.create(project=project, workspace=workspace, entity=referential["entity"])
    return project


def _url(project, suffix=""):
    return f"/api/v1/workspaces/{project.workspace.slug}/projects/{project.id}/work-items/{suffix}"


def _item(create_user, **steering):
    return {
        "name": "Clôture des comptes",
        "assignees": [str(create_user.id)],
        "target_date": "2026-12-31",
        "steering": {
            "category": "réglementaire",
            "supervisor": "Superviseur@infinity-africa.com",
            "approver": "superviseur@infinity-africa.com",
            **steering,
        },
    }


@pytest.mark.contract
@pytest.mark.django_db
class TestPublicApi:
    def test_create_with_names_and_e_mails(self, api_key_client, project, create_user, supervisor, referential):
        response = api_key_client.post(
            _url(project), _item(create_user, entity="Infinity Africa Capital"), format="json"
        )
        assert response.status_code == 201
        steering = IssueSteering.objects.get(issue_id=response.json()["id"])
        assert steering.category_id == referential["category"].id
        assert steering.supervisor_id == supervisor.id
        assert steering.entity_id == referential["other_entity"].id

    def test_unknown_names_and_missing_fields(self, api_key_client, project, create_user, supervisor):
        response = api_key_client.post(_url(project), _item(create_user, category="Inconnue"), format="json")
        assert response.json()["code"] == "unknown_category"
        assert response.json()["error"] == "Unknown category: Inconnue. Categories: Réglementaire."
        response = api_key_client.post(
            _url(project), _item(create_user, approver="personne@ailleurs.com"), format="json"
        )
        assert response.json()["code"] == "unknown_approver"
        response = api_key_client.post(_url(project), {"name": "Incomplète"}, format="json")
        assert response.json()["code"] == "steering_required"

    def test_bulk_creation_is_all_or_nothing(self, api_key_client, project, create_user, supervisor):
        payload = {"work_items": [_item(create_user), {"name": "Incomplète"}]}
        response = api_key_client.post(_url(project, "bulk/"), payload, format="json")
        assert response.status_code == 400
        [error] = response.json()["errors"]
        assert error["index"] == 1
        assert error["errors"]["steering"]["code"] == "steering_required"
        assert not Issue.objects.filter(project=project).exists()

        payload = {"work_items": [_item(create_user), _item(create_user)]}
        assert api_key_client.post(_url(project, "bulk/"), payload, format="json").status_code == 201
        assert IssueSteering.objects.filter(project=project).count() == 2

    def test_postponement_needs_a_comment(self, api_key_client, project, workspace, create_user):
        issue = Issue.objects.create(project=project, workspace=workspace, name="Audit", target_date="2026-11-30")
        IssueAssignee.objects.create(issue=issue, assignee=create_user, project=project, workspace=workspace)

        response = api_key_client.patch(_url(project, f"{issue.id}/"), {"target_date": "2026-12-20"}, format="json")
        assert response.json()["code"] == "deadline_comment_required"
        payload = {"target_date": "2026-12-20", "deadline_comment": "Retard du commissaire aux comptes"}
        assert api_key_client.patch(_url(project, f"{issue.id}/"), payload, format="json").status_code == 200

        bulk = {"work_items": [{"id": str(issue.id), "target_date": "2027-01-10"}]}
        response = api_key_client.patch(_url(project, "bulk/"), bulk, format="json")
        assert response.json()["errors"][0]["errors"]["steering"]["code"] == "deadline_comment_required"
        bulk["work_items"][0]["deadline_comment"] = "Nouvelle date du conseil"
        assert api_key_client.patch(_url(project, "bulk/"), bulk, format="json").status_code == 200

        issue.refresh_from_db()
        assert str(issue.target_date) == "2027-01-10"
        assert IssueActivity.objects.filter(issue=issue, field="steering_event").count() == 2
