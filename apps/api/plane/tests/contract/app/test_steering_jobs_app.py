# Copyright (c) 2023-present Plane Software, Inc. and contributors
# SPDX-License-Identifier: AGPL-3.0-only
# See the LICENSE file for details.

"""The periodic work of the steering space (§9): calendar alerts, lifted blocks, reminders, snapshots."""

from datetime import date, datetime, timedelta
from unittest import mock

import pytest
from django.utils import timezone

from plane.bgtasks.steering_jobs_task import steering_daily_alerts, steering_friday_noon
from plane.db.models import (
    Branch,
    Entity,
    Issue,
    IssueAssignee,
    IssueRelation,
    IssueSteering,
    Notification,
    Project,
    ProjectSteering,
    State,
    SteeringProfile,
    SteeringReminder,
    SteeringSnapshot,
    SteeringSubmission,
    User,
    WorkspaceMember,
)
from plane.utils.steering_dashboard import Scope
from plane.utils.steering_jobs import daily_alerts, take_snapshot, trend, unblock_alerts, weekly_reminders

TODAY = date(2026, 10, 7)


@pytest.fixture(autouse=True)
def no_email():
    with mock.patch("plane.bgtasks.steering_alert_email_task.steering_alert_email.delay") as delay:
        yield delay


def _person(workspace, email, role=None):
    user = User.objects.create(email=email, username=email.split("@")[0])
    WorkspaceMember.objects.create(workspace=workspace, member=user, role=15)
    if role:
        SteeringProfile.objects.create(workspace=workspace, member=user, role=role)
    return user


@pytest.fixture
def setup(workspace, create_user):
    branch = Branch.objects.create(workspace=workspace, name="Technologie")
    entity = Entity.objects.create(workspace=workspace, branch=branch, name="Infinity Africa Technologies")
    project = Project.objects.create(name="IAT", identifier="IAT", workspace=workspace)
    ProjectSteering.objects.create(project=project, workspace=workspace, entity=entity)
    started = State.objects.create(project=project, workspace=workspace, name="En cours", group="started")
    done = State.objects.create(project=project, workspace=workspace, name="Terminé", group="completed")
    return {
        "project": project,
        "entity": entity,
        "started": started,
        "done": done,
        "assignee": _person(workspace, "responsable@iag.com"),
        "supervisor": _person(workspace, "superviseur@iag.com"),
        "cabinet": _person(workspace, "cabinet@iag.com", "cabinet"),
        "ceo": _person(workspace, "pdg@iag.com", "ceo"),
    }


def _task(setup, name, target, **steering):
    project = setup["project"]
    issue = Issue.objects.create(
        project=project, workspace=project.workspace, name=name, state=setup["started"], target_date=target
    )
    IssueAssignee.objects.create(issue=issue, assignee=setup["assignee"], project=project, workspace=project.workspace)
    IssueSteering.objects.create(
        issue=issue, project=project, workspace=project.workspace, supervisor=setup["supervisor"], **steering
    )
    return issue


def _alerts(user, event=None):
    alerts = Notification.objects.filter(receiver=user, data__issue_activity__field="steering_alert")
    if event:
        alerts = alerts.filter(data__issue_activity__new_value=event)
    return [alert.data["issue"]["name"] for alert in alerts]


@pytest.mark.contract
@pytest.mark.django_db
class TestDailyAlerts:
    def test_calendar_alerts_go_once(self, workspace, setup):
        _task(setup, "Bientôt", TODAY + timedelta(days=3))
        _task(setup, "En retard", TODAY - timedelta(days=5))
        _task(setup, "Critique", TODAY - timedelta(days=40))

        first = daily_alerts(workspace.id, TODAY)
        assert first == {"deadline_soon": 1, "late": 2, "critical": 3}
        assert _alerts(setup["assignee"], "deadline_soon") == ["Bientôt"]
        assert _alerts(setup["supervisor"], "late") == ["En retard"]
        assert _alerts(setup["cabinet"], "critical") == ["Critique"]
        assert daily_alerts(workspace.id, TODAY) == {}

    def test_blocker_submission_and_risk(self, workspace, setup):
        blocker = _task(setup, "Maquettes", TODAY - timedelta(days=2))
        blocked = _task(setup, "Plateforme", TODAY + timedelta(days=60))
        IssueRelation.objects.create(
            issue=blocked,
            related_issue=blocker,
            relation_type="blocked_by",
            project=setup["project"],
            workspace=workspace,
        )
        submitted = _task(
            setup,
            "Agrément",
            TODAY + timedelta(days=60),
            status="in_validation",
            risk_nature="regulatory",
            risk_effective_date=TODAY + timedelta(days=5),
        )
        SteeringSubmission.objects.create(
            issue=submitted,
            project=setup["project"],
            workspace=workspace,
            submitted_by=setup["assignee"],
            submitted_at=timezone.make_aware(datetime(2026, 9, 28, 9, 0)),
            message="À valider",
        )
        sent = daily_alerts(workspace.id, TODAY)
        assert sent["blocker_late"] == 1
        assert "Plateforme" in _alerts(setup["assignee"], "blocker_late")
        assert _alerts(setup["ceo"], "submission_overdue") == ["Agrément"]
        assert _alerts(setup["cabinet"], "submission_overdue") == ["Agrément"]
        assert _alerts(setup["ceo"], "risk_soon") == ["Agrément"]

    def test_the_celery_task_covers_every_steered_workspace(self, workspace, setup):
        _task(setup, "Bientôt", timezone.now().date() + timedelta(days=3))
        assert steering_daily_alerts() == {str(workspace.id): {"deadline_soon": 1}}


