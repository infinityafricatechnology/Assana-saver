/**
 * Copyright (c) 2023-present Plane Software, Inc. and contributors
 * SPDX-License-Identifier: AGPL-3.0-only
 * See the LICENSE file for details.
 */

import { useMemo, useState } from "react";
import useSWR from "swr";
// services
import type { TDashboard, TDashboardTask, TRelatedTask } from "@/services/steering-dashboard.service";
import { SteeringDashboardService } from "@/services/steering-dashboard.service";

export const steeringDashboardService = new SteeringDashboardService();

/** §12 « Temps réel »: a change made in an entity's space shows here in less than 5 seconds. */
const VERSION_POLL_MS = 4000;

/**
 * The portfolio, reloaded whenever its version stamp changes. ``isLive`` turns false while the
 * server cannot be reached, so the header can say the figures may be stale.
 */
export const useSteeringDashboard = (workspaceSlug: string, branchId: string | null) => {
  const dashboard = useSWR(
    workspaceSlug ? ["STEERING_DASHBOARD", workspaceSlug, branchId ?? ""] : null,
    () => steeringDashboardService.getDashboard(workspaceSlug, branchId),
    { revalidateOnFocus: false, keepPreviousData: true, shouldRetryOnError: false }
  );
  const [checkedAt, setCheckedAt] = useState<Date | null>(null);
  const version = useSWR(
    dashboard.data ? ["STEERING_DASHBOARD_VERSION", workspaceSlug] : null,
    () => steeringDashboardService.getVersion(workspaceSlug),
    {
      refreshInterval: VERSION_POLL_MS,
      dedupingInterval: VERSION_POLL_MS / 2,
      onSuccess: (latest) => {
        setCheckedAt(new Date());
        if (dashboard.data && latest.version !== dashboard.data.version) void dashboard.mutate();
      },
    }
  );
  return {
    data: dashboard.data,
    error: dashboard.error as { code?: string } | undefined,
    isLoading: dashboard.isLoading,
    isLive: !version.error,
    checkedAt,
    reload: () => dashboard.mutate(),
  };
};

export type TDashboardIndex = ReturnType<typeof buildIndex>;

/** Lookups by id over one dashboard payload. */
export const buildIndex = (data: TDashboard) => {
  const tasks = new Map(data.tasks.map((task) => [task.id, task]));
  const entities = new Map(data.entities.map((entity) => [entity.id, entity]));
  const branches = new Map(data.branches.map((branch) => [branch.id, branch]));
  const projects = new Map(data.projects.map((project) => [project.id, project]));
  const people = new Map(data.people.map((person) => [person.id, person]));
  const categories = new Map(data.categories.map((category) => [category.id, category]));
  return {
    tasks,
    entities,
    branches,
    projects,
    people,
    categories,
    /** A work item of the scope, or what is known of one outside it. */
    item: (id: string): TDashboardTask | TRelatedTask | undefined => tasks.get(id) ?? data.related[id],
    entityName: (id: string | null | undefined) => (id ? (entities.get(id)?.name ?? "") : ""),
    branchName: (id: string | null | undefined) => (id ? (branches.get(id)?.name ?? "") : ""),
    personName: (id: string | null | undefined) => (id ? (people.get(id)?.name ?? "") : ""),
    assigneeNames: (task: TDashboardTask) => task.assignee_ids.map((id) => people.get(id)?.name ?? "").join(", "),
  };
};

export const useDashboardIndex = (data: TDashboard | undefined) =>
  useMemo(() => (data ? buildIndex(data) : null), [data]);
