# Copyright (c) 2023-present Plane Software, Inc. and contributors
# SPDX-License-Identifier: AGPL-3.0-only
# See the LICENSE file for details.

"""
Bulk creation and update of work items, with their custom field values.

A batch is all or nothing: every item is validated first, and nothing is written if one is invalid.
"""

# Python imports
import json
import uuid
from typing import Any, Dict, List, Optional, Tuple

# Django imports
from django.core.serializers.json import DjangoJSONEncoder
from django.db import transaction
from django.utils import timezone

# Third party imports
from drf_spectacular.utils import OpenApiRequest, OpenApiResponse, inline_serializer
from rest_framework import serializers, status
from rest_framework.response import Response

# Module imports
from plane.api.serializers import IssueSerializer
from plane.app.permissions import ProjectEntityPermission
from plane.bgtasks.issue_activities_task import issue_activity
from plane.bgtasks.webhook_task import model_activity
from plane.db.models import CustomField, Issue, Project
from plane.utils.custom_field import CustomFieldValueError, clean_custom_field_value
from plane.utils.custom_field_service import attached_project_fields, set_issue_custom_field_value
from plane.utils.host import base_host
from plane.utils.openapi import work_item_docs
from plane.utils.steering_required import (
    SteeringRuleError,
    attach_steering,
    check_steered_update,
    prepare_steering_on_create,
    record_postponement,
)

from .base import BaseAPIView

MAX_BULK_WORK_ITEMS = 100

_BULK_ITEMS_HELP = (
    f"1 to {MAX_BULK_WORK_ITEMS} work items, with the fields of the single create/update endpoints, plus "
    "`custom_fields`: an object mapping a project custom field id to its value."
)
_BULK_CREATE_REQUEST = inline_serializer(
    name="WorkItemBulkCreateRequest",
    fields={"work_items": serializers.ListField(child=serializers.JSONField(), help_text=_BULK_ITEMS_HELP)},
)
_BULK_UPDATE_REQUEST = inline_serializer(
    name="WorkItemBulkUpdateRequest",
    fields={
        "work_items": serializers.ListField(
            child=serializers.JSONField(), help_text=f"{_BULK_ITEMS_HELP} Each item needs its `id`."
        )
    },
)
_BULK_RESPONSE = inline_serializer(name="WorkItemBulkResponse", fields={"work_items": IssueSerializer(many=True)})
_BULK_ERROR_RESPONSE = OpenApiResponse(
    description="At least one item is invalid; nothing was written. `errors` lists the invalid items by index."
)


def _read_items(data: Any) -> Tuple[Optional[List[Dict[str, Any]]], Optional[str]]:
    items = data.get("work_items") if isinstance(data, dict) else None
    if not isinstance(items, list) or not items:
        return None, "'work_items' must be a non-empty list."
    if len(items) > MAX_BULK_WORK_ITEMS:
        return None, f"A batch is limited to {MAX_BULK_WORK_ITEMS} work items."
    if not all(isinstance(item, dict) for item in items):
        return None, "Each work item must be an object."
    return items, None


def _clean_custom_fields(raw: Any, fields: Dict[str, CustomField]) -> Tuple[Dict[CustomField, Any], Dict[str, str]]:
    """Check the values against the project's fields; returns the raw values by field and the errors."""
    if raw is None:
        return {}, {}
    if not isinstance(raw, dict):
        return {}, {"custom_fields": "Expected an object mapping a custom field id to its value."}
    values, errors = {}, {}
    for field_id, value in raw.items():
        field = fields.get(str(field_id))
        if not field:
            errors[str(field_id)] = "This field is not part of the project."
            continue
        try:
            clean_custom_field_value(field, value)
        except CustomFieldValueError as error:
            errors[str(field_id)] = str(error)
            continue
        values[field] = value
    return values, ({"custom_fields": errors} if errors else {})


def _is_uuid(value: str) -> bool:
    try:
        uuid.UUID(value)
    except ValueError:
        return False
    return True


