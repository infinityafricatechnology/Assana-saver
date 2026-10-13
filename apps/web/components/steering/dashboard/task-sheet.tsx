/**
 * Copyright (c) 2023-present Plane Software, Inc. and contributors
 * SPDX-License-Identifier: AGPL-3.0-only
 * See the LICENSE file for details.
 */

import type { ReactNode } from "react";
import useSWR from "swr";
import {
  Dialog,
  DialogBody,
  DialogContent,
  DialogDescription,
  DialogHeader,
  DialogHeading,
  DialogMain,
  DialogTitle,
} from "@makeplane/propel/components/dialog";
import { useTranslation } from "@plane/i18n";
// types
import type { TDashboard, TDashboardTask, THistoryLine } from "@/services/steering-dashboard.service";
// local imports
import type { TDashboardAction } from "./action-dialogs";
import { SignalBadge, formatDate, useDelayLabel, useRiskCountdown } from "./shared";
import type { TDashboardIndex } from "./use-dashboard";
import { steeringDashboardService } from "./use-dashboard";

const CHOICE_PREFIXES: Record<string, string> = {
  status: "steering.task.status",
  waiting_for: "steering.task.waiting_for",
  risk_nature: "steering.task.risk",
};

type TTaskSheetProps = {
  workspaceSlug: string;
  data: TDashboard;
  index: TDashboardIndex;
  taskId: string | null;
  onClose: () => void;
  onOpenTask: (id: string) => void;
  onAction: (action: TDashboardAction) => void;
};

/** §6.6: the sheet of a work item, read only, with its alerts, its chain and its history. */
export function TaskSheet(props: TTaskSheetProps) {
  const { workspaceSlug, data, index, taskId, onClose, onOpenTask, onAction } = props;
  const { t } = useTranslation();
  const task = taskId ? index.tasks.get(taskId) : undefined;
  const sheet = useSWR(
    task ? ["STEERING_SHEET", workspaceSlug, task.id, task.updated_at] : null,
    () => steeringDashboardService.getSheet(workspaceSlug, task!.id),
    { revalidateOnFocus: false }
  );

  return (
    <Dialog
      open={!!task}
      onOpenChange={(open) => {
        if (!open) onClose();
      }}
    >
      <DialogContent size="lg">
        {task && (
          <DialogMain>
            <DialogHeader>
              <DialogHeading>
                <DialogTitle>
                  <span className="iag-num mr-2 text-[var(--iag-text-2)]">{task.key}</span>
                  {task.name}
                </DialogTitle>
                <DialogDescription>
                  {index.projects.get(task.project_id)?.name} · {index.entityName(task.entity_id)} ·{" "}
                  {index.branchName(task.branch_id)}
                </DialogDescription>
              </DialogHeading>
            </DialogHeader>
            <DialogBody tabIndex={0}>
              <div className="iag-steering -m-1 flex flex-col gap-4 rounded-2xl p-3">
                <div className="flex flex-wrap items-center gap-2">
                  <SignalBadge signal={task.signal} />
                  {task.blocked && <SignalBadge signal="blocked" />}
                  {task.in_queue && <SignalBadge signal="queue" />}
                  <span className="rounded-full border border-[var(--iag-border)] px-2 text-11 text-[var(--iag-text-2)]">
                    {t("steering.dashboard.read_only")}
                  </span>
                  <a
                    href={`/${workspaceSlug}/browse/${task.key}/`}
                    target="_blank"
                    rel="noreferrer"
                    className="iag-pill iag-focus ml-auto"
                  >
                    {t("steering.dashboard.open_in_entity_space")}
                  </a>
                </div>
                <AlertBox task={task} index={index} chain={sheet.data?.chain} onOpenTask={onOpenTask} />
                <SheetActions data={data} task={task} onAction={onAction} />
                <Fields task={task} index={index} />
                <History lines={sheet.data?.history} isLoading={sheet.isLoading} />
              </div>
            </DialogBody>
          </DialogMain>
        )}
      </DialogContent>
    </Dialog>
  );
}

