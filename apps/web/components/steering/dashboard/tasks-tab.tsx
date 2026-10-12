/**
 * Copyright (c) 2023-present Plane Software, Inc. and contributors
 * SPDX-License-Identifier: AGPL-3.0-only
 * See the LICENSE file for details.
 */

import { useDeferredValue, useMemo, useState } from "react";
import type { ReactNode } from "react";
import { orderBy, sortBy } from "lodash-es";
import { useTranslation } from "@plane/i18n";
// types
import type { TDashboard, TDashboardTask } from "@/services/steering-dashboard.service";
import { STEERING_STATUSES } from "@/services/steering.service";
// local imports
import type { TTaskFilter, TTaskFilterPreset } from "./filters";
import { DEFAULT_TASK_FILTER, TASK_FILTER_PRESETS, filterTasks } from "./filters";
import { BlockedByLines, Card, EmptyLine, SignalBadge, TaskTitle, formatDate, useDelayLabel } from "./shared";
import type { TDashboardIndex } from "./use-dashboard";

type TSortKey = "task" | "entity" | "assignee" | "deadline" | "status" | "progress" | "signal";
const SIGNAL_ORDER = { critical: 0, late: 1, soon: 2, on_time: 3, closed: 4 };
const PAGE = 200;

type TTasksTabProps = {
  data: TDashboard;
  index: TDashboardIndex;
  branchId: string | null;
  filter: TTaskFilter;
  onFilterChange: (filter: TTaskFilter) => void;
  onOpenTask: (id: string) => void;
  actions?: ReactNode;
};

const selectClassName =
  "iag-focus min-w-0 rounded-full border border-[var(--iag-border)] bg-[var(--iag-card)] px-3 py-1.5 text-13 text-[var(--iag-text)]";

