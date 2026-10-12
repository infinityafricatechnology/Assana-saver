# Copyright (c) 2023-present Plane Software, Inc. and contributors
# SPDX-License-Identifier: AGPL-3.0-only
# See the LICENSE file for details.

"""
The weekly report (cahier des charges §9.3): prepared on Fridays at noon from the COMEX export, then
commented, arranged and sent by the Cabinet or the CEO. Its figures stay frozen until « Actualiser »;
the version sent is archived as it was.
"""

# Python imports
from datetime import date
from typing import Any, Dict, List, Optional, Tuple

# Django imports
from django.core.exceptions import ValidationError
from django.core.validators import validate_email
from django.db import IntegrityError, transaction
from django.utils import timezone

# Module imports
from plane.db.models import SteeringReportStatus, SteeringWeeklyReport, User, WorkspaceMember
from plane.utils.steering_alerts import profile_member_ids
from plane.utils.steering_dashboard import Portfolio, Scope, today_in_abidjan
from plane.utils.steering_exports import SECTIONS, ReportOptions, comex_data, render_comex_pdf

MAX_TEXT = 4000
MAX_EXTRA_EMAILS = 50


class ReportError(ValueError):
    def __init__(self, message: str, code: str):
        super().__init__(message)
        self.code = code


def iso_week(day: date) -> Tuple[int, int]:
    year, week, _ = day.isocalendar()
    return year, week


def _fresh_data(workspace_id) -> Dict[str, Any]:
    return comex_data(Portfolio(workspace_id, Scope(whole_group=True)))


def prepare_report(workspace_id, today: Optional[date] = None) -> Tuple[SteeringWeeklyReport, bool]:
    """
    The draft of the week, created once (on Fridays at noon, or earlier on demand), addressed by
    default to the Cabinet and the CEO.
    """
    year, week = iso_week(today or today_in_abidjan())
    existing = SteeringWeeklyReport.objects.filter(workspace_id=workspace_id, year=year, week=week).first()
    if existing:
        return existing, False
    try:
        with transaction.atomic():
            report = SteeringWeeklyReport.objects.create(
                workspace_id=workspace_id,
                year=year,
                week=week,
                data=_fresh_data(workspace_id),
                refreshed_at=timezone.now(),
                sections=[{"key": key, "visible": True} for key in SECTIONS],
                recipient_ids=profile_member_ids(workspace_id, "ceo", "cabinet"),
            )
    except IntegrityError:
        return SteeringWeeklyReport.objects.get(workspace_id=workspace_id, year=year, week=week), False
    return report, True


def _require_draft(report: SteeringWeeklyReport) -> None:
    if report.status != SteeringReportStatus.DRAFT:
        raise ReportError("A sent report is archived as it was.", "already_sent")


def refresh(report: SteeringWeeklyReport) -> SteeringWeeklyReport:
    """« Actualiser »: the figures of the moment, the comments kept."""
    _require_draft(report)
    report.data = _fresh_data(report.workspace_id)
    report.refreshed_at = timezone.now()
    report.save(update_fields=["data", "refreshed_at", "updated_at"])
    return report


def _clean_comments(value: Any, name: str) -> Dict[str, str]:
    if not isinstance(value, dict) or not all(
        isinstance(key, str) and isinstance(text, str) for key, text in value.items()
    ):
        raise ReportError(f"'{name}' must map ids to texts.", "invalid_comments")
    return {key: text.strip()[:MAX_TEXT] for key, text in value.items() if text.strip()}


def _clean_ids(value: Any, name: str) -> List[str]:
    if not isinstance(value, list) or not all(isinstance(item, str) for item in value):
        raise ReportError(f"'{name}' must be a list of ids.", "invalid_ids")
    return list(dict.fromkeys(value))


