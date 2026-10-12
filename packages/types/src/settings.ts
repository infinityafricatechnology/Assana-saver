/**
 * Copyright (c) 2023-present Plane Software, Inc. and contributors
 * SPDX-License-Identifier: AGPL-3.0-only
 * See the LICENSE file for details.
 */

// local imports
import type { EUserProjectRoles } from ".";
import type { EUserWorkspaceRoles } from "./workspace";

export type TProfileSettingsTabs =
  | "general"
  | "preferences"
  | "notifications"
  | "security"
  | "connect-claude"
  | "api-tokens";

export type TWorkspaceSettingsTabs = "general" | "people" | "members" | "referential" | "export" | "webhooks";
export type TWorkspaceSettingsItem = {
  key: TWorkspaceSettingsTabs;
  i18n_label: string;
  href: string;
  access: EUserWorkspaceRoles[];
  highlight: (pathname: string, baseUrl: string) => boolean;
};

export type TProjectSettingsTabs =
  | "general"
  | "members"
  | "features_views"
  | "features_pages"
  | "features_intake"
  | "states"
  | "labels"
  | "custom_fields"
  | "automations";
export type TProjectSettingsItem = {
  key: TProjectSettingsTabs;
  i18n_label: string;
  href: string;
  access: EUserProjectRoles[];
  highlight: (pathname: string, baseUrl: string) => boolean;
};
