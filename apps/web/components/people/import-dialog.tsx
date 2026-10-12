/**
 * Copyright (c) 2023-present Plane Software, Inc. and contributors
 * SPDX-License-Identifier: AGPL-3.0-only
 * See the LICENSE file for details.
 */

import { useEffect, useState } from "react";
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
import { setToast } from "@plane/blocks/toast";
import { useTranslation } from "@plane/i18n";
import { cn } from "@plane/utils";
// hooks
import { usePeople } from "@/hooks/store/use-people";
// types
import type { TImportResult } from "@/services/people.service";
// local imports
import { usePeopleErrorMessage } from "./shared";

const TEMPLATE = [
  "Prénom;Nom;E-mail;Rôle;Profil;Périmètre;Projets",
  "Awa;Diallo;awa.diallo@infinity-africa.com;Membre;Responsable d'entité;SCI Infinity;IAT",
  "Kofi;Mensah;kofi.mensah@infinity-africa.com;Admin;Directeur de pôle;Immobilier;",
].join("\r\n");

/** Saves a text file from the browser (BOM included, so Excel reads the accents). */
export const downloadText = (filename: string, content: string) => {
  const url = URL.createObjectURL(
    new Blob([content.startsWith("﻿") ? content : `﻿${content}`], { type: "text/csv;charset=utf-8" })
  );
  const link = document.createElement("a");
  link.href = url;
  link.download = filename;
  link.click();
  URL.revokeObjectURL(url);
};

type TImportDialogProps = { workspaceSlug: string; isOpen: boolean; onClose: () => void };

/** Import a list of people: preview every line with its errors, then create the valid ones. */
export const PeopleImportDialog = observer(function PeopleImportDialog(props: TImportDialogProps) {
  const { workspaceSlug, isOpen, onClose } = props;
  const { t } = useTranslation();
  const store = usePeople();
  const errorMessage = usePeopleErrorMessage();
  const [file, setFile] = useState<File | null>(null);
  const [preview, setPreview] = useState<TImportResult | null>(null);
  const [sendEmail, setSendEmail] = useState(true);
  const [isWorking, setIsWorking] = useState(false);

  useEffect(() => {
    if (!isOpen) {
      setFile(null);
      setPreview(null);
      setSendEmail(true);
    }
  }, [isOpen]);

  const validCount = preview?.rows.filter((row) => row.valid).length ?? 0;

  const choose = async (chosen: File | undefined) => {
    if (!chosen) return;
    setFile(chosen);
    setIsWorking(true);
    try {
      setPreview(await store.importFile(workspaceSlug, chosen, false, sendEmail));
    } catch (error) {
      setPreview(null);
      setToast({ type: "error", title: t("common.error.label"), message: errorMessage(error) });
    } finally {
      setIsWorking(false);
    }
  };

  const confirm = async () => {
    if (!file || !validCount) return;
    setIsWorking(true);
    try {
      const result = await store.importFile(workspaceSlug, file, true, sendEmail);
      setToast({
        type: "success",
        title: t("common.success"),
        message: t("people.import.done", { count: result.created }),
      });
      onClose();
    } catch (error) {
      setToast({ type: "error", title: t("common.error.label"), message: errorMessage(error) });
    } finally {
      setIsWorking(false);
    }
  };

  return (
    <Dialog
      open={isOpen}
      onOpenChange={(open) => {
        if (!open) onClose();
      }}
    >
      <DialogContent size="lg">
        <DialogMain>
          <DialogHeader>
            <DialogHeading>
              <DialogTitle>{t("people.import.title")}</DialogTitle>
              <DialogDescription>{t("people.import.description")}</DialogDescription>
            </DialogHeading>
          </DialogHeader>
          <DialogBody tabIndex={0}>
            <div className="flex flex-col gap-4">
              <div className="flex flex-wrap items-center gap-3">
                <label className="cursor-pointer rounded-md border border-dashed border-strong px-4 py-3 text-13 text-secondary hover:bg-layer-1">
                  {file ? file.name : t("people.import.choose")}
                  <input
                    type="file"
                    accept=".csv,.xlsx"
                    className="sr-only"
                    onChange={(event) => void choose(event.target.files?.[0])}
                  />
                </label>
                <Button
                  variant="ghost"
                  size="sm"
                  stretch="auto"
                  label={t("people.import.template")}
                  onClick={() => downloadText("modele-personnes.csv", TEMPLATE)}
                />
              </div>

              {preview && (
                <>
                  <p className="text-13 text-secondary">
                    {t("people.import.summary", {
                      valid: validCount,
                      invalid: preview.rows.length - validCount,
                    })}
                  </p>
                  <div className="max-h-72 overflow-auto rounded-md border border-subtle">
                    <table className="w-full text-left text-12">
                      <thead className="sticky top-0 bg-layer-1 text-tertiary">
                        <tr>
                          <th className="px-3 py-2 font-medium">{t("people.import.line")}</th>
                          <th className="px-3 py-2 font-medium">{t("people.fields.name")}</th>
                          <th className="px-3 py-2 font-medium">{t("people.fields.email")}</th>
                          <th className="px-3 py-2 font-medium">{t("people.import.result")}</th>
                        </tr>
                      </thead>
                      <tbody>
                        {preview.rows.map((row) => (
                          <tr key={row.line} className="border-t border-subtle">
                            <td className="px-3 py-1.5 text-tertiary">{row.line}</td>
                            <td className="px-3 py-1.5 text-primary">
                              {[row.values.first_name, row.values.last_name].filter(Boolean).join(" ")}
                            </td>
                            <td className="px-3 py-1.5 text-secondary">{row.values.email}</td>
                            <td
                              className={cn("px-3 py-1.5", row.valid ? "text-success-primary" : "text-danger-primary")}
                            >
                              {row.valid
                                ? t("people.import.ready")
                                : row.errors.map((code) => t(`people.import.errors.${code}`)).join(", ")}
                            </td>
                          </tr>
                        ))}
                      </tbody>
                    </table>
                  </div>
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
            variant="primary"
            size="md"
            stretch="auto"
            label={t("people.import.submit", { count: validCount })}
            loading={isWorking}
            disabled={!validCount || isWorking}
            onClick={confirm}
          />
        </DialogActions>
      </DialogContent>
    </Dialog>
  );
});