/** The alert box at the top (§6.6): delay, blocking chain (§7 « Chaînes »), CEO queue. */
function AlertBox(props: {
  task: TDashboardTask;
  index: TDashboardIndex;
  chain:
    | {
        id: string;
        key: string;
        name: string;
        entity_id: string | null;
        days_late: number;
        assignees?: string[];
        status: string;
      }[][]
    | undefined;
  onOpenTask: (id: string) => void;
}) {
  const { task, index, chain, onOpenTask } = props;
  const { t } = useTranslation();
  const delayLabel = useDelayLabel();
  const alerts: ReactNode[] = [];
  if (task.days_late > 0)
    alerts.push(
      <p key="late" className="font-medium" style={{ color: "var(--iag-signal)" }}>
        {t("steering.dashboard.alert.late", { delay: delayLabel(task), date: formatDate(task.target_date) })}
      </p>
    );
  if (task.blocked)
    alerts.push(
      <div key="blocked">
        <p className="font-medium text-[var(--iag-critical)]">{t("steering.dashboard.alert.blocked")}</p>
        <ol className="mt-1 flex flex-col gap-1">
          {(chain ?? [task.blocked_by.map((id) => index.item(id)).filter((item) => !!item)]).map((level, depth) => (
            <li
              key={level.map((item) => item.id).join(",")}
              className="flex flex-col gap-0.5"
              style={{ paddingLeft: depth * 16 }}
            >
              {level.map((item) => (
                <span key={item.id} className="text-12">
                  {depth > 0 && <span aria-hidden="true">↳ </span>}
                  <button
                    type="button"
                    className="iag-focus rounded font-medium hover:underline disabled:no-underline"
                    disabled={!index.tasks.has(item.id)}
                    onClick={() => onOpenTask(item.id)}
                  >
                    {item.key} {item.name}
                  </button>
                  <span className="text-[var(--iag-text-2)]">
                    {" "}
                    · {index.entityName(item.entity_id) || t("steering.dashboard.outside_steering")}
                    {"assignees" in item && item.assignees?.length ? ` · ${item.assignees.join(", ")}` : ""}
                    {" · "}
                    {item.days_late > 0
                      ? delayLabel({ days_late: item.days_late, days_left: null, is_open: true })
                      : t(`steering.task.status.${item.status}`)}
                  </span>
                </span>
              ))}
            </li>
          ))}
        </ol>
      </div>
    );
  if (task.in_queue && task.submission)
    alerts.push(
      <p key="queue" className="font-medium text-[var(--iag-queue)]">
        {t("steering.dashboard.alert.queue", {
          date: formatDate(task.submission.submitted_at),
          count: task.submission.waiting_days,
        })}
      </p>
    );
  if (!alerts.length) return null;
  return (
    <div
      className={`iag-card iag-edge iag-signal-${task.blocked ? "blocked" : task.signal} flex flex-col gap-2 p-3 text-13`}
    >
      {alerts}
    </div>
  );
}

function SheetActions(props: { data: TDashboard; task: TDashboardTask; onAction: (action: TDashboardAction) => void }) {
  const { data, task, onAction } = props;
  const { t } = useTranslation();
  const buttons = [
    task.in_queue && data.viewer.can_decide && (
      <button
        key="validate"
        type="button"
        className="iag-pill iag-pill-gold iag-focus"
        onClick={() => onAction({ kind: "validated", task })}
      >
        {t("steering.dashboard.actions.validated")}
      </button>
    ),
    task.in_queue && data.viewer.can_decide && (
      <button
        key="return"
        type="button"
        className="iag-pill iag-focus"
        onClick={() => onAction({ kind: "returned", task })}
      >
        {t("steering.dashboard.actions.returned")}
      </button>
    ),
    task.in_queue && data.viewer.can_requalify && (
      <button
        key="requalify"
        type="button"
        className="iag-pill iag-focus"
        onClick={() => onAction({ kind: "requalify", task })}
      >
        {t("steering.dashboard.actions.requalify")}
      </button>
    ),
    task.is_open && data.viewer.can_remind && (
      <button
        key="remind"
        type="button"
        className="iag-pill iag-focus"
        onClick={() => onAction({ kind: "remind", task })}
      >
        {t("steering.dashboard.actions.remind")}
      </button>
    ),
  ].filter(Boolean);
  return buttons.length ? <div className="flex flex-wrap gap-2">{buttons}</div> : null;
}

const field = (label: string, value: ReactNode) => (
  <div className="min-w-0">
    <dt className="text-12 text-[var(--iag-text-2)]">{label}</dt>
    <dd className="text-13 break-words">{value || "—"}</dd>
  </div>
);

