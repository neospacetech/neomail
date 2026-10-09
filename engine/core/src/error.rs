use std::fmt;

/// Every way the domain rules can reject an input.
///
/// Each variant has a stable, snake_case [`code`](MailError::code). Codes are
/// part of the public API: the backend returns them in RFC 9457 problem
/// documents and clients branch on them, so they never change meaning.
#[derive(Debug, Clone, PartialEq, Eq)]
pub enum MailError {
    /// An address is empty after trimming.
    AddressEmpty,
    /// An address is not well formed; `reason` says which part is wrong.
    AddressInvalid { value: String, reason: &'static str },
    /// The `local@domain` form is longer than `max` bytes.
    AddressTooLong { len: usize, max: usize },
    /// An envelope has no recipients.
    RecipientsEmpty,
    /// An envelope has more than `max` distinct recipients.
    RecipientsTooMany { count: usize, max: usize },
    /// The subject is longer than `max` characters.
    SubjectTooLong { len: usize, max: usize },
    /// A Message-ID is not of the form `<left@right>`.
    MessageIdInvalid { value: String },
    /// A mailbox name is empty after trimming.
    MailboxNameEmpty,
    /// A mailbox name has an empty path segment, a control character or is too long.
    MailboxNameInvalid { value: String, reason: &'static str },
    /// A string is not one of the known mailbox roles.
    MailboxRoleUnknown { value: String },
    /// A string is not one of the known Smart Send claim kinds.
    ClaimKindUnknown { value: String },
    /// A string is not one of the known calendar fact kinds.
    FactKindUnknown { value: String },
    /// An interval ends before or when it starts.
    IntervalInvalid { start: i64, end: i64 },
    /// Another mailbox of the same owner already has this unique role.
    MailboxRoleTaken { role: String },
    /// Another mailbox of the same owner already has this name.
    MailboxNameTaken { name: String },
    /// A Smart Send claim is malformed (empty or duplicate id, missing field).
    ClaimInvalid { reason: String },
    /// A JSON payload does not match the expected shape.
    PayloadInvalid { reason: String },
}

impl MailError {
    /// Stable machine-readable error code.
    pub fn code(&self) -> &'static str {
        match self {
            MailError::AddressEmpty => "address_empty",
            MailError::AddressInvalid { .. } => "address_invalid",
            MailError::AddressTooLong { .. } => "address_too_long",
            MailError::RecipientsEmpty => "recipients_empty",
            MailError::RecipientsTooMany { .. } => "recipients_too_many",
            MailError::SubjectTooLong { .. } => "subject_too_long",
            MailError::MessageIdInvalid { .. } => "message_id_invalid",
            MailError::MailboxNameEmpty => "mailbox_name_empty",
            MailError::MailboxNameInvalid { .. } => "mailbox_name_invalid",
            MailError::MailboxRoleUnknown { .. } => "mailbox_role_unknown",
            MailError::ClaimKindUnknown { .. } => "claim_kind_unknown",
            MailError::FactKindUnknown { .. } => "fact_kind_unknown",
            MailError::IntervalInvalid { .. } => "interval_invalid",
            MailError::MailboxRoleTaken { .. } => "mailbox_role_taken",
            MailError::MailboxNameTaken { .. } => "mailbox_name_taken",
            MailError::ClaimInvalid { .. } => "claim_invalid",
            MailError::PayloadInvalid { .. } => "payload_invalid",
        }
    }

    /// Every code this crate can produce, for documentation and tests.
    pub const CODES: [&'static str; 17] = [
        "address_empty",
        "address_invalid",
        "address_too_long",
        "recipients_empty",
        "recipients_too_many",
        "subject_too_long",
        "message_id_invalid",
        "mailbox_name_empty",
        "mailbox_name_invalid",
        "mailbox_role_unknown",
        "claim_kind_unknown",
        "fact_kind_unknown",
        "interval_invalid",
        "mailbox_role_taken",
        "mailbox_name_taken",
        "claim_invalid",
        "payload_invalid",
    ];
}

impl fmt::Display for MailError {
    fn fmt(&self, f: &mut fmt::Formatter<'_>) -> fmt::Result {
        match self {
            MailError::AddressEmpty => write!(f, "address must not be empty"),
            MailError::AddressInvalid { value, reason } => {
                write!(f, "{value:?} is not a valid address: {reason}")
            }
            MailError::AddressTooLong { len, max } => {
                write!(f, "address has {len} bytes; the maximum is {max}")
            }
            MailError::RecipientsEmpty => write!(f, "add at least one recipient"),
            MailError::RecipientsTooMany { count, max } => {
                write!(f, "message has {count} recipients; the maximum is {max}")
            }
            MailError::SubjectTooLong { len, max } => {
                write!(f, "subject has {len} characters; the maximum is {max}")
            }
            MailError::MessageIdInvalid { value } => {
                write!(f, "{value:?} is not a valid Message-ID; expected <left@right>")
            }
            MailError::MailboxNameEmpty => write!(f, "mailbox name must not be empty"),
            MailError::MailboxNameInvalid { value, reason } => {
                write!(f, "{value:?} is not a valid mailbox name: {reason}")
            }
            MailError::MailboxRoleUnknown { value } => write!(
                f,
                "unknown mailbox role {value:?}; expected inbox, drafts, sent, archive, junk, trash or custom"
            ),
            MailError::ClaimKindUnknown { value } => write!(f, "unknown claim kind {value:?}"),
            MailError::FactKindUnknown { value } => {
                write!(f, "unknown calendar fact kind {value:?}")
            }
            MailError::IntervalInvalid { start, end } => {
                write!(f, "interval must end after it starts (start {start}, end {end})")
            }
            MailError::MailboxRoleTaken { role } => {
                write!(f, "there is already a mailbox with role {role}")
            }
            MailError::MailboxNameTaken { name } => {
                write!(f, "there is already a mailbox named {name:?}")
            }
            MailError::ClaimInvalid { reason } => write!(f, "invalid claim: {reason}"),
            MailError::PayloadInvalid { reason } => write!(f, "invalid payload: {reason}"),
        }
    }
}

impl std::error::Error for MailError {}

#[cfg(test)]
mod tests {
    use super::*;

