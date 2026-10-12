# Copyright (c) 2023-present Plane Software, Inc. and contributors
# SPDX-License-Identifier: AGPL-3.0-only
# See the LICENSE file for details.

"""
Steered projects (cahier des charges §4, §9.4): a work item is created complete, keeps its deadline
and assignees, and postponing its deadline needs a comment. Other projects stay free.
"""

import json
from unittest import mock

import pytest

from plane.celery import app as celery_app
from plane.db.models import (
    Branch,
    DraftIssue,
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
    with mock.patch("plane.app.views.workspace.draft.base_host", return_value="http://testserver"):
        yield
    celery_app.conf.task_always_eager, celery_app.conf.task_eager_propagates = original


@pytest.fixture
def supervisor(workspace):
    user = User.objects.create(email="superviseur@infinity-africa.com", username="superviseur")
    WorkspaceMember.objects.create(workspace=workspace, member=user, role=15)
    return user


@pytest.fixture
def category(workspace):
    return SteeringCategory.objects.create(workspace=workspace, name="Réglementaire")


def _project(workspace, user, identifier, entity=None):
    project = Project.objects.create(name=identifier, identifier=identifier, workspace=workspace, created_by=user)
    ProjectMember.objects.create(workspace=workspace, project=project, member=user, role=20, is_active=True)
    State.objects.create(project=project, workspace=workspace, name="À faire", group="unstarted", default=True)
    if entity:
        ProjectSteering.objects.create(project=project, workspace=workspace, entity=entity)
    return project


@pytest.fixture
def steered(workspace, create_user):
    branch = Branch.objects.create(workspace=workspace, name="Finance")
    entity = Entity.objects.create(workspace=workspace, branch=branch, name="Infinity Africa Finance")
    return _project(workspace, create_user, "IAF", entity)


@pytest.fixture
def free(workspace, create_user):
    return _project(workspace, create_user, "LIB")


def _issues_url(project, issue_id=None):
    url = f"/api/workspaces/{project.workspace.slug}/projects/{project.id}/issues/"
    return f"{url}{issue_id}/" if issue_id else url


def _complete(user, supervisor, category, **extra):
    return {
        "name": "Renouveler l'agrément",
        "assignee_ids": [str(user.id)],
        "target_date": "2026-11-30",
        "priority": "urgent",
        "steering": {
            "category_id": str(category.id),
            "supervisor_id": str(supervisor.id),
            "approver_id": str(supervisor.id),
        },
        **extra,
    }


@pytest.fixture
def steered_issue(steered, workspace, create_user, supervisor, category):
    issue = Issue.objects.create(project=steered, workspace=workspace, name="Dossier CREPMF", target_date="2026-11-30")
    IssueAssignee.objects.create(issue=issue, assignee=create_user, project=steered, workspace=workspace)
    IssueSteering.objects.create(
        issue=issue, project=steered, workspace=workspace, category=category, supervisor=supervisor, approver=supervisor
    )
    return issue


def _events(issue):
    return [
        json.loads(comment)
        for comment in IssueActivity.objects.filter(issue=issue, field="steering_event").values_list(
            "comment", flat=True
        )
    ]


@pytest.mark.contract
@pytest.mark.django_db
class TestCreation:
    def test_an_incomplete_work_item_is_refused(self, session_client, steered):
        response = session_client.post(_issues_url(steered), {"name": "Incomplète"}, format="json")
        assert response.status_code == 400
        assert response.json()["code"] == "steering_required"
        assert response.json()["missing"] == ["assignee", "target_date", "category", "supervisor", "approver"]
        assert not Issue.objects.filter(project=steered).exists()

    def test_a_complete_work_item_gets_its_steering_record(
        self, session_client, steered, create_user, supervisor, category
    ):
        payload = _complete(create_user, supervisor, category)
        payload["steering"].update(status="waiting", waiting_for="regulatory")
        response = session_client.post(_issues_url(steered), payload, format="json")
        assert response.status_code == 201
        steering = IssueSteering.objects.get(issue_id=response.json()["id"])
        assert (steering.category_id, steering.supervisor_id, steering.approver_id) == (
            category.id,
            supervisor.id,
            supervisor.id,
        )
        assert (steering.status, steering.waiting_for) == ("waiting", "regulatory")
        assert steering.waiting_since is not None

    def test_the_steering_rules_apply_on_creation(self, session_client, steered, create_user, supervisor, category):
        payload = _complete(create_user, supervisor, category)
        payload["steering"]["status"] = "waiting"
        response = session_client.post(_issues_url(steered), payload, format="json")
        assert response.json()["code"] == "invalid_steering"
        assert not Issue.objects.filter(project=steered).exists()

    def test_the_project_default_assignee_counts(self, session_client, steered, create_user, supervisor, category):
        steered.default_assignee = create_user
        steered.save()
        payload = _complete(create_user, supervisor, category)
        del payload["assignee_ids"]
        assert session_client.post(_issues_url(steered), payload, format="json").status_code == 201

    def test_free_projects_stay_free(self, session_client, free):
        response = session_client.post(_issues_url(free), {"name": "Libre"}, format="json")
        assert response.status_code == 201
        assert not IssueSteering.objects.filter(issue_id=response.json()["id"]).exists()

    def test_a_draft_becomes_a_steered_work_item_only_complete(
        self, session_client, steered, workspace, create_user, supervisor, category
    ):
        draft = DraftIssue(name="Brouillon", workspace=workspace, project=steered)
        draft.save(created_by_id=create_user.id)
        url = f"/api/workspaces/{workspace.slug}/draft-to-issue/{draft.id}/"
        with mock.patch("plane.db.mixins.soft_delete_related_objects"):
            assert session_client.post(url, {"name": "Brouillon"}, format="json").json()["code"] == "steering_required"
            response = session_client.post(url, _complete(create_user, supervisor, category), format="json")
        assert response.status_code == 201
        assert IssueSteering.objects.filter(issue_id=response.json()["id"]).exists()


@pytest.mark.contract
@pytest.mark.django_db
class TestUpdates:
    def test_postponing_needs_a_comment(self, session_client, steered, steered_issue):
        url = _issues_url(steered, steered_issue.id)
        response = session_client.patch(url, {"target_date": "2026-12-15"}, format="json")
        assert response.status_code == 400
        assert response.json()["code"] == "deadline_comment_required"
        steered_issue.refresh_from_db()
        assert str(steered_issue.target_date) == "2026-11-30"

        payload = {"target_date": "2026-12-15", "deadline_comment": "Attente de l'avis du régulateur"}
        assert session_client.patch(url, payload, format="json").status_code == 204
        steered_issue.refresh_from_db()
        assert str(steered_issue.target_date) == "2026-12-15"
        [event] = _events(steered_issue)
        assert event["event"] == "deadline_postponed"
        assert event["text"] == "Attente de l'avis du régulateur"
        activity = IssueActivity.objects.get(issue=steered_issue, field="steering_event")
        assert (activity.old_value, activity.new_value) == ("2026-11-30", "2026-12-15")

    def test_moving_the_deadline_earlier_is_free(self, session_client, steered, steered_issue):
        url = _issues_url(steered, steered_issue.id)
        assert session_client.patch(url, {"target_date": "2026-11-20"}, format="json").status_code == 204
        assert _events(steered_issue) == []

    @pytest.mark.parametrize(
        "payload, missing",
        [({"target_date": None}, "target_date"), ({"assignee_ids": []}, "assignee")],
    )
    def test_deadline_and_assignees_are_kept(self, session_client, steered, steered_issue, payload, missing):
        response = session_client.patch(_issues_url(steered, steered_issue.id), payload, format="json")
        assert response.status_code == 400
        assert response.json()["missing"] == [missing]

    def test_the_steering_fields_cannot_be_cleared(self, session_client, steered, steered_issue):
        url = f"{_issues_url(steered, steered_issue.id)}steering/"
        response = session_client.patch(url, {"category_id": None}, format="json")
        assert response.status_code == 400
        assert response.json()["missing"] == ["category"]
        assert session_client.patch(url, {"progress": 40}, format="json").status_code == 200

    def test_the_timeline_postpones_with_a_comment(self, session_client, steered, steered_issue, workspace):
        url = f"/api/workspaces/{workspace.slug}/projects/{steered.id}/issue-dates/"
        earlier = {"updates": [{"id": str(steered_issue.id), "target_date": "2026-11-10"}]}
        assert session_client.post(url, earlier, format="json").status_code == 200
        later = {"updates": [{"id": str(steered_issue.id), "target_date": "2026-12-31"}]}
        assert session_client.post(url, later, format="json").json()["code"] == "deadline_comment_required"
        later["deadline_comment"] = "Décalage du comité de crédit"
        assert session_client.post(url, later, format="json").status_code == 200
        steered_issue.refresh_from_db()
        assert str(steered_issue.target_date) == "2026-12-31"
        activity = IssueActivity.objects.get(issue=steered_issue, field="steering_event")
        assert (activity.old_value, activity.new_value) == ("2026-11-10", "2026-12-31")

    def test_free_projects_postpone_freely(self, session_client, free, workspace):
        issue = Issue.objects.create(project=free, workspace=workspace, name="Libre", target_date="2026-11-30")
        url = _issues_url(free, issue.id)
        assert session_client.patch(url, {"target_date": "2027-01-15"}, format="json").status_code == 204
        assert session_client.patch(url, {"target_date": None}, format="json").status_code == 204
