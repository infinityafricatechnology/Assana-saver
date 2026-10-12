/**
 * Copyright (c) 2023-present Plane Software, Inc. and contributors
 * SPDX-License-Identifier: AGPL-3.0-only
 * See the LICENSE file for details.
 */

import { observer } from "mobx-react";
import Link from "next/link";
import { useParams, usePathname } from "next/navigation";
import useSWR from "swr";
import { DashboardsOutline } from "@makeplane/propel/icons";
import { useTranslation } from "@plane/i18n";
// components
import { SidebarNavItem } from "@/components/sidebar/sidebar-navigation";
// hooks
import { useAppTheme } from "@/hooks/store/use-app-theme";
import { useSteering } from "@/hooks/store/use-steering";

/** « Espace de pilotage », for the people with a steering profile and the workspace admins (§10). */
export const SteeringSidebarItem = observer(function SteeringSidebarItem() {
  const { t } = useTranslation();
  const pathname = usePathname();
  const { workspaceSlug } = useParams();
  const slug = workspaceSlug?.toString() ?? "";
  const steeringStore = useSteering();
  const { toggleSidebar, isExtendedSidebarOpened, toggleExtendedSidebar } = useAppTheme();

  useSWR(slug ? `STEERING_REFERENTIAL_${slug}` : null, () => steeringStore.fetchReferential(slug), {
    revalidateOnFocus: false,
  });
  const referential = steeringStore.getReferential(slug);
  if (!referential || !(referential.can_administer || referential.my_profiles.length > 0)) return null;

  const href = `/${slug}/steering/`;
  return (
    <Link
      href={href}
      onClick={() => {
        if (window.innerWidth < 768) toggleSidebar();
        if (isExtendedSidebarOpened) toggleExtendedSidebar(false);
      }}
    >
      <SidebarNavItem isActive={pathname.includes(`/${slug}/steering`)}>
        <div className="flex items-center gap-1.5 py-[1px]">
          <DashboardsOutline className="size-4 flex-shrink-0" />
          <p className="text-13 leading-5 font-medium">{t("steering.dashboard.title")}</p>
        </div>
      </SidebarNavItem>
    </Link>
  );
});
