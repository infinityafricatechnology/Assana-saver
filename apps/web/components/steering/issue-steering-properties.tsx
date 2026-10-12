/**
 * Copyright (c) 2023-present Plane Software, Inc. and contributors
 * SPDX-License-Identifier: AGPL-3.0-only
 * See the LICENSE file for details.
 */

import { useEffect, useState } from "react";
import { observer } from "mobx-react";
import useSWR from "swr";
import {
  BuildingOutline,
  CalendarOutline,
  CheckDoneOutline,
  HourglassOutline,
  LayerStackOutline,
  MessageSupportOutline,
  PauseOutline,
  ShieldOutline,
  StateOutline,
  StickyNoteOutline,
  UserCircleOutline,
  WarningTriangleOutline,
} from "@makeplane/propel/icons";
import { DateSelect } from "@plane/blocks/property-select";
import { Select } from "@plane/blocks/select";
import { setToast } from "@plane/blocks/toast";
import { useTranslation } from "@plane/i18n";
import { cn, getDate, renderFormattedDate, renderFormattedPayloadDate } from "@plane/utils";
// components
import { SidebarPropertyListItem } from "@/components/common/layout/sidebar/property-list-item";
import { InlineInput, OptionDot } from "@/components/custom-fields/value-editor";
import { MemberSelect } from "@/components/dropdowns/member/member-select";
// hooks
import { useIssueDetail } from "@/hooks/store/use-issue-detail";
import { useSteering } from "@/hooks/store/use-steering";
// types
import type {
  TIssueSteering,
  TIssueSteeringPayload,
  TSteeringMissingField,
  TSteeringStatus,
} from "@/services/steering.service";
import { STEERING_RISK_NATURES, STEERING_STATUSES, STEERING_WAITING_FOR } from "@/services/steering.service";
// local imports
import { SteeringCircuitSummary } from "./circuit-summary";
import { SteeringStatusDialog } from "./status-dialog";

export const STEERING_STATUS_COLORS: Record<TSteeringStatus, string> = {
  to_start: "#9CA3AF",
  in_progress: "#3B82F6",
  in_validation: "#8B5CF6",
  waiting: "#F59E0B",
  done: "#16A34A",
  cancelled: "#EF4444",
};

type TChoice = { value: string; label: string; color?: string; group?: string };

type TChoiceSelectProps = {
  /** The property name, announced before the value and shown in the tooltip. */
  fieldLabel: string;
  options: TChoice[];
  value: string | null;
  placeholder: string;
  disabled?: boolean;
  /** Picking the selected option again clears it, unless the field cannot be empty. */
  clearable?: boolean;
  showSearch?: boolean;
  onChange: (value: string | null) => void;
};

/** A single choice in the sidebar, styled like the other work item properties. */
function ChoiceSelect(props: TChoiceSelectProps) {
  const { fieldLabel, options, value, placeholder, disabled, clearable = true, showSearch = false, onChange } = props;
  const selected = options.find((option) => option.value === value) ?? null;
  return (
    <Select<TChoice>
      getValues={() => options}
      value={selected}
      onChange={(next) => {
        if (next && next !== value) onChange(next);
        else if (!next && clearable) onChange(null);
      }}
      disabled={disabled}
      placeholder={placeholder}
      showSearch={showSearch}
      getOptionValue={(option) => option.value}
      getOptionLabel={(option) => option.label}
      getOptionGroup={(option) => option.group}
      getOptionIcon={(option) => (option.color ? <OptionDot color={option.color} /> : undefined)}
    >
      <Select.Trigger<TChoice>
        disabled={disabled}
        tooltip={{ heading: fieldLabel }}
        variant="select-ghost-md"
        prependIcon={(chosen) => (chosen[0]?.color ? <OptionDot color={chosen[0].color} /> : undefined)}
        label={(chosen) => chosen[0]?.label ?? placeholder}
      >
        {(chosen) => (
          <span className={cn("min-w-0 grow truncate text-left", { "text-placeholder": !chosen[0] })}>
            {chosen[0]?.label ?? placeholder}
          </span>
        )}
      </Select.Trigger>
    </Select>
  );
}

type TInlineTextAreaProps = {
  value: string;
  placeholder: string;
  ariaLabel: string;
  disabled?: boolean;
  onCommit: (value: string) => void;
};