@pytest.mark.contract
@pytest.mark.django_db
class TestUnblock:
    def test_closing_a_blocker_alerts_once(self, workspace, setup):
        blocker = _task(setup, "Maquettes", TODAY)
        blocked = _task(setup, "Plateforme", TODAY + timedelta(days=30))
        IssueRelation.objects.create(
            issue=blocked,
            related_issue=blocker,
            relation_type="blocked_by",
            project=setup["project"],
            workspace=workspace,
        )
        assert unblock_alerts(workspace.id) == 0
        IssueSteering.objects.filter(issue=blocker).update(status="done", updated_at=timezone.now())
        assert unblock_alerts(workspace.id) == 1
        assert _alerts(setup["assignee"], "unblocked") == ["Plateforme"]
        assert unblock_alerts(workspace.id) == 0

    def test_a_relation_to_a_closed_work_item_never_blocked(self, workspace, setup):
        blocker = _task(setup, "Cadrage", TODAY, status="done")
        IssueSteering.objects.filter(issue=blocker).update(updated_at=timezone.now() - timedelta(days=3))
        blocked = _task(setup, "Plateforme", TODAY + timedelta(days=30))
        IssueRelation.objects.create(
            issue=blocked,
            related_issue=blocker,
            relation_type="blocked_by",
            project=setup["project"],
            workspace=workspace,
        )
        assert unblock_alerts(workspace.id) == 0


@pytest.mark.contract
@pytest.mark.django_db
class TestWeekly:
    def test_automatic_reminders(self, workspace, setup):
        dormant = _task(setup, "Oubliée", TODAY + timedelta(days=30), status="in_progress")
        old = timezone.now() - timedelta(days=60)
        Issue.objects.filter(pk=dormant.pk).update(updated_at=old)
        IssueSteering.objects.filter(issue=dormant).update(updated_at=old)
        _task(setup, "Pas démarrée", TODAY - timedelta(days=2), status="to_start")
        _task(setup, "À jour", TODAY + timedelta(days=30), status="in_progress")

        assert weekly_reminders(workspace.id, TODAY) == 2
        reasons = dict(SteeringReminder.objects.filter(sent_by__isnull=True).values_list("issue__name", "reason"))
        assert reasons == {"Oubliée": "dormant", "Pas démarrée": "inconsistent"}
        assert sorted(_alerts(setup["assignee"], "reminder_auto")) == ["Oubliée", "Pas démarrée"]

    def test_snapshot_and_scoped_trend(self, workspace, setup):
        other_branch = Branch.objects.create(workspace=workspace, name="Immobilier")
        other_entity = Entity.objects.create(workspace=workspace, branch=other_branch, name="SCI Infinity")
        _task(setup, "Retard", TODAY - timedelta(days=10))
        take_snapshot(workspace.id, TODAY - timedelta(days=7))
        _task(setup, "Critique", TODAY - timedelta(days=45))
        snapshot = take_snapshot(workspace.id, TODAY)
        assert snapshot.entities[str(setup["entity"].id)] == {
            "open": 2,
            "late": 2,
            "critical": 1,
            "blocked": 0,
            "queue": 0,
        }
        assert take_snapshot(workspace.id, TODAY).pk == snapshot.pk

        branches = {str(setup["entity"].id): str(setup["entity"].branch_id), str(other_entity.id): str(other_branch.id)}
        whole = trend(workspace.id, Scope(whole_group=True), branches)
        assert [(point["date"], point["late"]) for point in whole] == [("2026-09-30", 1), ("2026-10-07", 2)]
        elsewhere = trend(workspace.id, Scope(entity_ids={str(other_entity.id)}), branches)
        assert [point["late"] for point in elsewhere] == [0, 0]

    def test_friday_noon(self, workspace, setup):
        _task(setup, "Retard", timezone.now().date() - timedelta(days=4))
        steering_friday_noon()
        assert SteeringSnapshot.objects.filter(workspace=workspace).count() == 1
