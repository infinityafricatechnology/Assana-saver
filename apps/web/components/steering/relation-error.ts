/**
 * Copyright (c) 2023-present Plane Software, Inc. and contributors
 * SPDX-License-Identifier: AGPL-3.0-only
 * See the LICENSE file for details.
 */

import { setToast } from "@plane/blocks/toast";
import { useTranslation } from "@plane/i18n";

/** Explains a refused relation; the API refuses dependency loops (cahier des charges §7). */
export const useRelationErrorToast = () => {
  const { t } = useTranslation();
  return (error: unknown) => {
    const code = typeof error === "object" && error !== null && "code" in error ? error.code : undefined;
    setToast({
      type: "error",
      title: t("common.error.label"),
      message: code === "circular_dependency" ? t("steering.dependencies.circular") : t("common.error.message"),
    });
  };
};
