# Copyright (c) 2023-present Plane Software, Inc. and contributors
# SPDX-License-Identifier: AGPL-3.0-only
# See the LICENSE file for details.

"""The steering space's reading of the portfolio: rules RG-01 to RG-14 (§5) and who sees what (§10)."""

from datetime import date, datetime, timedelta

import pytest
from django.utils import timezone
from rest_framework.test import APIClient

from plane.db.models import (
    Branch,
    Entity,
    Issue,
    IssueActivity,
    IssueAssignee,
    IssueRelation,
    IssueSteering,
    PriorityRequalification,
    Project,
    ProjectMember,
    ProjectSteering,
    State,
    SteeringProfile,
    SteeringSubmission,
    User,
    WorkspaceMember,
)
from plane.utils.steering_dashboard import Portfolio, Scope, signal_of

TODAY = date(2026, 10, 7)
DASHBOARD = "/api/workspaces/test-workspace/steering/dashboard/"


@pytest.fixture
def group(workspace, create_user):
    """Two branches, three entities, one steered project each, and a free project."""
    finance = Branch.objects.create(workspace=workspace, name="Finance & Capital Markets")
    tech = Branch.objects.create(workspace=workspace, name="Technologie")
    entities = {
        "capital": Entity.objects.create(workspace=workspace, branch=finance, name="Infinity Africa Capital"),
        "securities": Entity.objects.create(workspace=workspace, branch=finance, name="Infinity Africa Securities"),
        "iat": Entity.objects.create(workspace=workspace, branch=tech, name="Infinity Africa Technologies"),
    }
    projects = {}
    for key, entity in entities.items():
        project = Project.objects.create(name=key, identifier=key[:3].upper(), workspace=workspace)
        ProjectMember.objects.create(workspace=workspace, project=project, member=create_user, role=20)
        ProjectSteering.objects.create(project=project, workspace=workspace, entity=entity)
        projects[key] = project
    free = Project.objects.create(name="Libre", identifier="LIB", workspace=workspace)
    return {"branches": {"finance": finance, "tech": tech}, "entities": entities, "projects": projects, "free": free}


def _task(group, key, name, target=None, priority="medium", user=None, **steering):
    project = group["projects"][key]
    state = State.objects.filter(project=project, group="started").first() or State.objects.create(
        project=project, workspace=project.workspace, name="En cours", group="started"
    )
    issue = Issue.objects.create(
        project=project, workspace=project.workspace, name=name, state=state, priority=priority, target_date=target
    )
    if user:
        IssueAssignee.objects.create(issue=issue, assignee=user, project=project, workspace=project.workspace)
    if steering:
        IssueSteering.objects.create(issue=issue, project=project, workspace=project.workspace, **steering)
    return issue


def _rows(workspace, scope=None):
    portfolio = Portfolio(workspace.id, scope or Scope(whole_group=True), today=TODAY)
    return portfolio, {row["name"]: row for row in portfolio.rows}


def _member(workspace, email, role=None, **profile):
    user = User.objects.create(email=email, username=email.split("@")[0])
    WorkspaceMember.objects.create(workspace=workspace, member=user, role=15)
    if role:
        SteeringProfile.objects.create(workspace=workspace, member=user, role=role, **profile)
    client = APIClient()
    client.force_authenticate(user=user)
    return user, client


