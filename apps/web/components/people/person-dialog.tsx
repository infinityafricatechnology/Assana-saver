/**
 * Copyright (c) 2023-present Plane Software, Inc. and contributors
 * SPDX-License-Identifier: AGPL-3.0-only
 * See the LICENSE file for details.
 */

import { useEffect, useState } from "react";
import type { FormEvent, ReactNode } from "react";
import { observer } from "mobx-react";
import { Button } from "@makeplane/propel/components/button";
import { Checkbox } from "@makeplane/propel/components/checkbox";
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
import { setToast } from "@plane/blocks/toast";
import { useTranslation } from "@plane/i18n";
// hooks
import { usePeople } from "@/hooks/store/use-people";
// types
import type { TPerson, TPersonProfileInput, TPersonRole } from "@/services/people.service";
// local imports
import { ProfilesEditor, ProjectsSelect, RoleSelect, usePeopleErrorMessage } from "./shared";

function Field(props: { label: string; children: ReactNode }) {
  return (
    <div className="flex flex-col gap-1 text-12 text-secondary">
      {props.label}
      {props.children}
    </div>
  );
}

type TPersonDialogProps = {
  workspaceSlug: string;
  isOpen: boolean;
  /** The person to edit; none to add someone. */
  person?: TPerson;
  onClose: () => void;
};

export const PersonDialog = observer(function PersonDialog(props: TPersonDialogProps) {
  const { workspaceSlug, isOpen, person, onClose } = props;
  const { t } = useTranslation();
  const people = usePeople();
  const errorMessage = usePeopleErrorMessage();
  const [firstName, setFirstName] = useState("");
  const [lastName, setLastName] = useState("");
  const [email, setEmail] = useState("");
  const [role, setRole] = useState<TPersonRole>(15);
  const [profiles, setProfiles] = useState<TPersonProfileInput[]>([]);
  const [projectIds, setProjectIds] = useState<string[]>([]);
  const [sendEmail, setSendEmail] = useState(true);
  const [isSubmitting, setIsSubmitting] = useState(false);

  useEffect(() => {
    if (!isOpen) return;
    setFirstName(person?.first_name ?? "");
    setLastName(person?.last_name ?? "");
    setEmail(person?.email ?? "");
    setRole(person?.role ?? 15);
    setProfiles(
      (person?.profiles ?? []).map((profile) => ({
        role: profile.role,
        branch_id: profile.branch_id,
        entity_id: profile.entity_id,
      }))
    );
    setProjectIds([]);
    setSendEmail(true);
  }, [isOpen, person]);

  const profilesComplete = profiles.every(
    (profile) =>
      (profile.role !== "branch_director" || profile.branch_id) &&
      (profile.role !== "entity_manager" || profile.entity_id)
  );
  const canSubmit = !!firstName.trim() && (!!person || !!email.trim()) && profilesComplete && !isSubmitting;

  const handleSubmit = async (event: FormEvent) => {
    event.preventDefault();
    if (!canSubmit) return;
    setIsSubmitting(true);
    try {
      if (person) {
        await people.updatePerson(workspaceSlug, person.id, {
          first_name: firstName,
          last_name: lastName,
          role,
          profiles,
        });
        setToast({ type: "success", title: t("common.success"), message: t("people.toasts.updated") });
      } else {
        await people.createPerson(workspaceSlug, {
          first_name: firstName,
          last_name: lastName,
          email,
          role,
          profiles,
          project_ids: projectIds,
          send_email: sendEmail,
        });
        setToast({
          type: "success",
          title: t("common.success"),
          message: sendEmail ? t("people.toasts.added_with_email") : t("people.toasts.added"),
        });
      }
      onClose();
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
        if (!open) onClose();
      }}
    >
      <DialogContent size="md">
        <form onSubmit={handleSubmit} className="flex min-h-0 flex-1 flex-col">
          <DialogMain>
            <DialogHeader>
              <DialogHeading>
                <DialogTitle>{person ? t("people.dialog.edit_title") : t("people.dialog.add_title")}</DialogTitle>
                <DialogDescription>{person ? person.email : t("people.dialog.add_description")}</DialogDescription>
              </DialogHeading>
            </DialogHeader>
            <DialogBody tabIndex={0}>
              <div className="flex flex-col gap-4">
                <div className="grid grid-cols-2 gap-3">
                  <Field label={t("people.fields.first_name")}>
                    <InputGroup size="md">
                      <Input size="md" value={firstName} onChange={(event) => setFirstName(event.target.value)} />
                    </InputGroup>
                  </Field>
                  <Field label={t("people.fields.last_name")}>
                    <InputGroup size="md">
                      <Input size="md" value={lastName} onChange={(event) => setLastName(event.target.value)} />
                    </InputGroup>
                  </Field>
                </div>
                {!person && (
                  <Field label={t("people.fields.email")}>
                    <InputGroup size="md">
                      <Input
                        size="md"
                        type="email"
                        value={email}
                        placeholder="prenom.nom@infinity-africa.com"
                        onChange={(event) => setEmail(event.target.value)}
                      />
                    </InputGroup>
                  </Field>
                )}
                <Field label={t("people.fields.role")}>
                  <div className="w-48">
                    <RoleSelect value={role} onChange={setRole} />
                  </div>
                </Field>
                <Field label={t("steering.profiles.title")}>
                  <ProfilesEditor workspaceSlug={workspaceSlug} value={profiles} onChange={setProfiles} />
                </Field>
                {!person && (
                  <>
                    <Field label={t("people.fields.projects")}>
                      <ProjectsSelect value={projectIds} onChange={setProjectIds} />
                    </Field>
                    <Checkbox
                      checked={sendEmail}
                      onCheckedChange={(checked) => setSendEmail(!!checked)}
                      label={t("people.fields.send_email")}
                    />
                  </>
                )}
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
              label={person ? t("steering.save") : t("people.add")}
              loading={isSubmitting}
              disabled={!canSubmit}
            />
          </DialogActions>
        </form>
      </DialogContent>
    </Dialog>
  );
});
