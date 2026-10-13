/**
 * Copyright (c) 2023-present Plane Software, Inc. and contributors
 * SPDX-License-Identifier: AGPL-3.0-only
 * See the LICENSE file for details.
 */

import { API_BASE_URL } from "@plane/constants";
// services
import { APIService } from "@/services/api.service";
// types
import type {
  TSteeringProfileRole,
  TSteeringRiskNature,
  TSteeringStatus,
  TSteeringWaitingFor,
} from "@/services/steering.service";

/** RG-03; « closed » for work items that are done or cancelled. */
export type TSteeringSignal = "critical" | "late" | "soon" | "on_time" | "closed";
export type TSteeringPriority = "urgent" | "high" | "medium";
export type TEntityState = "alert" | "watch" | "ok";
export type TInconsistency = "progress_without_closure" | "late_not_started";

export type TDashboardTask = {
  id: string;
  key: string;
  name: string;
  project_id: string;
  entity_id: string;
  branch_id: string | null;
  category_id: string | null;
  assignee_ids: string[];
  supervisor_id: string | null;
  approver_id: string | null;
  priority: TSteeringPriority;
  retained_priority: TSteeringPriority;
  requalification: { priority: TSteeringPriority; by_role: TSteeringProfileRole; comment: string } | null;
  status: TSteeringStatus;
  is_open: boolean;
  progress: number;
  target_date: string | null;
  days_late: number;
  days_left: number | null;
  signal: TSteeringSignal;
  waiting_for: TSteeringWaitingFor | null;
  waiting_since: string | null;
  waiting_days: number | null;
  risk: {
    nature: TSteeringRiskNature | null;
    effective_date: string | null;
    description: string;
    days: number | null;
    soon: boolean;
  } | null;
  in_queue: boolean;
  submission: {
    id: string;
    submitted_at: string;
    submitted_by_id: string | null;
    message: string;
    link: string;
    waiting_days: number;
  } | null;
  blocked_by: string[];
  blocking: string[];
  blocked: boolean;
  dormant: boolean;
  dormant_days: number;
  inconsistencies: TInconsistency[];
  closure_date: string | null;
  situation: string;
  situation_updated_at: string | null;
  reminders: { count: number; last_at: string | null };
  updated_at: string;
};

/** A work item outside the viewer's scope that blocks or waits on one inside it. */
export type TRelatedTask = {
  id: string;
  key: string;
  name: string;
  entity_id: string | null;
  status: TSteeringStatus;
  signal: TSteeringSignal;
  days_late: number;
};

type TCounts = { open: number; late: number; critical: number; blocked: number; queue: number };

export type TEntitySituation = TCounts & { id: string; name: string; project_ids: string[]; state: TEntityState };
export type TBranchSituation = TCounts & { id: string; name: string; has_alert: boolean; entities: TEntitySituation[] };

export type TDashboardSummary = {
  kpis: TCounts & { late_share: number; due_soon: number; average_progress: number };
  branches: TBranchSituation[];
  priority_delays: string[];
  blocking: { id: string; count: number; highlighted: boolean }[];
  load: { person_id: string; open: number; late: number; critical: number }[];
};

export type TDashboardViewer = {
  whole_group: boolean;
  branch_ids: string[];
  entity_ids: string[];
  is_ceo: boolean;
  can_requalify: boolean;
  can_remind: boolean;
  can_decide: boolean;
};

export type TTrendPoint = TCounts & { date: string };

export type TDashboard = {
  generated_at: string;
  today: string;
  version: string;
  viewer: TDashboardViewer;
  branches: { id: string; name: string; sort_order: number }[];
  entities: { id: string; name: string; branch_id: string }[];
  projects: { id: string; name: string; identifier: string; entity_id: string }[];
  categories: { id: string; name: string }[];
  people: { id: string; name: string }[];
  tasks: TDashboardTask[];
  related: Record<string, TRelatedTask>;
  summary: TDashboardSummary;
  queue: string[];
  trend: TTrendPoint[];
  /** For the Cabinet and the CEO: the draft of the week, when it waits to be sent. */
  report_ready: { id: string; week: number } | null;
};

export type THistoryLine = {
  id: string;
  field: string;
  verb: string;
  old_value: string | null;
  new_value: string | null;
  comment: string | null;
  actor: string | null;
  created_at: string;
};

export type TReportSectionKey = "kpis" | "situation" | "delays" | "queue" | "blocking";

