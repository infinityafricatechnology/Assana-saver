/**
 * Copyright (c) 2023-present Plane Software, Inc. and contributors
 * SPDX-License-Identifier: AGPL-3.0-only
 * See the LICENSE file for details.
 */

import { useEffect, useState } from "react";
import type { FormEvent, ReactNode } from "react";
import { observer } from "mobx-react";
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
import { Input, InputGroup } from "@makeplane/propel/components/input";
import { DateSelect } from "@plane/blocks/property-select";
import { setToast } from "@plane/blocks/toast";
import { useTranslation } from "@plane/i18n";
import { getDate, renderFormattedPayloadDate } from "@plane/utils";
// hooks
import { useIssueDetail } from "@/hooks/store/use-issue-detail";
import { useSteering } from "@/hooks/store/use-steering";
// types
import type { TIssueSteering, TSteeringRiskNature } from "@/services/steering.service";
import { STEERING_RISK_NATURES } from "@/services/steering.service";
// local imports
import { SteeringSelect } from "./select";

const textAreaClassName =
  "w-full rounded-md border border-subtle bg-surface-1 px-3 py-2 text-13 text-primary outline-none placeholder:text-placeholder focus:border-accent-strong";

function Field(props: { label: string; hint?: string; children: ReactNode }) {
  return (
    <div className="flex flex-col gap-1 text-12 text-secondary">
      {props.label}
      {props.children}
      {props.hint && <span className="text-11 text-tertiary">{props.hint}</span>}
    </div>
  );
}

type TSubmitDialogProps = {
  workspaceSlug: string;
  projectId: string;
  issueId: string;
  steering: TIssueSteering;
  isOpen: boolean;
  onClose: () => void;
};

/** « Soumettre au PDG » (§8.1): a message, the document to validate and, if useful, the risk of waiting. */
export const SteeringSubmitDialog = observer(function SteeringSubmitDialog(props: TSubmitDialogProps) {
  const { workspaceSlug, projectId, issueId, steering, isOpen, onClose } = props;
  const { t } = useTranslation();
  const steeringStore = useSteering();
  const {
    attachment: { getAttachmentsByIssueId, getAttachmentById },
  } = useIssueDetail();
  const [message, setMessage] = useState("");
  const [link, setLink] = useState("");
  const [attachmentId, setAttachmentId] = useState<string | null>(null);
  const [riskNature, setRiskNature] = useState<TSteeringRiskNature | null>(null);
  const [riskDate, setRiskDate] = useState<string | null>(null);
  const [riskDescription, setRiskDescription] = useState("");
  const [isSubmitting, setIsSubmitting] = useState(false);

  useEffect(() => {
    if (!isOpen) return;
    setMessage("");
    setLink("");
    setAttachmentId(null);
    setRiskNature(steering.risk_nature);
    setRiskDate(steering.risk_effective_date);
    setRiskDescription(steering.risk_description);
  }, [isOpen, steering]);

  const attachments = (getAttachmentsByIssueId(issueId) ?? [])
    .map((id) => getAttachmentById(id))
    .filter((attachment) => !!attachment)
    .map((attachment) => ({ value: attachment!.id, label: attachment!.attributes.name }));
  const canSubmit = !!message.trim() && (!!link.trim() || !!attachmentId) && !isSubmitting;

  const handleSubmit = async (event: FormEvent) => {
    event.preventDefault();
    if (!canSubmit) return;
    setIsSubmitting(true);
    try {
      await steeringStore.submitToCeo(workspaceSlug, projectId, issueId, {
        message: message.trim(),
        link: link.trim() || undefined,
        attachment_id: attachmentId,
        risk_nature: riskNature,
        risk_effective_date: riskDate,
        risk_description: riskDescription.trim(),
      });
      setToast({ type: "success", title: t("common.success"), message: t("steering.circuit.submitted_toast") });
      onClose();
    } catch (error) {
      const code = typeof error === "object" && error !== null && "code" in error ? String(error.code) : "";
      const key = `steering.circuit.errors.${code}`;
      const translated = code ? t(key) : "";
      setToast({
        type: "error",
        title: t("common.error.label"),
        message: translated && translated !== key ? translated : t("steering.task.errors.save"),
      });
    } finally {
      setIsSubmitting(false);
    }
  };

  return (
    <Dialog
      open={isOpen}
      onOpenChange={(open) => {
        if (!open) onClose();
      }}
    >
      <DialogContent size="md">
        <form onSubmit={handleSubmit} className="flex min-h-0 flex-1 flex-col">
          <DialogMain>
            <DialogHeader>
              <DialogHeading>
                <DialogTitle>{t("steering.circuit.submit_title")}</DialogTitle>
                <DialogDescription>{t("steering.circuit.submit_description")}</DialogDescription>
              </DialogHeading>
            </DialogHeader>
            <DialogBody tabIndex={0}>
              <div className="flex flex-col gap-4">
                <Field label={t("steering.circuit.message")}>
                  <textarea
                    rows={3}
                    value={message}
                    onChange={(event) => setMessage(event.target.value)}
                    className={textAreaClassName}
                  />
                </Field>
                <Field label={t("steering.circuit.link")} hint={t("steering.circuit.document_hint")}>
                  <InputGroup size="md">
                    <Input
                      size="md"
                      type="url"
                      value={link}
                      placeholder="https://"
                      onChange={(event) => setLink(event.target.value)}
                    />
                  </InputGroup>
                </Field>
                {attachments.length > 0 && (
                  <Field label={t("steering.circuit.attachment")}>
                    <SteeringSelect<string>
                      value={attachmentId}
                      options={attachments}
                      placeholder={t("steering.circuit.attachment_placeholder")}
                      ariaLabel={t("steering.circuit.attachment")}
                      onChange={setAttachmentId}
                    />
                  </Field>
                )}
                <div className="flex flex-col gap-3 rounded-md border border-subtle p-3">
                  <span className="text-12 font-medium text-secondary">{t("steering.circuit.risk_title")}</span>
                  <div className="grid grid-cols-2 gap-3">
                    <Field label={t("steering.task.fields.risk_nature")}>
                      <SteeringSelect<TSteeringRiskNature>
                        value={riskNature}
                        options={STEERING_RISK_NATURES.map((value) => ({
                          value,
                          label: t(`steering.task.risk.${value}`),
                        }))}
                        placeholder={t("steering.task.empty")}
                        ariaLabel={t("steering.task.fields.risk_nature")}
                        onChange={setRiskNature}
                      />
                    </Field>
                    <Field label={t("steering.task.fields.risk_effective_date")}>
                      <DateSelect
                        value={riskDate ? (getDate(riskDate) ?? null) : null}
                        onChange={(date) => setRiskDate(date ? (renderFormattedPayloadDate(date) ?? null) : null)}
                        placeholder={t("steering.task.empty")}
                        clearable
                        variant="select-md"
                      />
                    </Field>
                  </div>
                  <Field label={t("steering.task.fields.risk_description")}>
                    <textarea
                      rows={2}
                      value={riskDescription}
                      onChange={(event) => setRiskDescription(event.target.value)}
                      className={textAreaClassName}
                    />
                  </Field>
                </div>
              </div>
            </DialogBody>
          </DialogMain>
          <DialogActions>
            <Button variant="secondary" size="md" stretch="auto" label={t("common.cancel")} onClick={onClose} />
            <Button
              type="submit"
              variant="primary"
              size="md"
              stretch="auto"
              label={t("steering.circuit.submit")}
              loading={isSubmitting}
              disabled={!canSubmit}
            />
          </DialogActions>
        </form>
      </DialogContent>
    </Dialog>
  );
});
