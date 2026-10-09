/** Display helpers shared by the screens and widgets. */
import type { Mailbox, MailboxRole } from "./types";

const ROLE_LABELS: Record<MailboxRole, string> = {
  inbox: "Inbox",
  drafts: "Drafts",
  sent: "Sent",
  archive: "Archive",
  junk: "Junk",
  trash: "Trash",
  custom: "",
};

/** Localisable label for system mailboxes; custom mailboxes use their own name. */
export function mailboxLabel(mailbox: Mailbox): string {
  return ROLE_LABELS[mailbox.role] || mailbox.name;
}

const timeFormat = new Intl.DateTimeFormat(undefined, { hour: "numeric", minute: "2-digit" });
const dayFormat = new Intl.DateTimeFormat(undefined, { day: "numeric", month: "short" });
const fullFormat = new Intl.DateTimeFormat(undefined, { dateStyle: "medium", timeStyle: "short" });

/** Time for today, date otherwise. */
export function shortDate(instant: string, now: Date = new Date()): string {
  const date = new Date(instant);
  return date.toDateString() === now.toDateString() ? timeFormat.format(date) : dayFormat.format(date);
}

export function fullDate(instant: string): string {
  return fullFormat.format(new Date(instant));
}

/** Split a To/Cc field into entries; the server parses each one. */
export function splitRecipients(value: string): string[] {
  return value.trim() ? [value] : [];
}

/** `Re: subject`, unless it already is a reply. */
export function replySubject(subject: string): string {
  return /^(re|aw|sv)\s*:/i.test(subject) ? subject : `Re: ${subject}`;
}
