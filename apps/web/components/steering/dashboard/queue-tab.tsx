/**
 * Copyright (c) 2023-present Plane Software, Inc. and contributors
 * SPDX-License-Identifier: AGPL-3.0-only
 * See the LICENSE file for details.
 */

import { useMemo, useState } from "react";
import { sortBy } from "lodash-es";
import { useTranslation } from "@plane/i18n";
// types
import type { TDashboard, TDashboardTask, TSteeringPriority } from "@/services/steering-dashboard.service";
// local imports
import type { TDashboardAction } from "./action-dialogs";
import { Card, EmptyLine, SignalBadge, TaskTitle, formatDate, useDelayLabel, useRiskCountdown } from "./shared";
import type { TDashboardIndex } from "./use-dashboard";

type TQueueSort = "priority" | "deadline" | "waiting";
const PRIORITY_GROUPS: TSteeringPriority[] = ["urgent", "high", "medium"];

type TQueueTabProps = {
  data: TDashboard;
  index: TDashboardIndex;
  branchId: string | null;
  onOpenTask: (id: string) => void;
  onAction: (action: TDashboardAction) => void;
};

/** §6.3: the work items submitted to the CEO, then the other blockages (RG-05). */
export function QueueTab(props: TQueueTabProps) {
  const { data, index, branchId, onOpenTask, onAction } = props;
  const { t } = useTranslation();
  const [sort, setSort] = useState<TQueueSort>("priority");

  const queue = useMemo(() => {
    const rows = data.queue
      .map((id) => index.tasks.get(id))
      .filter((task): task is TDashboardTask => !!task && (!branchId || task.branch_id === branchId));
    if (sort === "deadline") return sortBy(rows, (task) => task.target_date ?? "9999");
    if (sort === "waiting") return sortBy(rows, (task) => -(task.submission?.waiting_days ?? 0));
    return rows;
  }, [data.queue, index, branchId, sort]);

  const others = useMemo(
    () =>
      sortBy(
        data.tasks.filter(
          (task) => task.is_open && task.status === "waiting" && (!branchId || task.branch_id === branchId)
        ),
        (task) => -(task.waiting_days ?? 0)
      ),
    [data.tasks, branchId]
  );

  const groups =
    sort === "priority"
      ? PRIORITY_GROUPS.map((priority) => ({
          priority,
          rows: queue.filter((task) => task.retained_priority === priority),
        })).filter((group) => group.rows.length)
      : [{ priority: null, rows: queue }];

  return (
    <div className="flex flex-col gap-4">
      <div className="flex flex-wrap items-center justify-between gap-2">
        <h2 className="text-16 font-semibold">
          {t("steering.dashboard.queue_title")}{" "}
          <span className="iag-num text-[var(--iag-text-2)]">({queue.length})</span>
        </h2>
        <label className="flex items-center gap-2 text-13 text-[var(--iag-text-2)]">
          {t("steering.dashboard.sort_by")}
          <select
            value={sort}
            onChange={(event) => setSort(event.target.value as TQueueSort)}
            className="iag-focus rounded-full border border-[var(--iag-border)] bg-[var(--iag-card)] px-3 py-1.5 text-13 text-[var(--iag-text)]"
          >
            <option value="priority">{t("steering.dashboard.sort.priority")}</option>
            <option value="deadline">{t("steering.dashboard.sort.deadline")}</option>
            <option value="waiting">{t("steering.dashboard.sort.waiting")}</option>
          </select>
        </label>
      </div>

      {queue.length === 0 && (
        <Card>
          <EmptyLine>{t("steering.dashboard.empty.queue")}</EmptyLine>
        </Card>
      )}
      {groups.map((group) => (
        <section key={group.priority ?? "all"} className="flex flex-col gap-3">
          {group.priority && (
            <h3 className="text-14 font-semibold">
              {t(group.priority)} <span className="iag-num text-[var(--iag-text-2)]">({group.rows.length})</span>
            </h3>
          )}
          <div className="grid gap-3 lg:grid-cols-2">
            {group.rows.map((task) => (
              <QueueCard
                key={task.id}
                task={task}
                data={data}
                index={index}
                onOpenTask={onOpenTask}
                onAction={onAction}
              />
            ))}
          </div>
        </section>
      ))}

      <Card title={t("steering.dashboard.other_blockages")} count={others.length}>
        {others.length === 0 ? (
          <EmptyLine>{t("steering.dashboard.empty.other_blockages")}</EmptyLine>
        ) : (
          <OtherBlockages rows={others} index={index} onOpenTask={onOpenTask} />
        )}
      </Card>
    </div>
  );
}