/** Every field of §4, the risk and the last situation point included. */
function Fields(props: { task: TDashboardTask; index: TDashboardIndex }) {
  const { task, index } = props;
  const { t } = useTranslation();
  const riskCountdown = useRiskCountdown();
  return (
    <dl className="iag-card grid grid-cols-1 gap-3 p-4 sm:grid-cols-2 lg:grid-cols-3">
      {field(t("steering.task.fields.category"), index.categories.get(task.category_id ?? "")?.name)}
      {field(t("steering.task.fields.assignee"), index.assigneeNames(task))}
      {field(t("steering.task.fields.supervisor"), index.personName(task.supervisor_id))}
      {field(t("steering.task.fields.approver"), index.personName(task.approver_id))}
      {field(
        t("steering.task.fields.priority"),
        task.retained_priority !== task.priority
          ? t("steering.dashboard.retained_priority", {
              declared: t(task.priority),
              retained: t(task.retained_priority),
            })
          : t(task.priority)
      )}
      {field(t("steering.task.fields.target_date"), formatDate(task.target_date))}
      {field(t("steering.task.fields.status"), t(`steering.task.status.${task.status}`))}
      {field(t("steering.task.fields.progress"), t("steering.dashboard.percent", { value: task.progress }))}
      {task.status === "waiting" &&
        field(
          t("steering.task.fields.waiting_for"),
          task.waiting_for &&
            `${t(`steering.task.waiting_for.${task.waiting_for}`)} · ${t("steering.dashboard.days_count", { count: task.waiting_days ?? 0 })}`
        )}
      {task.risk &&
        field(
          t("steering.task.risk_label"),
          <>
            {task.risk.nature && t(`steering.task.risk.${task.risk.nature}`)}
            {task.risk.effective_date &&
              ` · ${formatDate(task.risk.effective_date)} (${riskCountdown(task.risk.days)})`}
            {task.risk.description && (
              <span className="block text-12 text-[var(--iag-text-2)]">{task.risk.description}</span>
            )}
          </>
        )}
      {task.closure_date && field(t("steering.task.fields.closure_date"), formatDate(task.closure_date))}
      <div className="sm:col-span-2 lg:col-span-3">
        <dt className="text-12 text-[var(--iag-text-2)]">
          {t("steering.task.fields.situation")}
          {task.situation_updated_at && ` · ${formatDate(task.situation_updated_at)}`}
        </dt>
        <dd className="text-13 whitespace-pre-line">{task.situation || "—"}</dd>
      </div>
    </dl>
  );
}

/** §9.4: the record of the work item, oldest first. */
function History(props: { lines: THistoryLine[] | undefined; isLoading: boolean }) {
  const { t } = useTranslation();
  const describe = useHistoryLine();
  return (
    <section className="iag-card p-4">
      <h3 className="mb-2 text-14 font-semibold">{t("steering.dashboard.history")}</h3>
      {props.isLoading && <p className="text-13 text-[var(--iag-text-2)]">{t("common.loading")}</p>}
      {props.lines?.length === 0 && (
        <p className="text-13 text-[var(--iag-text-2)]">{t("steering.dashboard.empty.history")}</p>
      )}
      <ol className="flex flex-col gap-2">
        {props.lines?.map((line) => (
          <li key={line.id} className="text-13">
            <span className="iag-num text-12 text-[var(--iag-text-2)]">
              {formatDate(line.created_at)}{" "}
              {new Date(line.created_at).toLocaleTimeString(undefined, {
                hour: "2-digit",
                minute: "2-digit",
                hourCycle: "h23",
              })}
            </span>{" "}
            <span className="font-medium">{line.actor ?? t("steering.dashboard.platform")}</span> {describe(line)}
          </li>
        ))}
      </ol>
    </section>
  );
}

const readEvent = (comment: string | null): { event?: string; text?: string } => {
  try {
    return JSON.parse(comment ?? "{}") as { event?: string; text?: string };
  } catch {
    return {};
  }
};

function useHistoryLine() {
  const { t } = useTranslation();
  const change = (label: string, oldValue: string, newValue: string) =>
    newValue
      ? t("steering.dashboard.history_line.set", { field: label, old: oldValue || "—", new: newValue })
      : t("steering.dashboard.history_line.cleared", { field: label, old: oldValue });
  return (line: THistoryLine): string => {
    const oldValue = line.old_value ?? "";
    const newValue = line.new_value ?? "";
    switch (line.field) {
      case "steering_event": {
        const { event = "", text } = readEvent(line.comment);
        const isDate = event === "deadline_postponed";
        const show = (value: string) => (!value ? "" : isDate ? formatDate(value) : t(value));
        const sentence = t(`steering.history.${event}`, { old: show(oldValue), new: show(newValue) });
        return text ? `${sentence} — ${t("steering.dashboard.quoted", { text })}` : sentence;
      }
      case "steering": {
        const key = line.comment ?? "";
        const label = t(`steering.task.fields.${key.replace(/_id$/, "")}`);
        const display = (value: string) => {
          if (!value) return "";
          if (CHOICE_PREFIXES[key]) return t(`${CHOICE_PREFIXES[key]}.${value}`);
          if (key.endsWith("_date")) return formatDate(value);
          if (key === "progress") return t("steering.dashboard.percent", { value });
          return value;
        };
        return change(label, display(oldValue), display(newValue));
      }
      case "target_date":
        return change(t("steering.task.fields.target_date"), formatDate(oldValue), formatDate(newValue));
      case "priority":
        return change(t("steering.task.fields.priority"), oldValue && t(oldValue), newValue && t(newValue));
      case "assignees":
        return newValue
          ? t("steering.dashboard.history_line.assigned", { name: newValue })
          : t("steering.dashboard.history_line.unassigned", { name: oldValue });
      case "blocked_by":
      case "blocking":
        return t(`steering.dashboard.history_line.${line.field}_${newValue ? "added" : "removed"}`, {
          key: newValue || oldValue,
        });
      case "state":
        return change(t("steering.dashboard.history_line.section"), oldValue, newValue);
      default:
        return change(line.field, oldValue, newValue);
    }
  };
}
