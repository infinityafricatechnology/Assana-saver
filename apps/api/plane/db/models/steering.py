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


class SteeringSubmissionStatus(models.TextChoices):
    PENDING = "pending", "En attente de décision"
    VALIDATED = "validated", "Validée"
    RETURNED = "returned", "Renvoyée"


class SteeringSubmission(BaseModel):
    """
    A work item submitted to the CEO (§8.1): the assignee submits from the entity's space with a
    message and the document to validate, the CEO validates or returns it from the steering space.
    The submission date is frozen; every submission and decision is kept.
    """

    issue = models.ForeignKey("db.Issue", on_delete=models.CASCADE, related_name="steering_submissions")
    project = models.ForeignKey("db.Project", on_delete=models.CASCADE, related_name="steering_submissions")
    workspace = models.ForeignKey("db.Workspace", on_delete=models.CASCADE, related_name="steering_submissions")
    submitted_by = models.ForeignKey(
        settings.AUTH_USER_MODEL, on_delete=models.SET_NULL, null=True, related_name="steering_submissions"
    )
    submitted_at = models.DateTimeField()
    message = models.TextField()
    link = models.URLField(max_length=1000, blank=True, default="")
    attachment = models.ForeignKey(
        "db.FileAsset", on_delete=models.SET_NULL, null=True, blank=True, related_name="steering_submissions"
    )
    status = models.CharField(
        max_length=20, choices=SteeringSubmissionStatus.choices, default=SteeringSubmissionStatus.PENDING
    )
    decided_by = models.ForeignKey(
        settings.AUTH_USER_MODEL, on_delete=models.SET_NULL, null=True, blank=True, related_name="steering_decisions"
    )
    decided_at = models.DateTimeField(null=True, blank=True)
    decision_comment = models.TextField(blank=True, default="")

    class Meta:
        constraints = [
            models.UniqueConstraint(
                fields=["issue"],
                condition=Q(status="pending", deleted_at__isnull=True),
                name="steering_one_pending_submission_per_issue",
            )
        ]
        db_table = "steering_submissions"
        ordering = ("-submitted_at",)


class PriorityRequalification(BaseModel):
    """
    The priority the Cabinet or the CEO retains for a work item in the CEO queue (§8.2). The priority
    declared by the entity stays on the work item; a cancelled requalification no longer applies.
    """

    issue = models.ForeignKey("db.Issue", on_delete=models.CASCADE, related_name="priority_requalifications")
    project = models.ForeignKey("db.Project", on_delete=models.CASCADE, related_name="priority_requalifications")
    workspace = models.ForeignKey("db.Workspace", on_delete=models.CASCADE, related_name="priority_requalifications")
    priority = models.CharField(max_length=30)
    declared_priority = models.CharField(max_length=30)
    comment = models.TextField()
    requalified_by = models.ForeignKey(
        settings.AUTH_USER_MODEL, on_delete=models.SET_NULL, null=True, related_name="priority_requalifications"
    )
    by_role = models.CharField(max_length=30, choices=SteeringProfileRole.choices)
    cancelled_at = models.DateTimeField(null=True, blank=True)
    cancelled_by = models.ForeignKey(
        settings.AUTH_USER_MODEL, on_delete=models.SET_NULL, null=True, blank=True, related_name="+"
    )

    class Meta:
        db_table = "steering_priority_requalifications"
        ordering = ("-created_at",)


class SteeringReminderReason(models.TextChoices):
    MANUAL = "manual", "Relance manuelle"
    DORMANT = "dormant", "Fiche dormante"
    INCONSISTENT = "inconsistent", "Incohérence"
    INCOMPLETE = "incomplete", "Fiche incomplète"


class SteeringReminder(BaseModel):
    """A reminder sent to the people in charge of a work item (§9.1), by the Cabinet, the CEO or the weekly run."""

    issue = models.ForeignKey("db.Issue", on_delete=models.CASCADE, related_name="steering_reminders")
    project = models.ForeignKey("db.Project", on_delete=models.CASCADE, related_name="steering_reminders")
    workspace = models.ForeignKey("db.Workspace", on_delete=models.CASCADE, related_name="steering_reminders")
    # Null for the weekly automatic reminder.
    sent_by = models.ForeignKey(
        settings.AUTH_USER_MODEL, on_delete=models.SET_NULL, null=True, blank=True, related_name="steering_reminders"
    )
    reason = models.CharField(max_length=20, choices=SteeringReminderReason.choices)
    message = models.TextField(blank=True, default="")
    recipient_ids = models.JSONField(default=list)

    class Meta:
        db_table = "steering_reminders"
        ordering = ("-created_at",)