    #[test]
    fn codes_are_stable_and_listed() {
        let all = [
            MailError::AddressEmpty,
            MailError::AddressInvalid {
                value: "x".into(),
                reason: "missing @",
            },
            MailError::AddressTooLong { len: 300, max: 254 },
            MailError::RecipientsEmpty,
            MailError::RecipientsTooMany {
                count: 501,
                max: 500,
            },
            MailError::SubjectTooLong { len: 999, max: 998 },
            MailError::MessageIdInvalid { value: "x".into() },
            MailError::MailboxNameEmpty,
            MailError::MailboxNameInvalid {
                value: "a//b".into(),
                reason: "empty segment",
            },
            MailError::MailboxRoleUnknown { value: "x".into() },
            MailError::ClaimKindUnknown { value: "x".into() },
            MailError::FactKindUnknown { value: "x".into() },
            MailError::IntervalInvalid { start: 2, end: 1 },
            MailError::MailboxRoleTaken {
                role: "inbox".into(),
            },
            MailError::MailboxNameTaken { name: "x".into() },
            MailError::ClaimInvalid { reason: "x".into() },
            MailError::PayloadInvalid { reason: "x".into() },
        ];
        let codes: Vec<_> = all.iter().map(MailError::code).collect();
        assert_eq!(codes, MailError::CODES);
    }

    #[test]
    fn messages_are_human_readable() {
        assert_eq!(
            MailError::AddressInvalid {
                value: "bob".into(),
                reason: "missing @"
            }
            .to_string(),
            "\"bob\" is not a valid address: missing @"
        );
        assert_eq!(
            MailError::RecipientsEmpty.to_string(),
            "add at least one recipient"
        );
    }
}
