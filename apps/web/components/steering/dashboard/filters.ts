/**
 * Copyright (c) 2023-present Plane Software, Inc. and contributors
 * SPDX-License-Identifier: AGPL-3.0-only
 * See the LICENSE file for details.
 */

// types
import type { TDashboardTask } from "@/services/steering-dashboard.service";
import type { TSteeringStatus } from "@/services/steering.service";
// local imports
import type { TDashboardIndex } from "./use-dashboard";

/** The « signal » filter of §6.2, plus what the indicators of the Synthèse open. */
export type TTaskFilterPreset =
  | "open"
  | "late"
  | "critical"
  | "soon"
  | "on_time"
  | "blocked"
  | "queue"
  | "closed"
  | "all";

export const TASK_FILTER_PRESETS: TTaskFilterPreset[] = [
  "open",
  "late",
  "critical",
  "soon",
  "on_time",
  "blocked",
  "queue",
  "closed",
  "all",
];

export type TTaskFilter = {
  search: string;
  preset: TTaskFilterPreset;
  entityId: string | null;
  projectId: string | null;
  assigneeId: string | null;
  status: TSteeringStatus | null;
};

export const DEFAULT_TASK_FILTER: TTaskFilter = {
  search: "",
  preset: "open",
  entityId: null,
  projectId: null,
  assigneeId: null,
  status: null,
};

export const matchesPreset = (task: TDashboardTask, preset: TTaskFilterPreset): boolean => {
  switch (preset) {
    case "open":
      return task.is_open;
    case "late":
      return task.is_open && task.days_late > 0;
    case "critical":
      return task.signal === "critical";
    case "soon":
      return task.signal === "soon";
    case "on_time":
      return task.signal === "on_time";
    case "blocked":
      return task.blocked;
    case "queue":
      return task.in_queue;
    case "closed":
      return !task.is_open;
    default:
      return true;
  }
};

/** Lower case, without accents, so that « echeance » finds « Échéance ». */
export const normalize = (text: string) =>
  text
    .normalize("NFD")
    .replace(/[̀-ͯ]/g, "")
    .toLowerCase();

export const filterTasks = (
  tasks: TDashboardTask[],
  filter: TTaskFilter,
  branchId: string | null,
  index: TDashboardIndex
): TDashboardTask[] => {
  const words = normalize(filter.search).split(/\s+/).filter(Boolean);
  return tasks.filter((task) => {
    if (branchId && task.branch_id !== branchId) return false;
    if (!matchesPreset(task, filter.preset)) return false;
    if (filter.entityId && task.entity_id !== filter.entityId) return false;
    if (filter.projectId && task.project_id !== filter.projectId) return false;
    if (filter.assigneeId && !task.assignee_ids.includes(filter.assigneeId)) return false;
    if (filter.status && task.status !== filter.status) return false;
    if (!words.length) return true;
    const haystack = normalize(
      [
        task.key,
        task.name,
        index.entityName(task.entity_id),
        index.projects.get(task.project_id)?.name ?? "",
        index.assigneeNames(task),
      ].join(" ")
    );
    return words.every((word) => haystack.includes(word));
  });
};