class WorkItemBulkAPIEndpoint(BaseAPIView):
    """Create or update up to 100 work items of a project in one request."""

    permission_classes = [ProjectEntityPermission]

    def _track(self, request, slug, project_id, issue_id, requested_data, current_instance):
        origin = base_host(request=request, is_app=True)
        issue_activity.delay(
            via=self.activity_via,
            type="issue.activity.updated" if current_instance else "issue.activity.created",
            requested_data=json.dumps(requested_data, cls=DjangoJSONEncoder),
            actor_id=str(request.user.id),
            issue_id=str(issue_id),
            project_id=str(project_id),
            current_instance=current_instance,
            epoch=int(timezone.now().timestamp()),
            notification=True,
            origin=origin,
        )
        model_activity.delay(
            model_name="issue",
            model_id=str(issue_id),
            requested_data=requested_data,
            current_instance=current_instance,
            actor_id=request.user.id,
            slug=slug,
            origin=origin,
        )

    @work_item_docs(
        operation_id="bulk_create_work_items",
        summary="Bulk create work items",
        description=(
            f"Create up to {MAX_BULK_WORK_ITEMS} work items in the project, with their custom field values. "
            "All or nothing: if one item is invalid, none is created."
        ),
        request=OpenApiRequest(request=_BULK_CREATE_REQUEST),
        responses={
            201: OpenApiResponse(description="Work items created, in request order", response=_BULK_RESPONSE),
            400: _BULK_ERROR_RESPONSE,
        },
    )
    def post(self, request, slug, project_id):
        items, error = _read_items(request.data)
        if error:
            return Response({"error": error}, status=status.HTTP_400_BAD_REQUEST)

        project = Project.objects.get(workspace__slug=slug, pk=project_id)
        fields = attached_project_fields(project_id)
        context = {
            "project_id": project_id,
            "workspace_id": project.workspace_id,
            "default_assignee_id": project.default_assignee_id,
        }
        prepared, errors = [], []
        for index, item in enumerate(items):
            data = {key: value for key, value in item.items() if key != "custom_fields"}
            serializer = IssueSerializer(data=data, context=context)
            item_errors = {} if serializer.is_valid() else dict(serializer.errors)
            custom_values, custom_errors = _clean_custom_fields(item.get("custom_fields"), fields)
            item_errors.update(custom_errors)
            # Infinity Planning (cahier des charges §4): a work item of a steered project is created complete.
            steering_changes = None
            try:
                steering_changes = prepare_steering_on_create(project, item)
            except SteeringRuleError as rule_error:
                item_errors["steering"] = rule_error.payload
            if item_errors:
                errors.append({"index": index, "errors": item_errors})
            prepared.append((serializer, data, custom_values, steering_changes))
        if errors:
            return Response({"errors": errors}, status=status.HTTP_400_BAD_REQUEST)

        created = []
        with transaction.atomic():
            for serializer, data, custom_values, steering_changes in prepared:
                issue = serializer.save()
                attach_steering(issue, steering_changes)
                issue.created_by_id = request.user.id
                issue.save(update_fields=["created_by"])
                for field, value in custom_values.items():
                    set_issue_custom_field_value(issue, field, value, request.user, via=self.activity_via)
                created.append((issue.id, data))

        for issue_id, data in created:
            self._track(request, slug, project_id, issue_id, data, None)
        issues = {issue.id: issue for issue in Issue.issue_objects.filter(pk__in=[pk for pk, _ in created])}
        return Response(
            {"work_items": [IssueSerializer(issues[pk]).data for pk, _ in created]},
            status=status.HTTP_201_CREATED,
        )

    @work_item_docs(
        operation_id="bulk_update_work_items",
        summary="Bulk update work items",
        description=(
            f"Update up to {MAX_BULK_WORK_ITEMS} work items of the project, and their custom field values. "
            "Only the fields given are changed. All or nothing: if one item is invalid, none is updated."
        ),
        request=OpenApiRequest(request=_BULK_UPDATE_REQUEST),
        responses={
            200: OpenApiResponse(description="Work items updated, in request order", response=_BULK_RESPONSE),
            400: _BULK_ERROR_RESPONSE,
        },
    )
    def patch(self, request, slug, project_id):
        items, error = _read_items(request.data)
        if error:
            return Response({"error": error}, status=status.HTTP_400_BAD_REQUEST)
        ids = [str(item.get("id") or "") for item in items]
        if not all(ids):
            return Response({"error": "Each work item needs its 'id'."}, status=status.HTTP_400_BAD_REQUEST)
        if len(set(ids)) != len(ids):
            return Response({"error": "Each work item can appear only once."}, status=status.HTTP_400_BAD_REQUEST)

        project = Project.objects.get(workspace__slug=slug, pk=project_id)
        issues = {
            str(issue.id): issue
            for issue in Issue.issue_objects.filter(
                workspace__slug=slug, project_id=project_id, pk__in=[issue_id for issue_id in ids if _is_uuid(issue_id)]
            )
        }
        fields = attached_project_fields(project_id)
        context = {"project_id": project_id, "workspace_id": project.workspace_id}
        prepared, errors = [], []
        for index, (issue_id, item) in enumerate(zip(ids, items)):
            issue = issues.get(issue_id)
            if not issue:
                errors.append({"index": index, "errors": {"id": "Unknown work item in this project."}})
                continue
            data = {key: value for key, value in item.items() if key not in ("id", "custom_fields")}
            current_instance = json.dumps(IssueSerializer(issue).data, cls=DjangoJSONEncoder)
            serializer = IssueSerializer(issue, data=data, context=context, partial=True)
            item_errors = {} if serializer.is_valid() else dict(serializer.errors)
            custom_values, custom_errors = _clean_custom_fields(item.get("custom_fields"), fields)
            item_errors.update(custom_errors)
            # Infinity Planning (§4, §9.4): steered work items keep their deadline and assignees, and a
            # postponement needs a « deadline_comment ».
            postponement = None
            try:
                postponement = check_steered_update(issue, item)
            except SteeringRuleError as rule_error:
                item_errors["steering"] = rule_error.payload
            if item_errors:
                errors.append({"index": index, "errors": item_errors})
            prepared.append((issue, serializer, data, custom_values, current_instance, postponement, issue.target_date))
        if errors:
            return Response({"errors": errors}, status=status.HTTP_400_BAD_REQUEST)

        with transaction.atomic():
            for issue, serializer, data, custom_values, _, postponement, previous_target_date in prepared:
                if data:
                    serializer.save()
                    record_postponement(issue, request.user, previous_target_date, postponement)
                for field, value in custom_values.items():
                    set_issue_custom_field_value(issue, field, value, request.user, via=self.activity_via)

        for issue, _, data, _, current_instance, *_ in prepared:
            if data:
                self._track(request, slug, project_id, issue.id, data, current_instance)
        refreshed = {issue.id: issue for issue in Issue.issue_objects.filter(pk__in=[i.id for i, *_ in prepared])}
        return Response(
            {"work_items": [IssueSerializer(refreshed[issue.id]).data for issue, *_ in prepared]},
            status=status.HTTP_200_OK,
        )
