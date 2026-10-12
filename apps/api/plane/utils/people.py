# Copyright (c) 2023-present Plane Software, Inc. and contributors
# SPDX-License-Identifier: AGPL-3.0-only
# See the LICENSE file for details.

"""
People of the organisation, managed from one place: pre-registration, roles, steering profiles,
projects, departures. A pre-registered person gets a real account and membership right away, so
they can be assigned work before their first sign-in, and they land in the organisation without
the onboarding (they sign in with a code by e-mail, or later with Microsoft).
"""

# Python imports
import time
import uuid
from dataclasses import dataclass, field
from typing import Any, Dict, Iterable, List, Optional

# Django imports
from django.core.exceptions import ValidationError
from django.core.validators import validate_email
from django.db import transaction
from django.db.models import Min
from django.utils import timezone

# Module imports
from plane.db.models import (
    APIToken,
    Branch,
    Entity,
    IssueActivity,
    IssueAssignee,
    IssueSubscriber,
    Profile,
    Project,
    ProjectMember,
    ProjectUserProperty,
    Session,
    SteeringProfile,
    SteeringProfileRole,
    User,
    Workspace,
    WorkspaceMember,
)
from plane.utils.cache import invalidate_cache_directly

ADMIN, MEMBER = 20, 15
WORKSPACE_ROLES = (ADMIN, MEMBER)
OPEN_STATE_GROUPS_EXCLUDED = ("completed", "cancelled")


class PeopleError(ValueError):
    """A request the people page refuses; `code` lets the interface show a precise message."""

    def __init__(self, message: str, code: str = "invalid"):
        super().__init__(message)
        self.code = code


@dataclass
class ProfileSpec:
    role: str
    branch_id: Optional[str] = None
    entity_id: Optional[str] = None


@dataclass
class PersonSpec:
    email: str
    first_name: str
    last_name: str = ""
    role: int = MEMBER
    profiles: List[ProfileSpec] = field(default_factory=list)
    project_ids: List[str] = field(default_factory=list)


def clean_email(value: Any) -> str:
    email = str(value or "").strip().lower()
    try:
        validate_email(email)
    except ValidationError:
        raise PeopleError("A valid e-mail address is required.", "invalid_email")
    return email


def clean_role(value: Any) -> int:
    if value in (None, ""):
        return MEMBER
    try:
        role = int(value)
    except (TypeError, ValueError):
        raise PeopleError("The role must be 20 (admin) or 15 (member).", "invalid_role")
    if role not in WORKSPACE_ROLES:
        raise PeopleError("The role must be 20 (admin) or 15 (member).", "invalid_role")
    return role


def clean_profiles(workspace: Workspace, raw: Any) -> List[ProfileSpec]:
    """Validate ``[{role, branch_id?, entity_id?}]``: a branch director needs a branch, an entity manager an entity."""
    if raw in (None, ""):
        return []
    if not isinstance(raw, list):
        raise PeopleError("profiles must be a list.", "invalid_profile")
    profiles, seen = [], set()
    for item in raw:
        if not isinstance(item, dict) or item.get("role") not in SteeringProfileRole.values:
            raise PeopleError("Unknown steering profile.", "invalid_profile")
        role = item["role"]
        branch_id = entity_id = None
        if role == SteeringProfileRole.BRANCH_DIRECTOR:
            branch = Branch.objects.filter(workspace=workspace, pk=_uuid_or_none(item.get("branch_id"))).first()
            if not branch:
                raise PeopleError("A branch director needs a branch.", "profile_scope")
            branch_id = str(branch.id)
        if role == SteeringProfileRole.ENTITY_MANAGER:
            entity = Entity.objects.filter(workspace=workspace, pk=_uuid_or_none(item.get("entity_id"))).first()
            if not entity:
                raise PeopleError("An entity manager needs an entity.", "profile_scope")
            entity_id = str(entity.id)
        key = (role, branch_id, entity_id)
        if key not in seen:
            seen.add(key)
            profiles.append(ProfileSpec(role=role, branch_id=branch_id, entity_id=entity_id))
    return profiles


