/*
 * Wire types for the NeoMail API. They mirror contracts/api/openapi.yaml; keep both in step.
 */

export type ItemStatus = "todo" | "doing" | "done";

export interface Item {
  title: string;
  slug: string;
  status: ItemStatus;
  /** Status the item can move to next, decided by the server; null when final. */
  next_status: ItemStatus | null;
}

export interface Transition {
  slug: string;
  previous_status: ItemStatus;
  status: ItemStatus;
  next_status: ItemStatus | null;
}

/** Stable error codes the API returns in problem documents. */
export type ItemErrorCode =
  | "title_empty"
  | "title_too_long"
  | "status_unknown"
  | "transition_invalid"
  | "status_terminal"
  | "slug_invalid";
