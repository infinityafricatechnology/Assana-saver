/**
 * Copyright (c) 2023-present Plane Software, Inc. and contributors
 * SPDX-License-Identifier: AGPL-3.0-only
 * See the LICENSE file for details.
 */

import type { ReactNode } from "react";
import { useTranslation } from "@plane/i18n";
import { renderFormattedDate } from "@plane/utils";
// types
import type { TDashboard } from "@/services/steering-dashboard.service";

type THeaderProps = {
  data: TDashboard;
  branchId: string | null;
  isLive: boolean;
  onBranchChange: (branchId: string | null) => void;
  actions?: ReactNode;
};

const timeOf = (iso: string) =>
  new Date(iso).toLocaleTimeString(undefined, {
    hour: "2-digit",
    minute: "2-digit",
    hourCycle: "h23",
    timeZone: "Africa/Abidjan",
  });

/** §6: the title, the situation date, the real-time indicator, « Lecture seule » and the exports. */
export function SteeringDashboardHeader(props: THeaderProps) {
  const { data, branchId, isLive, onBranchChange, actions } = props;
  const { t } = useTranslation();
  const branches = data.branches;

  return (
    <div className="iag-banner px-4 pt-5 pb-6 sm:px-8">
      <div className="relative z-10 flex flex-wrap items-start justify-between gap-4">
        <div className="min-w-0">
          <p className="text-12 tracking-wide text-[#e8b93e] uppercase">{t("steering.dashboard.group")}</p>
          <h1 className="mt-1 text-24 leading-8 font-semibold">{t("steering.dashboard.title")}</h1>
          <p className="mt-1 flex flex-wrap items-center gap-x-3 gap-y-1 text-13 text-[#d9d3c4]">
            <span>
              {t("steering.dashboard.situation", {
                date: renderFormattedDate(data.today) ?? data.today,
                time: timeOf(data.generated_at),
              })}
            </span>
            <span className="inline-flex items-center gap-1.5" role="status">
              <span
                aria-hidden="true"
                className={`size-2 rounded-full ${isLive ? "animate-pulse bg-[#72b897]" : "bg-[#e59a4b]"}`}
              />
              {isLive ? t("steering.dashboard.live") : t("steering.dashboard.offline")}
            </span>
            <span className="rounded-full border border-[#e8b93e]/60 px-2 text-12 text-[#e8b93e]">
              {t("steering.dashboard.read_only")}
            </span>
          </p>
        </div>
        <div className="flex flex-wrap items-center gap-2">
          {branches.length > 1 && (
            <label className="flex items-center gap-2 text-12 text-[#d9d3c4]">
              <span className="sr-only sm:not-sr-only">{t("steering.dashboard.branch_filter")}</span>
              <select
                value={branchId ?? ""}
                onChange={(event) => onBranchChange(event.target.value || null)}
                className="iag-focus rounded-full border border-white/20 bg-white/10 px-3 py-1.5 text-13 text-white"
              >
                <option value="" className="text-black">
                  {t("steering.dashboard.all_branches")}
                </option>
                {branches.map((branch) => (
                  <option key={branch.id} value={branch.id} className="text-black">
                    {branch.name}
                  </option>
                ))}
              </select>
            </label>
          )}
          {actions}
        </div>
      </div>
    </div>
  );
}
