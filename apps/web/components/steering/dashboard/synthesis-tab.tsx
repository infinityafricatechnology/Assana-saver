/**
 * Copyright (c) 2023-present Plane Software, Inc. and contributors
 * SPDX-License-Identifier: AGPL-3.0-only
 * See the LICENSE file for details.
 */

import { useEffect, useState } from "react";
import { useTranslation } from "@plane/i18n";
import { cn } from "@plane/utils";
// types
import type {
  TBranchSituation,
  TDashboard,
  TEntitySituation,
  TTrendPoint,
} from "@/services/steering-dashboard.service";
// local imports
import type { TTaskFilterPreset } from "./filters";
import { Card, EmptyLine, EntityStateBadge, Kpi, SignalBadge, TaskTitle, useDelayLabel } from "./shared";
import type { TDashboardIndex } from "./use-dashboard";

type TSynthesisProps = {
  workspaceSlug: string;
  data: TDashboard;
  index: TDashboardIndex;
  onOpenTask: (id: string) => void;
  onShowTasks: (filter: { preset?: TTaskFilterPreset; entityId?: string; assigneeId?: string }) => void;
  onShowQueue: () => void;
};

export function SynthesisTab(props: TSynthesisProps) {
  const { workspaceSlug, data, index, onOpenTask, onShowTasks, onShowQueue } = props;
  const { t } = useTranslation();
  const { kpis } = data.summary;

  return (
    <div className="flex flex-col gap-4">
      <div className="grid grid-cols-2 gap-3 md:grid-cols-3 xl:grid-cols-6">
        <Kpi
          label={t("steering.dashboard.kpi.open")}
          value={kpis.open}
          detail={t("steering.dashboard.kpi.average_progress", { value: kpis.average_progress })}
          onClick={() => onShowTasks({ preset: "open" })}
        />
        <Kpi
          label={t("steering.dashboard.kpi.late")}
          value={kpis.late}
          detail={t("steering.dashboard.kpi.late_share", { value: kpis.late_share })}
          tone="late"
          onClick={() => onShowTasks({ preset: "late" })}
        />
        <Kpi
          label={t("steering.dashboard.kpi.critical")}
          value={kpis.critical}
          tone="critical"
          onClick={() => onShowTasks({ preset: "critical" })}
        />
        <Kpi
          label={t("steering.dashboard.kpi.blocked")}
          value={kpis.blocked}
          tone="critical"
          onClick={() => onShowTasks({ preset: "blocked" })}
        />
        <Kpi label={t("steering.dashboard.kpi.queue")} value={kpis.queue} tone="queue" onClick={onShowQueue} />
        <Kpi
          label={t("steering.dashboard.kpi.due_soon")}
          value={kpis.due_soon}
          tone="soon"
          onClick={() => onShowTasks({ preset: "soon" })}
        />
      </div>

      <Situation workspaceSlug={workspaceSlug} branches={data.summary.branches} onShowTasks={onShowTasks} />

      <div className="grid gap-4 lg:grid-cols-2">
        <PriorityDelays data={data} index={index} onOpenTask={onOpenTask} />
        <BlockingPanel data={data} index={index} onOpenTask={onOpenTask} />
      </div>
      <div className="grid gap-4 lg:grid-cols-2">
        <LoadPanel data={data} index={index} onShowTasks={onShowTasks} />
        <TrendPanel trend={data.trend} />
      </div>
    </div>
  );
}