@pytest.mark.contract
@pytest.mark.django_db
class TestRules:
    def test_the_two_control_cases(self, workspace, group):
        """§5: on 7 October 2026, 30 June 2026 reads J+99 critical, 15 October « Dans 8 j » soon."""
        _task(group, "iat", "Ancienne", date(2026, 6, 30))
        _task(group, "iat", "Proche", date(2026, 10, 15))
        _, rows = _rows(workspace)
        assert (rows["Ancienne"]["days_late"], rows["Ancienne"]["signal"]) == (99, "critical")
        assert (rows["Proche"]["days_left"], rows["Proche"]["signal"]) == (8, "soon")

    def test_signal_thresholds(self):
        assert signal_of(TODAY - timedelta(days=31), TODAY, True) == "critical"
        assert signal_of(TODAY - timedelta(days=30), TODAY, True) == "late"
        assert signal_of(TODAY - timedelta(days=1), TODAY, True) == "late"
        assert signal_of(TODAY, TODAY, True) == "soon"
        assert signal_of(TODAY + timedelta(days=14), TODAY, True) == "soon"
        assert signal_of(TODAY + timedelta(days=15), TODAY, True) == "on_time"
        assert signal_of(TODAY - timedelta(days=99), TODAY, False) == "closed"

    def test_closed_work_items_carry_no_signal(self, workspace, group):
        _task(group, "iat", "Terminée", date(2026, 6, 30), status="done", closure_date=TODAY)
        done_column = State.objects.create(
            project=group["projects"]["iat"], workspace=workspace, name="Fait", group="completed"
        )
        issue = _task(group, "iat", "Colonne terminée", date(2026, 6, 30))
        Issue.objects.filter(pk=issue.pk).update(state=done_column)
        portfolio, rows = _rows(workspace)
        assert rows["Terminée"]["is_open"] is False and rows["Terminée"]["days_late"] == 0
        assert rows["Colonne terminée"]["status"] == "done"
        assert portfolio.summary()["kpis"]["open"] == 0

    def test_dependencies(self, workspace, group, create_user):
        """RG-07, RG-08: a blocker counts while it is open, across entities."""
        blocker = _task(group, "iat", "Maquettes", date(2026, 9, 30))
        blocked = _task(group, "capital", "Plateforme", date(2026, 12, 1))
        done = _task(group, "iat", "Cadrage", date(2026, 9, 1), status="done", closure_date=TODAY)
        for other in (blocker, done):
            IssueRelation.objects.create(
                issue=blocked,
                related_issue=other,
                relation_type="blocked_by",
                project=blocked.project,
                workspace=workspace,
            )
        portfolio, rows = _rows(workspace)
        assert rows["Plateforme"]["blocked_by"] == [str(blocker.id)]
        assert rows["Maquettes"]["blocking"] == [str(blocked.id)]
        assert portfolio.summary()["blocking"] == [{"id": str(blocker.id), "count": 1, "highlighted": True}]

        capital_only = Scope(entity_ids={str(group["entities"]["capital"].id)})
        portfolio, rows = _rows(workspace, capital_only)
        assert list(rows) == ["Plateforme"]
        assert portfolio.related[str(blocker.id)]["entity_id"] == str(group["entities"]["iat"].id)
        assert portfolio.related[str(blocker.id)]["signal"] == "late"

    def test_ceo_queue_order_with_a_requalified_priority(self, workspace, group, create_user):
        """RG-04: the retained priority, then the oldest deadline."""
        names = [("Normal tôt", "medium", date(2026, 10, 20)), ("Urgent tard", "urgent", date(2026, 12, 1))]
        names += [("Urgent tôt", "urgent", date(2026, 11, 1)), ("Requalifiée", "medium", date(2026, 10, 10))]
        for name, priority, target in names:
            issue = _task(group, "iat", name, target, priority=priority, status="in_validation")
            SteeringSubmission.objects.create(
                issue=issue,
                project=issue.project,
                workspace=workspace,
                submitted_by=create_user,
                submitted_at=timezone.make_aware(datetime(2026, 10, 4, 9, 0)),
                message="À valider",
            )
            if name == "Requalifiée":
                PriorityRequalification.objects.create(
                    issue=issue,
                    project=issue.project,
                    workspace=workspace,
                    priority="urgent",
                    declared_priority="medium",
                    comment="Échéance réglementaire",
                    requalified_by=create_user,
                    by_role="cabinet",
                )
        portfolio, rows = _rows(workspace)
        assert [row["name"] for row in portfolio.queue()] == ["Requalifiée", "Urgent tôt", "Urgent tard", "Normal tôt"]
        assert rows["Requalifiée"]["priority"] == "medium"
        assert rows["Requalifiée"]["retained_priority"] == "urgent"
        assert rows["Urgent tôt"]["submission"]["waiting_days"] == 3

    def test_waiting_dormant_and_inconsistent(self, workspace, group):
        """RG-06, RG-09, RG-10."""
        waiting = _task(
            group,
            "iat",
            "En attente",
            date(2026, 12, 1),
            status="waiting",
            waiting_for="regulatory",
            waiting_since=timezone.now() - timedelta(days=40),
        )
        dormant = _task(group, "iat", "Oubliée", date(2026, 12, 1), status="in_progress")
        _task(group, "iat", "Pas démarrée", date(2026, 10, 1), status="to_start")
        _task(group, "iat", "Finie sans clôture", date(2026, 12, 1), status="in_progress", progress=100)
        old = timezone.now() - timedelta(days=30)
        Issue.objects.filter(pk__in=[waiting.pk, dormant.pk]).update(updated_at=old)
        IssueSteering.objects.filter(issue__in=[waiting, dormant]).update(updated_at=old)
        _, rows = _rows(workspace)
        assert rows["En attente"]["waiting_for"] == "regulatory"
        assert rows["En attente"]["dormant"] is False
        assert rows["Oubliée"]["dormant"] is True
        assert rows["Pas démarrée"]["inconsistencies"] == ["late_not_started"]
        assert rows["Finie sans clôture"]["inconsistencies"] == ["progress_without_closure"]

    def test_risk_countdown(self, workspace, group):
        """RG-13."""
        _task(
            group, "iat", "Risquée", date(2026, 12, 1), risk_nature="regulatory", risk_effective_date=date(2026, 10, 12)
        )
        _, rows = _rows(workspace)
        assert rows["Risquée"]["risk"]["days"] == 5
        assert rows["Risquée"]["risk"]["soon"] is True

    def test_synthesis(self, workspace, group, create_user):
        """§6.1, RG-12, RG-14, §3.2: alert branches first, priority delays, load per assignee."""
        _task(group, "iat", "Critique", date(2026, 6, 30), priority="medium", user=create_user)
        _task(group, "iat", "Retard urgent", date(2026, 10, 1), priority="urgent", user=create_user)
        _task(group, "capital", "Retard normal", date(2026, 9, 20))
        _task(group, "securities", "Dans les délais", date(2026, 12, 31))
        Issue.objects.create(
            project=group["free"], workspace=workspace, name="Hors pilotage", target_date=date(2026, 1, 1)
        )
        portfolio, rows = _rows(workspace)
        assert "Hors pilotage" not in rows
        summary = portfolio.summary()
        assert summary["kpis"] == {
            "open": 4,
            "late": 3,
            "late_share": 75,
            "critical": 1,
            "blocked": 0,
            "queue": 0,
            "due_soon": 0,
            "average_progress": 0,
        }
        assert [rows_id for rows_id in summary["priority_delays"]] == [
            rows["Retard urgent"]["id"],
            rows["Critique"]["id"],
            rows["Retard normal"]["id"],
        ]
        tech, finance = summary["branches"]
        assert (tech["name"], tech["late"], tech["has_alert"]) == ("Technologie", 2, True)
        assert [(entity["name"], entity["state"]) for entity in finance["entities"]] == [
            ("Infinity Africa Capital", "watch"),
            ("Infinity Africa Securities", "ok"),
        ]
        assert summary["load"] == [{"person_id": str(create_user.id), "open": 2, "late": 2, "critical": 1}]
        assert portfolio.summary(str(group["branches"]["finance"].id))["kpis"]["open"] == 2


