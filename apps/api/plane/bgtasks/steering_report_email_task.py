# Copyright (c) 2023-present Plane Software, Inc. and contributors
# SPDX-License-Identifier: AGPL-3.0-only
# See the LICENSE file for details.

"""E-mails of the weekly report (§9.3), in French: the draft is ready; the report is sent."""

# Python imports
import logging
from typing import List

# Third party imports
from celery import shared_task

# Django imports
from django.conf import settings
from django.core.mail import EmailMultiAlternatives, get_connection
from django.template.loader import render_to_string

# Module imports
from plane.db.models import SteeringEmailPreference, SteeringWeeklyReport, User
from plane.license.utils.instance_value import get_email_configuration
from plane.utils.email import generate_plain_text_from_html
from plane.utils.exception_logger import log_exception
from plane.utils.steering_alerts import profile_member_ids
from plane.utils.steering_report import recipient_emails


def _send(subject: str, context: dict, recipients: List[str], attachment: tuple = None) -> None:
    (
        EMAIL_HOST,
        EMAIL_HOST_USER,
        EMAIL_HOST_PASSWORD,
        EMAIL_PORT,
        EMAIL_USE_TLS,
        EMAIL_USE_SSL,
        EMAIL_FROM,
    ) = get_email_configuration()
    html_content = render_to_string("emails/notifications/steering_report.html", context)
    connection = get_connection(
        host=EMAIL_HOST,
        port=int(EMAIL_PORT),
        username=EMAIL_HOST_USER,
        password=EMAIL_HOST_PASSWORD,
        use_tls=EMAIL_USE_TLS == "1",
        use_ssl=EMAIL_USE_SSL == "1",
    )
    for email in recipients:
        message = EmailMultiAlternatives(
            subject=subject,
            body=generate_plain_text_from_html(html_content),
            from_email=EMAIL_FROM,
            to=[email],
            connection=connection,
        )
        message.attach_alternative(html_content, "text/html")
        if attachment:
            message.attach(*attachment)
        message.send()


def _steering_url(report: SteeringWeeklyReport) -> str:
    return f"{(settings.WEB_URL or '').rstrip('/')}/{report.workspace.slug}/steering/"


@shared_task
def steering_report_ready_email(report_id):
    """« Projet de rapport hebdomadaire prêt » to the Cabinet and the CEO (§9.2), unless they muted e-mails."""
    try:
        report = SteeringWeeklyReport.objects.select_related("workspace").get(pk=report_id)
        ids = profile_member_ids(report.workspace_id, "ceo", "cabinet")
        muted = {
            str(user_id)
            for user_id in SteeringEmailPreference.objects.filter(user_id__in=ids, emails_enabled=False).values_list(
                "user_id", flat=True
            )
        }
        recipients = list(
            User.objects.filter(pk__in=[i for i in ids if i not in muted], is_active=True).values_list(
                "email", flat=True
            )
        )
        if not recipients:
            return
        title = f"Projet de rapport hebdomadaire prêt — semaine {report.week}"
        _send(
            title,
            {
                "title": title,
                "situation": report.data.get("situation", ""),
                "paragraphs": [
                    "Le projet de rapport de la semaine est prêt dans l'espace de pilotage.",
                    "Vous pouvez le commenter, choisir et ordonner ses sections, ajuster les destinataires, "
                    "l'actualiser puis l'envoyer.",
                ],
                "button_url": _steering_url(report),
                "button_label": "Ouvrir le rapport",
            },
            recipients,
        )
        logging.getLogger("plane.worker").info("Steering report draft announced.")
    except Exception as e:
        log_exception(e)


@shared_task
def steering_report_email(report_id):
    """The report sent by the Cabinet or the CEO, with the archived PDF attached."""
    try:
        report = SteeringWeeklyReport.objects.select_related("workspace", "sent_by").get(pk=report_id)
        recipients = recipient_emails(report)
        if not recipients or not report.sent_pdf:
            return
        title = f"Rapport hebdomadaire — semaine {report.week} ({report.year})"
        _send(
            f"{title} · Infinity Africa Group",
            {
                "title": title,
                "situation": report.data.get("situation", ""),
                "paragraphs": [paragraph for paragraph in report.intro.split("\n") if paragraph.strip()]
                or ["Veuillez trouver ci-joint le rapport hebdomadaire de l'espace de pilotage."],
                "note": f"Envoyé par {report.sent_by.display_name}" if report.sent_by else "",
                "button_url": _steering_url(report),
                "button_label": "Ouvrir l'espace de pilotage",
            },
            recipients,
            (f"rapport-hebdomadaire-{report.year}-s{report.week:02d}.pdf", bytes(report.sent_pdf), "application/pdf"),
        )
        logging.getLogger("plane.worker").info("Steering report e-mailed.")
    except Exception as e:
        log_exception(e)
