# Copyright (c) 2023-present Plane Software, Inc. and contributors
# SPDX-License-Identifier: AGPL-3.0-only
# See the LICENSE file for details.

"""The weekly report (§9.3): prepared on Fridays, commented, refreshed, sent and archived (§10)."""

from datetime import date, timedelta
from unittest import mock

import pytest
from django.utils import timezone
from rest_framework.test import APIClient

from plane.bgtasks.steering_jobs_task import steering_friday_noon
from plane.bgtasks.steering_report_email_task import steering_report_email
from plane.db.models import (
    Branch,
    Entity,
    Issue,
    Project,
    ProjectSteering,
    State,
    SteeringProfile,
    SteeringWeeklyReport,
    User,
    WorkspaceMember,
)

REPORTS = "/api/workspaces/test-workspace/steering/reports/"


def _person(workspace, email, role=None, **profile):
    user = User.objects.create(email=email, username=email.split("@")[0], first_name=email.split("@")[0].title())
    WorkspaceMember.objects.create(workspace=workspace, member=user, role=15)
    if role:
        SteeringProfile.objects.create(workspace=workspace, member=user, role=role, **profile)
    client = APIClient()
    client.force_authenticate(user=user)
    return user, client


@pytest.fixture
def portfolio(workspace):
    branch = Branch.objects.create(workspace=workspace, name="Technologie")
    entity = Entity.objects.create(workspace=workspace, branch=branch, name="Infinity Africa Technologies")
    project = Project.objects.create(name="IAT", identifier="IAT", workspace=workspace)
    ProjectSteering.objects.create(project=project, workspace=workspace, entity=entity)
    State.objects.create(project=project, workspace=workspace, name="En cours", group="started", default=True)
    late = Issue.objects.create(
        project=project, workspace=workspace, name="Offre MDM", target_date=timezone.now().date() - timedelta(days=9)
    )
    return {"branch": branch, "entity": entity, "project": project, "late": late}


@pytest.fixture
def cabinet(workspace):
    return _person(workspace, "cabinet@iag.com", "cabinet")


@pytest.fixture
def ceo(workspace):
    return _person(workspace, "pdg@iag.com", "ceo")


@pytest.mark.contract
@pytest.mark.django_db
class TestPreparation:
    def test_friday_noon_prepares_the_draft_once(self, workspace, portfolio, cabinet, ceo):
        with mock.patch("plane.bgtasks.steering_report_email_task.steering_report_ready_email.delay") as ready:
            steering_friday_noon()
            steering_friday_noon()
        report = SteeringWeeklyReport.objects.get(workspace=workspace)
        assert ready.call_count == 1
        assert report.status == "draft"
        assert report.data["kpis"]["late"] == 1
        assert sorted(report.recipient_ids) == sorted([str(cabinet[0].id), str(ceo[0].id)])

    def test_only_the_cabinet_and_the_ceo(self, workspace, portfolio, cabinet):
        _, director = _person(workspace, "pole@iag.com", "branch_director", branch=portfolio["branch"])
        assert director.get(REPORTS).status_code == 403
        assert director.post(REPORTS).status_code == 403
        assert cabinet[1].post(REPORTS).status_code == 201
        assert cabinet[1].post(REPORTS).status_code == 200
        assert len(cabinet[1].get(REPORTS).json()) == 1

    def test_the_dashboard_announces_the_draft(self, workspace, portfolio, cabinet):
        dashboard = "/api/workspaces/test-workspace/steering/dashboard/"
        assert cabinet[1].get(dashboard).json()["report_ready"] is None
        report = cabinet[1].post(REPORTS).json()
        assert cabinet[1].get(dashboard).json()["report_ready"] == {"id": report["id"], "week": report["week"]}


