/**
 * Copyright (c) 2023-present Plane Software, Inc. and contributors
 * SPDX-License-Identifier: AGPL-3.0-only
 * See the LICENSE file for details.
 */

import { observer } from "mobx-react";
import { Button } from "@makeplane/propel/components/button";
import { Icon } from "@makeplane/propel/components/icon";
import { IconButton } from "@makeplane/propel/components/icon-button";
import { AddOutline, CloseOutline } from "@makeplane/propel/icons";
import { Select } from "@plane/blocks/select";
import { useTranslation } from "@plane/i18n";
import { cn } from "@plane/utils";
// components
import { SteeringSelect } from "@/components/steering/select";
// hooks
import { useProject } from "@/hooks/store/use-project";
import { useSteering } from "@/hooks/store/use-steering";
// types
import type { TPerson, TPersonProfileInput, TPersonRole, TPersonStatus } from "@/services/people.service";
import type { TSteeringProfile, TSteeringProfileRole } from "@/services/steering.service";
import { STEERING_PROFILE_ROLES } from "@/services/steering.service";

export const PERSON_STATUS_VARIANTS: Record<TPersonStatus, "success" | "warning" | "neutral"> = {
  active: "success",
  pending: "warning",
  departed: "neutral",
};

export const fullName = (person: Pick<TPerson, "first_name" | "last_name" | "display_name" | "email">) =>
  [person.first_name, person.last_name].filter(Boolean).join(" ") || person.display_name || person.email;

/** The API refuses with `{ code }`; the matching message, or the generic one. */
export const usePeopleErrorMessage = () => {
  const { t } = useTranslation();
  return (error: unknown) => {
    const code = typeof error === "object" && error !== null && "code" in error ? String(error.code) : "";
    const key = `people.errors.${code}`;
    const message = code ? t(key) : "";
    return message && message !== key ? message : t("people.errors.generic");
  };
};

/** « Responsable d'entité · SCI Infinity » */
export const useProfileLabel = (workspaceSlug: string) => {
  const { t } = useTranslation();
  const steering = useSteering();
  return (profile: Pick<TSteeringProfile, "role" | "branch_id" | "entity_id">) => {
    const role = t(`steering.profiles.roles.${profile.role}`);
    const referential = steering.getReferential(workspaceSlug);
    const scope = profile.branch_id
      ? referential?.branches.find((branch) => branch.id === profile.branch_id)?.name
      : profile.entity_id
        ? steering.getEntity(workspaceSlug, profile.entity_id)?.name
        : undefined;
    return scope ? `${role} · ${scope}` : role;
  };
};

export function PersonAvatar(props: { person: TPerson }) {
  const { person } = props;
  const initials = (person.first_name?.[0] ?? person.email[0] ?? "?").toUpperCase();
  if (person.avatar_url)
    return <img src={person.avatar_url} alt="" className="size-7 shrink-0 rounded-full object-cover" />;
  return (
    <span className="flex size-7 shrink-0 items-center justify-center rounded-full bg-layer-3 text-12 font-medium text-secondary">
      {initials}
    </span>
  );
}

type TRoleOption = { value: TPersonRole; label: string };

/** Admin or member, in a compact select that fits a table cell. */
export function RoleSelect(props: { value: TPersonRole; onChange: (role: TPersonRole) => void; disabled?: boolean }) {
  const { t } = useTranslation();
  const options: TRoleOption[] = [
    { value: 20, label: t("people.roles.admin") },
    { value: 15, label: t("people.roles.member") },
  ];
  const selected = options.find((option) => option.value === props.value) ?? null;
  return (
    <Select<TRoleOption>
      getValues={() => options}
      value={selected}
      onChange={(next) => next && Number(next) !== props.value && props.onChange(Number(next) as TPersonRole)}
      disabled={props.disabled}
      placeholder={t("people.fields.role")}
      getOptionValue={(option) => String(option.value)}
      getOptionLabel={(option) => option.label}
    >
      <Select.Trigger<TRoleOption>
        disabled={props.disabled}
        tooltip={{ heading: t("people.fields.role") }}
        variant="select-ghost-md"
        label={(chosen) => chosen[0]?.label ?? ""}
      >
        {(chosen) => <span className="min-w-0 grow truncate text-left">{chosen[0]?.label}</span>}
      </Select.Trigger>
    </Select>
  );
}

