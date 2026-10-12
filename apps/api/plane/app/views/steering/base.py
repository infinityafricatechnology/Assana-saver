# Copyright (c) 2023-present Plane Software, Inc. and contributors
# SPDX-License-Identifier: AGPL-3.0-only
# See the LICENSE file for details.

"""Group referential (branches, entities, categories), steering profiles and project entities."""

# Python imports
import time
from typing import Any, Dict, Optional

# Django imports
from django.db import IntegrityError, transaction
from django.db.models import Max

# Third party imports
from rest_framework import status
from rest_framework.response import Response

# Module imports
from plane.app.permissions import ROLE, allow_permission
from plane.db.models import (
    Branch,
    Entity,
    Issue,
    IssueActivity,
    IssueSteering,
    Project,
    ProjectMember,
    ProjectSteering,
    SteeringCategory,
    SteeringProfile,
    SteeringProfileRole,
    Workspace,
    WorkspaceMember,
)
from plane.utils.steering import (
    SteeringValueError,
    apply_steering_changes,
    clean_steering_changes,
    display_steering_value,
    missing_steering_fields,
)

from ..base import BaseAPIView
from .circuit import circuit_payload

# Starting referential from the specification (cahier des charges §3.1 and §4).
DEFAULT_BRANCHES = [
    ("Finance & Capital Markets", ["Infinity Africa Capital", "Infinity Africa Securities", "Sinsi Advisory SAS"]),
    ("Immobilier", ["Infinity Africa Properties", "SCI Infinity"]),
    ("Industrie & Mines", ["Infinity Africa Mining", "MINAFRICA", "Africa Mining Logistics"]),
    ("Technologie", ["Infinity Africa Technologies"]),
    ("Sports & Divertissement", ["Infinity Sports SAS"]),
    (
        "Fonctions Groupe",
        [
            "Direction générale & cabinet",
            "Finance Groupe",
            "Ressources humaines",
            "Juridique & conformité",
            "Agence de communication interne",
            "Systèmes d'information",
            "Achats & services généraux",
        ],
    ),
    ("Portefeuille", ["Amane Finance", "CRINIS CARE"]),
    ("Impact & philanthropie", ["Fin4Impact", "Fondation Maconi"]),
]
DEFAULT_CATEGORIES = ["Agréments", "Gouvernance", "Partenariats", "Développement"]

ADMIN_PROFILE_ROLES = (SteeringProfileRole.CEO, SteeringProfileRole.CABINET)


def _error(message: str, status_code=status.HTTP_400_BAD_REQUEST) -> Response:
    return Response({"error": message}, status=status_code)


def can_administer_referential(user, workspace_slug: str) -> bool:
    """Workspace admins, the CEO and the Cabinet administer the referential (§3.1, §10)."""
    is_workspace_admin = WorkspaceMember.objects.filter(
        workspace__slug=workspace_slug, member=user, role=ROLE.ADMIN.value, is_active=True
    ).exists()
    return (
        is_workspace_admin
        or SteeringProfile.objects.filter(
            workspace__slug=workspace_slug, member=user, role__in=ADMIN_PROFILE_ROLES
        ).exists()
    )


def _clean_name(value: Any) -> Optional[str]:
    if not isinstance(value, str) or not value.strip():
        return None
    return value.strip()[:255]


def _next_sort_order(queryset) -> float:
    return (queryset.aggregate(largest=Max("sort_order"))["largest"] or 0) + 1000


def _branch_payload(branch: Branch) -> Dict[str, Any]:
    return {"id": str(branch.id), "name": branch.name, "sort_order": branch.sort_order}


def _entity_payload(entity: Entity) -> Dict[str, Any]:
    return {
        "id": str(entity.id),
        "name": entity.name,
        "branch_id": str(entity.branch_id),
        "sort_order": entity.sort_order,
    }


def _category_payload(category: SteeringCategory) -> Dict[str, Any]:
    return {"id": str(category.id), "name": category.name, "sort_order": category.sort_order}


def _profile_payload(profile: SteeringProfile) -> Dict[str, Any]:
    return {
        "id": str(profile.id),
        "member_id": str(profile.member_id),
        "role": profile.role,
        "branch_id": str(profile.branch_id) if profile.branch_id else None,
        "entity_id": str(profile.entity_id) if profile.entity_id else None,
    }


def _referential_payload(user, slug: str) -> Dict[str, Any]:
    return {
        "branches": [_branch_payload(branch) for branch in Branch.objects.filter(workspace__slug=slug)],
        "entities": [
            _entity_payload(entity)
            for entity in Entity.objects.filter(workspace__slug=slug, branch__deleted_at__isnull=True)
        ],
        "categories": [
            _category_payload(category) for category in SteeringCategory.objects.filter(workspace__slug=slug)
        ],
        "can_administer": can_administer_referential(user, slug),
        "my_profiles": [
            _profile_payload(profile) for profile in SteeringProfile.objects.filter(workspace__slug=slug, member=user)
        ],
    }


