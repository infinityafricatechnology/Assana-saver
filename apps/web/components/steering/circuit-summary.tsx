/**
 * Copyright (c) 2023-present Plane Software, Inc. and contributors
 * SPDX-License-Identifier: AGPL-3.0-only
 * See the LICENSE file for details.
 */

import { useState } from "react";
import { observer } from "mobx-react";
import { Button } from "@makeplane/propel/components/button";
import { useTranslation } from "@plane/i18n";
import { renderFormattedDate } from "@plane/utils";
// hooks
import { useIssueDetail } from "@/hooks/store/use-issue-detail";
import { useUser } from "@/hooks/store/user";
// types
import type { TIssueSteering } from "@/services/steering.service";
// local imports
import { SteeringSubmitDialog } from "./submit-dialog";

type TCircuitSummaryProps = {
  workspaceSlug: string;
  projectId: string;
  issueId: string;
  steering: TIssueSteering;
  disabled?: boolean;
};

/** The CEO circuit seen from the work item (§6.6, §8): submission, decision, retained priority, reminders. */
export const SteeringCircuitSummary = observer(function SteeringCircuitSummary(props: TCircuitSummaryProps) {
  const { workspaceSlug, projectId, issueId, steering, disabled } = props;
  const { t } = useTranslation();
  const { data: currentUser } = useUser();
  const {
    issue: { getIssueById },
  } = useIssueDetail();
  const [isSubmitOpen, setIsSubmitOpen] = useState(false);

  const { circuit } = steering;
  const pending = circuit.submissions.find((submission) => submission.status === "pending");
  const lastDecision = circuit.submissions.find((submission) => submission.status !== "pending");
  const isClosed = steering.status === "done" || steering.status === "cancelled";
  const isAssignee = !!currentUser && (getIssueById(issueId)?.assignee_ids ?? []).includes(currentUser.id);
  const canSubmit = !disabled && isAssignee && !isClosed && !pending;

  if (!pending && !lastDecision && !circuit.requalification && !circuit.reminders.count && !canSubmit) return null;

  return (
    <div className="flex flex-col gap-2">
      {pending && (
        <div className="rounded-md border-l-4 border-[#6A4C9E] bg-layer-1 px-3 py-2 text-12">
          <p className="font-medium text-primary">
            {t("steering.circuit.pending", {
              date: renderFormattedDate(pending.submitted_at),
              name: pending.submitted_by?.display_name ?? "",
            })}
          </p>
          <p className="mt-1 whitespace-pre-line text-secondary">{pending.message}</p>
          {pending.link && (
            <a
              href={pending.link}
              target="_blank"
              rel="noreferrer"
              className="mt-1 inline-block text-accent-primary underline"
            >
              {t("steering.circuit.open_document")}
            </a>
          )}
        </div>
      )}
      {!pending && lastDecision && (
        <div
          className={`rounded-md border-l-4 bg-layer-1 px-3 py-2 text-12 ${
            lastDecision.status === "validated" ? "border-[#2E6B52]" : "border-[#C0701A]"
          }`}
        >
          <p className="font-medium text-primary">
            {t(`steering.circuit.${lastDecision.status}`, {
              date: lastDecision.decided_at ? renderFormattedDate(lastDecision.decided_at) : "",
            })}
          </p>
          {lastDecision.decision_comment && (
            <p className="mt-1 whitespace-pre-line text-secondary">{lastDecision.decision_comment}</p>
          )}
        </div>
      )}
      {circuit.requalification && (
        <p className="rounded-md bg-layer-1 px-3 py-2 text-12 text-secondary">
          {t("steering.circuit.requalified", {
            by: t(`steering.profiles.roles.${circuit.requalification.by_role}`),
            declared: t(circuit.requalification.declared_priority),
            retained: t(circuit.requalification.priority),
          })}
          {circuit.requalification.comment && ` — ${circuit.requalification.comment}`}
        </p>
      )}
      {circuit.reminders.count > 0 && (
        <p className="px-1 text-11 text-tertiary">
          {t("steering.circuit.reminders", {
            count: circuit.reminders.count,
            date: circuit.reminders.last_at ? renderFormattedDate(circuit.reminders.last_at) : "",
          })}
        </p>
      )}
      {canSubmit && (
        <div>
          <Button
            variant="secondary"
            size="sm"
            stretch="auto"
            label={t("steering.circuit.submit")}
            onClick={() => setIsSubmitOpen(true)}
          />
        </div>
      )}
      <SteeringSubmitDialog
        workspaceSlug={workspaceSlug}
        projectId={projectId}
        issueId={issueId}
        steering={steering}
        isOpen={isSubmitOpen}
        onClose={() => setIsSubmitOpen(false)}
      />
    </div>
  );
});
