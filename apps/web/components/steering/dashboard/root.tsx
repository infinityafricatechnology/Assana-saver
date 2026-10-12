/**
 * Copyright (c) 2023-present Plane Software, Inc. and contributors
 * SPDX-License-Identifier: AGPL-3.0-only
 * See the LICENSE file for details.
 */

import { useRef, useState } from "react";
import type { KeyboardEvent } from "react";
import { useParams } from "next/navigation";
import { useTranslation } from "@plane/i18n";
// local imports
import type { TDashboardAction } from "./action-dialogs";
import { DashboardActionDialog } from "./action-dialogs";
import { DeadlinesTab } from "./deadlines-tab";
import { ComexExportButton } from "./exports";
import type { TTaskFilter, TTaskFilterPreset } from "./filters";
import { DEFAULT_TASK_FILTER } from "./filters";
import { SteeringDashboardHeader } from "./header";
import { QueueTab } from "./queue-tab";
import { ReportTab } from "./report-tab";
import { ReviewTab } from "./review-tab";
import { SynthesisTab } from "./synthesis-tab";
import { TaskSheet } from "./task-sheet";
import { TasksTab } from "./tasks-tab";
import { useDashboardIndex, useSteeringDashboard } from "./use-dashboard";

const ALL_TABS = ["synthesis", "tasks", "queue", "deadlines", "review", "report"] as const;
type TTab = (typeof ALL_TABS)[number];

