# Copyright (c) 2023-present Plane Software, Inc. and contributors
# SPDX-License-Identifier: AGPL-3.0-only
# See the LICENSE file for details.

"""
Group referential for the steering space (« espace de pilotage », cahier des charges §3 and §10).

The Group is organised in branches (« pôles »); each branch holds entities (subsidiaries,
departments); every project is carried by one entity. The Cabinet of the Presidency and the
CEO administer this referential and the steering profiles of the people who read it.
These tables live beside Plane's own models so that Plane's tables stay untouched (ADR 0003).
"""

# Django imports
from django.conf import settings
from django.db import models
from django.db.models import Q
from django.db.models.signals import pre_save
from django.dispatch import receiver

# Module imports
from .base import BaseModel


class Branch(BaseModel):
    """A branch of the Group (« pôle »): Finance & Capital Markets, Immobilier, Fonctions Groupe…"""

    workspace = models.ForeignKey("db.Workspace", on_delete=models.CASCADE, related_name="steering_branches")
    name = models.CharField(max_length=255)
    sort_order = models.FloatField(default=65535)

    class Meta:
        constraints = [
            models.UniqueConstraint(
                fields=["workspace", "name"],
                condition=Q(deleted_at__isnull=True),
                name="steering_branch_unique_name_when_not_deleted",
            )
        ]
        db_table = "steering_branches"
        ordering = ("sort_order", "name")

    def __str__(self):
        return self.name


class Entity(BaseModel):
    """A company, subsidiary or department attached to exactly one branch."""

    workspace = models.ForeignKey("db.Workspace", on_delete=models.CASCADE, related_name="steering_entities")
    branch = models.ForeignKey(Branch, on_delete=models.CASCADE, related_name="entities")
    name = models.CharField(max_length=255)
    sort_order = models.FloatField(default=65535)

    class Meta:
        constraints = [
            models.UniqueConstraint(
                fields=["workspace", "name"],
                condition=Q(deleted_at__isnull=True),
                name="steering_entity_unique_name_when_not_deleted",
            )
        ]
        db_table = "steering_entities"
        ordering = ("sort_order", "name")

    def __str__(self):
        return self.name


class SteeringCategory(BaseModel):
    """Work item category kept by the Cabinet (Agréments, Gouvernance, Partenariats, Développement…)."""

    workspace = models.ForeignKey("db.Workspace", on_delete=models.CASCADE, related_name="steering_categories")
    name = models.CharField(max_length=255)
    sort_order = models.FloatField(default=65535)

    class Meta:
        constraints = [
            models.UniqueConstraint(
                fields=["workspace", "name"],
                condition=Q(deleted_at__isnull=True),
                name="steering_category_unique_name_when_not_deleted",
            )
        ]
        db_table = "steering_categories"
        ordering = ("sort_order", "name")

    def __str__(self):
        return self.name


class ProjectSteering(BaseModel):
    """Steering data of a project: the entity that carries it."""

    project = models.OneToOneField("db.Project", on_delete=models.CASCADE, related_name="steering")
    workspace = models.ForeignKey("db.Workspace", on_delete=models.CASCADE, related_name="project_steerings")
    entity = models.ForeignKey(Entity, on_delete=models.PROTECT, related_name="projects")

    class Meta:
        db_table = "project_steerings"


class SteeringProfileRole(models.TextChoices):
    CEO = "ceo", "PDG"
    CABINET = "cabinet", "Cabinet de la Présidence"
    BRANCH_DIRECTOR = "branch_director", "Directeur de pôle"
    ENTITY_MANAGER = "entity_manager", "Responsable d'entité"


class SteeringProfile(BaseModel):
    """
    What a person may see in the steering space: the whole Group (CEO, Cabinet), one branch
    (branch director) or one entity (entity manager). A person may hold several profiles.
    """

    workspace = models.ForeignKey("db.Workspace", on_delete=models.CASCADE, related_name="steering_profiles")
    member = models.ForeignKey(settings.AUTH_USER_MODEL, on_delete=models.CASCADE, related_name="steering_profiles")
    role = models.CharField(max_length=30, choices=SteeringProfileRole.choices)
    branch = models.ForeignKey(Branch, on_delete=models.CASCADE, null=True, blank=True, related_name="profiles")
    entity = models.ForeignKey(Entity, on_delete=models.CASCADE, null=True, blank=True, related_name="profiles")

    class Meta:
        constraints = [
            models.UniqueConstraint(
                fields=["workspace", "member", "role", "branch", "entity"],
                condition=Q(deleted_at__isnull=True),
                name="steering_profile_unique_when_not_deleted",
                nulls_distinct=False,
            )
        ]
        db_table = "steering_profiles"


