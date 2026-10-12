/**
 * Copyright (c) 2023-present Plane Software, Inc. and contributors
 * SPDX-License-Identifier: AGPL-3.0-only
 * See the LICENSE file for details.
 */

import { useEffect, useState } from "react";
import type { FormEvent, ReactNode } from "react";
import { Button } from "@makeplane/propel/components/button";
import {
  Dialog,
  DialogActions,
  DialogBody,
  DialogContent,
  DialogDescription,
  DialogHeader,
  DialogHeading,
  DialogMain,
  DialogTitle,
} from "@makeplane/propel/components/dialog";
import { setToast } from "@plane/blocks/toast";
import { useTranslation } from "@plane/i18n";
// services
import type { TDashboardTask, TSteeringPriority } from "@/services/steering-dashboard.service";
import { SteeringService } from "@/services/steering.service";

const steeringService = new SteeringService();

export type TDashboardAction =
  | { kind: "validated" | "returned"; task: TDashboardTask }
  | { kind: "requalify"; task: TDashboardTask }
  | { kind: "remind"; task: TDashboardTask };

const PRIORITIES: TSteeringPriority[] = ["urgent", "high", "medium"];

const textAreaClassName =
  "w-full rounded-md border border-subtle bg-surface-1 px-3 py-2 text-13 text-primary outline-none placeholder:text-placeholder focus:border-accent-strong";

function ActionDialog(props: {
  open: boolean;
  title: string;
  description: string;
  confirm: string;
  canConfirm: boolean;
  isSaving: boolean;
  onClose: () => void;
  onConfirm: () => void;
  extraAction?: ReactNode;
  children: ReactNode;
}) {
  const { t } = useTranslation();
  const handleSubmit = (event: FormEvent) => {
    event.preventDefault();
    if (props.canConfirm && !props.isSaving) props.onConfirm();
  };
  return (
    <Dialog
      open={props.open}
      onOpenChange={(open) => {
        if (!open) props.onClose();
      }}
    >
      <DialogContent size="sm">
        <form onSubmit={handleSubmit} className="flex min-h-0 flex-1 flex-col">
          <DialogMain>
            <DialogHeader>
              <DialogHeading>
                <DialogTitle>{props.title}</DialogTitle>
                <DialogDescription>{props.description}</DialogDescription>
              </DialogHeading>
            </DialogHeader>
            <DialogBody tabIndex={0}>
              <div className="flex flex-col gap-3">{props.children}</div>
            </DialogBody>
          </DialogMain>
          <DialogActions>
            {props.extraAction}
            <Button variant="secondary" size="md" stretch="auto" label={t("common.cancel")} onClick={props.onClose} />
            <Button
              type="submit"
              variant="primary"
              size="md"
              stretch="auto"
              label={props.confirm}
              loading={props.isSaving}
              disabled={!props.canConfirm}
            />
          </DialogActions>
        </form>
      </DialogContent>
    </Dialog>
  );
}

/**
 * The four actions of the steering space that leave the entered data alone (§2): the CEO's decision,
 * the requalification of a priority, the reminder of an assignee. The server checks the rights.
 */