class SteeringReferentialEndpoint(BaseAPIView):
    """The whole referential, readable by every member (to pick an entity or a category)."""

    @allow_permission([ROLE.ADMIN, ROLE.MEMBER], level="WORKSPACE")
    def get(self, request, slug):
        return Response(_referential_payload(request.user, slug), status=status.HTTP_200_OK)


class SteeringAdminView(BaseAPIView):
    """Base view: every mutation of the referential is reserved to its administrators."""

    def initial(self, request, *args, **kwargs):
        super().initial(request, *args, **kwargs)
        self.workspace = Workspace.objects.get(slug=kwargs["slug"])
        self.is_referential_admin = can_administer_referential(request.user, kwargs["slug"])

    def forbidden(self) -> Response:
        return _error(
            "Only the CEO, the Cabinet and workspace admins can change the Group referential.",
            status.HTTP_403_FORBIDDEN,
        )


class SteeringBootstrapEndpoint(SteeringAdminView):
    """Fill an empty referential with the branches, entities and categories of the specification."""

    def post(self, request, slug):
        if not self.is_referential_admin:
            return self.forbidden()
        if Branch.objects.filter(workspace=self.workspace).exists():
            return _error("The referential already has branches.")
        with transaction.atomic():
            for branch_index, (branch_name, entity_names) in enumerate(DEFAULT_BRANCHES):
                branch = Branch.objects.create(
                    workspace=self.workspace, name=branch_name, sort_order=(branch_index + 1) * 1000
                )
                for entity_index, entity_name in enumerate(entity_names):
                    Entity.objects.create(
                        workspace=self.workspace,
                        branch=branch,
                        name=entity_name,
                        sort_order=(entity_index + 1) * 1000,
                    )
            for category_index, category_name in enumerate(DEFAULT_CATEGORIES):
                SteeringCategory.objects.get_or_create(
                    workspace=self.workspace,
                    name=category_name,
                    defaults={"sort_order": (category_index + 1) * 1000},
                )
        return Response(_referential_payload(request.user, slug), status=status.HTTP_201_CREATED)


class SteeringBranchEndpoint(SteeringAdminView):
    def post(self, request, slug):
        if not self.is_referential_admin:
            return self.forbidden()
        name = _clean_name(request.data.get("name"))
        if not name:
            return _error("A name is required.")
        try:
            with transaction.atomic():
                branch = Branch.objects.create(
                    workspace=self.workspace,
                    name=name,
                    sort_order=_next_sort_order(Branch.objects.filter(workspace=self.workspace)),
                )
        except IntegrityError:
            return _error("A branch with this name already exists.")
        return Response(_branch_payload(branch), status=status.HTTP_201_CREATED)


class SteeringBranchDetailEndpoint(SteeringAdminView):
    def patch(self, request, slug, pk):
        if not self.is_referential_admin:
            return self.forbidden()
        branch = Branch.objects.get(workspace=self.workspace, pk=pk)
        if "name" in request.data:
            name = _clean_name(request.data["name"])
            if not name:
                return _error("A name is required.")
            branch.name = name
        if isinstance(request.data.get("sort_order"), (int, float)):
            branch.sort_order = request.data["sort_order"]
        try:
            with transaction.atomic():
                branch.save()
        except IntegrityError:
            return _error("A branch with this name already exists.")
        return Response(_branch_payload(branch), status=status.HTTP_200_OK)

    def delete(self, request, slug, pk):
        if not self.is_referential_admin:
            return self.forbidden()
        branch = Branch.objects.get(workspace=self.workspace, pk=pk)
        if branch.entities.exists():
            return _error("Move or delete the entities of this branch first.")
        branch.delete()
        return Response(status=status.HTTP_204_NO_CONTENT)


class SteeringEntityEndpoint(SteeringAdminView):
    def post(self, request, slug):
        if not self.is_referential_admin:
            return self.forbidden()
        name = _clean_name(request.data.get("name"))
        if not name:
            return _error("A name is required.")
        branch = Branch.objects.filter(workspace=self.workspace, pk=request.data.get("branch_id")).first()
        if not branch:
            return _error("A valid branch_id is required.")
        try:
            with transaction.atomic():
                entity = Entity.objects.create(
                    workspace=self.workspace,
                    branch=branch,
                    name=name,
                    sort_order=_next_sort_order(branch.entities.all()),
                )
        except IntegrityError:
            return _error("An entity with this name already exists.")
        return Response(_entity_payload(entity), status=status.HTTP_201_CREATED)


