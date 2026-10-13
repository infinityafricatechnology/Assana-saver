/**
 * Copyright (c) 2023-present Plane Software, Inc. and contributors
 * SPDX-License-Identifier: AGPL-3.0-only
 * See the LICENSE file for details.
 */

import { useMemo, useState } from "react";
import { addDays, addWeeks, format, getISOWeek, parseISO, startOfISOWeek } from "date-fns";
import { sortBy } from "lodash-es";
import { useTranslation } from "@plane/i18n";
import { cn } from "@plane/utils";
// types
import type { TDashboard, TDashboardTask } from "@/services/steering-dashboard.service";
// local imports
import { formatDate, useDelayLabel } from "./shared";
import type { TDashboardIndex } from "./use-dashboard";

const RANGES = [14, 30, 90] as const;

type TDeadlinesTabProps = {
  data: TDashboard;
  index: TDashboardIndex;
  branchId: string | null;
  onOpenTask: (id: string) => void;
};

/** §6.4: a weekly timeline over 14 days (30 or 90 for planning), the overdue ones first. */
export function DeadlinesTab(props: TDeadlinesTabProps) {
  const { data, index, branchId, onOpenTask } = props;
  const { t } = useTranslation();
  const [range, setRange] = useState<(typeof RANGES)[number]>(14);
  const today = parseISO(data.today);

  const { overdue, weeks } = useMemo(() => {
    const open = data.tasks.filter((task) => task.is_open && (!branchId || task.branch_id === branchId));
    const end = addDays(today, range);
    const columns: { start: Date; week: number; tasks: TDashboardTask[] }[] = [];
    for (let start = startOfISOWeek(today); start <= end; start = addWeeks(start, 1))
      columns.push({ start, week: getISOWeek(start), tasks: [] });
    for (const task of open) {
      if (!task.target_date || task.days_late > 0) continue;
      const due = parseISO(task.target_date);
      if (due > end) continue;
      const column = columns.find((item) => due >= item.start && due < addWeeks(item.start, 1));
      column?.tasks.push(task);
    }
    for (const column of columns) column.tasks = sortBy(column.tasks, "target_date");
    return {
      overdue: sortBy(
        open.filter((task) => task.days_late > 0),
        (task) => -task.days_late
      ),
      weeks: columns,
    };
    // `today` derives from data.today.
    // oxlint-disable-next-line eslint-plugin-react-hooks/exhaustive-deps
  }, [data.tasks, data.today, branchId, range]);

  const overdueByEntity = sortBy(
    Object.entries(
      overdue.reduce<Record<string, number>>((counts, task) => {
        counts[task.entity_id] = (counts[task.entity_id] ?? 0) + 1;
        return counts;
      }, {})
    ),
    ([, count]) => -count
  );

  return (
    <div className="flex flex-col gap-4">
      <div className="flex flex-wrap items-center gap-2" role="group" aria-label={t("steering.dashboard.horizon")}>
        <span className="text-13 text-[var(--iag-text-2)]">{t("steering.dashboard.horizon")}</span>
        {RANGES.map((days) => (
          <button
            key={days}
            type="button"
            aria-pressed={range === days}
            className="iag-pill iag-focus"
            onClick={() => setRange(days)}
          >
            {t("steering.dashboard.days_count", { count: days })}
          </button>
        ))}
      </div>
      <div className="flex flex-col gap-3 md:flex-row md:overflow-x-auto md:pb-2">
        <Column
          title={t("steering.dashboard.already_overdue")}
          subtitle={t("steering.dashboard.task_count", { count: overdue.length })}
          tone="critical"
        >
          {overdueByEntity.length > 0 && (
            <ul className="mb-2 flex flex-col gap-0.5 text-12">
              {overdueByEntity.map(([entityId, count]) => (
                <li key={entityId} className="flex justify-between gap-2">
                  <span className="truncate">{index.entityName(entityId)}</span>
                  <span className="iag-num font-semibold">{count}</span>
                </li>
              ))}
            </ul>
          )}
          {overdue.map((task) => (
            <TaskChip key={task.id} task={task} index={index} onOpenTask={onOpenTask} />
          ))}
        </Column>
        {weeks.map((column) => {
          const isCurrent = column.start.getTime() === startOfISOWeek(today).getTime();
          return (
            <Column
              key={column.week}
              title={t("steering.dashboard.week", { number: column.week })}
              subtitle={`${formatDate(format(column.start, "yyyy-MM-dd"))} – ${formatDate(format(addDays(column.start, 6), "yyyy-MM-dd"))}`}
              current={isCurrent}
            >
              {column.tasks.length === 0 && <p className="text-12 text-[var(--iag-text-2)]">—</p>}
              {column.tasks.map((task) => (
                <TaskChip key={task.id} task={task} index={index} onOpenTask={onOpenTask} />
              ))}
            </Column>
          );
        })}
      </div>
    </div>
  );
}

function Column(props: {
  title: string;
  subtitle: string;
  tone?: "critical";
  current?: boolean;
  children: React.ReactNode;
}) {
  const { t } = useTranslation();
  return (
    <section
      className={cn("iag-card flex shrink-0 flex-col gap-2 p-3 md:w-64", {
        "border-[var(--iag-gold)]! ring-1 ring-[var(--iag-gold)]": props.current,
      })}
    >
      <header>
        <h3
          className="flex items-center gap-2 text-13 font-semibold"
          style={props.tone ? { color: "var(--iag-critical)" } : undefined}
        >
          {props.title}
          {props.current && (
            <span className="rounded-full bg-[var(--iag-gold)] px-2 text-11 text-[var(--iag-on-gold)]">
              {t("steering.dashboard.current_week")}
            </span>
          )}
        </h3>
        <p className="iag-num text-12 text-[var(--iag-text-2)]">{props.subtitle}</p>
      </header>
      {props.children}
    </section>
  );
}

function TaskChip(props: { task: TDashboardTask; index: TDashboardIndex; onOpenTask: (id: string) => void }) {
  const { task, index, onOpenTask } = props;
  const { t } = useTranslation();
  const delayLabel = useDelayLabel();
  return (
    <button
      type="button"
      onClick={() => onOpenTask(task.id)}
      className={`iag-focus iag-edge iag-signal-${task.signal} flex flex-col gap-0.5 rounded-lg border border-[var(--iag-border)] py-1.5 pr-2 pl-3 text-left`}
    >
      <span className="text-12 font-medium">
        {task.blocked && (
          <span title={t("steering.dashboard.signal.blocked")} className="mr-1 text-[var(--iag-critical)]">
            ⛓<span className="sr-only">{t("steering.dashboard.signal.blocked")}</span>
          </span>
        )}
        {task.name}
      </span>
      <span className="iag-num text-11 text-[var(--iag-text-2)]">
        {task.key} · {index.entityName(task.entity_id)} · {formatDate(task.target_date)}
        {task.days_late > 0 && ` · ${delayLabel(task)}`}
      </span>
    </button>
  );
}
