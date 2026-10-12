# Copyright (c) 2023-present Plane Software, Inc. and contributors
# SPDX-License-Identifier: AGPL-3.0-only
# See the LICENSE file for details.

"""Steering record of a work item (cahier des charges §4): fields, conditional rules, history."""

from datetime import date, timedelta

import pytest
from rest_framework import status
from rest_framework.test import APIClient

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
    SteeringCategory,
    State,
    User,
    Workspace,
)


@pytest.fixture
def project(workspace, create_user):
    project = Project.objects.create(name="Licence", identifier="LIC", workspace=workspace, created_by=create_user)
    ProjectMember.objects.create(workspace=workspace, project=project, member=create_user, role=20, is_active=True)
    State.objects.create(project=project, workspace=workspace, name="À faire", group="unstarted", default=True)
    return project


@pytest.fixture
def issue(project):
    return Issue.objects.create(
        project=project,
        workspace=project.workspace,
        name="Dossier d'agrément",
        state=State.objects.get(project=project),
    )


@pytest.fixture
def entities(workspace):
    branch = Branch.objects.create(workspace=workspace, name="Finance & Capital Markets")
    return (
        Entity.objects.create(workspace=workspace, branch=branch, name="Infinity Africa Capital"),
        Entity.objects.create(workspace=workspace, branch=branch, name="Infinity Africa Securities"),
    )


@pytest.fixture
def category(workspace):
    return SteeringCategory.objects.create(workspace=workspace, name="Agréments")


def _url(issue):
    return f"/api/workspaces/{issue.workspace.slug}/projects/{issue.project_id}/issues/{issue.id}/steering/"


def _history(issue):
    return list(
        IssueActivity.objects.filter(issue=issue, field="steering")
        .order_by("created_at")
        .values_list("comment", "old_value", "new_value")
    )


