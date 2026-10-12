/**
 * Copyright (c) 2023-present Plane Software, Inc. and contributors
 * SPDX-License-Identifier: AGPL-3.0-only
 * See the LICENSE file for details.
 */

import { sortBy } from "lodash-es";
import { action, makeObservable, observable, runInAction } from "mobx";
import { computedFn } from "mobx-utils";
// services
import type {
  TIssueSteering,
  TIssueSteeringPayload,
  TSteeringCircuit,
  TSubmissionPayload,
  TSteeringBranch,
  TSteeringEntity,
  TSteeringProfile,
  TSteeringProfilePayload,
  TSteeringReferential,
} from "@/services/steering.service";
import { SteeringService } from "@/services/steering.service";

const bySortOrder = <T extends { sort_order: number; name: string }>(items: T[]) =>
  sortBy(items, ["sort_order", "name"]);

export interface ISteeringStore {
  // observables
  referentialMap: Record<string, TSteeringReferential>;
  profileMap: Record<string, TSteeringProfile[]>;
  projectEntityMap: Record<string, string | null>;
  issueSteeringMap: Record<string, TIssueSteering>;
  // computed functions
  getReferential: (workspaceSlug: string) => TSteeringReferential | undefined;
  getBranchEntities: (workspaceSlug: string, branchId: string) => TSteeringEntity[];
  getEntity: (workspaceSlug: string, entityId: string | null | undefined) => TSteeringEntity | undefined;
  // actions
  fetchReferential: (workspaceSlug: string) => Promise<TSteeringReferential>;
  bootstrap: (workspaceSlug: string) => Promise<void>;
  createBranch: (workspaceSlug: string, name: string) => Promise<void>;
  updateBranch: (workspaceSlug: string, branchId: string, data: Partial<TSteeringBranch>) => Promise<void>;
  deleteBranch: (workspaceSlug: string, branchId: string) => Promise<void>;
  createEntity: (workspaceSlug: string, branchId: string, name: string) => Promise<void>;
  updateEntity: (workspaceSlug: string, entityId: string, data: Partial<TSteeringEntity>) => Promise<void>;
  deleteEntity: (workspaceSlug: string, entityId: string) => Promise<void>;
  createCategory: (workspaceSlug: string, name: string) => Promise<void>;
  updateCategory: (workspaceSlug: string, categoryId: string, name: string) => Promise<void>;
  deleteCategory: (workspaceSlug: string, categoryId: string) => Promise<void>;
  fetchProfiles: (workspaceSlug: string) => Promise<TSteeringProfile[]>;
  createProfile: (workspaceSlug: string, data: TSteeringProfilePayload) => Promise<void>;
  deleteProfile: (workspaceSlug: string, profileId: string) => Promise<void>;
  fetchProjectEntity: (workspaceSlug: string, projectId: string) => Promise<string | null>;
  setProjectEntity: (workspaceSlug: string, projectId: string, entityId: string) => Promise<void>;
  fetchIssueSteering: (workspaceSlug: string, projectId: string, issueId: string) => Promise<TIssueSteering>;
  updateIssueSteering: (
    workspaceSlug: string,
    projectId: string,
    issueId: string,
    data: TIssueSteeringPayload
  ) => Promise<TIssueSteering>;
  submitToCeo: (workspaceSlug: string, projectId: string, issueId: string, data: TSubmissionPayload) => Promise<void>;
  setCircuit: (issueId: string, circuit: TSteeringCircuit) => void;
}

export class SteeringStore implements ISteeringStore {
  // observables
  referentialMap: Record<string, TSteeringReferential> = {};
  profileMap: Record<string, TSteeringProfile[]> = {};
  projectEntityMap: Record<string, string | null> = {};
  issueSteeringMap: Record<string, TIssueSteering> = {};
  // services
  private service = new SteeringService();

  constructor() {
    makeObservable(this, {
      referentialMap: observable,
      profileMap: observable,
      projectEntityMap: observable,
      issueSteeringMap: observable,
      fetchReferential: action,
      bootstrap: action,
      createBranch: action,
      updateBranch: action,
      deleteBranch: action,
      createEntity: action,
      updateEntity: action,
      deleteEntity: action,
      createCategory: action,
      updateCategory: action,
      deleteCategory: action,
      fetchProfiles: action,
      createProfile: action,
      deleteProfile: action,
      fetchProjectEntity: action,
      setProjectEntity: action,
      fetchIssueSteering: action,
      updateIssueSteering: action,
      submitToCeo: action,
      setCircuit: action,
    });
  }

  getReferential = computedFn((workspaceSlug: string) => this.referentialMap[workspaceSlug]);

  getBranchEntities = computedFn((workspaceSlug: string, branchId: string) =>
    bySortOrder((this.referentialMap[workspaceSlug]?.entities ?? []).filter((entity) => entity.branch_id === branchId))
  );

  getEntity = computedFn((workspaceSlug: string, entityId: string | null | undefined) =>
    entityId ? this.referentialMap[workspaceSlug]?.entities.find((entity) => entity.id === entityId) : undefined
  );

  /** Applies a change to a loaded referential; mutations always follow a fetch. */
  private update = (workspaceSlug: string, change: (referential: TSteeringReferential) => void) => {
    const referential = this.referentialMap[workspaceSlug];
    if (referential) runInAction(() => change(referential));
  };

  fetchReferential = async (workspaceSlug: string) => {
    const referential = await this.service.getReferential(workspaceSlug);
    runInAction(() => {
      this.referentialMap[workspaceSlug] = referential;
    });
    return referential;
  };

  bootstrap = async (workspaceSlug: string) => {
    const referential = await this.service.bootstrap(workspaceSlug);
    runInAction(() => {
      this.referentialMap[workspaceSlug] = referential;
    });
  };