function QueueCard(props: {
  task: TDashboardTask;
  data: TDashboard;
  index: TDashboardIndex;
  onOpenTask: (id: string) => void;
  onAction: (action: TDashboardAction) => void;
}) {
  const { task, data, index, onOpenTask, onAction } = props;
  const { t } = useTranslation();
  const delayLabel = useDelayLabel();
  const riskCountdown = useRiskCountdown();
  const submission = task.submission!;
  const unblocked = task.blocking.map((id) => index.item(id)).filter((item) => !!item);

  return (
    <article className="iag-card iag-edge iag-signal-queue flex flex-col gap-3 p-4">
      <div className="flex flex-wrap items-start justify-between gap-2">
        <div className="min-w-0">
          <TaskTitle task={task} onOpen={onOpenTask} />
          <p className="text-12 text-[var(--iag-text-2)]">
            {index.projects.get(task.project_id)?.name} · {index.entityName(task.entity_id)}
          </p>
        </div>
        <SignalBadge signal={task.signal} />
      </div>
      {task.requalification && (
        <p className="rounded-lg bg-[var(--iag-bg)] px-3 py-2 text-12">
          {t("steering.circuit.requalified", {
            by: t(`steering.profiles.roles.${task.requalification.by_role}`),
            declared: t(task.priority),
            retained: t(task.requalification.priority),
          })}
          {task.requalification.comment && ` — ${task.requalification.comment}`}
        </p>
      )}
      <blockquote className="border-l-2 border-[var(--iag-queue)] pl-3 text-13 whitespace-pre-line">
        {submission.message}
        {submission.link && (
          <a
            href={submission.link}
            target="_blank"
            rel="noreferrer"
            className="iag-focus mt-1 block rounded text-12 text-[var(--iag-gold-text)] underline"
          >
            {t("steering.circuit.open_document")}
          </a>
        )}
      </blockquote>
      {task.risk && (
        <div className="rounded-lg border border-[var(--iag-border)] p-3 text-12">
          <p className="font-medium" style={{ color: task.risk.soon ? "var(--iag-critical)" : undefined }}>
            {task.risk.nature
              ? t("steering.dashboard.label_value", {
                  label: t("steering.task.risk_label"),
                  value: t(`steering.task.risk.${task.risk.nature}`),
                })
              : t("steering.task.risk_label")}
            {task.risk.effective_date &&
              ` · ${formatDate(task.risk.effective_date)} (${riskCountdown(task.risk.days)})`}
          </p>
          {task.risk.description && <p className="mt-1 text-[var(--iag-text-2)]">{task.risk.description}</p>}
        </div>
      )}
      <dl className="iag-num grid grid-cols-2 gap-2 text-12">
        <div>
          <dt className="text-[var(--iag-text-2)]">{t("steering.task.fields.target_date")}</dt>
          <dd>
            {formatDate(task.target_date)} {delayLabel(task) && `· ${delayLabel(task)}`}
          </dd>
        </div>
        <div>
          <dt className="text-[var(--iag-text-2)]">{t("steering.dashboard.waiting_since")}</dt>
          <dd>{t("steering.dashboard.days_count", { count: submission.waiting_days })}</dd>
        </div>
      </dl>
      {unblocked.length > 0 && (
        <p className="text-12">
          <span className="text-[var(--iag-text-2)]">{t("steering.dashboard.will_unblock")} </span>
          {unblocked.map((item) => `${item.key} ${item.name}`).join(" · ")}
        </p>
      )}
      <div className="flex flex-wrap gap-2">
        {data.viewer.can_decide && (
          <>
            <button
              type="button"
              className="iag-pill iag-pill-gold iag-focus"
              onClick={() => onAction({ kind: "validated", task })}
            >
              {t("steering.dashboard.actions.validated")}
            </button>
            <button type="button" className="iag-pill iag-focus" onClick={() => onAction({ kind: "returned", task })}>
              {t("steering.dashboard.actions.returned")}
            </button>
          </>
        )}
        {data.viewer.can_requalify && (
          <button type="button" className="iag-pill iag-focus" onClick={() => onAction({ kind: "requalify", task })}>
            {t("steering.dashboard.actions.requalify")}
          </button>
        )}
        <button type="button" className="iag-pill iag-focus" onClick={() => onOpenTask(task.id)}>
          {t("steering.dashboard.open_sheet")}
        </button>
      </div>
    </article>
  );
}

function OtherBlockages(props: { rows: TDashboardTask[]; index: TDashboardIndex; onOpenTask: (id: string) => void }) {
  const { rows, index, onOpenTask } = props;
  const { t } = useTranslation();
  const riskCountdown = useRiskCountdown();
  return (
    <div className="overflow-x-auto">
      <table className="iag-table w-full min-w-[640px] text-13">
        <thead>
          <tr>
            <th scope="col">{t("steering.dashboard.columns.task")}</th>
            <th scope="col">{t("steering.task.fields.waiting_for")}</th>
            <th scope="col">{t("steering.task.fields.assignee")}</th>
            <th scope="col" className="text-right">
              {t("steering.dashboard.columns.duration")}
            </th>
            <th scope="col">{t("steering.task.risk_label")}</th>
          </tr>
        </thead>
        <tbody>
          {rows.map((task) => (
            <tr key={task.id} className={`iag-edge iag-signal-${task.signal} align-top`}>
              <td>
                <TaskTitle task={task} onOpen={onOpenTask} />
                <p className="text-12 text-[var(--iag-text-2)]">{index.entityName(task.entity_id)}</p>
              </td>
              <td>{task.waiting_for ? t(`steering.task.waiting_for.${task.waiting_for}`) : ""}</td>
              <td>{index.assigneeNames(task)}</td>
              <td className="iag-num text-right">
                {task.waiting_days !== null ? t("steering.dashboard.days_count", { count: task.waiting_days }) : ""}
              </td>
              <td className="text-12">
                {task.risk?.nature && t(`steering.task.risk.${task.risk.nature}`)}
                {task.risk?.effective_date && ` · ${riskCountdown(task.risk.days)}`}
              </td>
            </tr>
          ))}
        </tbody>
      </table>
    </div>
  );
}
