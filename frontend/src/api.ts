/*
 * Typed calls to the NeoMail backend.
 *
 * Every function takes the `ApiClient` the shell provides for this product; its `baseUrl` is the
 * product's API base (`.../api/v1`), so paths here are relative to it.
 */
import { isApiError, type ApiClient, type SseMessage } from "@neospacetech/neosuite-runtime";
import type { Item, ItemErrorCode, Transition } from "./types";

export function validateItem(client: ApiClient, title: string, signal?: AbortSignal): Promise<Item> {
  return client.post<Item>("items/validate", { title }, { signal });
}

export function transitionItem(
  client: ApiClient,
  item: Pick<Item, "slug" | "status">,
  signal?: AbortSignal,
): Promise<Transition> {
  return client.post<Transition>(`items/${encodeURIComponent(item.slug)}/transition`, { status: item.status }, { signal });
}

export type LifecycleEvent =
  | { event: "item.created"; id: string | undefined; data: Item }
  | { event: "item.status"; id: string | undefined; data: Transition }
  | { event: "end"; id: string | undefined; data: { slug: string } };

function decode(message: SseMessage): LifecycleEvent | null {
  switch (message.event) {
    case "item.created":
    case "item.status":
    case "end":
      return { event: message.event, id: message.id, data: JSON.parse(message.data) } as LifecycleEvent;
    default:
      return null;
  }
}

/** Stream an item's lifecycle as server-sent events. Abort with `signal`. */
export async function* streamLifecycle(client: ApiClient, title: string, signal?: AbortSignal): AsyncGenerator<LifecycleEvent> {
  for await (const message of client.stream("items/lifecycle", { query: { title }, signal })) {
    const event = decode(message);
    if (event) yield event;
  }
}

const MESSAGES: Record<ItemErrorCode, string> = {
  title_empty: "Enter a title.",
  title_too_long: "Use 200 characters or fewer.",
  status_unknown: "That status does not exist.",
  transition_invalid: "The item cannot move to that status.",
  status_terminal: "The item is already done.",
  slug_invalid: "That item address is not valid.",
};

/** User-facing message for any error thrown by the calls above. */
export function errorMessage(error: unknown): string {
  if (isApiError(error)) {
    return MESSAGES[error.code as ItemErrorCode] ?? error.detail ?? "Something went wrong. Try again.";
  }
  return "Something went wrong. Try again.";
}