@pytest.mark.contract
@pytest.mark.django_db
class TestIssueSteering:
    def test_defaults_and_missing_fields(self, session_client, issue, entities):
        ProjectSteering.objects.create(project=issue.project, workspace=issue.workspace, entity=entities[0])
        body = session_client.get(_url(issue)).json()
        assert body["status"] == "to_start"
        assert body["progress"] == 0
        assert body["entity_id"] is None
        assert body["project_entity_id"] == str(entities[0].id)
        assert body["missing"] == ["category", "assignee", "supervisor", "approver", "target_date"]
        assert not IssueSteering.objects.filter(issue=issue).exists()

    def test_fill_the_record_with_history(self, session_client, create_user, issue, entities, category):
        IssueAssignee.objects.create(issue=issue, assignee=create_user, project=issue.project)
        issue.priority = "urgent"
        issue.target_date = date(2026, 12, 31)
        issue.save()
        payload = {
            "entity_id": str(entities[1].id),
            "category_id": str(category.id),
            "supervisor_id": str(create_user.id),
            "approver_id": str(create_user.id),
            "status": "in_progress",
            "progress": 40,
        }
        response = session_client.patch(_url(issue), payload, format="json")
        assert response.status_code == status.HTTP_200_OK
        body = response.json()
        assert body["missing"] == []
        assert body["entity_id"] == str(entities[1].id)
        history = dict((key, new) for key, _, new in _history(issue))
        assert history["entity_id"] == "Infinity Africa Securities"
        assert history["category_id"] == "Agréments"
        assert history["supervisor_id"] == create_user.display_name
        assert history["status"] == "in_progress"
        assert history["progress"] == "40"
        # Sending the same values again records nothing.
        session_client.patch(_url(issue), payload, format="json")
        assert len(_history(issue)) == 6

    def test_waiting_needs_its_cause(self, session_client, issue):
        assert session_client.patch(_url(issue), {"status": "waiting"}, format="json").status_code == 400
        body = session_client.patch(
            _url(issue), {"status": "waiting", "waiting_for": "regulatory"}, format="json"
        ).json()
        assert body["waiting_for"] == "regulatory"
        assert body["waiting_since"] is not None
        body = session_client.patch(_url(issue), {"status": "in_progress"}, format="json").json()
        assert body["waiting_for"] is None

    def test_done_needs_a_closure_and_forces_100(self, session_client, issue):
        assert session_client.patch(_url(issue), {"status": "done"}, format="json").status_code == 400
        tomorrow = (date.today() + timedelta(days=2)).isoformat()
        future = {"status": "done", "closure_date": tomorrow, "closure_comment": "Agrément obtenu"}
        assert session_client.patch(_url(issue), future, format="json").status_code == 400
        closure = {"status": "done", "closure_date": date.today().isoformat(), "closure_comment": "Agrément obtenu"}
        body = session_client.patch(_url(issue), {**closure, "progress": 30}, format="json").json()
        assert body["status"] == "done"
        assert body["progress"] == 100
        assert "closure" not in body["missing"]

    def test_risk_is_frozen_once_closed(self, session_client, issue):
        risk = {"risk_nature": "regulatory", "risk_effective_date": "2026-11-30", "risk_description": "Licence"}
        assert session_client.patch(_url(issue), risk, format="json").json()["risk_nature"] == "regulatory"
        session_client.patch(_url(issue), {"status": "cancelled"}, format="json")
        assert session_client.patch(_url(issue), {"risk_nature": "legal"}, format="json").status_code == 400
        session_client.patch(_url(issue), {"status": "in_progress"}, format="json")
        assert session_client.patch(_url(issue), {"risk_nature": "legal"}, format="json").status_code == 200

    def test_situation_is_dated(self, session_client, issue):
        body = session_client.patch(_url(issue), {"situation": "Dossier déposé à la CREPMF"}, format="json").json()
        assert body["situation"] == "Dossier déposé à la CREPMF"
        assert body["situation_updated_at"] is not None

    @pytest.mark.parametrize(
        "payload",
        [
            {"progress": 120},
            {"progress": "50"},
            {"status": "blocked"},
            {"status": None},
            {"color": "red"},
            {"risk_effective_date": "30/11/2026"},
            {"category_id": "not-a-uuid"},
        ],
    )
    def test_rejects_invalid_values(self, session_client, issue, payload):
        assert session_client.patch(_url(issue), payload, format="json").status_code == 400

    def test_references_belong_to_the_workspace(self, session_client, issue, create_user):
        outsider = User.objects.create(email="outsider@example.com", username="outsider")
        assert session_client.patch(_url(issue), {"supervisor_id": str(outsider.id)}, format="json").status_code == 400
        other = Workspace.objects.create(name="Autre", owner=create_user, slug="autre")
        foreign = Entity.objects.create(
            workspace=other, branch=Branch.objects.create(workspace=other, name="Ailleurs"), name="Ailleurs SA"
        )
        assert session_client.patch(_url(issue), {"entity_id": str(foreign.id)}, format="json").status_code == 400

    def test_outsiders_cannot_read(self, issue):
        outsider = User.objects.create(email="outsider@example.com", username="outsider")
        client = APIClient()
        client.force_authenticate(user=outsider)
        assert client.get(_url(issue)).status_code == status.HTTP_403_FORBIDDEN

    def test_used_entities_and_categories_are_kept(self, session_client, issue, entities, category):
        session_client.patch(
            _url(issue), {"entity_id": str(entities[1].id), "category_id": str(category.id)}, format="json"
        )
        slug = issue.workspace.slug
        assert session_client.delete(f"/api/workspaces/{slug}/steering/entities/{entities[1].id}/").status_code == 400
        assert session_client.delete(f"/api/workspaces/{slug}/steering/categories/{category.id}/").status_code == 400


@pytest.mark.unit
@pytest.mark.django_db
class TestThreePriorities:
    def test_low_and_none_are_saved_as_normal(self, project):
        state = State.objects.get(project=project)
        for priority in ("low", "none"):
            issue = Issue.objects.create(
                project=project, workspace=project.workspace, name=priority, state=state, priority=priority
            )
            assert issue.priority == "medium"
        kept = Issue.objects.create(
            project=project, workspace=project.workspace, name="u", state=state, priority="urgent"
        )
        assert kept.priority == "urgent"
        assert (
            Issue.objects.create(project=project, workspace=project.workspace, name="d", state=state).priority
            == "medium"
        )
