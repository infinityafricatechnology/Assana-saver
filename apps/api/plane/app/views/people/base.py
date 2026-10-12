# Copyright (c) 2023-present Plane Software, Inc. and contributors
# SPDX-License-Identifier: AGPL-3.0-only
# See the LICENSE file for details.

"""The « Personnes » page: everyone in the organisation, managed by its administrators."""

# Python imports
from collections import defaultdict
from typing import Any, Dict, List

# Django imports
from django.db import transaction
from django.http import HttpResponse

# Third party imports
from rest_framework import status
from rest_framework.response import Response

# Module imports
from plane.bgtasks.person_welcome_email_task import person_welcome_email
from plane.db.models import (
    Branch,
    Entity,
    Project,
    ProjectMember,
    SteeringProfile,
    User,
    Workspace,
    WorkspaceMember,
)
from plane.utils.host import base_host
from plane.utils.people import (
    ADMIN,
    MEMBER,
    PeopleError,
    PersonSpec,
    add_to_projects,
    clean_email,
    clean_profiles,
    clean_project_ids,
    clean_role,
    depart_person,
    invalidate_members_cache,
    open_assignments,
    provision_person,
    reactivate_person,
    set_profiles,
)
from plane.utils.people_import import export_csv, parse_rows, read_table

from ..base import BaseAPIView
from ..steering.base import _profile_payload

MAX_IMPORT_SIZE = 2 * 1024 * 1024


def _error(error: PeopleError, status_code=status.HTTP_400_BAD_REQUEST) -> Response:
    return Response({"error": str(error), "code": error.code}, status=status_code)


def _status(membership: WorkspaceMember, user: User) -> str:
    if not membership.is_active or not user.is_active:
        return "departed"
    return "pending" if user.last_login_time is None else "active"


def people_payload(workspace: Workspace, user_ids: List[Any] = None) -> List[Dict[str, Any]]:
    """Every member (departed ones included) with role, status, steering profiles and projects."""
    memberships = WorkspaceMember.objects.filter(workspace=workspace, member__is_bot=False).select_related("member")
    if user_ids is not None:
        memberships = memberships.filter(member_id__in=user_ids)
    profiles = defaultdict(list)
    for profile in SteeringProfile.objects.filter(workspace=workspace).order_by("created_at"):
        profiles[profile.member_id].append(_profile_payload(profile))
    projects = defaultdict(list)
    for member_id, project_id, role in ProjectMember.objects.filter(
        workspace=workspace, is_active=True, project__archived_at__isnull=True
    ).values_list("member_id", "project_id", "role"):
        projects[member_id].append({"project_id": str(project_id), "role": role})

    people = []
    for membership in memberships.order_by("member__first_name", "member__last_name", "member__email"):
        user = membership.member
        people.append(
            {
                "id": str(user.id),
                "membership_id": str(membership.id),
                "email": user.email,
                "first_name": user.first_name,
                "last_name": user.last_name,
                "display_name": user.display_name,
                "avatar_url": user.avatar_url,
                "role": membership.role,
                "status": _status(membership, user),
                "last_login_time": user.last_login_time,
                "date_joined": user.date_joined,
                "profiles": profiles.get(user.id, []),
                "projects": projects.get(user.id, []),
            }
        )
    return people


class PeopleAdminView(BaseAPIView):
    """The people page is for the organisation's administrators."""

    def initial(self, request, *args, **kwargs):
        super().initial(request, *args, **kwargs)
        self.workspace = Workspace.objects.get(slug=kwargs["slug"])
        self.is_admin = WorkspaceMember.objects.filter(
            workspace=self.workspace, member=request.user, role=ADMIN, is_active=True
        ).exists()

    def forbidden(self) -> Response:
        return Response(
            {"error": "Only the organisation's administrators manage people.", "code": "forbidden"},
            status=status.HTTP_403_FORBIDDEN,
        )

    def get_person(self, user_id) -> User:
        return WorkspaceMember.objects.select_related("member").get(workspace=self.workspace, member_id=user_id).member

    def welcome(self, request, user: User) -> None:
        person_welcome_email.delay(
            base_host(request=request, is_app=True), str(user.id), str(request.user.id), self.workspace.slug
        )