/** §3.2: one title line per branch with its totals and a dot per entity; alert branches open. */
function Situation(props: {
  workspaceSlug: string;
  branches: TBranchSituation[];
  onShowTasks: TSynthesisProps["onShowTasks"];
}) {
  const { workspaceSlug, branches, onShowTasks } = props;
  const { t } = useTranslation();
  const [open, setOpen] = useState<Record<string, boolean> | null>(null);

  // Open the branches in alert on arrival only; later reloads keep the person's choices.
  useEffect(() => {
    if (open === null && branches.length)
      setOpen(Object.fromEntries(branches.map((branch) => [branch.id, branch.has_alert])));
  }, [branches, open]);

  const allOpen = branches.every((branch) => open?.[branch.id]);

  return (
    <Card
      title={t("steering.dashboard.situation_title")}
      action={
        <button
          type="button"
          className="iag-pill iag-focus"
          onClick={() => setOpen(Object.fromEntries(branches.map((branch) => [branch.id, !allOpen])))}
        >
          {allOpen ? t("steering.dashboard.collapse_all") : t("steering.dashboard.expand_all")}
        </button>
      }
    >
      {branches.length === 0 && <EmptyLine>{t("steering.dashboard.empty.situation")}</EmptyLine>}
      <div className="flex flex-col gap-2">
        {branches.map((branch) => {
          const isOpen = !!open?.[branch.id];
          return (
            <div key={branch.id} className="rounded-xl border border-[var(--iag-border)]">
              <button
                type="button"
                aria-expanded={isOpen}
                onClick={() => setOpen({ ...open, [branch.id]: !isOpen })}
                className="iag-focus flex w-full flex-wrap items-center gap-x-4 gap-y-2 rounded-xl border-l-4 border-l-[var(--iag-gold)] bg-[var(--iag-bg)] px-3 py-2 text-left"
              >
                <span aria-hidden="true" className="text-12 text-[var(--iag-text-2)]">
                  {isOpen ? "▾" : "▸"}
                </span>
                <span className="min-w-40 flex-1 text-14 font-semibold">{branch.name}</span>
                <span className="iag-num flex flex-wrap gap-3 text-12 text-[var(--iag-text-2)]">
                  <span>{t("steering.dashboard.count.late", { count: branch.late })}</span>
                  <span>{t("steering.dashboard.count.critical", { count: branch.critical })}</span>
                  <span>{t("steering.dashboard.count.blocked", { count: branch.blocked })}</span>
                  <span>{t("steering.dashboard.count.queue", { count: branch.queue })}</span>
                </span>
                <span className="flex flex-wrap gap-1" aria-hidden="true">
                  {branch.entities.map((entity) => (
                    <span
                      key={entity.id}
                      title={`${entity.name} · ${t(`steering.dashboard.entity_state.${entity.state}`)}`}
                      className={`iag-signal-${entity.state} size-2.5 rounded-full bg-[var(--iag-signal)]`}
                    />
                  ))}
                </span>
              </button>
              {isOpen && (
                <div className="grid grid-cols-1 gap-2 p-3 sm:grid-cols-2 lg:grid-cols-3 xl:grid-cols-4">
                  {branch.entities.map((entity) => (
                    <EntityTile
                      key={entity.id}
                      workspaceSlug={workspaceSlug}
                      entity={entity}
                      onShowTasks={() => onShowTasks({ entityId: entity.id })}
                    />
                  ))}
                </div>
              )}
            </div>
          );
        })}
      </div>
    </Card>
  );
}

/** RG-14 colors the tile; the click opens the entity's space in a new tab (§3.2). */
function EntityTile(props: { workspaceSlug: string; entity: TEntitySituation; onShowTasks: () => void }) {
  const { workspaceSlug, entity, onShowTasks } = props;
  const { t } = useTranslation();
  const href =
    entity.project_ids.length === 1
      ? `/${workspaceSlug}/projects/${entity.project_ids[0]}/issues/`
      : `/${workspaceSlug}/projects/`;
  const signals = [
    entity.critical ? t("steering.dashboard.count.critical", { count: entity.critical }) : null,
    entity.blocked ? t("steering.dashboard.count.blocked", { count: entity.blocked }) : null,
    entity.queue ? t("steering.dashboard.count.queue", { count: entity.queue }) : null,
  ].filter(Boolean);

  return (
    <div
      className={cn(
        "iag-edge flex flex-col gap-1 rounded-xl border border-[var(--iag-border)] p-3",
        `iag-signal-${entity.state}`
      )}
    >
      <a
        href={href}
        target="_blank"
        rel="noreferrer"
        className="iag-focus truncate rounded text-13 font-medium hover:underline"
        title={t("steering.dashboard.open_entity_space")}
      >
        {entity.name}
      </a>
      <div className="flex items-baseline gap-2">
        <span
          className="iag-num text-24 leading-7 font-semibold"
          style={{ color: entity.late ? "var(--iag-signal)" : undefined }}
        >
          {entity.late}
        </span>
        <span className="text-12 text-[var(--iag-text-2)]">
          {t("steering.dashboard.late_label", { count: entity.late })}
        </span>
      </div>
      <p className="min-h-4 text-12 text-[var(--iag-text-2)]">{signals.join(" · ") || " "}</p>
      <div className="flex items-center justify-between gap-2">
        <EntityStateBadge state={entity.state} />
        <button
          type="button"
          onClick={onShowTasks}
          className="iag-focus rounded text-12 text-[var(--iag-gold-text)] hover:underline"
        >
          {t("steering.dashboard.see_tasks", { count: entity.open })}
        </button>
      </div>
    </div>
  );
}