/** The steering space (cahier des charges §6): five tabs, a work item sheet, read only. */
export function SteeringDashboardRoot() {
  const { t } = useTranslation();
  const { workspaceSlug } = useParams();
  const slug = workspaceSlug?.toString() ?? "";
  const [branchId, setBranchId] = useState<string | null>(null);
  const [tab, setTab] = useState<TTab>("synthesis");
  const [taskFilter, setTaskFilter] = useState<TTaskFilter>(DEFAULT_TASK_FILTER);
  const [sheetId, setSheetId] = useState<string | null>(null);
  const [action, setAction] = useState<TDashboardAction | null>(null);
  const tabRefs = useRef<Record<string, HTMLButtonElement | null>>({});
  const { data, error, isLive, reload } = useSteeringDashboard(slug, branchId);
  const index = useDashboardIndex(data);

  if (error?.code === "no_steering_profile")
    return (
      <div className="iag-steering flex h-full items-center justify-center p-8">
        <div className="iag-card max-w-md p-6 text-center">
          <h1 className="text-16 font-semibold">{t("steering.dashboard.title")}</h1>
          <p className="mt-2 text-13 text-[var(--iag-text-2)]">{t("steering.dashboard.no_access")}</p>
        </div>
      </div>
    );
  if (!data || !index)
    return (
      <div className="iag-steering flex h-full items-center justify-center p-8" role="status">
        <p className="text-13 text-[var(--iag-text-2)]">{error ? t("common.error.message") : t("common.loading")}</p>
      </div>
    );

  // The weekly report is prepared and sent by the Cabinet and the CEO (§9.3, §10).
  const TABS = ALL_TABS.filter((key) => key !== "report" || data.viewer.can_requalify);

  const showTasks = (filter: { preset?: TTaskFilterPreset; entityId?: string; assigneeId?: string }) => {
    setTaskFilter({
      ...DEFAULT_TASK_FILTER,
      preset: filter.preset ?? "open",
      entityId: filter.entityId ?? null,
      assigneeId: filter.assigneeId ?? null,
    });
    setTab("tasks");
  };

  const inBranch = (task: { branch_id: string | null }) => !branchId || task.branch_id === branchId;
  const counts: Partial<Record<TTab, number>> = {
    queue: data.tasks.filter((task) => task.in_queue && inBranch(task)).length,
    review: data.tasks.filter((task) => (task.dormant || task.inconsistencies.length > 0) && inBranch(task)).length,
  };

  // Arrow keys move between the tabs (WAI-ARIA tabs pattern).
  const handleTabKey = (event: KeyboardEvent<HTMLButtonElement>) => {
    const position = TABS.indexOf(tab);
    const next =
      event.key === "ArrowRight"
        ? TABS[(position + 1) % TABS.length]
        : event.key === "ArrowLeft"
          ? TABS[(position + TABS.length - 1) % TABS.length]
          : event.key === "Home"
            ? TABS[0]
            : event.key === "End"
              ? TABS[TABS.length - 1]
              : null;
    if (!next) return;
    event.preventDefault();
    setTab(next);
    tabRefs.current[next]?.focus();
  };

  return (
    <div className="iag-steering min-h-full pb-10">
      <SteeringDashboardHeader
        data={data}
        branchId={branchId}
        isLive={isLive}
        onBranchChange={setBranchId}
        actions={<ComexExportButton workspaceSlug={slug} branchId={branchId} today={data.today} />}
      />
      <div className="mx-auto flex max-w-[1600px] flex-col gap-4 px-4 pt-4 sm:px-8">
        {data.report_ready && tab !== "report" && (
          <div
            role="status"
            className="iag-card flex flex-wrap items-center justify-between gap-2 border-[var(--iag-gold)] px-4 py-3 text-13"
          >
            <span>{t("steering.report.ready_banner", { week: data.report_ready.week })}</span>
            <button type="button" className="iag-pill iag-pill-gold iag-focus" onClick={() => setTab("report")}>
              {t("steering.report.open")}
            </button>
          </div>
        )}
        <div
          role="tablist"
          aria-label={t("steering.dashboard.title")}
          className="-mx-4 flex gap-2 overflow-x-auto px-4 pb-1 sm:mx-0 sm:px-0"
        >
          {TABS.map((key) => (
            <button
              key={key}
              ref={(element) => {
                tabRefs.current[key] = element;
              }}
              id={`steering-tab-${key}`}
              type="button"
              role="tab"
              aria-selected={tab === key}
              aria-controls={`steering-panel-${key}`}
              tabIndex={tab === key ? 0 : -1}
              onClick={() => setTab(key)}
              onKeyDown={handleTabKey}
              className="iag-pill iag-focus shrink-0"
            >
              {key === "report" ? t("steering.report.tab") : t(`steering.dashboard.tabs.${key}`)}
              {counts[key] !== undefined && <span className="iag-num opacity-75">{counts[key]}</span>}
            </button>
          ))}
        </div>
        <div
          role="tabpanel"
          id={`steering-panel-${tab}`}
          aria-labelledby={`steering-tab-${tab}`}
          tabIndex={0}
          className="outline-none"
        >
          {tab === "synthesis" && (
            <SynthesisTab
              workspaceSlug={slug}
              data={data}
              index={index}
              onOpenTask={setSheetId}
              onShowTasks={showTasks}
              onShowQueue={() => setTab("queue")}
            />
          )}
          {tab === "tasks" && (
            <TasksTab
              data={data}
              index={index}
              branchId={branchId}
              filter={taskFilter}
              onFilterChange={setTaskFilter}
              onOpenTask={setSheetId}
              workspaceSlug={slug}
            />
          )}
          {tab === "queue" && (
            <QueueTab data={data} index={index} branchId={branchId} onOpenTask={setSheetId} onAction={setAction} />
          )}
          {tab === "deadlines" && (
            <DeadlinesTab data={data} index={index} branchId={branchId} onOpenTask={setSheetId} />
          )}
          {tab === "report" && <ReportTab workspaceSlug={slug} initialReportId={data.report_ready?.id ?? null} />}
          {tab === "review" && (
            <ReviewTab data={data} index={index} branchId={branchId} onOpenTask={setSheetId} onAction={setAction} />
          )}
        </div>
      </div>
      <TaskSheet
        workspaceSlug={slug}
        data={data}
        index={index}
        taskId={sheetId}
        onClose={() => setSheetId(null)}
        onOpenTask={setSheetId}
        onAction={setAction}
      />
      <DashboardActionDialog
        workspaceSlug={slug}
        action={action}
        onClose={() => setAction(null)}
        onDone={() => void reload()}
      />
    </div>
  );
}