class SteeringEntityDetailEndpoint(SteeringAdminView):
    def patch(self, request, slug, pk):
        if not self.is_referential_admin:
            return self.forbidden()
        entity = Entity.objects.get(workspace=self.workspace, pk=pk)
        if "name" in request.data:
            name = _clean_name(request.data["name"])
            if not name:
                return _error("A name is required.")
            entity.name = name
        if "branch_id" in request.data:
            branch = Branch.objects.filter(workspace=self.workspace, pk=request.data["branch_id"]).first()
            if not branch:
                return _error("A valid branch_id is required.")
            entity.branch = branch
        if isinstance(request.data.get("sort_order"), (int, float)):
            entity.sort_order = request.data["sort_order"]
        try:
            with transaction.atomic():
                entity.save()
        except IntegrityError:
            return _error("An entity with this name already exists.")
        return Response(_entity_payload(entity), status=status.HTTP_200_OK)

    def delete(self, request, slug, pk):
        if not self.is_referential_admin:
            return self.forbidden()
        entity = Entity.objects.get(workspace=self.workspace, pk=pk)
        if (
            ProjectSteering.objects.filter(entity=entity).exists()
            or IssueSteering.objects.filter(entity=entity).exists()
        ):
            return _error("Projects or work items are carried by this entity: assign them to another entity first.")
        with transaction.atomic():
            entity.profiles.all().delete()
            entity.delete()
        return Response(status=status.HTTP_204_NO_CONTENT)


class SteeringCategoryEndpoint(SteeringAdminView):
    def post(self, request, slug):
        if not self.is_referential_admin:
            return self.forbidden()
        name = _clean_name(request.data.get("name"))
        if not name:
            return _error("A name is required.")
        try:
            with transaction.atomic():
                category = SteeringCategory.objects.create(
                    workspace=self.workspace,
                    name=name,
                    sort_order=_next_sort_order(SteeringCategory.objects.filter(workspace=self.workspace)),
                )
        except IntegrityError:
            return _error("A category with this name already exists.")
        return Response(_category_payload(category), status=status.HTTP_201_CREATED)


class SteeringCategoryDetailEndpoint(SteeringAdminView):
    def patch(self, request, slug, pk):
        if not self.is_referential_admin:
            return self.forbidden()
        category = SteeringCategory.objects.get(workspace=self.workspace, pk=pk)
        name = _clean_name(request.data.get("name"))
        if not name:
            return _error("A name is required.")
        category.name = name
        try:
            with transaction.atomic():
                category.save()
        except IntegrityError:
            return _error("A category with this name already exists.")
        return Response(_category_payload(category), status=status.HTTP_200_OK)

    def delete(self, request, slug, pk):
        if not self.is_referential_admin:
            return self.forbidden()
        category = SteeringCategory.objects.get(workspace=self.workspace, pk=pk)
        if IssueSteering.objects.filter(category=category).exists():
            return _error("Work items use this category: change their category first.")
        category.delete()
        return Response(status=status.HTTP_204_NO_CONTENT)


class SteeringProfileEndpoint(SteeringAdminView):
    def get(self, request, slug):
        if not self.is_referential_admin:
            return self.forbidden()
        profiles = SteeringProfile.objects.filter(workspace=self.workspace).order_by("role", "created_at")
        return Response([_profile_payload(profile) for profile in profiles], status=status.HTTP_200_OK)

    def post(self, request, slug):
        if not self.is_referential_admin:
            return self.forbidden()
        role = request.data.get("role")
        if role not in SteeringProfileRole.values:
            return _error("Unknown role.")
        member_id = request.data.get("member_id")
        if not WorkspaceMember.objects.filter(workspace=self.workspace, member_id=member_id, is_active=True).exists():
            return _error("The person must be a member of the workspace.")
        branch = entity = None
        if role == SteeringProfileRole.BRANCH_DIRECTOR:
            branch = Branch.objects.filter(workspace=self.workspace, pk=request.data.get("branch_id")).first()
            if not branch:
                return _error("A branch director needs a branch.")
        if role == SteeringProfileRole.ENTITY_MANAGER:
            entity = Entity.objects.filter(workspace=self.workspace, pk=request.data.get("entity_id")).first()
            if not entity:
                return _error("An entity manager needs an entity.")
        try:
            with transaction.atomic():
                profile = SteeringProfile.objects.create(
                    workspace=self.workspace, member_id=member_id, role=role, branch=branch, entity=entity
                )
        except IntegrityError:
            return _error("This person already has this profile.")
        return Response(_profile_payload(profile), status=status.HTTP_201_CREATED)


