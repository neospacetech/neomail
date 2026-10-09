/*
 * Typed calls to the NeoMail backend.
 *
 * Every function takes the `ApiClient` the shell provides for this product; its `baseUrl` is the
 * product's API base (`.../api/v1`), so paths here are relative to it.
 */
import { isApiError, type ApiClient } from "@neospacetech/neosuite-runtime";
import type {
  Address,
  Draft,
  MailErrorCode,
  Mailbox,
  Message,
  SendResult,
  SmartSendReport,
  Thread,
  ThreadSummary,
} from "./types";

export function listMailboxes(client: ApiClient, signal?: AbortSignal): Promise<Mailbox[]> {
  return client.get<Mailbox[]>("mailboxes", { signal });
}

export function listThreads(client: ApiClient, mailboxId: string | null, signal?: AbortSignal): Promise<ThreadSummary[]> {
  return client.get<ThreadSummary[]>("threads", { query: mailboxId ? { mailbox_id: mailboxId } : {}, signal });
}

export function getThread(client: ApiClient, id: string, signal?: AbortSignal): Promise<Thread> {
  return client.get<Thread>(`threads/${encodeURIComponent(id)}`, { signal });
}

export function updateMessage(
  client: ApiClient,
  id: string,
  changes: { seen?: boolean; flagged?: boolean; mailbox_ids?: string[] },
  signal?: AbortSignal,
): Promise<Message> {
  return client.patch<Message>(`messages/${encodeURIComponent(id)}`, changes, { signal });
}

export function sendMessage(client: ApiClient, draft: Draft, signal?: AbortSignal): Promise<SendResult> {
  return client.post<SendResult>("messages/send", draft, { signal });
}

export function checkSmartSend(client: ApiClient, draft: Draft, signal?: AbortSignal): Promise<SmartSendReport> {
  const { owner, to, cc, bcc, text, attachments } = draft;
  return client.post<SmartSendReport>("smart-send/check", { owner, draft: { to, cc, bcc, text, attachments } }, { signal });
}

export async function parseAddresses(client: ApiClient, value: string, signal?: AbortSignal): Promise<Address[]> {
  const result = await client.post<{ addresses: Address[] }>("addresses/parse", { value }, { signal });
  return result.addresses;
}

/** Follow domain events, resuming after `after`. Abort with `signal`. */
export async function* streamChanges(client: ApiClient, after: number, signal?: AbortSignal): AsyncGenerator<{ seq: number; type: string }> {
  for await (const message of client.stream("changes", { query: { after }, signal })) {
    if (message.event !== "change") continue;
    const envelope = JSON.parse(message.data) as { type: string };
    yield { seq: Number(message.id ?? after), type: envelope.type };
  }
}

const MESSAGES: Record<MailErrorCode, string> = {
  not_found: "That mailbox or message no longer exists.",
  request_invalid: "Some fields are missing or malformed.",
  address_empty: "Enter an address.",
  address_invalid: "One of the addresses is not valid.",
  address_too_long: "One of the addresses is too long.",
  recipients_empty: "Add at least one recipient.",
  recipients_too_many: "There are too many recipients.",
  subject_too_long: "The subject is too long.",
  message_id_invalid: "The message has an invalid Message-ID.",
  mailbox_name_empty: "Enter a mailbox name.",
  mailbox_name_invalid: "That mailbox name is not valid.",
  mailbox_role_unknown: "That mailbox role does not exist.",
  mailbox_role_taken: "There is already a mailbox with that role.",
  mailbox_name_taken: "There is already a mailbox with that name.",
  claim_kind_unknown: "Smart Send could not read the draft.",
  fact_kind_unknown: "Smart Send could not read the calendar.",
  interval_invalid: "A time in the draft ends before it starts.",
  claim_invalid: "Smart Send could not read the draft.",
  payload_invalid: "The request was malformed.",
  smart_send_blocked: "Smart Send found a conflict. Review it, then send anyway or edit.",
  transport_failed: "The mail server did not accept the message. Try again.",
};

/** User-facing message for any error thrown by the calls above. */
export function errorMessage(error: unknown): string {
  if (isApiError(error)) {
    return MESSAGES[error.code as MailErrorCode] ?? error.detail ?? "Something went wrong. Try again.";
  }
  return "Something went wrong. Try again.";
}

/** Whether `error` is Smart Send stopping a send for confirmation. */
export function isSmartSendBlock(error: unknown): boolean {
  return isApiError(error) && error.code === "smart_send_blocked";
}