export function DashboardActionDialog(props: {
  workspaceSlug: string;
  action: TDashboardAction | null;
  onClose: () => void;
  onDone: () => void;
}) {
  const { workspaceSlug, action, onClose, onDone } = props;
  const { t } = useTranslation();
  const [comment, setComment] = useState("");
  const [priority, setPriority] = useState<TSteeringPriority>("urgent");
  const [isSaving, setIsSaving] = useState(false);

  useEffect(() => {
    if (!action) return;
    setComment("");
    setPriority(action.task.retained_priority);
  }, [action]);

  if (!action) return null;
  const { task } = action;

  const run = async (request: () => Promise<unknown>, success: string) => {
    setIsSaving(true);
    try {
      await request();
      setToast({ type: "success", title: t("common.success"), message: success });
      onDone();
      onClose();
    } catch (error) {
      const code = typeof error === "object" && error !== null && "code" in error ? String(error.code) : "";
      const key = `steering.circuit.errors.${code}`;
      const translated = code ? t(key) : "";
      setToast({
        type: "error",
        title: t("common.error.label"),
        message: translated && translated !== key ? translated : t("common.error.message"),
      });
    } finally {
      setIsSaving(false);
    }
  };

  const commentField = (label: string, required: boolean) => (
    <label className="flex flex-col gap-1 text-12 text-secondary">
      {label}
      <textarea
        rows={3}
        value={comment}
        required={required}
        onChange={(event) => setComment(event.target.value)}
        className={textAreaClassName}
      />
    </label>
  );

  if (action.kind === "validated" || action.kind === "returned") {
    const returned = action.kind === "returned";
    return (
      <ActionDialog
        open
        title={t(`steering.dashboard.actions.${action.kind}_title`)}
        description={`${task.key} · ${task.name}`}
        confirm={t(`steering.dashboard.actions.${action.kind}`)}
        canConfirm={!returned || !!comment.trim()}
        isSaving={isSaving}
        onClose={onClose}
        onConfirm={() =>
          void run(
            () => steeringService.decide(workspaceSlug, task.submission!.id, action.kind, comment.trim()),
            t(`steering.dashboard.actions.${action.kind}_done`)
          )
        }
      >
        {commentField(
          returned ? t("steering.dashboard.actions.return_comment") : t("steering.dashboard.actions.optional_comment"),
          returned
        )}
      </ActionDialog>
    );
  }

  if (action.kind === "requalify") {
    return (
      <ActionDialog
        open
        title={t("steering.dashboard.actions.requalify_title")}
        description={t("steering.dashboard.actions.requalify_description", {
          name: task.name,
          declared: t(task.priority),
        })}
        confirm={t("steering.dashboard.actions.requalify")}
        canConfirm={!!comment.trim() && priority !== task.retained_priority}
        isSaving={isSaving}
        onClose={onClose}
        onConfirm={() =>
          void run(
            () => steeringService.requalify(workspaceSlug, task.id, priority, comment.trim()),
            t("steering.dashboard.actions.requalify_done")
          )
        }
        extraAction={
          task.requalification && (
            <Button
              variant="secondary"
              size="md"
              stretch="auto"
              label={t("steering.dashboard.actions.cancel_requalification")}
              onClick={() =>
                void run(
                  () => steeringService.cancelRequalification(workspaceSlug, task.id),
                  t("steering.dashboard.actions.requalify_done")
                )
              }
            />
          )
        }
      >
        <fieldset className="flex flex-wrap gap-2">
          <legend className="mb-1 text-12 text-secondary">{t("steering.dashboard.actions.retained_priority")}</legend>
          {PRIORITIES.map((value) => (
            <label key={value} className="flex items-center gap-1.5 text-13">
              <input
                type="radio"
                name="retained-priority"
                value={value}
                checked={priority === value}
                onChange={() => setPriority(value)}
              />
              {t(value)}
            </label>
          ))}
        </fieldset>
        {commentField(t("steering.dashboard.actions.justification"), true)}
      </ActionDialog>
    );
  }

  return (
    <ActionDialog
      open
      title={t("steering.dashboard.actions.remind_title")}
      description={t("steering.dashboard.actions.remind_description", { name: task.name })}
      confirm={t("steering.dashboard.actions.remind")}
      canConfirm
      isSaving={isSaving}
      onClose={onClose}
      onConfirm={() =>
        void run(
          () => steeringService.remind(workspaceSlug, task.id, comment.trim()),
          t("steering.dashboard.actions.remind_done")
        )
      }
    >
      {commentField(t("steering.dashboard.actions.optional_message"), false)}
    </ActionDialog>
  );
}
