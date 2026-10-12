/**
 * Copyright (c) 2023-present Plane Software, Inc. and contributors
 * SPDX-License-Identifier: AGPL-3.0-only
 * See the LICENSE file for details.
 */

import { action, makeObservable, observable, runInAction } from "mobx";
import { computedFn } from "mobx-utils";
// services
import type { TImportResult, TPerson, TPersonPayload, TPersonRole } from "@/services/people.service";
import { PeopleService } from "@/services/people.service";

export interface IPeopleStore {
  // observables
  peopleMap: Record<string, TPerson[]>;
  // computed functions
  getPeople: (workspaceSlug: string) => TPerson[] | undefined;
  // actions
  fetchPeople: (workspaceSlug: string) => Promise<TPerson[]>;
  createPerson: (workspaceSlug: string, data: TPersonPayload) => Promise<TPerson>;
  updatePerson: (workspaceSlug: string, userId: string, data: TPersonPayload) => Promise<TPerson>;
  addToProjects: (workspaceSlug: string, userIds: string[], projectIds: string[], role: TPersonRole) => Promise<number>;
  departurePreview: (workspaceSlug: string, userId: string) => Promise<number>;
  depart: (workspaceSlug: string, userId: string, reassignTo: string | null) => Promise<void>;
  reactivate: (workspaceSlug: string, userId: string, role: TPersonRole) => Promise<void>;
  importFile: (workspaceSlug: string, file: File, confirm: boolean, sendEmail: boolean) => Promise<TImportResult>;
  exportCsv: (workspaceSlug: string) => Promise<string>;
}

export class PeopleStore implements IPeopleStore {
  // observables
  peopleMap: Record<string, TPerson[]> = {};
  // services
  private service = new PeopleService();

  constructor() {
    makeObservable(this, {
      peopleMap: observable,
      fetchPeople: action,
      createPerson: action,
      updatePerson: action,
      addToProjects: action,
      depart: action,
      reactivate: action,
      importFile: action,
    });
  }

  getPeople = computedFn((workspaceSlug: string) => this.peopleMap[workspaceSlug]);

  /** Replace people by id, or add them at the end. */
  private upsert = (workspaceSlug: string, people: TPerson[]) => {
    const current = this.peopleMap[workspaceSlug] ?? [];
    const updated = new Map(people.map((person) => [person.id, person]));
    const merged = current.map((person) => updated.get(person.id) ?? person);
    const known = new Set(current.map((person) => person.id));
    runInAction(() => {
      this.peopleMap[workspaceSlug] = [...merged, ...people.filter((person) => !known.has(person.id))];
    });
  };

  fetchPeople = async (workspaceSlug: string) => {
    const people = await this.service.list(workspaceSlug);
    runInAction(() => {
      this.peopleMap[workspaceSlug] = people;
    });
    return people;
  };

  createPerson = async (workspaceSlug: string, data: TPersonPayload) => {
    const person = await this.service.create(workspaceSlug, data);
    this.upsert(workspaceSlug, [person]);
    return person;
  };

  updatePerson = async (workspaceSlug: string, userId: string, data: TPersonPayload) => {
    const person = await this.service.update(workspaceSlug, userId, data);
    this.upsert(workspaceSlug, [person]);
    return person;
  };

  addToProjects = async (workspaceSlug: string, userIds: string[], projectIds: string[], role: TPersonRole) => {
    const { added, people } = await this.service.addToProjects(workspaceSlug, {
      user_ids: userIds,
      project_ids: projectIds,
      role,
    });
    this.upsert(workspaceSlug, people);
    return added;
  };

  departurePreview = async (workspaceSlug: string, userId: string) =>
    (await this.service.departurePreview(workspaceSlug, userId)).open_work_items;

  depart = async (workspaceSlug: string, userId: string, reassignTo: string | null) => {
    const { person } = await this.service.depart(workspaceSlug, userId, reassignTo);
    this.upsert(workspaceSlug, [person]);
  };

  reactivate = async (workspaceSlug: string, userId: string, role: TPersonRole) => {
    const person = await this.service.reactivate(workspaceSlug, userId, role);
    this.upsert(workspaceSlug, [person]);
  };

  importFile = async (workspaceSlug: string, file: File, confirm: boolean, sendEmail: boolean) => {
    const result = await this.service.importFile(workspaceSlug, file, confirm, sendEmail);
    if (confirm && result.created > 0) await this.fetchPeople(workspaceSlug);
    return result;
  };

  exportCsv = (workspaceSlug: string) => this.service.exportCsv(workspaceSlug);
}