/** RG-12: the eight first. */
function PriorityDelays(props: { data: TDashboard; index: TDashboardIndex; onOpenTask: (id: string) => void }) {
  const { data, index, onOpenTask } = props;
  const { t } = useTranslation();
  const delayLabel = useDelayLabel();
  const rows = data.summary.priority_delays.map((id) => index.tasks.get(id)).filter((task) => !!task);
  return (
    <Card title={t("steering.dashboard.priority_delays")} count={rows.length}>
      {rows.length === 0 ? (
        <EmptyLine>{t("steering.dashboard.empty.delays")}</EmptyLine>
      ) : (
        <ul className="flex flex-col divide-y divide-[var(--iag-border)]">
          {rows.map((task) => (
            <li
              key={task.id}
              className={`iag-edge iag-signal-${task.signal} flex flex-wrap items-center gap-2 py-2 pl-3`}
            >
              <div className="min-w-0 flex-1">
                <TaskTitle task={task} onOpen={onOpenTask} />
                <p className="text-12 text-[var(--iag-text-2)]">
                  {index.entityName(task.entity_id)} · {t(task.priority)} · {index.assigneeNames(task)}
                </p>
              </div>
              <span className="iag-num text-13 font-semibold" style={{ color: "var(--iag-signal)" }}>
                {delayLabel(task)}
              </span>
              <SignalBadge signal={task.signal} />
            </li>
          ))}
        </ul>
      )}
    </Card>
  );
}

/** §7 « Vue d'ensemble »: the work items others wait on, late ones first. */
function BlockingPanel(props: { data: TDashboard; index: TDashboardIndex; onOpenTask: (id: string) => void }) {
  const { data, index, onOpenTask } = props;
  const { t } = useTranslation();
  const delayLabel = useDelayLabel();
  return (
    <Card title={t("steering.dashboard.blocking_title")} count={data.summary.blocking.length}>
      {data.summary.blocking.length === 0 ? (
        <EmptyLine>{t("steering.dashboard.empty.blocking")}</EmptyLine>
      ) : (
        <ul className="flex flex-col divide-y divide-[var(--iag-border)]">
          {data.summary.blocking.map((item) => {
            const task = index.tasks.get(item.id);
            if (!task) return null;
            return (
              <li
                key={item.id}
                className={`iag-edge iag-signal-${task.signal} flex flex-wrap items-center gap-2 py-2 pl-3`}
              >
                <div className="min-w-0 flex-1">
                  <TaskTitle task={task} onOpen={onOpenTask} />
                  <p className="text-12 text-[var(--iag-text-2)]">
                    {index.entityName(task.entity_id)} · {t("steering.dashboard.blocks_count", { count: item.count })}
                  </p>
                </div>
                {task.in_queue && <SignalBadge signal="queue" />}
                {task.days_late > 0 && (
                  <span className="iag-num text-13 font-semibold" style={{ color: "var(--iag-signal)" }}>
                    {delayLabel(task)}
                  </span>
                )}
              </li>
            );
          })}
        </ul>
      )}
    </Card>
  );
}

