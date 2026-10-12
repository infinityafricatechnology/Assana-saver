/**
 * Copyright (c) 2023-present Plane Software, Inc. and contributors
 * SPDX-License-Identifier: AGPL-3.0-only
 * See the LICENSE file for details.
 */

import { observer } from "mobx-react";
import useSWR from "swr";
import { BuildingOutline, LayerStackOutline } from "@makeplane/propel/icons";
import { useTranslation } from "@plane/i18n";
import { cn } from "@plane/utils";
// components
import { MemberSelect } from "@/components/dropdowns/member/member-select";
// hooks
import { useSteering } from "@/hooks/store/use-steering";
// types
import type { TSteeringMissingField } from "@/services/steering.service";
// local imports
import { ChoiceSelect } from "./choice-select";

/** What the create form sends as « steering » for a work item of a steered project. */
export type TSteeringDraft = {
  category_id: string | null;
  supervisor_id: string | null;
  approver_id: string | null;
  /** null: carried by the project's entity. */
  entity_id: string | null;
};

export const EMPTY_STEERING_DRAFT: TSteeringDraft = {
  category_id: null,
  supervisor_id: null,
  approver_id: null,
  entity_id: null,
};

/** Whether the project is carried by an entity, i.e. steered; undefined while it loads. */
export const useIsSteeredProject = (workspaceSlug: string, projectId: string | null | undefined) => {
  const steeringStore = useSteering();
  useSWR(
    workspaceSlug && projectId ? `PROJECT_STEERING_${projectId}` : null,
    () => steeringStore.fetchProjectEntity(workspaceSlug, projectId!),
    { revalidateOnFocus: false }
  );
  if (!projectId) return false;
  const entityId = steeringStore.projectEntityMap[projectId];
  return entityId === undefined ? undefined : !!entityId;
};

/** The §4 fields a new work item of a steered project still lacks, in the order of the form. */
export const missingSteeringFields = (
  values: { assignee_ids?: string[] | null; target_date?: string | null },
  draft: TSteeringDraft,
  hasDefaultAssignee = false
): TSteeringMissingField[] => {
  const missing: TSteeringMissingField[] = [];
  if (!values.assignee_ids?.length && !hasDefaultAssignee) missing.push("assignee");
  if (!values.target_date) missing.push("target_date");
  if (!draft.category_id) missing.push("category");
  if (!draft.supervisor_id) missing.push("supervisor");
  if (!draft.approver_id) missing.push("approver");
  return missing;
};

type TSteeringCreateFieldsProps = {
  workspaceSlug: string;
  projectId: string;
  value: TSteeringDraft;
  /** Fields to point out after a refused save. */
  missing: TSteeringMissingField[];
  onChange: (value: TSteeringDraft) => void;
};

/** The « Pilotage » fields of the create form, shown for a steered project only (cahier des charges §4). */
export const SteeringCreateFields = observer(function SteeringCreateFields(props: TSteeringCreateFieldsProps) {
  const { workspaceSlug, projectId, value, missing, onChange } = props;
  const { t } = useTranslation();
  const steeringStore = useSteering();

  useSWR(`STEERING_REFERENTIAL_${workspaceSlug}`, () => steeringStore.fetchReferential(workspaceSlug), {
    revalidateOnFocus: false,
  });

  const referential = steeringStore.getReferential(workspaceSlug);
  const projectEntity = steeringStore.getEntity(workspaceSlug, steeringStore.projectEntityMap[projectId]);
  const branchName = (branchId: string) => referential?.branches.find((branch) => branch.id === branchId)?.name;
  const set = (patch: Partial<TSteeringDraft>) => onChange({ ...value, ...patch });
  const required = (field: TSteeringMissingField) =>
    cn("rounded-md", { "ring-1 ring-danger-strong": missing.includes(field) });

  return (
    <div className="mt-3 flex flex-col gap-2 border-t border-subtle pt-3">
      <div className="flex items-baseline gap-2">
        <span className="text-body-xs-medium text-secondary">{t("steering.task.section")}</span>
        <span className="text-11 text-tertiary">{t("steering.create.hint")}</span>
      </div>
      <div className="flex flex-wrap items-center gap-2">
        <div className={required("category")}>
          <ChoiceSelect
            fieldLabel={t("steering.task.fields.category")}
            options={(referential?.categories ?? []).map((category) => ({ value: category.id, label: category.name }))}
            value={value.category_id}
            placeholder={t("steering.task.fields.category")}
            icon={<LayerStackOutline />}
            variant="pill-md"
            onChange={(next) => set({ category_id: next })}
          />
        </div>
        <div className={required("supervisor")}>
          <MemberSelect
            tooltip={{ heading: t("steering.task.fields.supervisor") }}
            value={value.supervisor_id}
            onChange={(userId) => set({ supervisor_id: userId || null })}
            clearable
            placeholder={t("steering.task.fields.supervisor")}
            variant="pill-md"
          />
        </div>
        <div className={required("approver")}>
          <MemberSelect
            tooltip={{ heading: t("steering.task.fields.approver") }}
            value={value.approver_id}
            onChange={(userId) => set({ approver_id: userId || null })}
            clearable
            placeholder={t("steering.task.fields.approver")}
            variant="pill-md"
          />
        </div>
        <ChoiceSelect
          fieldLabel={t("steering.task.fields.entity")}
          options={(referential?.branches ?? []).flatMap((branch) =>
            steeringStore.getBranchEntities(workspaceSlug, branch.id).map((entity) => ({
              value: entity.id,
              label: entity.name,
              group: branchName(entity.branch_id),
            }))
          )}
          value={value.entity_id}
          placeholder={
            projectEntity
              ? t("steering.task.project_entity", { name: projectEntity.name })
              : t("steering.task.fields.entity")
          }
          icon={<BuildingOutline />}
          showSearch
          variant="pill-md"
          onChange={(next) => set({ entity_id: next })}
        />
      </div>
    </div>
  );
});