/** §6.2: grouped by entity or as a flat list, with search, filters and sortable columns. */
export function TasksTab(props: TTasksTabProps) {
  const { data, index, branchId, filter, onFilterChange, onOpenTask, actions } = props;
  const { t } = useTranslation();
  const [grouped, setGrouped] = useState(true);
  const [sort, setSort] = useState<{ key: TSortKey; descending: boolean }>({ key: "signal", descending: false });
  const search = useDeferredValue(filter.search);
  const set = (patch: Partial<TTaskFilter>) => onFilterChange({ ...filter, ...patch });

  const tasks = useMemo(() => {
    const filtered = filterTasks(data.tasks, { ...filter, search }, branchId, index);
    const value = (task: TDashboardTask): string | number => {
      switch (sort.key) {
        case "task":
          return task.name.toLowerCase();
        case "entity":
          return index.entityName(task.entity_id).toLowerCase();
        case "assignee":
          return index.assigneeNames(task).toLowerCase();
        case "deadline":
          return task.target_date ?? "9999";
        case "status":
          return STEERING_STATUSES.indexOf(task.status);
        case "progress":
          return task.progress;
        default:
          return SIGNAL_ORDER[task.signal] * 10000 - task.days_late;
      }
    };
    return orderBy(filtered, [value], [sort.descending ? "desc" : "asc"]);
  }, [data.tasks, filter, search, branchId, index, sort]);

  const projectView = !!filter.projectId;
  const entities = useMemo(
    () => data.branches.flatMap((branch) => data.entities.filter((entity) => entity.branch_id === branch.id)),
    [data.branches, data.entities]
  );
  const visiblePeople = useMemo(() => sortBy(data.people, (person) => person.name.toLowerCase()), [data.people]);
  const isFiltered = JSON.stringify(filter) !== JSON.stringify(DEFAULT_TASK_FILTER);

  const sortHeader = (key: TSortKey, label: string, className = "") => (
    <th
      scope="col"
      className={className}
      aria-sort={sort.key === key ? (sort.descending ? "descending" : "ascending") : "none"}
    >
      <button
        type="button"
        className="iag-focus rounded hover:underline"
        onClick={() => setSort({ key, descending: sort.key === key ? !sort.descending : false })}
      >
        {label}
        {sort.key === key && <span aria-hidden="true">{sort.descending ? " ↓" : " ↑"}</span>}
      </button>
    </th>
  );

  const table = (rows: TDashboardTask[], showEntity: boolean) => (
    <TaskTable
      rows={rows}
      index={index}
      showEntity={showEntity}
      onOpenTask={onOpenTask}
      header={
        <tr>
          {sortHeader("task", t("steering.dashboard.columns.task"))}
          {showEntity && sortHeader("entity", t("steering.task.fields.entity"))}
          {sortHeader("assignee", t("steering.task.fields.assignee"))}
          {sortHeader("deadline", t("steering.task.fields.target_date"))}
          {sortHeader("status", t("steering.task.fields.status"))}
          {sortHeader("progress", t("steering.task.fields.progress"), "text-right")}
          {sortHeader("signal", t("steering.dashboard.columns.signal"))}
        </tr>
      }
    />
  );

  return (
    <div className="flex flex-col gap-4">
      <div className="iag-card flex flex-col gap-3 p-4">
        <div className="flex flex-wrap items-center gap-2">
          <input
            type="search"
            value={filter.search}
            onChange={(event) => set({ search: event.target.value })}
            placeholder={t("steering.dashboard.search_placeholder")}
            aria-label={t("steering.dashboard.search_placeholder")}
            className={`${selectClassName} w-full sm:w-72`}
          />
          <select
            aria-label={t("steering.dashboard.columns.signal")}
            value={filter.preset}
            onChange={(event) => set({ preset: event.target.value as TTaskFilterPreset })}
            className={selectClassName}
          >
            {TASK_FILTER_PRESETS.map((preset) => (
              <option key={preset} value={preset}>
                {t(`steering.dashboard.preset.${preset}`)}
              </option>
            ))}
          </select>
          <select
            aria-label={t("steering.task.fields.entity")}
            value={filter.entityId ?? ""}
            onChange={(event) => set({ entityId: event.target.value || null })}
            className={selectClassName}
          >
            <option value="">{t("steering.dashboard.all_entities")}</option>
            {entities
              .filter((entity) => !branchId || entity.branch_id === branchId)
              .map((entity) => (
                <option key={entity.id} value={entity.id}>
                  {entity.name} — {index.branchName(entity.branch_id)}
                </option>
              ))}
          </select>
          <select
            aria-label={t("steering.dashboard.columns.project")}
            value={filter.projectId ?? ""}
            onChange={(event) => set({ projectId: event.target.value || null })}
            className={selectClassName}
          >
            <option value="">{t("steering.dashboard.all_projects")}</option>
            {sortBy(data.projects, "name").map((project) => (
              <option key={project.id} value={project.id}>
                {project.name}
              </option>
            ))}
          </select>
          <select
            aria-label={t("steering.task.fields.assignee")}
            value={filter.assigneeId ?? ""}
            onChange={(event) => set({ assigneeId: event.target.value || null })}
            className={selectClassName}
          >
            <option value="">{t("steering.dashboard.all_assignees")}</option>
            {visiblePeople.map((person) => (
              <option key={person.id} value={person.id}>
                {person.name}
              </option>
            ))}
          </select>
          <select
            aria-label={t("steering.task.fields.status")}
            value={filter.status ?? ""}
            onChange={(event) => set({ status: (event.target.value || null) as TTaskFilter["status"] })}
            className={selectClassName}
          >
            <option value="">{t("steering.dashboard.all_statuses")}</option>
            {STEERING_STATUSES.map((status) => (
              <option key={status} value={status}>
                {t(`steering.task.status.${status}`)}
              </option>
            ))}
          </select>
          {isFiltered && (
            <button type="button" className="iag-pill iag-focus" onClick={() => onFilterChange(DEFAULT_TASK_FILTER)}>
              {t("steering.dashboard.reset_filters")}
            </button>
          )}
        </div>
        <div className="flex flex-wrap items-center justify-between gap-2">
          <p className="iag-num text-13 text-[var(--iag-text-2)]" role="status">
            {t("steering.dashboard.task_count", { count: tasks.length })}
          </p>
          <div className="flex flex-wrap items-center gap-2">
            {!projectView && (
              <div className="flex gap-1" role="group" aria-label={t("steering.dashboard.view_mode")}>
                <button
                  type="button"
                  aria-pressed={grouped}
                  className="iag-pill iag-focus"
                  onClick={() => setGrouped(true)}
                >
                  {t("steering.dashboard.by_entity")}
                </button>
                <button
                  type="button"
                  aria-pressed={!grouped}
                  className="iag-pill iag-focus"
                  onClick={() => setGrouped(false)}
                >
                  {t("steering.dashboard.flat_list")}
                </button>
              </div>
            )}
            {actions}
          </div>
        </div>
      </div>

      {projectView ? (
        <ProjectView data={data} index={index} projectId={filter.projectId!} tasks={tasks}>
          {table(tasks, true)}
        </ProjectView>
      ) : tasks.length === 0 ? (
        <Card>
          <EmptyLine>{t("steering.dashboard.empty.tasks")}</EmptyLine>
        </Card>
      ) : grouped ? (
        <EntityGroups tasks={tasks} index={index} render={(rows) => table(rows, false)} />
      ) : (
        <Card>{table(tasks, true)}</Card>
      )}
    </div>
  );
}

