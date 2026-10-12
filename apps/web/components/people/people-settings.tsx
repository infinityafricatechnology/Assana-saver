/**
 * Copyright (c) 2023-present Plane Software, Inc. and contributors
 * SPDX-License-Identifier: AGPL-3.0-only
 * See the LICENSE file for details.
 */

import { useMemo, useState } from "react";
import { observer } from "mobx-react";
import useSWR from "swr";
import { Badge } from "@makeplane/propel/components/badge";
import { Button } from "@makeplane/propel/components/button";
import { Checkbox } from "@makeplane/propel/components/checkbox";
import { Icon } from "@makeplane/propel/components/icon";
import { IconButton } from "@makeplane/propel/components/icon-button";
import { Input, InputGroup } from "@makeplane/propel/components/input";
import { Menu, MenuContent, MenuItem, MenuTrigger } from "@makeplane/propel/components/menu";
import { AddOutline, MoreHorizontalOutline } from "@makeplane/propel/icons";
import { setToast } from "@plane/blocks/toast";
import { useTranslation } from "@plane/i18n";
import { renderFormattedDate } from "@plane/utils";
// components
import { SteeringSelect } from "@/components/steering/select";
// hooks
import { usePeople } from "@/hooks/store/use-people";
import { useProject } from "@/hooks/store/use-project";
import { useSteering } from "@/hooks/store/use-steering";
import { useUser } from "@/hooks/store/user";
// types
import type { TPerson, TPersonStatus } from "@/services/people.service";
// local imports
import { PersonDepartureDialog } from "./departure-dialog";
import { PeopleImportDialog, downloadText } from "./import-dialog";
import { PersonDialog } from "./person-dialog";
import { PeopleProjectsDialog } from "./projects-dialog";
import {
  PERSON_STATUS_VARIANTS,
  PersonAvatar,
  RoleSelect,
  fullName,
  usePeopleErrorMessage,
  useProfileLabel,
} from "./shared";

type TStatusFilter = "all" | TPersonStatus;

