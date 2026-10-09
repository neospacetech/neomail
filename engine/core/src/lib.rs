//! Domain logic for NeoMail.
//!
//! This crate holds every domain decision the mail product makes: how
//! addresses are parsed and normalised, how messages group into threads, which
//! mailbox names and roles are valid, what a well-formed envelope is, and which
//! claims in a draft conflict with the sender's calendar (Smart Send).
//! It is pure: no I/O, no clock, no randomness. The FastAPI backend calls it
//! through the `neomail_core` Python extension built from `engine/py`.

mod address;
mod envelope;
mod error;
mod mailbox;
mod message_id;
mod smartsend;
mod subject;
mod threading;

pub use address::{normalize_email, parse_address_list, Address, EMAIL_MAX_LEN, LOCAL_MAX_LEN};
pub use envelope::{Envelope, RECIPIENTS_MAX};
pub use error::MailError;
pub use mailbox::{
    normalize_mailbox_name, role_for_name, validate_new_mailbox, MailboxRole,
    MAILBOX_NAME_MAX_CHARS,
};
pub use message_id::{extract_message_ids, parse_message_id};
pub use smartsend::{
    check_claims, extract_local_claims, CalendarFact, Claim, ClaimKind, DraftContext, FactKind,
    Finding, Interval, Rule, Severity, MAX_CLAIMS, MAX_FACTS,
};
pub use subject::{
    is_reply_subject, normalize_subject, subject_key, validate_subject, SUBJECT_MAX_CHARS,
};
pub use threading::{build_threads, MessageHeaders, ThreadGroup};