@pytest.mark.contract
@pytest.mark.django_db
class TestAccess:
    def test_profiles_decide_the_scope(self, workspace, group):
        _task(group, "iat", "Tech", date(2026, 12, 1))
        _task(group, "capital", "Capital", date(2026, 12, 1))
        _task(group, "securities", "Titres", date(2026, 12, 1))
        _, director = _member(workspace, "pole@iag.com", "branch_director", branch=group["branches"]["finance"])
        _, manager = _member(workspace, "entite@iag.com", "entity_manager", entity=group["entities"]["iat"])
        _, ceo = _member(workspace, "pdg@iag.com", "ceo")
        _, nobody = _member(workspace, "membre@iag.com")

        names = lambda client: sorted(task["name"] for task in client.get(DASHBOARD).json()["tasks"])  # noqa: E731
        assert names(director) == ["Capital", "Titres"]
        assert names(manager) == ["Tech"]
        assert names(ceo) == ["Capital", "Tech", "Titres"]
        assert ceo.get(DASHBOARD).json()["viewer"]["can_decide"] is True
        assert director.get(DASHBOARD).json()["viewer"]["can_remind"] is False
        assert nobody.get(DASHBOARD).status_code == 403
        assert nobody.get(f"{DASHBOARD}version/").status_code == 403

    def test_workspace_admins_read_the_whole_group(self, session_client, workspace, group):
        _task(group, "iat", "Tech", date(2026, 12, 1))
        body = session_client.get(DASHBOARD).json()
        assert [task["name"] for task in body["tasks"]] == ["Tech"]
        assert {project["identifier"] for project in body["projects"]} == {"CAP", "SEC", "IAT"}

    def test_the_version_follows_the_changes(self, session_client, workspace, group):
        issue = _task(group, "iat", "Tech", date(2026, 12, 1))
        first = session_client.get(f"{DASHBOARD}version/").json()["version"]
        assert session_client.get(f"{DASHBOARD}version/").json()["version"] == first
        IssueSteering.objects.create(issue=issue, project=issue.project, workspace=workspace, progress=40)
        assert session_client.get(f"{DASHBOARD}version/").json()["version"] != first

    def test_the_sheet_shows_the_chain_and_the_history(self, session_client, workspace, group, create_user):
        origin = _task(group, "iat", "Maquettes", timezone.now().date() - timedelta(days=5), user=create_user)
        middle = _task(group, "capital", "Développement", date(2026, 11, 1))
        end = _task(group, "securities", "Lancement", date(2026, 12, 1))
        for blocked, blocker in ((end, middle), (middle, origin)):
            IssueRelation.objects.create(
                issue=blocked,
                related_issue=blocker,
                relation_type="blocked_by",
                project=blocked.project,
                workspace=workspace,
            )
        IssueActivity.objects.create(
            issue=end,
            project=end.project,
            workspace=workspace,
            actor=create_user,
            verb="updated",
            field="target_date",
            old_value="2026-11-15",
            new_value="2026-12-01",
        )
        body = session_client.get(f"{DASHBOARD}issues/{end.id}/").json()
        assert [[item["name"] for item in level] for level in body["chain"]] == [["Développement"], ["Maquettes"]]
        assert body["chain"][1][0]["signal"] == "late"
        assert body["chain"][1][0]["assignees"] == [create_user.display_name]
        assert [line["field"] for line in body["history"]] == ["target_date"]

        _, manager = _member(workspace, "entite@iag.com", "entity_manager", entity=group["entities"]["iat"])
        assert manager.get(f"{DASHBOARD}issues/{end.id}/").status_code == 404
        assert manager.get(f"{DASHBOARD}issues/{origin.id}/").status_code == 200