/** Multi-line text saved when it loses focus; Escape restores the saved text. */
function InlineTextArea(props: TInlineTextAreaProps) {
  const { value, placeholder, ariaLabel, disabled, onCommit } = props;
  const [draft, setDraft] = useState(value);
  useEffect(() => setDraft(value), [value]);
  return (
    <textarea
      rows={2}
      value={draft}
      placeholder={placeholder}
      aria-label={ariaLabel}
      disabled={disabled}
      onChange={(event) => setDraft(event.target.value)}
      onBlur={() => draft.trim() !== value && onCommit(draft.trim())}
      onKeyDown={(event) => {
        if (event.key === "Escape") {
          setDraft(value);
          event.currentTarget.blur();
        }
      }}
      className="w-full min-w-0 resize-none rounded-sm bg-transparent px-2 py-1.5 text-body-xs-regular text-primary outline-none placeholder:text-placeholder hover:bg-layer-transparent-hover focus:bg-layer-transparent-hover disabled:cursor-not-allowed"
    />
  );
}

/**
 * Required §4 fields still missing. Assignee, priority and target date live on the work item and
 * change elsewhere in the sidebar, so they are read from it rather than from the steering record.
 */
function missingFields(
  steering: TIssueSteering,
  issue: { assignee_ids?: string[]; priority?: string | null; target_date?: string | null } | undefined
): TSteeringMissingField[] {
  const fromRecord = steering.missing.filter(
    (field) => field !== "assignee" && field !== "priority" && field !== "target_date"
  );
  const fromIssue: TSteeringMissingField[] = [];
  if (!issue?.assignee_ids?.length) fromIssue.push("assignee");
  if (!issue?.priority || issue.priority === "none") fromIssue.push("priority");
  if (!issue?.target_date) fromIssue.push("target_date");
  return [...fromRecord, ...fromIssue];
}

type TIssueSteeringPropertiesProps = {
  workspaceSlug: string;
  projectId: string;
  issueId: string;
  disabled?: boolean;
};