/** One group per entity, with its counters, folding on a click. */
function EntityGroups(props: {
  tasks: TDashboardTask[];
  index: TDashboardIndex;
  render: (rows: TDashboardTask[]) => ReactNode;
}) {
  const { tasks, index, render } = props;
  const { t } = useTranslation();
  const [closed, setClosed] = useState<Record<string, boolean>>({});
  const groups = useMemo(() => {
    const byEntity = new Map<string, TDashboardTask[]>();
    for (const task of tasks) byEntity.set(task.entity_id, [...(byEntity.get(task.entity_id) ?? []), task]);
    return sortBy([...byEntity.entries()], ([, rows]) => -rows.filter((row) => row.days_late > 0).length);
  }, [tasks]);

  return (
    <div className="flex flex-col gap-3">
      {groups.map(([entityId, rows]) => {
        const isOpen = !closed[entityId];
        const late = rows.filter((row) => row.days_late > 0).length;
        const critical = rows.filter((row) => row.signal === "critical").length;
        const blocked = rows.filter((row) => row.blocked).length;
        const entity = index.entities.get(entityId);
        return (
          <section key={entityId} className="iag-card">
            <button
              type="button"
              aria-expanded={isOpen}
              onClick={() => setClosed({ ...closed, [entityId]: isOpen })}
              className="iag-focus flex w-full flex-wrap items-center gap-x-3 gap-y-1 rounded-2xl px-4 py-3 text-left"
            >
              <span aria-hidden="true" className="text-12 text-[var(--iag-text-2)]">
                {isOpen ? "▾" : "▸"}
              </span>
              <span className="text-14 font-semibold">{entity?.name}</span>
              <span className="rounded-full bg-[var(--iag-bg)] px-2 text-11 text-[var(--iag-text-2)]">
                {index.branchName(entity?.branch_id)}
              </span>
              <span className="iag-num ml-auto flex flex-wrap gap-3 text-12 text-[var(--iag-text-2)]">
                <span>{t("steering.dashboard.task_count", { count: rows.length })}</span>
                <span>{t("steering.dashboard.count.late", { count: late })}</span>
                <span>{t("steering.dashboard.count.critical", { count: critical })}</span>
                <span>{t("steering.dashboard.count.blocked", { count: blocked })}</span>
              </span>
            </button>
            {isOpen && <div className="px-4 pb-4">{render(rows)}</div>}
          </section>
        );
      })}
    </div>
  );
}