class PeopleEndpoint(PeopleAdminView):
    def get(self, request, slug):
        if not self.is_admin:
            return self.forbidden()
        return Response(people_payload(self.workspace), status=status.HTTP_200_OK)

    def post(self, request, slug):
        """Pre-register one person: account, role, steering profiles and projects in one go."""
        if not self.is_admin:
            return self.forbidden()
        try:
            first_name = str(request.data.get("first_name") or "").strip()[:255]
            if not first_name:
                raise PeopleError("The first name is required.", "missing_first_name")
            spec = PersonSpec(
                email=clean_email(request.data.get("email")),
                first_name=first_name,
                last_name=str(request.data.get("last_name") or "").strip()[:255],
                role=clean_role(request.data.get("role")),
                profiles=clean_profiles(self.workspace, request.data.get("profiles")),
                project_ids=clean_project_ids(self.workspace, request.data.get("project_ids")),
            )
            user = provision_person(self.workspace, spec)
        except PeopleError as error:
            return _error(error)
        if request.data.get("send_email", True):
            self.welcome(request, user)
        return Response(people_payload(self.workspace, [user.id])[0], status=status.HTTP_201_CREATED)


class PersonDetailEndpoint(PeopleAdminView):
    def patch(self, request, slug, user_id):
        """Names, role in the organisation and steering profiles (replaced as a whole)."""
        if not self.is_admin:
            return self.forbidden()
        user = self.get_person(user_id)
        membership = WorkspaceMember.objects.get(workspace=self.workspace, member=user)
        try:
            with transaction.atomic():
                if "role" in request.data:
                    role = clean_role(request.data["role"])
                    if user.id == request.user.id and role != ADMIN:
                        raise PeopleError("You cannot remove your own administrator role.", "self")
                    other_admins = WorkspaceMember.objects.filter(
                        workspace=self.workspace, role=ADMIN, is_active=True, member__is_active=True
                    ).exclude(member=user)
                    if role != ADMIN and membership.role == ADMIN and not other_admins.exists():
                        raise PeopleError("The organisation needs at least one administrator.", "last_admin")
                    membership.role = role
                    membership.save(update_fields=["role", "updated_at"])
                    if role == ADMIN:
                        # Plane requires organisation admins to be admins of their projects.
                        ProjectMember.objects.filter(workspace=self.workspace, member=user).update(role=ADMIN)
                if "first_name" in request.data or "last_name" in request.data:
                    first_name = str(request.data.get("first_name", user.first_name) or "").strip()[:255]
                    if not first_name:
                        raise PeopleError("The first name is required.", "missing_first_name")
                    user.first_name = first_name
                    user.last_name = str(request.data.get("last_name", user.last_name) or "").strip()[:255]
                    user.save(update_fields=["first_name", "last_name"])
                if "profiles" in request.data:
                    set_profiles(self.workspace, user, clean_profiles(self.workspace, request.data["profiles"]))
        except PeopleError as error:
            return _error(error)
        invalidate_members_cache(self.workspace)
        return Response(people_payload(self.workspace, [user.id])[0], status=status.HTTP_200_OK)


class PeopleProjectsEndpoint(PeopleAdminView):
    def post(self, request, slug):
        """Add several people to several projects at once."""
        if not self.is_admin:
            return self.forbidden()
        user_ids = request.data.get("user_ids") or []
        try:
            project_ids = clean_project_ids(self.workspace, request.data.get("project_ids"))
            project_role = clean_role(request.data.get("role"))
            if not project_ids or not isinstance(user_ids, list) or not user_ids:
                raise PeopleError("Choose people and projects.", "missing_selection")
        except PeopleError as error:
            return _error(error)
        users = list(
            User.objects.filter(
                pk__in=[user_id for user_id in user_ids if isinstance(user_id, str)],
                member_workspace__workspace=self.workspace,
                member_workspace__is_active=True,
                is_active=True,
            ).distinct()
        )
        if len(users) != len(set(user_ids)):
            return _error(PeopleError("Only active members can join projects.", "inactive_member"))
        added = add_to_projects(self.workspace, users, project_ids, project_role)
        return Response(
            {"added": added, "people": people_payload(self.workspace, [user.id for user in users])},
            status=status.HTTP_200_OK,
        )


