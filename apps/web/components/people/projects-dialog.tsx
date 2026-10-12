/**
 * Copyright (c) 2023-present Plane Software, Inc. and contributors
 * SPDX-License-Identifier: AGPL-3.0-only
 * See the LICENSE file for details.
 */

import { useEffect, useState } from "react";
import type { FormEvent } from "react";
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
// hooks
import { usePeople } from "@/hooks/store/use-people";
// types
import type { TPerson, TPersonRole } from "@/services/people.service";
// local imports
import { ProjectsSelect, RoleSelect, fullName, usePeopleErrorMessage } from "./shared";

type TProjectsDialogProps = {
  workspaceSlug: string;
  /** The people to add; the dialog is closed when empty. */
  people: TPerson[];
  onClose: (added: boolean) => void;
};

/** Add one or several people to one or several projects. */
export const PeopleProjectsDialog = observer(function PeopleProjectsDialog(props: TProjectsDialogProps) {
  const { workspaceSlug, people, onClose } = props;
  const { t } = useTranslation();
  const store = usePeople();
  const errorMessage = usePeopleErrorMessage();
  const [projectIds, setProjectIds] = useState<string[]>([]);
  const [role, setRole] = useState<TPersonRole>(15);
  const [isSubmitting, setIsSubmitting] = useState(false);
  const isOpen = people.length > 0;

  useEffect(() => {
    if (isOpen) {
      setProjectIds([]);
      setRole(15);
    }
  }, [isOpen]);

  const handleSubmit = async (event: FormEvent) => {
    event.preventDefault();
    if (!projectIds.length || isSubmitting) return;
    setIsSubmitting(true);
    try {
      await store.addToProjects(
        workspaceSlug,
        people.map((person) => person.id),
        projectIds,
        role
      );
      setToast({ type: "success", title: t("common.success"), message: t("people.toasts.projects_added") });
      onClose(true);
    } catch (error) {
      setToast({ type: "error", title: t("common.error.label"), message: errorMessage(error) });
    } finally {
      setIsSubmitting(false);
    }
  };

  return (
    <Dialog
      open={isOpen}
      onOpenChange={(open) => {
        if (!open) onClose(false);
      }}
    >
      <DialogContent size="sm">
        <form onSubmit={handleSubmit} className="flex min-h-0 flex-1 flex-col">
          <DialogMain>
            <DialogHeader>
              <DialogHeading>
                <DialogTitle>{t("people.projects_dialog.title")}</DialogTitle>
                <DialogDescription>
                  {people.length === 1
                    ? fullName(people[0])
                    : t("people.projects_dialog.description", { count: people.length })}
                </DialogDescription>
              </DialogHeading>
            </DialogHeader>
            <DialogBody tabIndex={0}>
              <div className="flex flex-col gap-4">
                <div className="flex flex-col gap-1 text-12 text-secondary">
                  {t("people.fields.projects")}
                  <ProjectsSelect value={projectIds} onChange={setProjectIds} />
                </div>
                <div className="flex flex-col gap-1 text-12 text-secondary">
                  {t("people.fields.project_role")}
                  <div className="w-48">
                    <RoleSelect value={role} onChange={setRole} />
                  </div>
                  <span className="text-11 text-tertiary">{t("people.projects_dialog.admin_hint")}</span>
                </div>
              </div>
            </DialogBody>
          </DialogMain>
          <DialogActions>
            <Button
              variant="secondary"
              size="md"
              stretch="auto"
              label={t("common.cancel")}
              onClick={() => onClose(false)}
            />
            <Button
              type="submit"
              variant="primary"
              size="md"
              stretch="auto"
              label={t("people.projects_dialog.submit")}
              loading={isSubmitting}
              disabled={!projectIds.length}
            />
          </DialogActions>
        </form>
      </DialogContent>
    </Dialog>
  );
});