/** §3.3, §6.2: a project's tasks from every entity, with a line of totals and the contributors. */
function ProjectView(props: {
  data: TDashboard;
  index: TDashboardIndex;
  projectId: string;
  tasks: TDashboardTask[];
  children: ReactNode;
}) {
  const { index, projectId, tasks, children } = props;
  const { t } = useTranslation();
  const project = index.projects.get(projectId);
  const contributors = [...new Set(tasks.map((task) => task.entity_id))];
  return (
    <Card
      title={
        <>
          {project?.name}
          <span className="font-normal text-12 text-[var(--iag-text-2)]">
            {t("steering.dashboard.carried_by", { name: index.entityName(project?.entity_id) })}
          </span>
        </>
      }
    >
      <p className="iag-num mb-2 flex flex-wrap gap-3 text-13 text-[var(--iag-text-2)]">
        <span>{t("steering.dashboard.task_count", { count: tasks.length })}</span>
        <span>{t("steering.dashboard.count.late", { count: tasks.filter((task) => task.days_late > 0).length })}</span>
        <span>{t("steering.dashboard.count.blocked", { count: tasks.filter((task) => task.blocked).length })}</span>
      </p>
      <p className="mb-3 flex flex-wrap items-center gap-1.5 text-12">
        <span className="text-[var(--iag-text-2)]">{t("steering.dashboard.contributors")}</span>
        {contributors.map((entityId) => (
          <EntityPill key={entityId} name={index.entityName(entityId)} />
        ))}
      </p>
      {children}
    </Card>
  );
}

function EntityPill(props: { name: string }) {
  return (
    <span className="inline-flex items-center gap-1 rounded-full border border-[var(--iag-border)] px-2 py-0.5 text-11">
      <span aria-hidden="true" className="size-1.5 rounded-full bg-[var(--iag-gold)]" />
      {props.name}
    </span>
  );
}

function TaskTable(props: {
  rows: TDashboardTask[];
  index: TDashboardIndex;
  showEntity: boolean;
  header: ReactNode;
  onOpenTask: (id: string) => void;
}) {
  const { rows, index, showEntity, header, onOpenTask } = props;
  const { t } = useTranslation();
  const delayLabel = useDelayLabel();
  const [limit, setLimit] = useState(PAGE);
  return (
    <div className="overflow-x-auto">
      <table className="iag-table w-full min-w-[720px] text-13">
        <thead>{header}</thead>
        <tbody>
          {rows.slice(0, limit).map((task) => (
            <tr key={task.id} className={`iag-edge iag-signal-${task.signal} align-top`}>
              <td className="max-w-md">
                <TaskTitle task={task} onOpen={onOpenTask} />
                <BlockedByLines task={task} index={index} onOpen={onOpenTask} />
              </td>
              {showEntity && (
                <td>
                  <EntityPill name={index.entityName(task.entity_id)} />
                </td>
              )}
              <td>{index.assigneeNames(task)}</td>
              <td className="iag-num whitespace-nowrap">
                {formatDate(task.target_date)}
                <span className="block text-12" style={{ color: "var(--iag-signal)" }}>
                  {delayLabel(task)}
                </span>
              </td>
              <td className="whitespace-nowrap">{t(`steering.task.status.${task.status}`)}</td>
              <td className="iag-num text-right">{task.progress} %</td>
              <td>
                <div className="flex flex-wrap gap-1">
                  <SignalBadge signal={task.signal} />
                  {task.blocked && <SignalBadge signal="blocked" />}
                  {task.in_queue && <SignalBadge signal="queue" />}
                </div>
              </td>
            </tr>
          ))}
        </tbody>
      </table>
      {rows.length > limit && (
        <button type="button" className="iag-pill iag-focus mt-3" onClick={() => setLimit(limit + PAGE)}>
          {t("steering.dashboard.show_more", { count: rows.length - limit })}
        </button>
      )}
    </div>
  );
}
