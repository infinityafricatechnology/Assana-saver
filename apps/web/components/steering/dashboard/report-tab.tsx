/**
 * Copyright (c) 2023-present Plane Software, Inc. and contributors
 * SPDX-License-Identifier: AGPL-3.0-only
 * See the LICENSE file for details.
 */

import { useEffect, useMemo, useState } from "react";
import type { ReactNode } from "react";
import useSWR from "swr";
import { Button } from "@makeplane/propel/components/button";
import {
  Dialog,
  DialogActions,
  DialogContent,
  DialogDescription,
  DialogHeader,
  DialogHeading,
  DialogMain,
  DialogTitle,
} from "@makeplane/propel/components/dialog";
import { setToast } from "@plane/blocks/toast";
import { useTranslation } from "@plane/i18n";
import { renderFormattedDate } from "@plane/utils";
// components
import { MemberSelect } from "@/components/dropdowns/member/member-select";
// types
import type { TReport, TReportPatch, TReportSectionKey } from "@/services/steering-dashboard.service";
// local imports
import { saveBlob } from "./exports";
import { Card, EmptyLine } from "./shared";
import { steeringDashboardService } from "./use-dashboard";

const textAreaClassName =
  "iag-focus w-full rounded-xl border border-[var(--iag-border)] bg-[var(--iag-card)] px-3 py-2 text-13 text-[var(--iag-text)] placeholder:text-[var(--iag-text-2)]";

const timeOf = (iso: string) =>
  new Date(iso).toLocaleTimeString(undefined, { hour: "2-digit", minute: "2-digit", hourCycle: "h23" });

/** A text saved when it loses focus, like the other fields of the platform. */
function BlurText(props: {
  value: string;
  label: string;
  placeholder?: string;
  rows?: number;
  disabled?: boolean;
  onSave: (value: string) => void;
}) {
  const [draft, setDraft] = useState(props.value);
  useEffect(() => setDraft(props.value), [props.value]);
  return (
    <textarea
      rows={props.rows ?? 2}
      value={draft}
      aria-label={props.label}
      placeholder={props.placeholder}
      disabled={props.disabled}
      onChange={(event) => setDraft(event.target.value)}
      onBlur={() => draft.trim() !== props.value.trim() && props.onSave(draft.trim())}
      className={textAreaClassName}
    />
  );
}

type TReportTabProps = { workspaceSlug: string; initialReportId?: string | null };

/** §9.3: the weekly report, commented and arranged by the Cabinet or the CEO, then sent and archived. */
export function ReportTab(props: TReportTabProps) {
  const { workspaceSlug, initialReportId } = props;
  const { t } = useTranslation();
  const list = useSWR(["STEERING_REPORTS", workspaceSlug], () => steeringDashboardService.listReports(workspaceSlug), {
    revalidateOnFocus: false,
  });
  const [selectedId, setSelectedId] = useState<string | null>(initialReportId ?? null);
  const reportId = selectedId ?? list.data?.[0]?.id ?? null;
  const report = useSWR(
    reportId ? ["STEERING_REPORT", workspaceSlug, reportId] : null,
    () => steeringDashboardService.getReport(workspaceSlug, reportId!),
    { revalidateOnFocus: false }
  );
  const [isPreparing, setIsPreparing] = useState(false);

  const fail = (error: unknown) => {
    const code = typeof error === "object" && error !== null && "code" in error ? String(error.code) : "";
    const key = `steering.report.errors.${code}`;
    const translated = code ? t(key) : "";
    setToast({
      type: "error",
      title: t("common.error.label"),
      message: translated && translated !== key ? translated : t("steering.report.errors.generic"),
    });
  };

  const prepare = async () => {
    setIsPreparing(true);
    try {
      const prepared = await steeringDashboardService.prepareReport(workspaceSlug);
      await list.mutate();
      setSelectedId(prepared.id);
    } catch (error) {
      fail(error);
    } finally {
      setIsPreparing(false);
    }
  };

  const today = new Date();
  const hasCurrentWeek = (list.data ?? []).some((item) => item.week === isoWeek(today) && item.year === isoYear(today));

  return (
    <div className="grid gap-4 lg:grid-cols-[280px_minmax(0,1fr)]">
      <Card title={t("steering.report.list_title")}>
        <div className="flex flex-col gap-2">
          {!hasCurrentWeek && (
            <button
              type="button"
              className="iag-pill iag-pill-gold iag-focus justify-center"
              disabled={isPreparing}
              onClick={() => void prepare()}
            >
              {t("steering.report.prepare")}
            </button>
          )}
          {list.data?.length === 0 && <EmptyLine>{t("steering.report.empty")}</EmptyLine>}
          <ul className="flex flex-col gap-1">
            {list.data?.map((item) => (
              <li key={item.id}>
                <button
                  type="button"
                  aria-pressed={item.id === reportId}
                  onClick={() => setSelectedId(item.id)}
                  className="iag-focus flex w-full items-center justify-between gap-2 rounded-xl px-3 py-2 text-left text-13 hover:bg-[var(--iag-bg)] aria-pressed:bg-[var(--iag-bg)]"
                >
                  <span className="font-medium">{t("steering.report.week", { week: item.week, year: item.year })}</span>
                  <span className={`iag-signal ${item.status === "sent" ? "iag-signal-ok" : "iag-signal-queue"}`}>
                    {t(`steering.report.status.${item.status}`)}
                  </span>
                </button>
              </li>
            ))}
          </ul>
        </div>
      </Card>
      {report.data ? (
        <ReportEditor
          key={report.data.id}
          workspaceSlug={workspaceSlug}
          report={report.data}
          onChange={(next) => {
            void report.mutate(next, { revalidate: false });
            void list.mutate();
          }}
          onError={fail}
        />
      ) : (
        <Card>
          <EmptyLine>{reportId ? t("common.loading") : t("steering.report.empty")}</EmptyLine>
        </Card>
      )}
    </div>
  );
}

