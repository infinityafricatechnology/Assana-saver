/**
 * Copyright (c) 2023-present Plane Software, Inc. and contributors
 * SPDX-License-Identifier: AGPL-3.0-only
 * See the LICENSE file for details.
 */

/**
 * Rules of the steered projects (cahier des charges §4, §9.4), seen from the services: the API refuses
 * an incomplete work item (« steering_required ») and a postponed deadline without a comment
 * (« deadline_comment_required »). The dialog mounted with the workspace asks for the comment and
 * explains the refusals; the services only retry.
 */

export type TSteeringRuleError = { error?: string; code?: string; missing?: string[]; handled?: boolean };

type TSteeringRuleHandlers = {
  /** Resolves with the comment, or null when the person gives up. */
  askDeadlineComment: (date: string | null) => Promise<string | null>;
  explain: (error: TSteeringRuleError) => void;
};

let handlers: TSteeringRuleHandlers | null = null;

export const registerSteeringRuleHandlers = (next: TSteeringRuleHandlers | null) => {
  handlers = next;
};

export const steeringRuleCode = (error: unknown): string =>
  typeof error === "object" && error !== null && "code" in error ? String(error.code) : "";

/** The person already knows why it failed: callers skip their generic error toast. */
export const isHandledSteeringError = (error: unknown): boolean =>
  typeof error === "object" && error !== null && "handled" in error && !!error.handled;

const handled = (error: unknown): TSteeringRuleError => ({ ...(error as TSteeringRuleError), handled: true });

/**
 * Sends an update; when the API wants a postponement comment, asks for it and sends again with it.
 * Giving up rejects, so the stores restore the previous deadline.
 */
export async function withDeadlineComment<T>(
  send: (deadlineComment?: string) => Promise<T>,
  date?: string | null
): Promise<T> {
  try {
    return await send();
  } catch (error) {
    const code = steeringRuleCode(error);
    if (!handlers || (code !== "deadline_comment_required" && code !== "steering_required")) throw error;
    if (code === "steering_required") {
      handlers.explain(error as TSteeringRuleError);
      throw handled(error);
    }
    const comment = await handlers.askDeadlineComment(date ?? null);
    if (!comment) throw handled(error);
    return send(comment);
  }
}
