/**
 * Copyright (c) 2023-present Plane Software, Inc. and contributors
 * SPDX-License-Identifier: AGPL-3.0-only
 * See the LICENSE file for details.
 */

import { useState } from "react";
import { setToast } from "@plane/blocks/toast";
import { useTranslation } from "@plane/i18n";
import { cn } from "@plane/utils";
// local imports
import { steeringDashboardService } from "./use-dashboard";

const saveBlob = (blob: Blob, filename: string) => {
  const url = URL.createObjectURL(blob);
  const link = document.createElement("a");
  link.href = url;
  link.download = filename;
  document.body.appendChild(link);
  link.click();
  link.remove();
  URL.revokeObjectURL(url);
};

function ExportButton(props: { label: string; className?: string; run: () => Promise<void> }) {
  const { t } = useTranslation();
  const [isBusy, setIsBusy] = useState(false);
  return (
    <button
      type="button"
      disabled={isBusy}
      aria-busy={isBusy}
      className={cn("iag-pill iag-focus disabled:opacity-60", props.className)}
      onClick={async () => {
        setIsBusy(true);
        try {
          await props.run();
        } catch {
          setToast({ type: "error", title: t("common.error.label"), message: t("steering.dashboard.export_failed") });
        } finally {
          setIsBusy(false);
        }
      }}
    >
      {props.label}
    </button>
  );
}

/** §6.7: the COMEX PDF, following the branch filter of the header. */
export function ComexExportButton(props: { workspaceSlug: string; branchId: string | null; today: string }) {
  const { t } = useTranslation();
  return (
    <ExportButton
      label={t("steering.dashboard.export_pdf")}
      className="iag-pill-gold"
      run={async () =>
        saveBlob(
          await steeringDashboardService.downloadComex(props.workspaceSlug, props.branchId),
          `pilotage-comex-${props.today}.pdf`
        )
      }
    />
  );
}

/** §12 « Export de données »: the list as filtered on the screen. */
export function TasksExportButton(props: { workspaceSlug: string; ids: string[]; today: string }) {
  const { t } = useTranslation();
  return (
    <ExportButton
      label={t("steering.dashboard.export_excel")}
      run={async () =>
        saveBlob(
          await steeringDashboardService.downloadTasks(props.workspaceSlug, props.ids),
          `pilotage-taches-${props.today}.xlsx`
        )
      }
    />
  );
}