def update_report(report: SteeringWeeklyReport, data: Dict[str, Any]) -> SteeringWeeklyReport:
    """The introduction, comments, highlights, order of the sections and recipients (§9.3)."""
    _require_draft(report)
    changed = []
    if "intro" in data:
        report.intro = str(data["intro"] or "").strip()[:MAX_TEXT]
        changed.append("intro")
    if "sections" in data:
        sections = data["sections"]
        keys = [section.get("key") for section in sections] if isinstance(sections, list) else []
        if sorted(keys) != sorted(SECTIONS) or not all(isinstance(section, dict) for section in sections):
            raise ReportError("Every section appears once.", "invalid_sections")
        report.sections = [
            {"key": section["key"], "visible": bool(section.get("visible", True))} for section in sections
        ]
        changed.append("sections")
    for name in ("section_comments", "entity_comments", "task_comments"):
        if name in data:
            setattr(report, name, _clean_comments(data[name], name))
            changed.append(name)
    for name in ("highlighted_tasks", "highlighted_entities"):
        if name in data:
            setattr(report, name, _clean_ids(data[name], name))
            changed.append(name)
    if "recipient_ids" in data:
        ids = _clean_ids(data["recipient_ids"], "recipient_ids")
        members = {
            str(member_id)
            for member_id in WorkspaceMember.objects.filter(
                workspace_id=report.workspace_id, member_id__in=ids, is_active=True
            ).values_list("member_id", flat=True)
        }
        if set(ids) - members:
            raise ReportError("Recipients are members of the workspace.", "invalid_recipients")
        report.recipient_ids = ids
        changed.append("recipient_ids")
    if "extra_emails" in data:
        emails = data["extra_emails"]
        if not isinstance(emails, list) or len(emails) > MAX_EXTRA_EMAILS:
            raise ReportError("'extra_emails' is a list of e-mail addresses.", "invalid_emails")
        cleaned = []
        for email in emails:
            email = str(email or "").strip().lower()
            try:
                validate_email(email)
            except ValidationError:
                raise ReportError(f"Invalid e-mail address: {email}.", "invalid_emails")
            cleaned.append(email)
        report.extra_emails = list(dict.fromkeys(cleaned))
        changed.append("extra_emails")
    if changed:
        report.save(update_fields=[*changed, "updated_at"])
    return report


def report_options(report: SteeringWeeklyReport) -> ReportOptions:
    return ReportOptions(
        title=f"Rapport hebdomadaire — semaine {report.week} ({report.year})",
        intro=report.intro,
        sections=report.sections or [{"key": key, "visible": True} for key in SECTIONS],
        section_comments=report.section_comments,
        entity_comments=report.entity_comments,
        task_comments=report.task_comments,
        highlighted_tasks=report.highlighted_tasks,
        highlighted_entities=report.highlighted_entities,
    )


def render_report(report: SteeringWeeklyReport) -> bytes:
    """The PDF: the archive once sent, the preview of the draft otherwise."""
    if report.status == SteeringReportStatus.SENT and report.sent_pdf:
        return bytes(report.sent_pdf)
    return render_comex_pdf(report.data, report_options(report))


def recipient_emails(report: SteeringWeeklyReport) -> List[str]:
    users = User.objects.filter(pk__in=report.recipient_ids, is_active=True).values_list("email", flat=True)
    return list(dict.fromkeys([*users, *report.extra_emails]))


@transaction.atomic
def send_report(report: SteeringWeeklyReport, actor: User) -> SteeringWeeklyReport:
    """« Envoyer »: the PDF is archived as sent, then e-mailed to the recipients."""
    _require_draft(report)
    if not recipient_emails(report):
        raise ReportError("The report has no recipient.", "no_recipient")
    report.sent_pdf = render_comex_pdf(report.data, report_options(report))
    report.status = SteeringReportStatus.SENT
    report.sent_at = timezone.now()
    report.sent_by = actor
    report.save(update_fields=["sent_pdf", "status", "sent_at", "sent_by", "updated_at"])

    from plane.bgtasks.steering_report_email_task import steering_report_email

    transaction.on_commit(lambda: steering_report_email.delay(str(report.id)))
    return report