class SteeringAlertLog(models.Model):
    """One line per alert sent: « une même alerte n'est envoyée qu'une fois par tâche et par événement » (§9.2)."""

    workspace = models.ForeignKey("db.Workspace", on_delete=models.CASCADE, related_name="steering_alert_logs")
    issue = models.ForeignKey("db.Issue", on_delete=models.CASCADE, related_name="steering_alert_logs")
    event = models.CharField(max_length=40)
    # What makes the event unique, e.g. the deadline it is about or the submission it follows.
    key = models.CharField(max_length=100, blank=True, default="")
    recipient = models.ForeignKey(settings.AUTH_USER_MODEL, on_delete=models.CASCADE, related_name="+")
    sent_at = models.DateTimeField(auto_now_add=True)

    class Meta:
        constraints = [
            models.UniqueConstraint(fields=["issue", "event", "key", "recipient"], name="steering_alert_once_per_event")
        ]
        db_table = "steering_alert_logs"


class SteeringEmailPreference(models.Model):
    """« Chaque utilisateur peut couper les e-mails, pas les alertes dans la plateforme » (§9.2)."""

    user = models.OneToOneField(settings.AUTH_USER_MODEL, on_delete=models.CASCADE, related_name="steering_email")
    emails_enabled = models.BooleanField(default=True)

    class Meta:
        db_table = "steering_email_preferences"


class SteeringSnapshot(BaseModel):
    """
    The weekly picture of the portfolio, frozen on Fridays at noon (§9.3) for the trend (§6.1). The
    counts are kept per entity, so that each profile reads the trend of its own scope.
    """

    workspace = models.ForeignKey("db.Workspace", on_delete=models.CASCADE, related_name="steering_snapshots")
    date = models.DateField()
    # {entity id: {"open", "late", "critical", "blocked", "queue"}}
    entities = models.JSONField(default=dict)

    class Meta:
        constraints = [
            models.UniqueConstraint(
                fields=["workspace", "date"],
                condition=Q(deleted_at__isnull=True),
                name="steering_snapshot_once_a_day",
            )
        ]
        db_table = "steering_snapshots"
        ordering = ("date",)


class SteeringReportStatus(models.TextChoices):
    DRAFT = "draft", "Projet"
    SENT = "sent", "Envoyé"


class SteeringWeeklyReport(BaseModel):
    """
    The weekly report (§9.3): a draft prepared on Fridays at noon from the COMEX export, which the
    Cabinet or the CEO comment, arrange and send. Its figures come from the entities' spaces and do
    not change until « Actualiser »; the version sent is archived as it was.
    """

    workspace = models.ForeignKey("db.Workspace", on_delete=models.CASCADE, related_name="steering_reports")
    year = models.PositiveSmallIntegerField()
    week = models.PositiveSmallIntegerField()
    status = models.CharField(max_length=10, choices=SteeringReportStatus.choices, default=SteeringReportStatus.DRAFT)
    # The COMEX data, frozen at ``refreshed_at``.
    data = models.JSONField(default=dict)
    refreshed_at = models.DateTimeField()
    intro = models.TextField(blank=True, default="")
    # [{"key": section, "visible": bool}], in the order of the report
    sections = models.JSONField(default=list)
    section_comments = models.JSONField(default=dict)
    entity_comments = models.JSONField(default=dict)
    task_comments = models.JSONField(default=dict)
    highlighted_tasks = models.JSONField(default=list)
    highlighted_entities = models.JSONField(default=list)
    recipient_ids = models.JSONField(default=list)
    extra_emails = models.JSONField(default=list)
    sent_at = models.DateTimeField(null=True, blank=True)
    sent_by = models.ForeignKey(
        settings.AUTH_USER_MODEL, on_delete=models.SET_NULL, null=True, blank=True, related_name="+"
    )
    sent_pdf = models.BinaryField(null=True, blank=True)

    class Meta:
        constraints = [
            models.UniqueConstraint(
                fields=["workspace", "year", "week"],
                condition=Q(deleted_at__isnull=True),
                name="steering_report_once_a_week",
            )
        ]
        db_table = "steering_weekly_reports"
        ordering = ("-year", "-week")


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