@pytest.mark.contract
@pytest.mark.django_db
class TestEditing:
    def test_comments_sections_and_recipients(self, workspace, portfolio, cabinet, ceo):
        report = cabinet[1].post(REPORTS).json()
        url = f"{REPORTS}{report['id']}/"
        sections = [
            {"key": key, "visible": key != "blocking"} for key in ("queue", "kpis", "delays", "situation", "blocking")
        ]
        body = (
            cabinet[1]
            .patch(
                url,
                {
                    "intro": "Semaine chargée.",
                    "sections": sections,
                    "section_comments": {"delays": "Concentrés sur IAT."},
                    "task_comments": {str(portfolio["late"].id): "Relance faite.", "vide": "  "},
                    "highlighted_tasks": [str(portfolio["late"].id)],
                    "recipient_ids": [str(ceo[0].id)],
                    "extra_emails": ["Comex@Infinity-Africa.com"],
                },
                format="json",
            )
            .json()
        )
        assert body["sections"][0] == {"key": "queue", "visible": True}
        assert body["task_comments"] == {str(portfolio["late"].id): "Relance faite."}
        assert body["extra_emails"] == ["comex@infinity-africa.com"]

        assert cabinet[1].patch(url, {"sections": sections[:3]}, format="json").json()["code"] == "invalid_sections"
        outsider = User.objects.create(email="ailleurs@x.com", username="ailleurs")
        assert (
            cabinet[1].patch(url, {"recipient_ids": [str(outsider.id)]}, format="json").json()["code"]
            == "invalid_recipients"
        )
        assert (
            cabinet[1].patch(url, {"extra_emails": ["pas-un-mail"]}, format="json").json()["code"] == "invalid_emails"
        )

    def test_refresh_keeps_the_comments(self, workspace, portfolio, cabinet):
        report = cabinet[1].post(REPORTS).json()
        url = f"{REPORTS}{report['id']}/"
        cabinet[1].patch(url, {"intro": "Gardée."}, format="json")
        Issue.objects.create(
            project=portfolio["project"],
            workspace=workspace,
            name="Nouveau retard",
            target_date=timezone.now().date() - timedelta(days=2),
        )
        assert cabinet[1].get(url).json()["data"]["kpis"]["late"] == 1
        body = cabinet[1].post(f"{url}refresh/").json()
        assert body["data"]["kpis"]["late"] == 2
        assert body["intro"] == "Gardée."

    def test_preview(self, workspace, portfolio, cabinet):
        report = cabinet[1].post(REPORTS).json()
        response = cabinet[1].get(f"{REPORTS}{report['id']}/pdf/")
        assert response.status_code == 200
        assert response.content.startswith(b"%PDF")


@pytest.mark.contract
@pytest.mark.django_db
class TestSending:
    def test_send_archives_then_e_mails(self, workspace, portfolio, cabinet, django_capture_on_commit_callbacks):
        report = cabinet[1].post(REPORTS).json()
        url = f"{REPORTS}{report['id']}/"
        cabinet[1].patch(url, {"recipient_ids": []}, format="json")
        assert cabinet[1].post(f"{url}send/").json()["code"] == "no_recipient"

        cabinet[1].patch(url, {"recipient_ids": [str(cabinet[0].id)], "intro": "Bonne lecture."}, format="json")
        with mock.patch("plane.bgtasks.steering_report_email_task.steering_report_email.delay") as email:
            with django_capture_on_commit_callbacks(execute=True):
                body = cabinet[1].post(f"{url}send/").json()
        assert body["status"] == "sent"
        email.assert_called_once_with(report["id"])
        archived = SteeringWeeklyReport.objects.get(pk=report["id"])
        assert bytes(archived.sent_pdf).startswith(b"%PDF")
        assert archived.sent_by_id == cabinet[0].id

        assert cabinet[1].patch(url, {"intro": "Trop tard."}, format="json").json()["code"] == "already_sent"
        assert cabinet[1].post(f"{url}refresh/").json()["code"] == "already_sent"
        assert cabinet[1].get(f"{url}pdf/").content == bytes(archived.sent_pdf)

        with mock.patch("plane.bgtasks.steering_report_email_task._send") as send:
            steering_report_email(report["id"])
        subject, context, recipients, attachment = send.call_args.args
        assert recipients == ["cabinet@iag.com"]
        assert context["paragraphs"] == ["Bonne lecture."]
        assert attachment[0].endswith(".pdf") and attachment[2] == "application/pdf"
        assert subject.startswith(f"Rapport hebdomadaire — semaine {report['week']}")


def test_iso_week_of_the_report():
    from plane.utils.steering_report import iso_week

    assert iso_week(date(2026, 10, 9)) == (2026, 41)
    assert iso_week(date(2027, 1, 1)) == (2026, 53)
