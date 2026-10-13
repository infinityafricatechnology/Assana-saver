/**
 * Copyright (c) 2023-present Plane Software, Inc. and contributors
 * SPDX-License-Identifier: AGPL-3.0-only
 * See the LICENSE file for details.
 */

import { useTranslation } from "@plane/i18n";
// components
import { PageHead } from "@/components/core/page-title";
import { SteeringDashboardRoot } from "@/components/steering/dashboard/root";

export default function SteeringPage() {
  const { t } = useTranslation();
  return (
    <>
      <PageHead title={t("steering.dashboard.title")} />
      <div className="relative h-full w-full overflow-hidden overflow-y-auto">
        <SteeringDashboardRoot />
      </div>
    </>
  );
}
