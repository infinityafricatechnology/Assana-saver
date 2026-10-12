# Copyright (c) 2023-present Plane Software, Inc. and contributors
# SPDX-License-Identifier: AGPL-3.0-only
# See the LICENSE file for details.

# Python imports
import logging

# Third party imports
from celery import shared_task

# Django imports
from django.conf import settings
from django.core.mail import EmailMultiAlternatives, get_connection
from django.template.loader import render_to_string

# Module imports
from plane.db.models import Issue, User
from plane.license.utils.instance_value import get_email_configuration
from plane.utils.email import generate_plain_text_from_html
from plane.utils.exception_logger import log_exception
from plane.utils.steering_alerts import EVENTS


@shared_task
def steering_alert_email(issue_id, event, recipient_ids, detail, actor_name):
    """E-mail version of a steering alert (§9.2), in French, with a link to the work item."""
    try:
        issue = Issue.all_objects.select_related("project", "workspace").get(pk=issue_id)
        recipients = list(User.objects.filter(pk__in=recipient_ids, is_active=True).values_list("email", flat=True))
        if not recipients:
            return
        base_url = (settings.WEB_URL or "").rstrip("/")
        identifier = f"{issue.project.identifier}-{issue.sequence_id}"
        context = {
            "title": EVENTS[event].title,
            "issue_name": issue.name,
            "identifier": identifier,
            "project_name": issue.project.name,
            "detail": detail,
            "actor_name": actor_name,
            "issue_url": f"{base_url}/{issue.workspace.slug}/browse/{identifier}/",
            "preferences_url": f"{base_url}/settings/profile/notifications",
        }
        (
            EMAIL_HOST,
            EMAIL_HOST_USER,
            EMAIL_HOST_PASSWORD,
            EMAIL_PORT,
            EMAIL_USE_TLS,
            EMAIL_USE_SSL,
            EMAIL_FROM,
        ) = get_email_configuration()
        html_content = render_to_string("emails/notifications/steering_alert.html", context)
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
                subject=f"{context['title']} · {identifier} {issue.name}",
                body=generate_plain_text_from_html(html_content),
                from_email=EMAIL_FROM,
                to=[email],
                connection=connection,
            )
            message.attach_alternative(html_content, "text/html")
            message.send()
        logging.getLogger("plane.worker").info("Steering alert e-mailed.")
    except Exception as e:
        log_exception(e)