/** The « Pilotage » section of a work item: the fields the steering space reads (cahier des charges §4). */
export const IssueSteeringProperties = observer(function IssueSteeringProperties(props: TIssueSteeringPropertiesProps) {
  const { workspaceSlug, projectId, issueId, disabled } = props;
  const { t } = useTranslation();
  const steeringStore = useSteering();
  const {
    issue: { getIssueById },
    activity,
  } = useIssueDetail();
  const [dialogKind, setDialogKind] = useState<"waiting" | "done" | null>(null);

  useSWR(`STEERING_REFERENTIAL_${workspaceSlug}`, () => steeringStore.fetchReferential(workspaceSlug), {
    revalidateOnFocus: false,
  });
  useSWR(`ISSUE_STEERING_${issueId}`, () => steeringStore.fetchIssueSteering(workspaceSlug, projectId, issueId), {
    revalidateOnFocus: false,
  });

  const steering = steeringStore.issueSteeringMap[issueId];
  const referential = steeringStore.getReferential(workspaceSlug);
  if (!steering) return null;

  const empty = t("steering.task.empty");
  const isClosed = steering.status === "done" || steering.status === "cancelled";
  const missing = missingFields(steering, getIssueById(issueId));
  const projectEntity = steeringStore.getEntity(workspaceSlug, steering.project_entity_id);
  const branchName = (branchId: string) => referential?.branches.find((branch) => branch.id === branchId)?.name;

  const update = async (payload: TIssueSteeringPayload) => {
    try {
      await steeringStore.updateIssueSteering(workspaceSlug, projectId, issueId, payload);
      // A class method: keep it bound to its store.
      void activity.fetchActivities(workspaceSlug, projectId, issueId);
      return true;
    } catch {
      setToast({ type: "error", title: t("common.error.label"), message: t("steering.task.errors.save") });
      return false;
    }
  };

  const changeStatus = (next: TSteeringStatus) => {
    if (next === "waiting" && !steering.waiting_for) setDialogKind("waiting");
    else if (next === "done" && !(steering.closure_date && steering.closure_comment)) setDialogKind("done");
    else void update({ status: next });
  };

  const dateValue = (value: string | null) => (value ? (getDate(value) ?? null) : null);
  const datePayload = (date: Date | null) => (date ? (renderFormattedPayloadDate(date) ?? null) : null);

  return (
    <div className="mt-2 flex flex-col gap-2 border-t border-subtle pt-3">
      <div className="text-body-xs-medium text-secondary">{t("steering.task.section")}</div>
      {missing.length > 0 && (
        <p className="rounded-md bg-warning-subtle px-2 py-1.5 text-12 text-warning-primary">
          {t("steering.task.incomplete", {
            fields: missing.map((field) => t(`steering.task.fields.${field}`)).join(", "),
          })}
        </p>
      )}

      <SteeringCircuitSummary
        workspaceSlug={workspaceSlug}
        projectId={projectId}
        issueId={issueId}
        steering={steering}
        disabled={disabled}
      />

      <SidebarPropertyListItem icon={StateOutline} label={t("steering.task.fields.status")}>
        <ChoiceSelect
          fieldLabel={t("steering.task.fields.status")}
          options={STEERING_STATUSES.map((value) => ({
            value,
            label: t(`steering.task.status.${value}`),
            color: STEERING_STATUS_COLORS[value],
          }))}
          value={steering.status}
          placeholder={empty}
          clearable={false}
          disabled={disabled}
          onChange={(next) => next && changeStatus(next as TSteeringStatus)}
        />
      </SidebarPropertyListItem>

      <SidebarPropertyListItem icon={CheckDoneOutline} label={t("steering.task.fields.progress")}>
        <div className="flex w-full items-center">
          <InlineInput
            value={String(steering.progress)}
            placeholder="0"
            inputMode="decimal"
            ariaLabel={t("steering.task.fields.progress")}
            disabled={disabled || steering.status === "done"}
            onCommit={(next) => {
              const progress = Number(next || 0);
              if (Number.isInteger(progress) && progress >= 0 && progress <= 100) void update({ progress });
              else
                setToast({
                  type: "error",
                  title: t("common.error.label"),
                  message: t("steering.task.errors.progress"),
                });
            }}
          />
          <span className="pr-2 text-body-xs-regular text-tertiary">%</span>
        </div>
      </SidebarPropertyListItem>

      {steering.status === "waiting" && (
        <>
          <SidebarPropertyListItem icon={PauseOutline} label={t("steering.task.fields.waiting_for")}>
            <ChoiceSelect
              fieldLabel={t("steering.task.fields.waiting_for")}
              options={STEERING_WAITING_FOR.map((value) => ({ value, label: t(`steering.task.waiting_for.${value}`) }))}
              value={steering.waiting_for}
              placeholder={empty}
              clearable={false}
              disabled={disabled}
              onChange={(next) => next && void update({ waiting_for: next as TIssueSteering["waiting_for"] })}
            />
          </SidebarPropertyListItem>
          <SidebarPropertyListItem icon={HourglassOutline} label={t("steering.task.fields.waiting_since")}>
            <span className="flex h-7.5 items-center px-2 text-body-xs-regular text-primary">
              {steering.waiting_since ? renderFormattedDate(steering.waiting_since) : empty}
            </span>
          </SidebarPropertyListItem>
        </>
      )}

      <SidebarPropertyListItem icon={BuildingOutline} label={t("steering.task.fields.entity")}>
        <ChoiceSelect
          fieldLabel={t("steering.task.fields.entity")}
          options={(referential?.branches ?? []).flatMap((branch) =>
            steeringStore.getBranchEntities(workspaceSlug, branch.id).map((entity) => ({
              value: entity.id,
              label: entity.name,
              group: branchName(entity.branch_id),
            }))
          )}
          value={steering.entity_id}
          placeholder={projectEntity ? t("steering.task.project_entity", { name: projectEntity.name }) : empty}
          showSearch
          disabled={disabled}
          onChange={(next) => void update({ entity_id: next })}
        />
      </SidebarPropertyListItem>

      <SidebarPropertyListItem icon={LayerStackOutline} label={t("steering.task.fields.category")}>
        <ChoiceSelect
          fieldLabel={t("steering.task.fields.category")}
          options={(referential?.categories ?? []).map((category) => ({ value: category.id, label: category.name }))}
          value={steering.category_id}
          placeholder={empty}
          disabled={disabled}
          onChange={(next) => void update({ category_id: next })}
        />
      </SidebarPropertyListItem>

      <SidebarPropertyListItem icon={UserCircleOutline} label={t("steering.task.fields.supervisor")}>
        <MemberSelect
          tooltip={{ heading: t("steering.task.fields.supervisor") }}
          value={steering.supervisor_id}
          onChange={(userId) => void update({ supervisor_id: userId || null })}
          clearable
          disabled={disabled}
          placeholder={empty}
          variant="select-ghost-md"
        />
      </SidebarPropertyListItem>

      <SidebarPropertyListItem icon={ShieldOutline} label={t("steering.task.fields.approver")}>
        <MemberSelect
          tooltip={{ heading: t("steering.task.fields.approver") }}
          value={steering.approver_id}
          onChange={(userId) => void update({ approver_id: userId || null })}
          clearable
          disabled={disabled}
          placeholder={empty}
          variant="select-ghost-md"
        />
      </SidebarPropertyListItem>

      <SidebarPropertyListItem icon={WarningTriangleOutline} label={t("steering.task.risk_label")}>
        <ChoiceSelect
          fieldLabel={t("steering.task.fields.risk_nature")}
          options={STEERING_RISK_NATURES.map((value) => ({ value, label: t(`steering.task.risk.${value}`) }))}
          value={steering.risk_nature}
          placeholder={empty}
          disabled={disabled || isClosed}
          onChange={(next) => void update({ risk_nature: next as TIssueSteering["risk_nature"] })}
        />
      </SidebarPropertyListItem>
      {(steering.risk_nature || steering.risk_effective_date || steering.risk_description) && (
        <>
          <SidebarPropertyListItem icon={CalendarOutline} label={t("steering.task.fields.risk_effective_date")}>
            <DateSelect
              value={dateValue(steering.risk_effective_date)}
              onChange={(date) => void update({ risk_effective_date: datePayload(date) })}
              placeholder={empty}
              disabled={disabled || isClosed}
              clearable
              variant="select-ghost-md"
            />
          </SidebarPropertyListItem>
          <SidebarPropertyListItem icon={StickyNoteOutline} label={t("steering.task.fields.risk_description")}>
            <InlineTextArea
              value={steering.risk_description}
              placeholder={empty}
              ariaLabel={t("steering.task.fields.risk_description")}
              disabled={disabled || isClosed}
              onCommit={(risk_description) => void update({ risk_description })}
            />
          </SidebarPropertyListItem>
        </>
      )}

      {(steering.status === "done" || steering.closure_date || steering.closure_comment) && (
        <>
          <SidebarPropertyListItem icon={CalendarOutline} label={t("steering.task.fields.closure_date")}>
            <DateSelect
              value={dateValue(steering.closure_date)}
              onChange={(date) => void update({ closure_date: datePayload(date) })}
              placeholder={empty}
              maxDate={new Date()}
              disabled={disabled}
              variant="select-ghost-md"
            />
          </SidebarPropertyListItem>
          <SidebarPropertyListItem icon={MessageSupportOutline} label={t("steering.task.fields.closure_comment")}>
            <InlineTextArea
              value={steering.closure_comment}
              placeholder={empty}
              ariaLabel={t("steering.task.fields.closure_comment")}
              disabled={disabled}
              onCommit={(closure_comment) => void update({ closure_comment })}
            />
          </SidebarPropertyListItem>
        </>
      )}

      <SidebarPropertyListItem icon={MessageSupportOutline} label={t("steering.task.fields.situation")}>
        <div className="flex w-full flex-col">
          <InlineTextArea
            value={steering.situation}
            placeholder={t("steering.task.situation_placeholder")}
            ariaLabel={t("steering.task.fields.situation")}
            disabled={disabled}
            onCommit={(situation) => void update({ situation })}
          />
          {steering.situation_updated_at && (
            <span className="px-2 text-11 text-tertiary">
              {t("steering.task.situation_updated", { date: renderFormattedDate(steering.situation_updated_at) })}
            </span>
          )}
        </div>
      </SidebarPropertyListItem>

      <SteeringStatusDialog
        kind={dialogKind}
        onClose={() => setDialogKind(null)}
        onSubmit={async (payload) => {
          const saved = await update(payload);
          if (saved) setDialogKind(null);
          return saved;
        }}
      />
    </div>
  );
});
