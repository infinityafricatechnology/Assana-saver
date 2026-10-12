/**
 * Copyright (c) 2023-present Plane Software, Inc. and contributors
 * SPDX-License-Identifier: AGPL-3.0-only
 * See the LICENSE file for details.
 */

import { useEffect, useState } from "react";
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
import { setToast } from "@plane/blocks/toast";
import { useTranslation } from "@plane/i18n";
// components
import { SteeringSelect } from "@/components/steering/select";
// hooks
import { usePeople } from "@/hooks/store/use-people";
// types
import type { TPerson } from "@/services/people.service";
// local imports
import { fullName, usePeopleErrorMessage } from "./shared";

const NOBODY = "__nobody__";

type TDepartureDialogProps = {
  workspaceSlug: string;
  person: TPerson | undefined;
  onClose: () => void;
};

/** A person leaves: hand over their open work items, then close their access. */
export const PersonDepartureDialog = observer(function PersonDepartureDialog(props: TDepartureDialogProps) {
  const { workspaceSlug, person, onClose } = props;
  const { t } = useTranslation();
  const store = usePeople();
  const errorMessage = usePeopleErrorMessage();
  const [openCount, setOpenCount] = useState<number | null>(null);
  const [reassignTo, setReassignTo] = useState<string | null>(null);
  const [isSubmitting, setIsSubmitting] = useState(false);

  useEffect(() => {
    setOpenCount(null);
    setReassignTo(null);
    if (!person) return;
    store
      .departurePreview(workspaceSlug, person.id)
      .then(setOpenCount)
      .catch(() => setOpenCount(0));
  }, [person, store, workspaceSlug]);

  const candidates = (store.getPeople(workspaceSlug) ?? [])
    .filter((candidate) => candidate.status !== "departed" && candidate.id !== person?.id)
    .map((candidate) => ({ value: candidate.id, label: fullName(candidate) }));
  const needsChoice = (openCount ?? 0) > 0;
  const canSubmit = !!person && openCount !== null && (!needsChoice || !!reassignTo) && !isSubmitting;

  const confirm = async () => {
    if (!person || !canSubmit) return;
    setIsSubmitting(true);
    try {
      await store.depart(workspaceSlug, person.id, reassignTo && reassignTo !== NOBODY ? reassignTo : null);
      setToast({ type: "success", title: t("common.success"), message: t("people.toasts.departed") });
      onClose();
    } catch (error) {
      setToast({ type: "error", title: t("common.error.label"), message: errorMessage(error) });
    } finally {
      setIsSubmitting(false);
    }
  };

  return (
    <Dialog
      open={!!person}
      onOpenChange={(open) => {
        if (!open) onClose();
      }}
    >
      <DialogContent size="sm">
        <DialogMain>
          <DialogHeader>
            <DialogHeading>
              <DialogTitle>{t("people.departure.title", { name: person ? fullName(person) : "" })}</DialogTitle>
              <DialogDescription>{t("people.departure.description")}</DialogDescription>
            </DialogHeading>
          </DialogHeader>
          <DialogBody tabIndex={0}>
            <div className="flex flex-col gap-3 text-13 text-secondary">
              {openCount === null ? (
                <p>{t("common.loading")}</p>
              ) : needsChoice ? (
                <>
                  <p>{t("people.departure.open_work_items", { count: openCount })}</p>
                  <SteeringSelect<string>
                    value={reassignTo}
                    options={[...candidates, { value: NOBODY, label: t("people.departure.nobody") }]}
                    placeholder={t("people.departure.reassign_placeholder")}
                    ariaLabel={t("people.departure.reassign_placeholder")}
                    onChange={setReassignTo}
                  />
                </>
              ) : (
                <p>{t("people.departure.no_open_work_items")}</p>
              )}
            </div>
          </DialogBody>
        </DialogMain>
        <DialogActions>
          <Button variant="secondary" size="md" stretch="auto" label={t("common.cancel")} onClick={onClose} />
          <Button
            variant="danger"
            size="md"
            stretch="auto"
            label={t("people.departure.confirm")}
            loading={isSubmitting}
            disabled={!canSubmit}
            onClick={confirm}
          />
        </DialogActions>
      </DialogContent>
    </Dialog>
  );
});