type TProjectOption = { id: string; label: string };

/** Several projects of the organisation, archived ones left out. */
export const ProjectsSelect = observer(function ProjectsSelect(props: {
  value: string[];
  onChange: (projectIds: string[]) => void;
}) {
  const { t } = useTranslation();
  const { workspaceProjectIds, getProjectById } = useProject();
  const options: TProjectOption[] = (workspaceProjectIds ?? [])
    .map((id) => getProjectById(id))
    .filter((project) => project && !project.archived_at)
    .map((project) => ({ id: project!.id, label: `${project!.name} (${project!.identifier})` }));
  const selected = options.filter((option) => props.value.includes(option.id));
  const placeholder = t("people.fields.projects_placeholder");

  return (
    <Select<TProjectOption>
      multiple
      getValues={() => options}
      value={selected}
      onChange={(ids) => props.onChange(ids)}
      placeholder={placeholder}
      showSearch
      getOptionValue={(option) => option.id}
      getOptionLabel={(option) => option.label}
    >
      <Select.Trigger<TProjectOption>
        variant="select-md"
        label={(chosen) => chosen.map((option) => option.label).join(", ") || placeholder}
      >
        {(chosen) => (
          <span className={cn("min-w-0 grow truncate text-left", { "text-placeholder": chosen.length === 0 })}>
            {chosen.length ? chosen.map((option) => option.label).join(", ") : placeholder}
          </span>
        )}
      </Select.Trigger>
    </Select>
  );
});

/** The steering profiles of a person: a profile, and its branch or entity when it needs one. */
export const ProfilesEditor = observer(function ProfilesEditor(props: {
  workspaceSlug: string;
  value: TPersonProfileInput[];
  onChange: (profiles: TPersonProfileInput[]) => void;
}) {
  const { workspaceSlug, value, onChange } = props;
  const { t } = useTranslation();
  const steering = useSteering();
  const referential = steering.getReferential(workspaceSlug);

  const update = (index: number, next: TPersonProfileInput) =>
    onChange(value.map((profile, position) => (position === index ? next : profile)));

  return (
    <div className="flex flex-col gap-2">
      {value.map((profile, index) => {
        const scopeOptions =
          profile.role === "branch_director"
            ? (referential?.branches ?? []).map((branch) => ({ value: branch.id, label: branch.name }))
            : profile.role === "entity_manager"
              ? (referential?.entities ?? []).map((entity) => ({ value: entity.id, label: entity.name }))
              : [];
        return (
          // oxlint-disable-next-line react/no-array-index-key -- rows have no id until saved
          <div key={index} className="flex items-center gap-2">
            <div className="w-48 shrink-0">
              <SteeringSelect<TSteeringProfileRole>
                value={profile.role}
                options={STEERING_PROFILE_ROLES.map((role) => ({
                  value: role,
                  label: t(`steering.profiles.roles.${role}`),
                }))}
                ariaLabel={t("steering.profiles.role")}
                onChange={(role) => update(index, { role })}
              />
            </div>
            {scopeOptions.length > 0 && (
              <div className="min-w-0 grow">
                <SteeringSelect<string>
                  value={(profile.role === "branch_director" ? profile.branch_id : profile.entity_id) ?? null}
                  options={scopeOptions}
                  placeholder={t("steering.profiles.scope")}
                  ariaLabel={t("steering.profiles.scope")}
                  onChange={(scope) =>
                    update(
                      index,
                      profile.role === "branch_director"
                        ? { role: profile.role, branch_id: scope }
                        : { role: profile.role, entity_id: scope }
                    )
                  }
                />
              </div>
            )}
            <IconButton
              variant="ghost"
              size="sm"
              icon={<Icon icon={CloseOutline} />}
              aria-label={t("common.remove")}
              onClick={() => onChange(value.filter((_, position) => position !== index))}
            />
          </div>
        );
      })}
      <div>
        <Button
          variant="ghost"
          size="sm"
          stretch="auto"
          icon={<Icon icon={AddOutline} />}
          label={t("steering.profiles.add")}
          onClick={() => onChange([...value, { role: "cabinet" }])}
        />
      </div>
    </div>
  );
});