/** §6.1 « Charge par responsable ». */
function LoadPanel(props: { data: TDashboard; index: TDashboardIndex; onShowTasks: TSynthesisProps["onShowTasks"] }) {
  const { data, index, onShowTasks } = props;
  const { t } = useTranslation();
  const [showAll, setShowAll] = useState(false);
  const load = showAll ? data.summary.load : data.summary.load.slice(0, 10);
  return (
    <Card
      title={t("steering.dashboard.load_title")}
      count={data.summary.load.length}
      action={
        data.summary.load.length > 10 && (
          <button type="button" className="iag-pill iag-focus" onClick={() => setShowAll(!showAll)}>
            {showAll ? t("steering.dashboard.show_less") : t("steering.dashboard.show_all")}
          </button>
        )
      }
    >
      {load.length === 0 ? (
        <EmptyLine>{t("steering.dashboard.empty.load")}</EmptyLine>
      ) : (
        <div className="overflow-x-auto">
          <table className="iag-table w-full text-13">
            <thead>
              <tr>
                <th scope="col">{t("steering.task.fields.assignee")}</th>
                <th scope="col" className="text-right">
                  {t("steering.dashboard.columns.open")}
                </th>
                <th scope="col" className="text-right">
                  {t("steering.dashboard.columns.late")}
                </th>
                <th scope="col" className="text-right">
                  {t("steering.dashboard.columns.critical")}
                </th>
              </tr>
            </thead>
            <tbody>
              {load.map((item) => (
                <tr key={item.person_id}>
                  <td>
                    <button
                      type="button"
                      className="iag-focus rounded hover:underline"
                      onClick={() => onShowTasks({ assigneeId: item.person_id })}
                    >
                      {index.personName(item.person_id)}
                    </button>
                  </td>
                  <td className="iag-num text-right">{item.open}</td>
                  <td className="iag-num text-right" style={{ color: item.late ? "var(--iag-late)" : undefined }}>
                    {item.late}
                  </td>
                  <td
                    className="iag-num text-right"
                    style={{ color: item.critical ? "var(--iag-critical)" : undefined }}
                  >
                    {item.critical}
                  </td>
                </tr>
              ))}
            </tbody>
          </table>
        </div>
      )}
    </Card>
  );
}

const TREND_SERIES = [
  { key: "open", color: "var(--iag-text-2)" },
  { key: "late", color: "var(--iag-late)" },
  { key: "critical", color: "var(--iag-critical)" },
] as const;

/** §6.1 « Tendance hebdomadaire »: the weekly snapshots, taken on Fridays at noon. */
function TrendPanel(props: { trend: TTrendPoint[] }) {
  const { t } = useTranslation();
  const { trend } = props;
  if (trend.length < 2)
    return (
      <Card title={t("steering.dashboard.trend_title")}>
        <EmptyLine>{t("steering.dashboard.empty.trend")}</EmptyLine>
      </Card>
    );
  const width = 520;
  const height = 160;
  const max = Math.max(1, ...trend.flatMap((point) => TREND_SERIES.map((serie) => point[serie.key])));
  const x = (position: number) => 24 + (position * (width - 48)) / (trend.length - 1);
  const y = (value: number) => height - 24 - (value * (height - 48)) / max;
  return (
    <Card title={t("steering.dashboard.trend_title")}>
      <svg
        viewBox={`0 0 ${width} ${height}`}
        className="h-40 w-full"
        role="img"
        aria-label={t("steering.dashboard.trend_title")}
      >
        {TREND_SERIES.map((serie) => (
          <polyline
            key={serie.key}
            fill="none"
            stroke={serie.color}
            strokeWidth={2}
            points={trend.map((point, position) => `${x(position)},${y(point[serie.key])}`).join(" ")}
          />
        ))}
        {trend.map((point, position) => (
          <text
            key={point.date}
            x={x(position)}
            y={height - 6}
            textAnchor="middle"
            fontSize="10"
            fill="var(--iag-text-2)"
          >
            {point.date.slice(5)}
          </text>
        ))}
      </svg>
      <p className="flex flex-wrap gap-3 text-12 text-[var(--iag-text-2)]">
        {TREND_SERIES.map((serie) => (
          <span key={serie.key} className="inline-flex items-center gap-1">
            <span aria-hidden="true" className="h-0.5 w-4" style={{ background: serie.color }} />
            {t(`steering.dashboard.columns.${serie.key}`)}
          </span>
        ))}
      </p>
    </Card>
  );
}
