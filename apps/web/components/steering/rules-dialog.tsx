/**
 * Copyright (c) 2023-present Plane Software, Inc. and contributors
 * SPDX-License-Identifier: AGPL-3.0-only
 * See the LICENSE file for details.
 */

import { useEffect, useRef, useState } from "react";
import type { FormEvent } from "react";
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
import { renderFormattedDate } from "@plane/utils";
// helpers
import type { TSteeringRuleError } from "@/helpers/steering-rules.helper";
import { registerSteeringRuleHandlers, steeringRuleCode } from "@/helpers/steering-rules.helper";

/** The sentence that explains why the API refused a work item of a steered project, if it did. */
export const useSteeringRuleMessage = () => {
  const { t } = useTranslation();
  return (error: unknown): string | undefined => {
    const code = steeringRuleCode(error);
    if (code === "steering_required") {
      const missing = (error as TSteeringRuleError).missing ?? [];
      return t("steering.rules.required", {
        fields: missing.map((field) => t(`steering.task.fields.${field}`)).join(", "),
      });
    }
    if (code === "deadline_comment_required") return t("steering.rules.deadline_comment");
    return undefined;
  };
};

type TRequest = { date: string | null; resolve: (comment: string | null) => void };

/**
 * Mounted once per workspace: asks for the reason of a postponed deadline wherever the deadline
 * moves (list, board, timeline, work item), and explains the other refusals of a steered project.
 */
export function SteeringRulesDialog() {
  const { t } = useTranslation();
  const ruleMessage = useSteeringRuleMessage();
  const [request, setRequest] = useState<TRequest | null>(null);
  const [comment, setComment] = useState("");
  const requestRef = useRef<TRequest | null>(null);

  const settle = (value: string | null) => {
    requestRef.current?.resolve(value);
    requestRef.current = null;
    setRequest(null);
  };

  // Registered once: the toast reads the latest translations through this ref.
  const explainRef = useRef<(error: TSteeringRuleError) => void>(() => undefined);
  explainRef.current = (error) =>
    setToast({
      type: "error",
      title: t("common.error.label"),
      message: ruleMessage(error) ?? t("common.error.message"),
    });

  useEffect(() => {
    registerSteeringRuleHandlers({
      askDeadlineComment: (date) =>
        new Promise((resolve) => {
          requestRef.current?.resolve(null);
          const next = { date, resolve };
          requestRef.current = next;
          setComment("");
          setRequest(next);
        }),
      explain: (error) => explainRef.current(error),
    });
    return () => {
      registerSteeringRuleHandlers(null);
      requestRef.current?.resolve(null);
      requestRef.current = null;
    };
  }, []);

  const handleSubmit = (event: FormEvent) => {
    event.preventDefault();
    if (comment.trim()) settle(comment.trim());
  };

  return (
    <Dialog
      open={!!request}
      onOpenChange={(open) => {
        if (!open) settle(null);
      }}
    >
      <DialogContent size="sm">
        <form onSubmit={handleSubmit} className="flex min-h-0 flex-1 flex-col">
          <DialogMain>
            <DialogHeader>
              <DialogHeading>
                <DialogTitle>{t("steering.rules.postpone_title")}</DialogTitle>
                <DialogDescription>
                  {request?.date
                    ? t("steering.rules.postpone_description_date", { date: renderFormattedDate(request.date) })
                    : t("steering.rules.postpone_description")}
                </DialogDescription>
              </DialogHeading>
            </DialogHeader>
            <DialogBody tabIndex={0}>
              <label className="flex flex-col gap-1 text-12 text-secondary">
                {t("steering.rules.postpone_reason")}
                <textarea
                  rows={3}
                  value={comment}
                  onChange={(event) => setComment(event.target.value)}
                  className="w-full rounded-md border border-subtle bg-surface-1 px-3 py-2 text-13 text-primary outline-none placeholder:text-placeholder focus:border-accent-strong"
                />
              </label>
            </DialogBody>
          </DialogMain>
          <DialogActions>
            <Button
              variant="secondary"
              size="md"
              stretch="auto"
              label={t("common.cancel")}
              onClick={() => settle(null)}
            />
            <Button
              type="submit"
              variant="primary"
              size="md"
              stretch="auto"
              label={t("steering.rules.postpone_confirm")}
              disabled={!comment.trim()}
            />
          </DialogActions>
        </form>
      </DialogContent>
    </Dialog>
  );
}