class SteeringStatus(models.TextChoices):
    """The six statuses of a work item in the steering space (cahier des charges §4)."""

    TO_START = "to_start", "À démarrer"
    IN_PROGRESS = "in_progress", "En cours"
    IN_VALIDATION = "in_validation", "En validation"
    WAITING = "waiting", "En attente"
    DONE = "done", "Terminé"
    CANCELLED = "cancelled", "Annulé"


CLOSED_STEERING_STATUSES = (SteeringStatus.DONE, SteeringStatus.CANCELLED)


class SteeringWaitingFor(models.TextChoices):
    INTERNAL = "internal", "Interne"
    CLIENT_PARTNER = "client_partner", "Client / partenaire"
    REGULATORY = "regulatory", "Réglementaire"


class SteeringRiskNature(models.TextChoices):
    FINANCIAL = "financial", "Financier"
    REGULATORY = "regulatory", "Réglementaire"
    LEGAL = "legal", "Juridique"
    SCHEDULE = "schedule", "Calendrier"
    REPUTATION = "reputation", "Réputation"
    GOVERNANCE = "governance", "Gouvernance"
    HR = "hr", "RH"
    OPERATIONAL = "operational", "Opérationnel"


class IssueSteering(BaseModel):
    """
    The steering record of a work item (§4). The fields Plane already has stay on the work item:
    project, assignee (responsable), priority and target date (deadline). A missing record reads as
    « À démarrer », 0 %, carried by the project's entity.
    """

    issue = models.OneToOneField("db.Issue", on_delete=models.CASCADE, related_name="steering")
    project = models.ForeignKey("db.Project", on_delete=models.CASCADE, related_name="issue_steerings")
    workspace = models.ForeignKey("db.Workspace", on_delete=models.CASCADE, related_name="issue_steerings")
    # Null: carried by the project's entity.
    entity = models.ForeignKey(Entity, on_delete=models.PROTECT, null=True, blank=True, related_name="issues")
    category = models.ForeignKey(
        SteeringCategory, on_delete=models.PROTECT, null=True, blank=True, related_name="issues"
    )
    supervisor = models.ForeignKey(
        settings.AUTH_USER_MODEL, on_delete=models.SET_NULL, null=True, blank=True, related_name="supervised_steerings"
    )
    approver = models.ForeignKey(
        settings.AUTH_USER_MODEL, on_delete=models.SET_NULL, null=True, blank=True, related_name="approved_steerings"
    )
    status = models.CharField(max_length=20, choices=SteeringStatus.choices, default=SteeringStatus.TO_START)
    progress = models.PositiveSmallIntegerField(default=0)
    waiting_for = models.CharField(max_length=20, choices=SteeringWaitingFor.choices, blank=True, default="")
    # Last change of the status or of « En attente de » (§4 « En attente depuis »).
    waiting_since = models.DateTimeField(null=True, blank=True)
    risk_nature = models.CharField(max_length=20, choices=SteeringRiskNature.choices, blank=True, default="")
    risk_effective_date = models.DateField(null=True, blank=True)
    risk_description = models.TextField(blank=True, default="")
    closure_date = models.DateField(null=True, blank=True)
    closure_comment = models.TextField(blank=True, default="")
    situation = models.TextField(blank=True, default="")
    situation_updated_at = models.DateTimeField(null=True, blank=True)

    class Meta:
        db_table = "issue_steerings"


THREE_PRIORITIES = ("urgent", "high", "medium")


@receiver(pre_save, sender="db.Issue")
@receiver(pre_save, sender="db.DraftIssue")
def keep_three_priorities(sender, instance, **kwargs):
    """
    The Group works with three priorities (§4): Urgent, Important (high) and Normal (medium). Low and
    none, still accepted by Plane's API and clients, are saved as Normal whatever the path.
    """
    if instance.priority not in THREE_PRIORITIES:
        instance.priority = "medium"
