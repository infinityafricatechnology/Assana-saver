# Copyright (c) 2023-present Plane Software, Inc. and contributors
# SPDX-License-Identifier: AGPL-3.0-only
# See the LICENSE file for details.

"""The periodic work of the steering space (§9), scheduled in plane/celery.py. Abidjan is on UTC."""

# Third party imports
from celery import shared_task

# Module imports
from plane.utils.steering_jobs import (
    daily_alerts,
    run_for_steered_workspaces,
    take_snapshot,
    unblock_alerts,
    weekly_reminders,
)


@shared_task
def steering_daily_alerts():
    """§9.2: deadline in 3 days, late, critical, blocker late, submission overdue, risk soon."""
    return run_for_steered_workspaces(daily_alerts)


@shared_task
def steering_unblock_alerts():
    """§7: the assignee of a work item whose blocker was just closed is alerted."""
    return run_for_steered_workspaces(unblock_alerts)


@shared_task
def steering_weekly_reminders():
    """§9.1: the weekly reminder of the assignees of dormant or inconsistent records."""
    return run_for_steered_workspaces(weekly_reminders)


@shared_task
def steering_friday_noon():
    """§9.3: on Fridays at noon, the weekly snapshot is frozen."""
    run_for_steered_workspaces(take_snapshot)