class PersonDepartureEndpoint(PeopleAdminView):
    def get(self, request, slug, user_id):
        """What a departure would change: the open work items to hand over."""
        if not self.is_admin:
            return self.forbidden()
        user = self.get_person(user_id)
        return Response({"open_work_items": open_assignments(self.workspace, user).count()}, status=status.HTTP_200_OK)

    def post(self, request, slug, user_id):
        if not self.is_admin:
            return self.forbidden()
        user = self.get_person(user_id)
        reassign_to = None
        if request.data.get("reassign_to"):
            reassign_to = User.objects.filter(
                pk=request.data["reassign_to"],
                member_workspace__workspace=self.workspace,
                member_workspace__is_active=True,
                is_active=True,
            ).first()
            if not reassign_to:
                return _error(PeopleError("Hand the work items over to an active member.", "invalid_reassign"))
        try:
            result = depart_person(self.workspace, user, request.user, reassign_to)
        except PeopleError as error:
            return _error(error)
        return Response({**result, "person": people_payload(self.workspace, [user.id])[0]}, status=status.HTTP_200_OK)


class PersonReactivationEndpoint(PeopleAdminView):
    def post(self, request, slug, user_id):
        if not self.is_admin:
            return self.forbidden()
        user = self.get_person(user_id)
        try:
            reactivate_person(self.workspace, user, clean_role(request.data.get("role", MEMBER)))
        except PeopleError as error:
            return _error(error)
        if request.data.get("send_email", True):
            self.welcome(request, user)
        return Response(people_payload(self.workspace, [user.id])[0], status=status.HTTP_200_OK)


class PeopleImportEndpoint(PeopleAdminView):
    def post(self, request, slug):
        """
        Upload a .csv or .xlsx file. With ``confirm`` false (the default), nothing is written: every
        line comes back with its errors, for a preview. With ``confirm`` true, the valid new people
        are created and the others are reported.
        """
        if not self.is_admin:
            return self.forbidden()
        upload = request.FILES.get("file")
        if not upload:
            return _error(PeopleError("Attach a .csv or .xlsx file.", "missing_file"))
        if upload.size > MAX_IMPORT_SIZE:
            return _error(PeopleError("The file is too large (2 MB at most).", "file_too_large"))
        try:
            rows = parse_rows(self.workspace, read_table(upload.name, upload.read()))
        except PeopleError as error:
            return _error(error)

        existing = set(
            WorkspaceMember.objects.filter(
                workspace=self.workspace, member__email__in=[row["spec"].email for row in rows if row["spec"]]
            ).values_list("member__email", flat=True)
        )
        for row in rows:
            if row["spec"] and row["spec"].email in existing:
                row["errors"].append("already_member")
                row["spec"] = None

        confirm = str(request.data.get("confirm", "")).lower() in ("1", "true")
        created = []
        if confirm:
            send_email = str(request.data.get("send_email", "true")).lower() in ("1", "true")
            for row in rows:
                if not row["spec"]:
                    continue
                try:
                    user = provision_person(self.workspace, row["spec"])
                except PeopleError as error:
                    row["errors"].append(error.code)
                    continue
                created.append(user.id)
                row["created"] = True
                if send_email:
                    self.welcome(request, user)

        return Response(
            {
                "rows": [
                    {
                        "line": row["line"],
                        "values": row["values"],
                        "errors": row["errors"],
                        "valid": not row["errors"],
                        "created": bool(row.get("created")),
                    }
                    for row in rows
                ],
                "created": len(created),
            },
            status=status.HTTP_200_OK,
        )


class PeopleExportEndpoint(PeopleAdminView):
    def get(self, request, slug):
        if not self.is_admin:
            return self.forbidden()
        content = export_csv(
            people_payload(self.workspace),
            branches={str(b.id): b.name for b in Branch.objects.filter(workspace=self.workspace)},
            entities={str(e.id): e.name for e in Entity.objects.filter(workspace=self.workspace)},
            projects={str(p.id): p.identifier for p in Project.objects.filter(workspace=self.workspace)},
        )
        response = HttpResponse(content, content_type="text/csv; charset=utf-8")
        response["Content-Disposition"] = f'attachment; filename="personnes-{self.workspace.slug}.csv"'
        return response
