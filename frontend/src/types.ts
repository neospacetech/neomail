/*
 * Wire types for the NeoMail API. They mirror contracts/api/openapi.yaml; keep both in step.
 */

export type MailboxRole = "inbox" | "drafts" | "sent" | "archive" | "junk" | "trash" | "custom";

export interface Mailbox {
  id: string;
  ref: string;
  owner: string;
  /** Hierarchical, `/`-separated; the inbox is `INBOX`. */
  name: string;
  role: MailboxRole;
  total: number;
  unread: number;
  version: number;
  created_at: string;
  updated_at: string;
}

export interface Address {
  name: string | null;
  email: string;
  /** Case-folded `local@domain`, for comparing people. */
  canonical: string;
  /** `Name <local@domain>`. */
  display: string;
}

export interface Message {
  id: string;
  ref: string;
  owner: string;
  thread_id: string;
  mailbox_ids: string[];
  message_id: string;
  in_reply_to: string[];
  references: string[];
  from: Address;
  to: Address[];
  cc: Address[];
  bcc: Address[];
  subject: string;
  text: string;
  attachments: string[];
  received_at: string;
  seen: boolean;
  flagged: boolean;
  version: number;
}

export interface ThreadSummary {
  id: string;
  ref: string;
  owner: string;
  /** Base subject, without `Re:`/`Fwd:` prefixes. */
  subject: string;
  message_ids: string[];
  message_count: number;
  unread_count: number;
  flagged: boolean;
  participants: string[];
  mailbox_ids: string[];
  snippet: string;
  last_at: string;
}

export interface Thread extends ThreadSummary {
  messages: Message[];
}

export type SmartSendRule =
  | "overlap"
  | "out_of_office"
  | "focus_time"
  | "elsewhere_then"
  | "missing_attachment"
  | "missing_recipient";

export interface SmartSendFinding {
  claim: string;
  rule: SmartSendRule;
  severity: "info" | "warn" | "conflict";
  why: string;
  evidence: string[];
  /** `[start, end)` character offsets in the draft text. */
  span: [number, number] | null;
}

export interface SmartSendReport {
  findings: SmartSendFinding[];
  claims_checked: number;
  /** True when a conflict should stop Send for confirmation. */
  blocking: boolean;
}

export interface Draft {
  owner: string;
  sender: string;
  to: string[];
  cc: string[];
  bcc: string[];
  subject: string;
  text: string;
  attachments: string[];
  reply_to_id?: string | null;
  send_anyway?: boolean;
}

export interface SendResult {
  message: Message;
  submission_id: string | null;
  findings: SmartSendFinding[];
}

/** Stable error codes the API returns in problem documents. */
export type MailErrorCode =
  | "not_found"
  | "request_invalid"
  | "address_empty"
  | "address_invalid"
  | "address_too_long"
  | "recipients_empty"
  | "recipients_too_many"
  | "subject_too_long"
  | "message_id_invalid"
  | "mailbox_name_empty"
  | "mailbox_name_invalid"
  | "mailbox_role_unknown"
  | "mailbox_role_taken"
  | "mailbox_name_taken"
  | "claim_kind_unknown"
  | "fact_kind_unknown"
  | "interval_invalid"
  | "claim_invalid"
  | "payload_invalid"
  | "smart_send_blocked"
  | "transport_failed";
