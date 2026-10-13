# Copyright (c) 2023-present Plane Software, Inc. and contributors
# SPDX-License-Identifier: AGPL-3.0-only
# See the LICENSE file for details.

"""Dependencies between work items (cahier des charges §7): loops refused, chains, closed work items."""

from unittest import mock

import pytest
from rest_framework import status

from plane.db.models import Issue, IssueRelation, Project, ProjectMember, State
from plane.utils.steering_rules import blocked_by_graph, blocking_chain, is_closed


@pytest.fixture(autouse=True)
def no_activity_task():
    with mock.patch("plane.app.views.issue.relation.issue_activity.delay"):
        yield


@pytest.fixture
def issues(workspace, create_user):
    project = Project.objects.create(name="Plateforme", identifier="PLAT", workspace=workspace, created_by=create_user)
    ProjectMember.objects.create(workspace=workspace, project=project, member=create_user, role=20, is_active=True)
    state = State.objects.create(project=project, workspace=workspace, name="À faire", group="unstarted", default=True)
    return {
        name: Issue.objects.create(project=project, workspace=workspace, name=name, state=state)
        for name in ("maquettes", "developpement", "recette", "lancement")
    }


def _relate(client, issue, relation_type, *others):
    url = f"/api/workspaces/{issue.workspace.slug}/projects/{issue.project_id}/issues/{issue.id}/issue-relation/"
    return client.post(url, {"relation_type": relation_type, "issues": [str(o.id) for o in others]}, format="json")


@pytest.mark.contract
@pytest.mark.django_db
class TestDependencies:
    def test_loops_are_refused(self, session_client, issues):
        # développement is blocked by maquettes, recette by développement
        assert _relate(session_client, issues["developpement"], "blocked_by", issues["maquettes"]).status_code == 201
        assert _relate(session_client, issues["recette"], "blocked_by", issues["developpement"]).status_code == 201
        # maquettes blocked by recette would close the loop maquettes ← développement ← recette ← maquettes
        response = _relate(session_client, issues["maquettes"], "blocked_by", issues["recette"])
        assert response.status_code == status.HTTP_400_BAD_REQUEST
        assert response.json()["code"] == "circular_dependency"
        # same loop expressed from the other side
        assert _relate(session_client, issues["recette"], "blocking", issues["maquettes"]).status_code == 400
        assert _relate(session_client, issues["maquettes"], "blocked_by", issues["maquettes"]).status_code == 400
        # other relation types never loop
        assert _relate(session_client, issues["maquettes"], "relates_to", issues["recette"]).status_code == 201

    def test_chain_up_to_the_origin(self, session_client, issues):
        _relate(session_client, issues["developpement"], "blocked_by", issues["maquettes"])
        _relate(session_client, issues["recette"], "blocked_by", issues["developpement"])
        _relate(session_client, issues["lancement"], "blocked_by", issues["recette"], issues["maquettes"])
        graph = blocked_by_graph(issues["maquettes"].workspace_id)
        chain = blocking_chain(graph, issues["lancement"].id)
        assert chain[0] == sorted([str(issues["recette"].id), str(issues["maquettes"].id)])
        assert chain[1] == [str(issues["developpement"].id)]
        assert len(chain) == 2
        assert IssueRelation.objects.filter(relation_type="blocked_by").count() == 4

    def test_closed_work_items(self):
        assert is_closed("done", "started")
        assert is_closed("cancelled", "backlog")
        assert is_closed("in_progress", "completed")
        assert not is_closed("waiting", "started")
