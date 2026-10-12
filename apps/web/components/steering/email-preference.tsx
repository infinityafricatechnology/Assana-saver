/**
 * Copyright (c) 2023-present Plane Software, Inc. and contributors
 * SPDX-License-Identifier: AGPL-3.0-only
 * See the LICENSE file for details.
 */

import useSWR from "swr";
import { Switch } from "@makeplane/propel/components/switch";
import { API_BASE_URL } from "@plane/constants";
import { setToast } from "@plane/blocks/toast";
import { useTranslation } from "@plane/i18n";
// components
import { SettingsControlItem } from "@/components/settings/control-item";
// services
import { APIService } from "@/services/api.service";

class SteeringEmailService extends APIService {
  constructor() {
    super(API_BASE_URL);
  }

  getPreference(): Promise<{ emails_enabled: boolean }> {
    return this.get("/api/users/me/steering-emails/").then((response) => response?.data);
  }

  setPreference(emails_enabled: boolean): Promise<{ emails_enabled: boolean }> {
    return this.patch("/api/users/me/steering-emails/", { emails_enabled }).then((response) => response?.data);
  }
}

const service = new SteeringEmailService();

/** §9.2: anyone can turn the steering e-mails off; the alerts stay in the platform. */
export function SteeringEmailPreference() {
  const { t } = useTranslation();
  const { data, mutate } = useSWR("STEERING_EMAIL_PREFERENCE", () => service.getPreference());
  if (!data) return null;
  return (
    <SettingsControlItem
      title={t("steering.emails.title")}
      description={t("steering.emails.description")}
      control={
        <Switch
          size="sm"
          checked={data.emails_enabled}
          aria-label={t("steering.emails.title")}
          onCheckedChange={async (enabled) => {
            try {
              await mutate(service.setPreference(enabled), {
                optimisticData: { emails_enabled: enabled },
                rollbackOnError: true,
              });
              setToast({ type: "success", title: t("success"), message: t("steering.emails.saved") });
            } catch {
              setToast({ type: "error", title: t("error"), message: t("steering.emails.error") });
            }
          }}
        />
      }
    />
  );
}