const toggle = (list: string[], id: string) => (list.includes(id) ? list.filter((item) => item !== id) : [...list, id]);

function isoWeek(day: Date) {
  const date = new Date(Date.UTC(day.getFullYear(), day.getMonth(), day.getDate()));
  date.setUTCDate(date.getUTCDate() + 4 - (date.getUTCDay() || 7));
  const yearStart = new Date(Date.UTC(date.getUTCFullYear(), 0, 1));
  return Math.ceil(((date.getTime() - yearStart.getTime()) / 86400000 + 1) / 7);
}

function isoYear(day: Date) {
  const date = new Date(Date.UTC(day.getFullYear(), day.getMonth(), day.getDate()));
  date.setUTCDate(date.getUTCDate() + 4 - (date.getUTCDay() || 7));
  return date.getUTCFullYear();
}

function ReportEditor(props: {
  workspaceSlug: string;
  report: TReport;
  onChange: (report: TReport) => void;
  onError: (error: unknown) => void;
}) {
  const { workspaceSlug, report, onChange, onError } = props;
  const { t } = useTranslation();
  const [busy, setBusy] = useState<"refresh" | "preview" | "send" | null>(null);
  const [confirmSend, setConfirmSend] = useState(false);
  const [savedAt, setSavedAt] = useState<Date | null>(null);
  const isDraft = report.status === "draft";

  const save = async (patch: TReportPatch) => {
    try {
      onChange(await steeringDashboardService.updateReport(workspaceSlug, report.id, patch));
      setSavedAt(new Date());
    } catch (error) {
      onError(error);
    }
  };

  const run = async (kind: "refresh" | "preview" | "send", action: () => Promise<void>) => {
    setBusy(kind);
    try {
      await action();
    } catch (error) {
      onError(error);
    } finally {
      setBusy(null);
    }
  };

  const tasks = useMemo(() => {
    const seen = new Map<string, { id: string; key: string; name: string; entity: string }>();
    for (const item of [...report.data.delays, ...report.data.queue, ...report.data.blocking])
      if (!seen.has(item.id)) seen.set(item.id, item);
    return [...seen.values()];
  }, [report.data]);
  const entities = report.data.entities.filter(
    (entity, position) =>
      position < 10 || report.highlighted_entities.includes(entity.id) || !!report.entity_comments[entity.id]
  );
  const recipientCount = report.recipient_ids.length + report.extra_emails.length;

  const moveSection = (position: number, offset: number) => {
    const sections = [...report.sections];
    const target = position + offset;
    if (target < 0 || target >= sections.length) return;
    [sections[position], sections[target]] = [sections[target], sections[position]];
    void save({ sections });
  };

  return (
    <div className="flex min-w-0 flex-col gap-4">
      <section className="iag-card flex flex-col gap-3 p-4">
        <div className="flex flex-wrap items-start justify-between gap-3">
          <div className="min-w-0">
            <h2 className="text-16 font-semibold">
              {t("steering.report.title", { week: report.week, year: report.year })}
            </h2>
            <p className="text-12 text-[var(--iag-text-2)]">{report.situation}</p>
            <p className="text-12 text-[var(--iag-text-2)]" role="status">
              {isDraft
                ? t("steering.report.refreshed_on", {
                    date: renderFormattedDate(report.refreshed_at) ?? "",
                    time: timeOf(report.refreshed_at),
                  })
                : t("steering.report.sent_on", {
                    date: renderFormattedDate(report.sent_at ?? "") ?? "",
                    name: report.sent_by ?? "",
                  })}
              {savedAt && isDraft && ` · ${t("steering.report.saved")}`}
            </p>
          </div>
          <div className="flex flex-wrap gap-2">
            {isDraft && (
              <button
                type="button"
                className="iag-pill iag-focus"
                disabled={!!busy}
                onClick={() =>
                  void run("refresh", async () => {
                    onChange(await steeringDashboardService.refreshReport(workspaceSlug, report.id));
                    setToast({ type: "success", title: t("common.success"), message: t("steering.report.refreshed") });
                  })
                }
              >
                {t("steering.report.refresh")}
              </button>
            )}
            <button
              type="button"
              className="iag-pill iag-focus"
              disabled={!!busy}
              onClick={() =>
                void run("preview", async () =>
                  saveBlob(
                    await steeringDashboardService.downloadReport(workspaceSlug, report.id),
                    `rapport-hebdomadaire-${report.year}-s${String(report.week).padStart(2, "0")}.pdf`
                  )
                )
              }
            >
              {isDraft ? t("steering.report.preview") : t("steering.report.download_sent")}
            </button>
            {isDraft && (
              <button
                type="button"
                className="iag-pill iag-pill-gold iag-focus"
                disabled={!!busy}
                onClick={() => setConfirmSend(true)}
              >
                {t("steering.report.send")}
              </button>
            )}
          </div>
        </div>
        {!isDraft && <p className="text-13 text-[var(--iag-text-2)]">{t("steering.report.archived")}</p>}
      </section>

      <Card title={t("steering.report.intro")}>
        <BlurText
          value={report.intro}
          label={t("steering.report.intro")}
          placeholder={t("steering.report.intro_placeholder")}
          rows={3}
          disabled={!isDraft}
          onSave={(intro) => void save({ intro })}
        />
      </Card>

      <Card title={t("steering.report.sections_title")}>
        <ol className="flex flex-col gap-3">
          {report.sections.map((section, position) => (
            <li key={section.key} className="flex flex-col gap-2 rounded-xl border border-[var(--iag-border)] p-3">
              <div className="flex flex-wrap items-center gap-2">
                <label className="flex min-w-0 flex-1 items-center gap-2 text-13 font-medium">
                  <input
                    type="checkbox"
                    checked={section.visible}
                    disabled={!isDraft}
                    onChange={() =>
                      void save({
                        sections: report.sections.map((item) =>
                          item.key === section.key ? { ...item, visible: !item.visible } : item
                        ),
                      })
                    }
                    aria-label={t("steering.report.show_section")}
                  />
                  {t(`steering.report.section.${section.key}`)}
                </label>
                <button
                  type="button"
                  className="iag-pill iag-focus px-2"
                  disabled={!isDraft || position === 0}
                  onClick={() => moveSection(position, -1)}
                  aria-label={`${t("steering.report.move_up")} · ${t(`steering.report.section.${section.key}`)}`}
                >
                  ↑
                </button>
                <button
                  type="button"
                  className="iag-pill iag-focus px-2"
                  disabled={!isDraft || position === report.sections.length - 1}
                  onClick={() => moveSection(position, 1)}
                  aria-label={`${t("steering.report.move_down")} · ${t(`steering.report.section.${section.key}`)}`}
                >
                  ↓
                </button>
              </div>
              <BlurText
                value={report.section_comments[section.key] ?? ""}
                label={`${t("steering.report.section_comment")} · ${t(`steering.report.section.${section.key}`)}`}
                placeholder={t("steering.report.section_comment")}
                disabled={!isDraft}
                onSave={(text) =>
                  void save({
                    section_comments: { ...report.section_comments, [section.key as TReportSectionKey]: text },
                  })
                }
              />
            </li>
          ))}
        </ol>
      </Card>

      <Card title={t("steering.report.entities_title")}>
        <CommentList
          items={entities.map((entity) => ({ id: entity.id, label: entity.name, detail: entity.branch }))}
          comments={report.entity_comments}
          highlighted={report.highlighted_entities}
          disabled={!isDraft}
          onComment={(id, text) => void save({ entity_comments: { ...report.entity_comments, [id]: text } })}
          onHighlight={(id) => void save({ highlighted_entities: toggle(report.highlighted_entities, id) })}
        />
      </Card>

      <Card title={t("steering.report.tasks_title")}>
        {tasks.length === 0 ? (
          <EmptyLine>{t("steering.report.no_tasks")}</EmptyLine>
        ) : (
          <CommentList
            items={tasks.map((task) => ({ id: task.id, label: `${task.key} · ${task.name}`, detail: task.entity }))}
            comments={report.task_comments}
            highlighted={report.highlighted_tasks}
            disabled={!isDraft}
            onComment={(id, text) => void save({ task_comments: { ...report.task_comments, [id]: text } })}
            onHighlight={(id) => void save({ highlighted_tasks: toggle(report.highlighted_tasks, id) })}
          />
        )}
      </Card>

      <Card title={t("steering.report.recipients_title")} count={recipientCount}>
        <div className="flex flex-col gap-3">
          <div className="flex flex-col gap-1 text-12 text-[var(--iag-text-2)]">
            {t("steering.report.recipients_members")}
            <MemberSelect
              multiple
              value={report.recipient_ids}
              onChange={(ids) => void save({ recipient_ids: ids })}
              disabled={!isDraft}
              placeholder={t("steering.report.recipients_members")}
              variant={report.recipient_ids.length ? "avatar-group-md" : "pill-md"}
            />
          </div>
          <label className="flex flex-col gap-1 text-12 text-[var(--iag-text-2)]">
            {t("steering.report.extra_emails")}
            <BlurText
              value={report.extra_emails.join(", ")}
              label={t("steering.report.extra_emails")}
              placeholder="comex@infinity-africa.com"
              disabled={!isDraft}
              onSave={(text) =>
                void save({
                  extra_emails: text
                    .split(/[\s,;]+/)
                    .map((email) => email.trim())
                    .filter(Boolean),
                })
              }
            />
            <span className="text-11">{t("steering.report.extra_emails_hint")}</span>
          </label>
        </div>
      </Card>

      <Dialog
        open={confirmSend}
        onOpenChange={(open) => {
          if (!open) setConfirmSend(false);
        }}
      >
        <DialogContent size="sm">
          <DialogMain>
            <DialogHeader>
              <DialogHeading>
                <DialogTitle>{t("steering.report.send_title")}</DialogTitle>
                <DialogDescription>
                  {t("steering.report.send_description", { count: recipientCount })}
                </DialogDescription>
              </DialogHeading>
            </DialogHeader>
          </DialogMain>
          <DialogActions>
            <Button
              variant="secondary"
              size="md"
              stretch="auto"
              label={t("common.cancel")}
              onClick={() => setConfirmSend(false)}
            />
            <Button
              variant="primary"
              size="md"
              stretch="auto"
              label={t("steering.report.send")}
              loading={busy === "send"}
              onClick={() =>
                void run("send", async () => {
                  onChange(await steeringDashboardService.sendReport(workspaceSlug, report.id));
                  setConfirmSend(false);
                  setToast({ type: "success", title: t("common.success"), message: t("steering.report.sent_toast") });
                })
              }
            />
          </DialogActions>
        </DialogContent>
      </Dialog>
    </div>
  );
}