class SteeringProfileDetailEndpoint(SteeringAdminView):
    def delete(self, request, slug, pk):
        if not self.is_referential_admin:
            return self.forbidden()
        SteeringProfile.objects.get(workspace=self.workspace, pk=pk).delete()
        return Response(status=status.HTTP_204_NO_CONTENT)


class ProjectSteeringEndpoint(BaseAPIView):
    """The entity carrying a project (§3: every project is carried by exactly one entity)."""

    @allow_permission([ROLE.ADMIN, ROLE.MEMBER])
    def get(self, request, slug, project_id):
        steering = ProjectSteering.objects.filter(project_id=project_id).first()
        return Response(
            {"entity_id": str(steering.entity_id) if steering else None},
            status=status.HTTP_200_OK,
        )

    def put(self, request, slug, project_id):
        project = Project.objects.get(pk=project_id, workspace__slug=slug)
        is_project_admin = ProjectMember.objects.filter(
            project=project, member=request.user, role=ROLE.ADMIN.value, is_active=True
        ).exists()
        if not (is_project_admin or can_administer_referential(request.user, slug)):
            return _error("Only project admins and the Cabinet can set the carrying entity.", status.HTTP_403_FORBIDDEN)
        entity = Entity.objects.filter(workspace__slug=slug, pk=request.data.get("entity_id")).first()
        if not entity:
            return _error("A valid entity_id is required.")
        steering = ProjectSteering.objects.filter(project=project).first()
        if steering:
            steering.entity = entity
            steering.save(update_fields=["entity", "updated_at", "updated_by"])
        else:
            ProjectSteering.objects.create(project=project, workspace=project.workspace, entity=entity)
        return Response({"entity_id": str(entity.id)}, status=status.HTTP_200_OK)


def _issue_steering_payload(issue: Issue, steering: Optional[IssueSteering]) -> Dict[str, Any]:
    project_entity_id = (
        ProjectSteering.objects.filter(project_id=issue.project_id).values_list("entity_id", flat=True).first()
    )
    record = steering or IssueSteering(issue=issue)

    def as_text(value):
        return str(value) if value else None

    return {
        "issue_id": str(issue.id),
        "entity_id": as_text(record.entity_id),
        "project_entity_id": as_text(project_entity_id),
        "category_id": as_text(record.category_id),
        "supervisor_id": as_text(record.supervisor_id),
        "approver_id": as_text(record.approver_id),
        "status": record.status,
        "progress": record.progress,
        "waiting_for": record.waiting_for or None,
        "waiting_since": record.waiting_since,
        "risk_nature": record.risk_nature or None,
        "risk_effective_date": record.risk_effective_date,
        "risk_description": record.risk_description,
        "closure_date": record.closure_date,
        "closure_comment": record.closure_comment,
        "situation": record.situation,
        "situation_updated_at": record.situation_updated_at,
        "updated_at": steering.updated_at if steering else None,
        "missing": missing_steering_fields(issue, steering, project_entity_id),
        "circuit": circuit_payload(issue),
    }


class IssueSteeringEndpoint(BaseAPIView):
    """The steering record of a work item (§4), edited from the work item and kept in its history."""

    @allow_permission([ROLE.ADMIN, ROLE.MEMBER])
    def get(self, request, slug, project_id, issue_id):
        issue = Issue.issue_objects.get(project_id=project_id, pk=issue_id)
        steering = IssueSteering.objects.filter(issue=issue).first()
        return Response(_issue_steering_payload(issue, steering), status=status.HTTP_200_OK)

    @allow_permission([ROLE.ADMIN, ROLE.MEMBER])
    def patch(self, request, slug, project_id, issue_id):
        issue = Issue.issue_objects.get(project_id=project_id, pk=issue_id)
        steering = IssueSteering.objects.filter(issue=issue).first() or IssueSteering(
            issue=issue, project_id=project_id, workspace_id=issue.workspace_id
        )
        try:
            changes = clean_steering_changes(request.data, issue.workspace_id)
            changed = apply_steering_changes(steering, changes)
        except SteeringValueError as error:
            return _error(str(error))

        if changed or steering._state.adding:
            epoch = int(time.time())
            with transaction.atomic():
                steering.save()
                IssueActivity.objects.bulk_create(
                    IssueActivity(
                        issue=issue,
                        project_id=project_id,
                        workspace_id=issue.workspace_id,
                        actor=request.user,
                        verb="updated",
                        field="steering",
                        old_value=display_steering_value(key, old),
                        new_value=display_steering_value(key, new),
                        comment=key,
                        epoch=epoch,
                    )
                    for key, old, new in changed
                )
        return Response(_issue_steering_payload(issue, steering), status=status.HTTP_200_OK)
