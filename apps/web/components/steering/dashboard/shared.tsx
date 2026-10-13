/**
 * Copyright (c) 2023-present Plane Software, Inc. and contributors
 * SPDX-License-Identifier: AGPL-3.0-only
 * See the LICENSE file for details.
 */

import type { ReactNode } from "react";
import { useTranslation } from "@plane/i18n";
import { cn, renderFormattedDate } from "@plane/utils";
// types
import type {
  TDashboardTask,
  TEntityState,
  TRelatedTask,
  TSteeringSignal,
} from "@/services/steering-dashboard.service";
// local imports
import type { TDashboardIndex } from "./use-dashboard";

export const formatDate = (value: string | null | undefined) => (value ? (renderFormattedDate(value) ?? "") : "");

/** RG-03: a signal reads by its label as much as by its color. */
export function SignalBadge(props: { signal: TSteeringSignal | "blocked" | "queue"; className?: string }) {
  const { t } = useTranslation();
  return (
    <span className={cn("iag-signal", `iag-signal-${props.signal}`, props.className)}>
      {t(`steering.dashboard.signal.${props.signal}`)}
    </span>
  );
}

export function EntityStateBadge(props: { state: TEntityState }) {
  const { t } = useTranslation();
  return (
    <span className={`iag-signal iag-signal-${props.state}`}>
      {t(`steering.dashboard.entity_state.${props.state}`)}
    </span>
  );
}

/** « J+99 », « Dans 8 j », « Aujourd'hui » (§5 control cases). */
export function useDelayLabel() {
  const { t } = useTranslation();
  return (task: Pick<TDashboardTask, "days_late" | "days_left" | "is_open">) => {
    if (!task.is_open) return "";
    if (task.days_late > 0) return t("steering.dashboard.days.late", { count: task.days_late });
    if (task.days_left === 0) return t("steering.dashboard.days.today");
    if (task.days_left !== null && task.days_left !== undefined)
      return t("steering.dashboard.days.left", { count: task.days_left });
    return "";
  };
}

/** RG-13: « J-n » before the risk takes effect, « J+n » once it has. */
export function useRiskCountdown() {
  const { t } = useTranslation();
  return (days: number | null | undefined) => {
    if (days === null || days === undefined) return "";
    return days >= 0
      ? t("steering.dashboard.days.before", { count: days })
      : t("steering.dashboard.days.late", { count: -days });
  };
}

export function Card(props: {
  title?: ReactNode;
  count?: number;
  action?: ReactNode;
  children: ReactNode;
  className?: string;
}) {
  return (
    <section className={cn("iag-card flex min-w-0 flex-col", props.className)}>
      {(props.title || props.action) && (
        <header className="flex items-center justify-between gap-2 px-4 pt-4 pb-2">
          <h2 className="flex items-center gap-2 text-14 font-semibold">
            {props.title}
            {props.count !== undefined && (
              <span className="iag-num rounded-full bg-[var(--iag-bg)] px-2 text-12 font-medium text-[var(--iag-text-2)]">
                {props.count}
              </span>
            )}
          </h2>
          {props.action}
        </header>
      )}
      <div className="min-w-0 px-4 pb-4">{props.children}</div>
    </section>
  );
}

export function EmptyLine(props: { children: ReactNode }) {
  return <p className="py-3 text-13 text-[var(--iag-text-2)]">{props.children}</p>;
}

/** A work item's key and name, opening its sheet. */
export function TaskTitle(props: { task: Pick<TDashboardTask, "id" | "key" | "name">; onOpen: (id: string) => void }) {
  return (
    <button
      type="button"
      onClick={() => props.onOpen(props.task.id)}
      className="iag-focus min-w-0 rounded text-left hover:underline"
    >
      <span className="iag-num mr-2 text-12 text-[var(--iag-text-2)]">{props.task.key}</span>
      <span className="text-13 font-medium">{props.task.name}</span>
    </button>
  );
}

/** §6.2, §7: under a blocked work item, what blocks it, its entity and its state. */
export function BlockedByLines(props: { task: TDashboardTask; index: TDashboardIndex; onOpen: (id: string) => void }) {
  const { t } = useTranslation();
  const delayLabel = useDelayLabel();
  if (!props.task.blocked_by.length) return null;
  return (
    <ul className="mt-1 flex flex-col gap-0.5">
      {props.task.blocked_by.map((id) => {
        const blocker: TDashboardTask | TRelatedTask | undefined = props.index.item(id);
        if (!blocker) return null;
        const state =
          blocker.days_late > 0
            ? delayLabel({ days_late: blocker.days_late, days_left: null, is_open: true })
            : t(`steering.task.status.${blocker.status}`);
        return (
          <li key={id} className="flex flex-wrap items-center gap-1 text-12 text-[var(--iag-critical)]">
            <span aria-hidden="true">⛓</span>
            <span>{t("steering.dashboard.blocked_by")}</span>
            <button
              type="button"
              onClick={() => props.onOpen(id)}
              className="iag-focus rounded font-medium hover:underline"
              disabled={!props.index.tasks.has(id)}
            >
              {blocker.key} {blocker.name}
            </button>
            <span className="text-[var(--iag-text-2)]">
              · {props.index.entityName(blocker.entity_id) || t("steering.dashboard.outside_steering")} · {state}
            </span>
          </li>
        );
      })}
    </ul>
  );
}

/** One of the six indicators (§6.1); every figure opens the list behind it. */
export function Kpi(props: {
  label: string;
  value: number;
  detail?: string;
  tone?: "critical" | "late" | "soon" | "queue" | "neutral";
  onClick: () => void;
}) {
  const tone = props.tone && props.tone !== "neutral" ? `iag-signal-${props.tone}` : "";
  return (
    <button
      type="button"
      onClick={props.onClick}
      className={cn("iag-card iag-focus iag-edge flex flex-col items-start gap-1 p-4 text-left", tone)}
    >
      <span className="text-12 text-[var(--iag-text-2)]">{props.label}</span>
      <span
        className="iag-num text-28 leading-8 font-semibold"
        style={tone ? { color: "var(--iag-signal)" } : undefined}
      >
        {props.value}
      </span>
      {props.detail && <span className="text-12 text-[var(--iag-text-2)]">{props.detail}</span>}
    </button>
  );
}
