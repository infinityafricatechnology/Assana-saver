/**
 * Copyright (c) 2023-present Plane Software, Inc. and contributors
 * SPDX-License-Identifier: AGPL-3.0-only
 * See the LICENSE file for details.
 */

import { useMemo } from "react";
import type { ReactNode } from "react";
import { sortBy } from "lodash-es";
import { useTranslation } from "@plane/i18n";
// types
import type { TDashboard, TDashboardTask } from "@/services/steering-dashboard.service";
// local imports
import type { TDashboardAction } from "./action-dialogs";
import { Card, EmptyLine, TaskTitle, formatDate } from "./shared";
import type { TDashboardIndex } from "./use-dashboard";

type TReviewTabProps = {
  data: TDashboard;
  index: TDashboardIndex;
  branchId: string | null;
  onOpenTask: (id: string) => void;
  onAction: (action: TDashboardAction) => void;
};

/** §6.5: the records that contradict themselves (RG-10) and those nobody updates (RG-09). */
export function ReviewTab(props: TReviewTabProps) {
  const { data, index, branchId, onOpenTask, onAction } = props;
  const { t } = useTranslation();
  const inScope = (task: TDashboardTask) => !branchId || task.branch_id === branchId;
  const inconsistent = useMemo(
    () => data.tasks.filter((task) => task.inconsistencies.length && inScope(task)),
    // oxlint-disable-next-line eslint-plugin-react-hooks/exhaustive-deps
    [data.tasks, branchId]
  );
  const dormant = useMemo(
    () =>
      sortBy(
        data.tasks.filter((task) => task.dormant && inScope(task)),
        (task) => -task.dormant_days
      ),
    // oxlint-disable-next-line eslint-plugin-react-hooks/exhaustive-deps
    [data.tasks, branchId]
  );

  const row = (task: TDashboardTask, reason: ReactNode) => (
    <ReviewRow
      key={task.id}
      task={task}
      index={index}
      reason={reason}
      canRemind={data.viewer.can_remind}
      onOpenTask={onOpenTask}
      onRemind={() => onAction({ kind: "remind", task })}
    />
  );

  return (
    <div className="flex flex-col gap-4">
      <Card title={t("steering.dashboard.inconsistencies_title")} count={inconsistent.length}>
        {inconsistent.length === 0 ? (
          <EmptyLine>{t("steering.dashboard.empty.inconsistencies")}</EmptyLine>
        ) : (
          <ul className="flex flex-col divide-y divide-[var(--iag-border)]">
            {inconsistent.map((task) =>
              row(
                task,
                task.inconsistencies.map((reason) => t(`steering.dashboard.inconsistency.${reason}`)).join(" · ")
              )
            )}
          </ul>
        )}
      </Card>
      <Card title={t("steering.dashboard.dormant_title")} count={dormant.length}>
        {dormant.length === 0 ? (
          <EmptyLine>{t("steering.dashboard.empty.dormant")}</EmptyLine>
        ) : (
          <ul className="flex flex-col divide-y divide-[var(--iag-border)]">
            {dormant.map((task) => row(task, t("steering.dashboard.not_updated_for", { count: task.dormant_days })))}
          </ul>
        )}
      </Card>
    </div>
  );
}

function ReviewRow(props: {
  task: TDashboardTask;
  index: TDashboardIndex;
  reason: ReactNode;
  canRemind: boolean;
  onOpenTask: (id: string) => void;
  onRemind: () => void;
}) {
  const { task, index, reason, canRemind, onOpenTask, onRemind } = props;
  const { t } = useTranslation();
  return (
    <li className="flex flex-wrap items-center gap-3 py-3">
      <div className="min-w-0 flex-1">
        <TaskTitle task={task} onOpen={onOpenTask} />
        <p className="text-12 text-[var(--iag-text-2)]">
          {index.entityName(task.entity_id)} · {index.assigneeNames(task)}
        </p>
        <p className="text-12 font-medium text-[var(--iag-late)]">{reason}</p>
        <p className="text-11 text-[var(--iag-text-2)]">
          {task.reminders.count
            ? t("steering.dashboard.reminders_sent", {
                count: task.reminders.count,
                date: formatDate(task.reminders.last_at),
              })
            : t("steering.dashboard.never_reminded")}
        </p>
      </div>
      <div className="flex flex-wrap gap-2">
        {canRemind && (
          <button type="button" className="iag-pill iag-pill-gold iag-focus" onClick={onRemind}>
            {t("steering.dashboard.actions.remind")}
          </button>
        )}
        <button type="button" className="iag-pill iag-focus" onClick={() => onOpenTask(task.id)}>
          {t("steering.dashboard.open_sheet")}
        </button>
      </div>
    </li>
  );
}