export const PeopleSettings = observer(function PeopleSettings(props: { workspaceSlug: string }) {
  const { workspaceSlug } = props;
  const { t } = useTranslation();
  const store = usePeople();
  const steering = useSteering();
  const { fetchProjects } = useProject();
  const { data: currentUser } = useUser();
  const profileLabel = useProfileLabel(workspaceSlug);
  const errorMessage = usePeopleErrorMessage();
  // states
  const [search, setSearch] = useState("");
  const [statusFilter, setStatusFilter] = useState<TStatusFilter>("all");
  const [selectedIds, setSelectedIds] = useState<string[]>([]);
  const [dialog, setDialog] = useState<"add" | "import" | null>(null);
  const [editing, setEditing] = useState<TPerson | undefined>(undefined);
  const [projectsFor, setProjectsFor] = useState<TPerson[]>([]);
  const [leaving, setLeaving] = useState<TPerson | undefined>(undefined);

  useSWR(`PEOPLE_${workspaceSlug}`, () => store.fetchPeople(workspaceSlug), { revalidateOnFocus: false });
  useSWR(`STEERING_REFERENTIAL_${workspaceSlug}`, () => steering.fetchReferential(workspaceSlug), {
    revalidateOnFocus: false,
  });
  useSWR(`PEOPLE_PROJECTS_${workspaceSlug}`, () => fetchProjects(workspaceSlug), { revalidateOnFocus: false });

  const people = store.getPeople(workspaceSlug);
  const visible = useMemo(() => {
    const query = search.trim().toLowerCase();
    return (people ?? []).filter(
      (person) =>
        (statusFilter === "all" || person.status === statusFilter) &&
        (!query || `${fullName(person)} ${person.email}`.toLowerCase().includes(query))
    );
  }, [people, search, statusFilter]);

  if (!people) return <div className="text-13 text-tertiary">{t("common.loading")}</div>;

  const counts: Record<TPersonStatus, number> = { active: 0, pending: 0, departed: 0 };
  for (const person of people) counts[person.status] += 1;
  const selectable = visible.filter((person) => person.status !== "departed");
  const allSelected = selectable.length > 0 && selectable.every((person) => selectedIds.includes(person.id));
  const toggle = (personId: string) =>
    setSelectedIds((ids) => (ids.includes(personId) ? ids.filter((id) => id !== personId) : [...ids, personId]));

  const changeRole = async (person: TPerson, role: TPerson["role"]) => {
    try {
      await store.updatePerson(workspaceSlug, person.id, { role });
    } catch (error) {
      setToast({ type: "error", title: t("common.error.label"), message: errorMessage(error) });
    }
  };

  const reactivate = async (person: TPerson) => {
    try {
      await store.reactivate(workspaceSlug, person.id, 15);
      setToast({ type: "success", title: t("common.success"), message: t("people.toasts.reactivated") });
    } catch (error) {
      setToast({ type: "error", title: t("common.error.label"), message: errorMessage(error) });
    }
  };

  const exportList = async () => {
    try {
      downloadText(`personnes-${workspaceSlug}.csv`, await store.exportCsv(workspaceSlug));
    } catch (error) {
      setToast({ type: "error", title: t("common.error.label"), message: errorMessage(error) });
    }
  };

  const statusOptions: { value: TStatusFilter; label: string }[] = [
    { value: "all", label: t("people.filters.all", { count: people.length }) },
    { value: "active", label: t("people.filters.active", { count: counts.active }) },
    { value: "pending", label: t("people.filters.pending", { count: counts.pending }) },
    { value: "departed", label: t("people.filters.departed", { count: counts.departed }) },
  ];

  return (
    <div className="flex flex-col gap-4">
      <div className="flex flex-wrap items-center gap-2">
        <div className="w-64">
          <InputGroup size="md">
            <Input
              size="md"
              value={search}
              placeholder={t("people.search")}
              aria-label={t("people.search")}
              onChange={(event) => setSearch(event.target.value)}
            />
          </InputGroup>
        </div>
        <div className="w-56">
          <SteeringSelect<TStatusFilter>
            value={statusFilter}
            options={statusOptions}
            ariaLabel={t("people.filters.label")}
            onChange={setStatusFilter}
          />
        </div>
        <div className="ml-auto flex items-center gap-2">
          {selectedIds.length > 0 && (
            <Button
              variant="secondary"
              size="md"
              stretch="auto"
              label={t("people.add_to_projects_selected", { count: selectedIds.length })}
              onClick={() => setProjectsFor(people.filter((person) => selectedIds.includes(person.id)))}
            />
          )}
          <Button variant="secondary" size="md" stretch="auto" label={t("people.export")} onClick={exportList} />
          <Button
            variant="secondary"
            size="md"
            stretch="auto"
            label={t("people.import.button")}
            onClick={() => setDialog("import")}
          />
          <Button
            variant="primary"
            size="md"
            stretch="auto"
            icon={<Icon icon={AddOutline} />}
            label={t("people.add")}
            onClick={() => setDialog("add")}
          />
        </div>
      </div>

      <div className="overflow-x-auto rounded-md border border-subtle">
        <table className="w-full min-w-[60rem] table-fixed text-left text-13">
          <thead className="bg-layer-1 text-12 text-tertiary">
            <tr>
              <th className="w-11 px-3 py-2">
                <Checkbox
                  checked={allSelected}
                  aria-label={t("people.select_all")}
                  onCheckedChange={(checked) => setSelectedIds(checked ? selectable.map((person) => person.id) : [])}
                />
              </th>
              <th className="w-[24%] px-3 py-2 font-medium">{t("people.fields.name")}</th>
              <th className="w-40 px-3 py-2 font-medium">{t("people.fields.role")}</th>
              <th className="px-3 py-2 font-medium">{t("steering.profiles.title")}</th>
              <th className="w-24 px-3 py-2 font-medium">{t("people.fields.projects")}</th>
              <th className="w-36 px-3 py-2 font-medium">{t("people.fields.status")}</th>
              <th className="w-32 px-3 py-2 font-medium">{t("people.fields.last_login")}</th>
              <th className="w-14 px-3 py-2" />
            </tr>
          </thead>
          <tbody>
            {visible.length === 0 && (
              <tr>
                <td colSpan={8} className="px-3 py-8 text-center text-tertiary">
                  {t("people.empty")}
                </td>
              </tr>
            )}
            {visible.map((person) => {
              const isDeparted = person.status === "departed";
              const isMe = person.id === currentUser?.id;
              return (
                <tr key={person.id} className="border-t border-subtle align-middle">
                  <td className="px-3 py-2">
                    {!isDeparted && (
                      <Checkbox
                        checked={selectedIds.includes(person.id)}
                        aria-label={fullName(person)}
                        onCheckedChange={() => toggle(person.id)}
                      />
                    )}
                  </td>
                  <td className="px-3 py-2">
                    <div className="flex items-center gap-2">
                      <PersonAvatar person={person} />
                      <div className="flex min-w-0 flex-col">
                        <span className="truncate font-medium text-primary">{fullName(person)}</span>
                        <span className="truncate text-12 text-tertiary">{person.email}</span>
                      </div>
                    </div>
                  </td>
                  <td className="px-3 py-2">
                    <RoleSelect
                      value={person.role}
                      disabled={isDeparted || isMe}
                      onChange={(role) => void changeRole(person, role)}
                    />
                  </td>
                  <td className="px-3 py-2">
                    <div className="flex flex-col gap-0.5 text-12">
                      {person.profiles.length === 0 && <span className="text-tertiary">—</span>}
                      {person.profiles.map((profile) => (
                        <span key={profile.id} className="text-primary">
                          {profileLabel(profile)}
                        </span>
                      ))}
                    </div>
                  </td>
                  <td className="px-3 py-2 whitespace-nowrap text-secondary">
                    {t("people.project_count", { count: person.projects.length })}
                  </td>
                  <td className="px-3 py-2">
                    <Badge
                      variant={PERSON_STATUS_VARIANTS[person.status]}
                      size="sm"
                      label={t(`people.status.${person.status}`)}
                    />
                  </td>
                  <td className="px-3 py-2 whitespace-nowrap text-secondary">
                    {person.last_login_time ? renderFormattedDate(person.last_login_time) : "—"}
                  </td>
                  <td className="px-3 py-2">
                    <Menu>
                      <MenuTrigger
                        render={
                          <IconButton
                            variant="ghost"
                            size="sm"
                            icon={<Icon icon={MoreHorizontalOutline} />}
                            aria-label={`${t("people.actions")} ${fullName(person)}`}
                          />
                        }
                      />
                      <MenuContent side="bottom" align="end">
                        {isDeparted ? (
                          <MenuItem label={t("people.reactivate")} onClick={() => void reactivate(person)} />
                        ) : (
                          <>
                            <MenuItem label={t("people.edit")} onClick={() => setEditing(person)} />
                            <MenuItem label={t("people.add_to_projects")} onClick={() => setProjectsFor([person])} />
                            {!isMe && (
                              <MenuItem label={t("people.departure.action")} onClick={() => setLeaving(person)} />
                            )}
                          </>
                        )}
                      </MenuContent>
                    </Menu>
                  </td>
                </tr>
              );
            })}
          </tbody>
        </table>
      </div>

      <PersonDialog workspaceSlug={workspaceSlug} isOpen={dialog === "add"} onClose={() => setDialog(null)} />
      <PersonDialog
        workspaceSlug={workspaceSlug}
        isOpen={!!editing}
        person={editing}
        onClose={() => setEditing(undefined)}
      />
      <PeopleImportDialog workspaceSlug={workspaceSlug} isOpen={dialog === "import"} onClose={() => setDialog(null)} />
      <PeopleProjectsDialog
        workspaceSlug={workspaceSlug}
        people={projectsFor}
        onClose={(added) => {
          setProjectsFor([]);
          if (added) setSelectedIds([]);
        }}
      />
      <PersonDepartureDialog workspaceSlug={workspaceSlug} person={leaving} onClose={() => setLeaving(undefined)} />
    </div>
  );
});