def clean_project_ids(workspace: Workspace, raw: Any) -> List[str]:
    if raw in (None, ""):
        return []
    if not isinstance(raw, list):
        raise PeopleError("project_ids must be a list.", "invalid_project")
    ids = [_uuid_or_none(value) for value in raw]
    found = set(
        str(pk)
        for pk in Project.objects.filter(workspace=workspace, pk__in=[i for i in ids if i]).values_list("pk", flat=True)
    )
    if any(str(i) not in found for i in ids):
        raise PeopleError("Unknown project.", "invalid_project")
    return list(dict.fromkeys(str(i) for i in ids))


def _uuid_or_none(value: Any) -> Optional[uuid.UUID]:
    try:
        return uuid.UUID(str(value))
    except (TypeError, ValueError):
        return None


def invalidate_members_cache(workspace: Workspace) -> None:
    """Plane caches the member list that every member picker reads."""
    invalidate_cache_directly(
        path=f"/api/workspaces/{workspace.slug}/members/", url_params=False, user=False, multiple=True
    )


def set_profiles(workspace: Workspace, user: User, profiles: Iterable[ProfileSpec]) -> None:
    """Replace the steering profiles of a person."""
    SteeringProfile.objects.filter(workspace=workspace, member=user).delete(soft=False)
    SteeringProfile.objects.bulk_create(
        [
            SteeringProfile(
                workspace=workspace,
                member=user,
                role=profile.role,
                branch_id=profile.branch_id,
                entity_id=profile.entity_id,
            )
            for profile in profiles
        ]
    )


def add_to_projects(workspace: Workspace, users: List[User], project_ids: List[str], project_role: int = MEMBER) -> int:
    """
    Add people to projects as Plane does (membership and per-project properties). Organisation
    admins are always project admins, as Plane requires. Returns the number of memberships added.
    """
    workspace_roles = dict(
        WorkspaceMember.objects.filter(workspace=workspace, member__in=users, is_active=True).values_list(
            "member_id", "role"
        )
    )
    min_sort = dict(
        ProjectUserProperty.objects.filter(workspace=workspace, user__in=users)
        .values("user_id")
        .annotate(lowest=Min("sort_order"))
        .values_list("user_id", "lowest")
    )
    added = 0
    for project_id in project_ids:
        existing = {
            member.member_id: member for member in ProjectMember.objects.filter(project_id=project_id, member__in=users)
        }
        for user in users:
            role = ADMIN if workspace_roles.get(user.id) == ADMIN else project_role
            membership = existing.get(user.id)
            if membership:
                if not membership.is_active or membership.role != role:
                    membership.is_active, membership.role = True, role
                    membership.save(update_fields=["is_active", "role", "updated_at"])
                    added += 1
                continue
            ProjectMember.objects.create(project_id=project_id, workspace=workspace, member=user, role=role)
            ProjectUserProperty.objects.get_or_create(
                project_id=project_id,
                user=user,
                defaults={
                    "workspace": workspace,
                    "sort_order": (min_sort[user.id] - 10000) if min_sort.get(user.id) is not None else 65535,
                },
            )
            added += 1
    return added


@transaction.atomic
def provision_person(workspace: Workspace, spec: PersonSpec) -> User:
    """
    Create the account and membership of a new person, with role, steering profiles and projects.
    An existing account that is not yet in the organisation is added to it; a member, even
    departed, is refused (a departed person is reactivated instead).
    """
    user = User.objects.filter(email=spec.email).first()
    if user:
        membership = WorkspaceMember.objects.filter(workspace=workspace, member=user).first()
        if membership and membership.is_active and user.is_active:
            raise PeopleError("This person is already a member.", "already_member")
        if membership or not user.is_active:
            raise PeopleError("This person has left the organisation: reactivate them instead.", "departed")
    else:
        user = User(
            email=spec.email,
            username=uuid.uuid4().hex,
            first_name=spec.first_name,
            last_name=spec.last_name,
            is_password_autoset=True,
        )
        user.set_password(uuid.uuid4().hex)
        user.save()
        # Straight into the organisation at first sign-in: no profile step, no workspace creation.
        Profile.objects.create(
            user=user,
            is_onboarded=True,
            last_workspace_id=workspace.id,
            onboarding_step={
                "profile_complete": True,
                "workspace_create": True,
                "workspace_invite": True,
                "workspace_join": True,
            },
        )
    WorkspaceMember.objects.create(workspace=workspace, member=user, role=spec.role)
    set_profiles(workspace, user, spec.profiles)
    if spec.project_ids:
        add_to_projects(workspace, [user], spec.project_ids)
    invalidate_members_cache(workspace)
    return user