  createBranch = async (workspaceSlug: string, name: string) => {
    const branch = await this.service.createBranch(workspaceSlug, name);
    this.update(workspaceSlug, (referential) => {
      referential.branches = bySortOrder([...referential.branches, branch]);
    });
  };

  updateBranch = async (workspaceSlug: string, branchId: string, data: Partial<TSteeringBranch>) => {
    const branch = await this.service.updateBranch(workspaceSlug, branchId, data);
    this.update(workspaceSlug, (referential) => {
      referential.branches = bySortOrder(referential.branches.map((item) => (item.id === branchId ? branch : item)));
    });
  };

  deleteBranch = async (workspaceSlug: string, branchId: string) => {
    await this.service.deleteBranch(workspaceSlug, branchId);
    this.update(workspaceSlug, (referential) => {
      referential.branches = referential.branches.filter((branch) => branch.id !== branchId);
    });
  };

  createEntity = async (workspaceSlug: string, branchId: string, name: string) => {
    const entity = await this.service.createEntity(workspaceSlug, { name, branch_id: branchId });
    this.update(workspaceSlug, (referential) => {
      referential.entities = [...referential.entities, entity];
    });
  };

  updateEntity = async (workspaceSlug: string, entityId: string, data: Partial<TSteeringEntity>) => {
    const entity = await this.service.updateEntity(workspaceSlug, entityId, data);
    this.update(workspaceSlug, (referential) => {
      referential.entities = referential.entities.map((item) => (item.id === entityId ? entity : item));
    });
  };

  deleteEntity = async (workspaceSlug: string, entityId: string) => {
    await this.service.deleteEntity(workspaceSlug, entityId);
    this.update(workspaceSlug, (referential) => {
      referential.entities = referential.entities.filter((entity) => entity.id !== entityId);
    });
    runInAction(() => {
      if (this.profileMap[workspaceSlug])
        this.profileMap[workspaceSlug] = this.profileMap[workspaceSlug].filter(
          (profile) => profile.entity_id !== entityId
        );
    });
  };

  createCategory = async (workspaceSlug: string, name: string) => {
    const category = await this.service.createCategory(workspaceSlug, name);
    this.update(workspaceSlug, (referential) => {
      referential.categories = bySortOrder([...referential.categories, category]);
    });
  };

  updateCategory = async (workspaceSlug: string, categoryId: string, name: string) => {
    const category = await this.service.updateCategory(workspaceSlug, categoryId, name);
    this.update(workspaceSlug, (referential) => {
      referential.categories = referential.categories.map((item) => (item.id === categoryId ? category : item));
    });
  };

  deleteCategory = async (workspaceSlug: string, categoryId: string) => {
    await this.service.deleteCategory(workspaceSlug, categoryId);
    this.update(workspaceSlug, (referential) => {
      referential.categories = referential.categories.filter((category) => category.id !== categoryId);
    });
  };

  fetchProfiles = async (workspaceSlug: string) => {
    const profiles = await this.service.listProfiles(workspaceSlug);
    runInAction(() => {
      this.profileMap[workspaceSlug] = profiles;
    });
    return profiles;
  };

  createProfile = async (workspaceSlug: string, data: TSteeringProfilePayload) => {
    const profile = await this.service.createProfile(workspaceSlug, data);
    runInAction(() => {
      this.profileMap[workspaceSlug] = [...(this.profileMap[workspaceSlug] ?? []), profile];
    });
  };

  deleteProfile = async (workspaceSlug: string, profileId: string) => {
    await this.service.deleteProfile(workspaceSlug, profileId);
    runInAction(() => {
      this.profileMap[workspaceSlug] = (this.profileMap[workspaceSlug] ?? []).filter(
        (profile) => profile.id !== profileId
      );
    });
  };

  fetchProjectEntity = async (workspaceSlug: string, projectId: string) => {
    const { entity_id } = await this.service.getProjectEntity(workspaceSlug, projectId);
    runInAction(() => {
      this.projectEntityMap[projectId] = entity_id;
    });
    return entity_id;
  };

  setProjectEntity = async (workspaceSlug: string, projectId: string, entityId: string) => {
    const { entity_id } = await this.service.setProjectEntity(workspaceSlug, projectId, entityId);
    runInAction(() => {
      this.projectEntityMap[projectId] = entity_id;
    });
  };

  fetchIssueSteering = async (workspaceSlug: string, projectId: string, issueId: string) => {
    const steering = await this.service.getIssueSteering(workspaceSlug, projectId, issueId);
    runInAction(() => {
      this.issueSteeringMap[issueId] = steering;
    });
    return steering;
  };

  /** The server applies the §4 rules (100 % when done, cause cleared when no longer waiting): keep its answer. */
  updateIssueSteering = async (
    workspaceSlug: string,
    projectId: string,
    issueId: string,
    data: TIssueSteeringPayload
  ) => {
    const steering = await this.service.updateIssueSteering(workspaceSlug, projectId, issueId, data);
    runInAction(() => {
      this.issueSteeringMap[issueId] = steering;
    });
    return steering;
  };

  setCircuit = (issueId: string, circuit: TSteeringCircuit) => {
    const steering = this.issueSteeringMap[issueId];
    if (steering) this.issueSteeringMap[issueId] = { ...steering, circuit };
  };

  /** The submission changes the status and the approver too: reload the whole record. */
  submitToCeo = async (workspaceSlug: string, projectId: string, issueId: string, data: TSubmissionPayload) => {
    await this.service.submitToCeo(workspaceSlug, projectId, issueId, data);
    await this.fetchIssueSteering(workspaceSlug, projectId, issueId);
  };
}
