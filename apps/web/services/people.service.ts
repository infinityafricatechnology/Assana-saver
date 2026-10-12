/**
 * Copyright (c) 2023-present Plane Software, Inc. and contributors
 * SPDX-License-Identifier: AGPL-3.0-only
 * See the LICENSE file for details.
 */

import { API_BASE_URL } from "@plane/constants";
// services
import { APIService } from "@/services/api.service";
// types
import type { TSteeringProfile, TSteeringProfileRole } from "@/services/steering.service";

/** 20 = admin, 15 = member (organisation and projects alike). */
export type TPersonRole = 20 | 15;

/** pending: never signed in yet · active · departed: access closed. */
export type TPersonStatus = "pending" | "active" | "departed";

export type TPerson = {
  id: string;
  membership_id: string;
  email: string;
  first_name: string;
  last_name: string;
  display_name: string;
  avatar_url: string | null;
  role: TPersonRole;
  status: TPersonStatus;
  last_login_time: string | null;
  date_joined: string;
  profiles: TSteeringProfile[];
  projects: { project_id: string; role: TPersonRole }[];
};

export type TPersonProfileInput = { role: TSteeringProfileRole; branch_id?: string | null; entity_id?: string | null };

export type TPersonPayload = {
  email?: string;
  first_name?: string;
  last_name?: string;
  role?: TPersonRole;
  profiles?: TPersonProfileInput[];
  project_ids?: string[];
  send_email?: boolean;
};

export type TImportRow = {
  line: number;
  values: Record<"first_name" | "last_name" | "email" | "role" | "profile" | "scope" | "projects", string>;
  errors: string[];
  valid: boolean;
  created: boolean;
};

export type TImportResult = { rows: TImportRow[]; created: number };

/** The API answers refusals with `{ error, code }`; the code picks the message to show. */
export type TPeopleError = { error?: string; code?: string };

export class PeopleService extends APIService {
  constructor() {
    super(API_BASE_URL);
  }

  private unwrap<T>(request: Promise<{ data: T }>): Promise<T> {
    return request
      .then((response) => response?.data)
      .catch((error) => {
        throw error?.response?.data;
      });
  }

  private url(workspaceSlug: string, suffix = ""): string {
    return `/api/workspaces/${workspaceSlug}/people/${suffix}`;
  }

  list(workspaceSlug: string): Promise<TPerson[]> {
    return this.unwrap(this.get(this.url(workspaceSlug)));
  }

  create(workspaceSlug: string, data: TPersonPayload): Promise<TPerson> {
    return this.unwrap(this.post(this.url(workspaceSlug), data));
  }

  update(workspaceSlug: string, userId: string, data: TPersonPayload): Promise<TPerson> {
    return this.unwrap(this.patch(this.url(workspaceSlug, `${userId}/`), data));
  }

  addToProjects(
    workspaceSlug: string,
    data: { user_ids: string[]; project_ids: string[]; role: TPersonRole }
  ): Promise<{ added: number; people: TPerson[] }> {
    return this.unwrap(this.post(this.url(workspaceSlug, "projects/"), data));
  }

  departurePreview(workspaceSlug: string, userId: string): Promise<{ open_work_items: number }> {
    return this.unwrap(this.get(this.url(workspaceSlug, `${userId}/departure/`)));
  }

  depart(
    workspaceSlug: string,
    userId: string,
    reassignTo: string | null
  ): Promise<{ reassigned: number; unassigned: number; person: TPerson }> {
    return this.unwrap(this.post(this.url(workspaceSlug, `${userId}/departure/`), { reassign_to: reassignTo }));
  }

  reactivate(workspaceSlug: string, userId: string, role: TPersonRole): Promise<TPerson> {
    return this.unwrap(this.post(this.url(workspaceSlug, `${userId}/reactivation/`), { role }));
  }

  importFile(workspaceSlug: string, file: File, confirm: boolean, sendEmail: boolean): Promise<TImportResult> {
    const form = new FormData();
    form.append("file", file);
    form.append("confirm", confirm ? "true" : "false");
    form.append("send_email", sendEmail ? "true" : "false");
    return this.unwrap(this.post(this.url(workspaceSlug, "import/"), form));
  }

  exportCsv(workspaceSlug: string): Promise<string> {
    return this.unwrap(this.get(this.url(workspaceSlug, "export/"), { responseType: "text" }));
  }
}