def open_assignments(workspace: Workspace, user: User):
    """Assignments of the person on work items that are not closed (Plane state or steering status)."""
    return (
        IssueAssignee.objects.filter(
            workspace=workspace,
            assignee=user,
            issue__deleted_at__isnull=True,
            issue__archived_at__isnull=True,
            issue__is_draft=False,
        )
        .exclude(issue__state__group__in=OPEN_STATE_GROUPS_EXCLUDED)
        .exclude(issue__steering__status__in=("done", "cancelled"))
        .select_related("issue")
    )


@transaction.atomic
def depart_person(workspace: Workspace, user: User, actor: User, reassign_to: Optional[User]) -> Dict[str, int]:
    """
    A person leaves: their open work items go to ``reassign_to`` (or stay unassigned), then the
    account is closed everywhere (organisation, projects, sessions, API and Claude tokens) and
    their steering profiles are removed. The history of their work is kept.
    """
    if user.id == actor.id:
        raise PeopleError("You cannot record your own departure.", "self")
    if reassign_to and reassign_to.id == user.id:
        raise PeopleError("Choose someone else to take over the work items.", "invalid_reassign")

    assignments = list(open_assignments(workspace, user))
    epoch = int(time.time())
    activities = []
    for assignment in assignments:
        issue = assignment.issue
        if reassign_to:
            add_to_projects(workspace, [reassign_to], [str(issue.project_id)])
            _, created = IssueAssignee.objects.get_or_create(
                issue=issue, assignee=reassign_to, defaults={"project_id": issue.project_id, "workspace": workspace}
            )
            if created:
                IssueSubscriber.objects.get_or_create(
                    issue=issue,
                    subscriber=reassign_to,
                    defaults={"project_id": issue.project_id, "workspace": workspace},
                )
                activities.append(
                    IssueActivity(
                        issue=issue,
                        actor=actor,
                        verb="updated",
                        old_value="",
                        new_value=reassign_to.display_name,
                        field="assignees",
                        project_id=issue.project_id,
                        workspace=workspace,
                        comment="added assignee ",
                        new_identifier=reassign_to.id,
                        epoch=epoch,
                    )
                )
        activities.append(
            IssueActivity(
                issue=issue,
                actor=actor,
                verb="updated",
                old_value=user.display_name,
                new_value="",
                field="assignees",
                project_id=issue.project_id,
                workspace=workspace,
                comment="removed assignee ",
                old_identifier=user.id,
                epoch=epoch,
            )
        )
    IssueAssignee.objects.filter(pk__in=[assignment.pk for assignment in assignments]).delete()
    IssueActivity.objects.bulk_create(activities)

    ProjectMember.objects.filter(workspace=workspace, member=user, is_active=True).update(
        is_active=False, updated_at=timezone.now()
    )
    WorkspaceMember.objects.filter(workspace=workspace, member=user).update(is_active=False, updated_at=timezone.now())
    SteeringProfile.objects.filter(workspace=workspace, member=user).delete(soft=False)
    APIToken.objects.filter(user=user, is_active=True).update(is_active=False)
    Session.objects.filter(user_id=user.id).delete()

    user.is_active = False
    user.last_logout_time = timezone.now()
    user.save(update_fields=["is_active", "last_logout_time"])
    invalidate_members_cache(workspace)
    return {"reassigned": len(assignments) if reassign_to else 0, "unassigned": 0 if reassign_to else len(assignments)}


@transaction.atomic
def reactivate_person(workspace: Workspace, user: User, role: int) -> None:
    """Give a departed person their access back; their projects are restored, their profiles are not."""
    membership = WorkspaceMember.objects.filter(workspace=workspace, member=user).first()
    if not membership:
        raise PeopleError("This person was never a member.", "not_member")
    if membership.is_active and user.is_active:
        raise PeopleError("This person is already active.", "already_member")
    membership.is_active, membership.role = True, role
    membership.save(update_fields=["is_active", "role", "updated_at"])
    ProjectMember.objects.filter(workspace=workspace, member=user).update(is_active=True, updated_at=timezone.now())
    user.is_active = True
    user.save(update_fields=["is_active"])
    invalidate_members_cache(workspace)
