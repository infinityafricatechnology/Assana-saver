# Copyright (c) 2023-present Plane Software, Inc. and contributors
# SPDX-License-Identifier: AGPL-3.0-only
# See the LICENSE file for details.

"""The weekly report (cahier des charges §9.3), prepared and sent by the Cabinet or the CEO (§10)."""

# Python imports
from typing import Any, Dict

# Django imports
from django.http import HttpResponse

# Third party imports
from rest_framework import status
from rest_framework.response import Response

# Module imports
from plane.app.permissions import ROLE, allow_permission
from plane.db.models import SteeringWeeklyReport, Workspace
from plane.utils.steering_circuit import is_cabinet_or_ceo
from plane.utils.steering_report import ReportError, prepare_report, refresh, render_report, send_report, update_report

from ..base import BaseAPIView


def _summary(report: SteeringWeeklyReport) -> Dict[str, Any]:
    return {
        "id": str(report.id),
        "year": report.year,
        "week": report.week,
        "status": report.status,
        "refreshed_at": report.refreshed_at.isoformat(),
        "sent_at": report.sent_at.isoformat() if report.sent_at else None,
        "sent_by": report.sent_by.display_name if report.sent_by else None,
        "situation": report.data.get("situation", ""),
    }


def _detail(report: SteeringWeeklyReport) -> Dict[str, Any]:
    return {
        **_summary(report),
        "intro": report.intro,
        "sections": report.sections,
        "section_comments": report.section_comments,
        "entity_comments": report.entity_comments,
        "task_comments": report.task_comments,
        "highlighted_tasks": report.highlighted_tasks,
        "highlighted_entities": report.highlighted_entities,
        "recipient_ids": report.recipient_ids,
        "extra_emails": report.extra_emails,
        "data": report.data,
    }


def _error(error: ReportError) -> Response:
    return Response({"error": str(error), "code": error.code}, status=status.HTTP_400_BAD_REQUEST)


class _ReportView(BaseAPIView):
    def workspace_or_none(self, request, slug):
        workspace = Workspace.objects.get(slug=slug)
        return workspace if is_cabinet_or_ceo(request.user, workspace.id) else None

    @staticmethod
    def forbidden() -> Response:
        return Response(
            {"error": "Only the Cabinet and the CEO prepare the weekly report.", "code": "not_cabinet"},
            status=status.HTTP_403_FORBIDDEN,
        )


class SteeringReportsEndpoint(_ReportView):
    """The reports of the workspace, newest first; POST prepares the one of the week if needed."""

    @allow_permission([ROLE.ADMIN, ROLE.MEMBER, ROLE.GUEST], level="WORKSPACE")
    def get(self, request, slug):
        workspace = self.workspace_or_none(request, slug)
        if not workspace:
            return self.forbidden()
        reports = SteeringWeeklyReport.objects.filter(workspace=workspace).select_related("sent_by")
        return Response([_summary(report) for report in reports], status=status.HTTP_200_OK)

    @allow_permission([ROLE.ADMIN, ROLE.MEMBER, ROLE.GUEST], level="WORKSPACE")
    def post(self, request, slug):
        workspace = self.workspace_or_none(request, slug)
        if not workspace:
            return self.forbidden()
        report, created = prepare_report(workspace.id)
        return Response(_detail(report), status=status.HTTP_201_CREATED if created else status.HTTP_200_OK)


class SteeringReportEndpoint(_ReportView):
    @allow_permission([ROLE.ADMIN, ROLE.MEMBER, ROLE.GUEST], level="WORKSPACE")
    def get(self, request, slug, report_id):
        workspace = self.workspace_or_none(request, slug)
        if not workspace:
            return self.forbidden()
        report = SteeringWeeklyReport.objects.select_related("sent_by").get(workspace=workspace, pk=report_id)
        return Response(_detail(report), status=status.HTTP_200_OK)

    @allow_permission([ROLE.ADMIN, ROLE.MEMBER, ROLE.GUEST], level="WORKSPACE")
    def patch(self, request, slug, report_id):
        workspace = self.workspace_or_none(request, slug)
        if not workspace:
            return self.forbidden()
        report = SteeringWeeklyReport.objects.get(workspace=workspace, pk=report_id)
        try:
            update_report(report, request.data)
        except ReportError as error:
            return _error(error)
        return Response(_detail(report), status=status.HTTP_200_OK)


class SteeringReportRefreshEndpoint(_ReportView):
    """« Actualiser »: the figures of the moment, the comments kept."""

    @allow_permission([ROLE.ADMIN, ROLE.MEMBER, ROLE.GUEST], level="WORKSPACE")
    def post(self, request, slug, report_id):
        workspace = self.workspace_or_none(request, slug)
        if not workspace:
            return self.forbidden()
        report = SteeringWeeklyReport.objects.get(workspace=workspace, pk=report_id)
        try:
            refresh(report)
        except ReportError as error:
            return _error(error)
        return Response(_detail(report), status=status.HTTP_200_OK)


class SteeringReportPdfEndpoint(_ReportView):
    """The preview of a draft, or the archive of a sent report."""

    @allow_permission([ROLE.ADMIN, ROLE.MEMBER, ROLE.GUEST], level="WORKSPACE")
    def get(self, request, slug, report_id):
        workspace = self.workspace_or_none(request, slug)
        if not workspace:
            return self.forbidden()
        report = SteeringWeeklyReport.objects.get(workspace=workspace, pk=report_id)
        response = HttpResponse(render_report(report), content_type="application/pdf")
        response["Content-Disposition"] = (
            f'attachment; filename="rapport-hebdomadaire-{report.year}-s{report.week:02d}.pdf"'
        )
        return response


class SteeringReportSendEndpoint(_ReportView):
    """« Envoyer »: archived as it is, then e-mailed with the PDF."""

    @allow_permission([ROLE.ADMIN, ROLE.MEMBER, ROLE.GUEST], level="WORKSPACE")
    def post(self, request, slug, report_id):
        workspace = self.workspace_or_none(request, slug)
        if not workspace:
            return self.forbidden()
        report = SteeringWeeklyReport.objects.get(workspace=workspace, pk=report_id)
        try:
            send_report(report, request.user)
        except ReportError as error:
            return _error(error)
        return Response(_detail(report), status=status.HTTP_200_OK)