function CommentList(props: {
  items: { id: string; label: string; detail: string }[];
  comments: Record<string, string>;
  highlighted: string[];
  disabled: boolean;
  onComment: (id: string, text: string) => void;
  onHighlight: (id: string) => void;
}) {
  const { t } = useTranslation();
  const rows: ReactNode[] = props.items.map((item) => {
    const isHighlighted = props.highlighted.includes(item.id);
    return (
      <li
        key={item.id}
        className={`flex flex-col gap-2 rounded-xl border p-3 ${isHighlighted ? "border-[var(--iag-gold)] bg-[color-mix(in_srgb,var(--iag-gold)_10%,transparent)]" : "border-[var(--iag-border)]"}`}
      >
        <div className="flex flex-wrap items-center justify-between gap-2">
          <div className="min-w-0">
            <p className="truncate text-13 font-medium">{item.label}</p>
            <p className="text-12 text-[var(--iag-text-2)]">{item.detail}</p>
          </div>
          <button
            type="button"
            aria-pressed={isHighlighted}
            disabled={props.disabled}
            onClick={() => props.onHighlight(item.id)}
            className="iag-pill iag-focus"
          >
            {t("steering.report.highlight")}
          </button>
        </div>
        <BlurText
          value={props.comments[item.id] ?? ""}
          label={`${t("steering.report.comment")} · ${item.label}`}
          placeholder={t("steering.report.comment")}
          disabled={props.disabled}
          onSave={(text) => props.onComment(item.id, text)}
        />
      </li>
    );
  });
  return <ul className="flex flex-col gap-2">{rows}</ul>;
}
