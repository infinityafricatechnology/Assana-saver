/**
 * Copyright (c) 2023-present Plane Software, Inc. and contributors
 * SPDX-License-Identifier: AGPL-3.0-only
 * See the LICENSE file for details.
 */

import { observer } from "mobx-react";
import { StateOutline } from "@makeplane/propel/icons";
import { useTranslation } from "@plane/i18n";
import { renderFormattedDate } from "@plane/utils";
// hooks
import { useIssueDetail } from "@/hooks/store/use-issue-detail";
// components
import { IssueActivityBlockComponent } from "./";

type TIssueSteeringActivity = { activityId: string; ends: "top" | "bottom" | undefined };

const CHOICE_PREFIXES: Record<string, string> = {
  status: "steering.task.status",
  waiting_for: "steering.task.waiting_for",
  risk_nature: "steering.task.risk",
};

/** "set Status to In progress" / "cleared Supervisor": the steering field key is stored in the activity comment. */
export const IssueSteeringActivity = observer(function IssueSteeringActivity(props: TIssueSteeringActivity) {
  const { activityId, ends } = props;
  const { t } = useTranslation();
  const {
    activity: { getActivityById },
  } = useIssueDetail();

  const activity = getActivityById(activityId);
  if (!activity) return <></>;

  const key = activity.comment ?? "";
  const field = t(`steering.task.fields.${key.replace(/_id$/, "")}`);
  const raw = activity.new_value;
  let value = raw ?? "";
  if (raw && CHOICE_PREFIXES[key]) value = t(`${CHOICE_PREFIXES[key]}.${raw}`);
  else if (raw && key === "progress") value = `${raw} %`;
  else if (raw && (key === "risk_effective_date" || key === "closure_date")) value = renderFormattedDate(raw) ?? raw;

  return (
    <IssueActivityBlockComponent
      icon={<StateOutline className="h-3.5 w-3.5 text-secondary" aria-hidden="true" />}
      activityId={activityId}
      ends={ends}
    >
      <>{raw ? t("steering.task.activity.set", { field, value }) : t("steering.task.activity.cleared", { field })}</>
    </IssueActivityBlockComponent>
  );
});

type TSteeringEvent = { event?: string; text?: string; role?: string; reason?: string };

const readEvent = (comment: string | undefined): TSteeringEvent => {
  try {
    return JSON.parse(comment ?? "{}") as TSteeringEvent;
  } catch {
    return {};
  }
};

/** A step of the CEO circuit or a reminder (§8, §9.1): the event and its comment travel as JSON. */
export const IssueSteeringEventActivity = observer(function IssueSteeringEventActivity(props: TIssueSteeringActivity) {
  const { activityId, ends } = props;
  const { t } = useTranslation();
  const {
    activity: { getActivityById },
  } = useIssueDetail();

  const activity = getActivityById(activityId);
  if (!activity) return <></>;

  const { event = "", text } = readEvent(activity.comment);
  const key = event === "reminded" && !activity.actor ? "reminded_auto" : event;
  // A postponement carries dates (§9.4), a requalification priorities.
  const show = (value: string | null | undefined) =>
    !value ? "" : event === "deadline_postponed" ? (renderFormattedDate(value) ?? value) : t(value);
  const sentence = t(`steering.history.${key}`, { old: show(activity.old_value), new: show(activity.new_value) });

  return (
    <IssueActivityBlockComponent
      icon={<StateOutline className="h-3.5 w-3.5 text-secondary" aria-hidden="true" />}
      activityId={activityId}
      ends={ends}
    >
      <>
        {sentence}
        {text && <span className="text-secondary">{` : « ${text} »`}</span>}
      </>
    </IssueActivityBlockComponent>
  );
});
