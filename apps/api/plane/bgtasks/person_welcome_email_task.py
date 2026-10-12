# Copyright (c) 2023-present Plane Software, Inc. and contributors
# SPDX-License-Identifier: AGPL-3.0-only
# See the LICENSE file for details.

# Python imports
import logging

# Third party imports
from celery import shared_task

# Django imports
from django.core.mail import EmailMultiAlternatives, get_connection
from django.template.loader import render_to_string

# Module imports
from plane.db.models import User, Workspace
from plane.license.utils.instance_value import get_email_configuration
from plane.utils.email import generate_plain_text_from_html
from plane.utils.exception_logger import log_exception


@shared_task
def person_welcome_email(current_site, user_id, added_by_id, workspace_slug):
    """Tell a pre-registered person that their access is ready and how to sign in."""
    try:
        user = User.objects.get(pk=user_id)
        added_by = User.objects.get(pk=added_by_id)
        workspace = Workspace.objects.get(slug=workspace_slug)
        context = {
            "first_name": user.first_name,
            "added_by": added_by.display_name if not added_by.first_name else added_by.first_name,
            "workspace_name": workspace.name,
            "email": user.email,
            "sign_in_url": current_site,
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

        html_content = render_to_string("emails/user/person_welcome.html", context)
        connection = get_connection(
            host=EMAIL_HOST,
            port=int(EMAIL_PORT),
            username=EMAIL_HOST_USER,
            password=EMAIL_HOST_PASSWORD,
            use_tls=EMAIL_USE_TLS == "1",
            use_ssl=EMAIL_USE_SSL == "1",
        )
        message = EmailMultiAlternatives(
            subject=f"Votre accès à Infinity Planning ({workspace.name})",
            body=generate_plain_text_from_html(html_content),
            from_email=EMAIL_FROM,
            to=[user.email],
            connection=connection,
        )
        message.attach_alternative(html_content, "text/html")
        message.send()
        logging.getLogger("plane.worker").info("Welcome email sent.")
    except Exception as e:
        log_exception(e)