/** The COMEX figures frozen in a weekly report (§9.3), already in French. */
export type TReportData = {
  situation: string;
  today: string;
  kpis: TDashboardSummary["kpis"];
  entities: (TEntitySituation & { branch: string })[];
  delays: { id: string; key: string; name: string; entity: string; delay: string; signal: TSteeringSignal }[];
  queue: { id: string; key: string; name: string; entity: string; priority: string }[];
  blocking: { id: string; key: string; name: string; entity: string; count: number }[];
};

export type TReportSummary = {
  id: string;
  year: number;
  week: number;
  status: "draft" | "sent";
  refreshed_at: string;
  sent_at: string | null;
  sent_by: string | null;
  situation: string;
};

export type TReport = TReportSummary & {
  intro: string;
  sections: { key: TReportSectionKey; visible: boolean }[];
  section_comments: Partial<Record<TReportSectionKey, string>>;
  entity_comments: Record<string, string>;
  task_comments: Record<string, string>;
  highlighted_tasks: string[];
  highlighted_entities: string[];
  recipient_ids: string[];
  extra_emails: string[];
  data: TReportData;
};

export type TReportPatch = Partial<
  Pick<
    TReport,
    | "intro"
    | "sections"
    | "section_comments"
    | "entity_comments"
    | "task_comments"
    | "highlighted_tasks"
    | "highlighted_entities"
    | "recipient_ids"
    | "extra_emails"
  >
>;

export type TDashboardSheet = { chain: (TRelatedTask & { assignees?: string[] })[][]; history: THistoryLine[] };

export class SteeringDashboardService extends APIService {
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

  getDashboard(workspaceSlug: string, branchId?: string | null): Promise<TDashboard> {
    return this.unwrap(
      this.get(`/api/workspaces/${workspaceSlug}/steering/dashboard/`, {
        params: branchId ? { branch: branchId } : {},
      })
    );
  }

  getVersion(workspaceSlug: string): Promise<{ version: string }> {
    return this.unwrap(this.get(`/api/workspaces/${workspaceSlug}/steering/dashboard/version/`));
  }

  /** §6.7: the COMEX PDF of the viewer's scope, on one branch if given. */
  downloadComex(workspaceSlug: string, branchId?: string | null): Promise<Blob> {
    return this.unwrap(
      this.get(`/api/workspaces/${workspaceSlug}/steering/dashboard/export/comex/`, {
        params: branchId ? { branch: branchId } : {},
        responseType: "blob",
      })
    );
  }

  /** §12: the work items of the filtered list, in the order of the screen, as an Excel file. */
  downloadTasks(workspaceSlug: string, ids: string[]): Promise<Blob> {
    return this.unwrap(
      this.post(`/api/workspaces/${workspaceSlug}/steering/dashboard/export/tasks/`, { ids }, { responseType: "blob" })
    );
  }

  private reports(workspaceSlug: string, suffix = ""): string {
    return `/api/workspaces/${workspaceSlug}/steering/reports/${suffix}`;
  }

  listReports(workspaceSlug: string): Promise<TReportSummary[]> {
    return this.unwrap(this.get(this.reports(workspaceSlug)));
  }

  /** The draft of the week, prepared now if Friday's has not come yet. */
  prepareReport(workspaceSlug: string): Promise<TReport> {
    return this.unwrap(this.post(this.reports(workspaceSlug)));
  }

  getReport(workspaceSlug: string, reportId: string): Promise<TReport> {
    return this.unwrap(this.get(this.reports(workspaceSlug, `${reportId}/`)));
  }

  updateReport(workspaceSlug: string, reportId: string, data: TReportPatch): Promise<TReport> {
    return this.unwrap(this.patch(this.reports(workspaceSlug, `${reportId}/`), data));
  }

  refreshReport(workspaceSlug: string, reportId: string): Promise<TReport> {
    return this.unwrap(this.post(this.reports(workspaceSlug, `${reportId}/refresh/`)));
  }

  sendReport(workspaceSlug: string, reportId: string): Promise<TReport> {
    return this.unwrap(this.post(this.reports(workspaceSlug, `${reportId}/send/`)));
  }

  downloadReport(workspaceSlug: string, reportId: string): Promise<Blob> {
    return this.unwrap(this.get(this.reports(workspaceSlug, `${reportId}/pdf/`), { responseType: "blob" }));
  }

  getSheet(workspaceSlug: string, issueId: string): Promise<TDashboardSheet> {
    return this.unwrap(this.get(`/api/workspaces/${workspaceSlug}/steering/dashboard/issues/${issueId}/`));
  }
}
