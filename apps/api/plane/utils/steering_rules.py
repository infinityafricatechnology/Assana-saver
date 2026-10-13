# Copyright (c) 2023-present Plane Software, Inc. and contributors
# SPDX-License-Identifier: AGPL-3.0-only
# See the LICENSE file for details.

"""
Rules of the steering space shared by its screens, alerts and reports (cahier des charges §5, §7).
A work item is closed when its steering status is « Terminé » or « Annulé », or when it sits in a
completed or cancelled column; the dependencies are Plane's « blocked by » relations.
"""

# Python imports
from collections import defaultdict, deque
from typing import Dict, Iterable, List, Set

# Module imports
from plane.db.models import IssueRelation

CLOSED_STEERING_STATUSES = ("done", "cancelled")
CLOSED_STATE_GROUPS = ("completed", "cancelled")


def is_closed(steering_status: str, state_group: str) -> bool:
    """RG-01, reversed: the steering status decides, a closed column counts as well."""
    return steering_status in CLOSED_STEERING_STATUSES or state_group in CLOSED_STATE_GROUPS


def blocked_by_graph(workspace_id) -> Dict[str, Set[str]]:
    """``{blocked issue id: {blocker ids}}`` over the live work items of the workspace."""
    graph: Dict[str, Set[str]] = defaultdict(set)
    relations = IssueRelation.objects.filter(
        workspace_id=workspace_id,
        relation_type="blocked_by",
        issue__deleted_at__isnull=True,
        related_issue__deleted_at__isnull=True,
    ).values_list("issue_id", "related_issue_id")
    for blocked, blocker in relations:
        graph[str(blocked)].add(str(blocker))
    return graph


def _reaches(graph: Dict[str, Set[str]], start: str, target: str) -> bool:
    seen, queue = {start}, deque([start])
    while queue:
        current = queue.popleft()
        if current == target:
            return True
        for following in graph.get(current, ()):
            if following not in seen:
                seen.add(following)
                queue.append(following)
    return False


def creates_circular_dependency(workspace_id, relation_type: str, issue_id, other_ids: Iterable) -> bool:
    """
    §7: « A bloquée par B » is refused when B already depends, directly or through other work items,
    on A. ``relation_type`` is the one the client sends: ``blocked_by`` (``issue_id`` is blocked by the
    others) or ``blocking`` (``issue_id`` blocks them). Other relation types never loop.
    """
    if relation_type not in ("blocked_by", "blocking"):
        return False
    graph = blocked_by_graph(workspace_id)
    for other in other_ids:
        blocked, blocker = (str(other), str(issue_id)) if relation_type == "blocking" else (str(issue_id), str(other))
        if blocked == blocker or _reaches(graph, blocker, blocked):
            return True
    return False


def blocking_chain(graph: Dict[str, Set[str]], issue_id) -> List[List[str]]:
    """
    §7 « Chaînes »: the blockers of a work item level by level, up to the originating ones
    (``[[direct blockers], [their blockers], …]``), each work item listed once.
    """
    levels, seen = [], {str(issue_id)}
    current = [str(issue_id)]
    while current:
        following = sorted({blocker for item in current for blocker in graph.get(item, ()) if blocker not in seen})
        if not following:
            break
        seen.update(following)
        levels.append(following)
        current = following
    return levels
