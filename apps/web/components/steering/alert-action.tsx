/**
 * Copyright (c) 2023-present Plane Software, Inc. and contributors
 * SPDX-License-Identifier: AGPL-3.0-only
 * See the LICENSE file for details.
 */

import { useTranslation } from "@plane/i18n";

/** The words of a steering alert in the notification inbox (§9.2), after the name of who acted, if anyone. */
export function SteeringAlertAction(props: { event: string | undefined }) {
  const { t } = useTranslation();
  return <>{props.event ? t(`steering.alerts.${props.event}`) : ""}</>;
}
