use std::fmt;
use std::str::FromStr;

use crate::error::MailError;

/// Maximum length of a full mailbox path in characters.
pub const MAILBOX_NAME_MAX_CHARS: usize = 255;

/// What a mailbox is for (JMAP `Mailbox.role`, RFC 6154 special-use).
///
/// Roles also fix the display order: inbox first, then drafts, sent, archive,
/// junk and trash, then custom folders.
#[derive(Debug, Clone, Copy, PartialEq, Eq, Hash, PartialOrd, Ord)]
pub enum MailboxRole {
    Inbox,
    Drafts,
    Sent,
    Archive,
    Junk,
    Trash,
    Custom,
}

impl MailboxRole {
    /// All roles in display order.
    pub const ALL: [MailboxRole; 7] = [
        MailboxRole::Inbox,
        MailboxRole::Drafts,
        MailboxRole::Sent,
        MailboxRole::Archive,
        MailboxRole::Junk,
        MailboxRole::Trash,
        MailboxRole::Custom,
    ];

    pub fn as_str(self) -> &'static str {
        match self {
            MailboxRole::Inbox => "inbox",
            MailboxRole::Drafts => "drafts",
            MailboxRole::Sent => "sent",
            MailboxRole::Archive => "archive",
            MailboxRole::Junk => "junk",
            MailboxRole::Trash => "trash",
            MailboxRole::Custom => "custom",
        }
    }

    /// Position in the display order (0 = first).
    pub fn rank(self) -> usize {
        self as usize
    }

    /// Whether an account may have at most one mailbox with this role.
    pub fn is_unique(self) -> bool {
        self != MailboxRole::Custom
    }
}

impl fmt::Display for MailboxRole {
    fn fmt(&self, f: &mut fmt::Formatter<'_>) -> fmt::Result {
        f.write_str(self.as_str())
    }
}

impl FromStr for MailboxRole {
    type Err = MailError;

    fn from_str(s: &str) -> Result<Self, Self::Err> {
        MailboxRole::ALL
            .into_iter()
            .find(|role| role.as_str() == s)
            .ok_or_else(|| MailError::MailboxRoleUnknown {
                value: s.to_owned(),
            })
    }
}

/// Normalise a hierarchical mailbox name such as `Projects / Acme`.
///
/// The name is split on `/`; each segment is trimmed and has its internal
/// whitespace collapsed. Empty segments and control characters are rejected,
/// and the joined result (`Projects/Acme`) must fit [`MAILBOX_NAME_MAX_CHARS`].
/// `INBOX` is matched case-insensitively and always written `INBOX`, as IMAP requires.
pub fn normalize_mailbox_name(raw: &str) -> Result<String, MailError> {
    if raw.trim().is_empty() {
        return Err(MailError::MailboxNameEmpty);
    }
    let invalid = |reason| MailError::MailboxNameInvalid {
        value: raw.trim().to_owned(),
        reason,
    };
    if raw.chars().any(char::is_control) {
        return Err(invalid("control character"));
    }
    let segments = raw
        .split('/')
        .map(|segment| segment.split_whitespace().collect::<Vec<_>>().join(" "))
        .collect::<Vec<_>>();
    if segments.iter().any(String::is_empty) {
        return Err(invalid("empty path segment"));
    }
    let mut name = segments.join("/");
    if name.chars().count() > MAILBOX_NAME_MAX_CHARS {
        return Err(invalid("longer than 255 characters"));
    }
    if name.eq_ignore_ascii_case("inbox") {
        name = "INBOX".to_owned();
    }
    Ok(name)
}

/// Guess the role of a top-level mailbox from its name, as servers without
/// special-use flags name them. Anything unrecognised is `custom`.
pub fn role_for_name(name: &str) -> MailboxRole {
    let lower = name.trim().to_lowercase();
    match lower.as_str() {
        "inbox" => MailboxRole::Inbox,
        "drafts" | "draft" => MailboxRole::Drafts,
        "sent" | "sent items" | "sent mail" | "sent messages" => MailboxRole::Sent,
        "archive" | "archives" | "all mail" => MailboxRole::Archive,
        "junk" | "spam" | "junk e-mail" | "junk email" | "bulk mail" => MailboxRole::Junk,
        "trash" | "bin" | "deleted items" | "deleted messages" => MailboxRole::Trash,
        _ => MailboxRole::Custom,
    }
}

/// Check that a mailbox named `name` with `role` can join an owner's existing
/// mailboxes, given as `(name, role)` pairs already normalised.
///
/// Names are unique per owner ignoring case, and every role except `custom`
/// may appear at most once. Returns the normalised name.
pub fn validate_new_mailbox(
    raw_name: &str,
    role: MailboxRole,
    existing: &[(String, MailboxRole)],
) -> Result<String, MailError> {
    let name = normalize_mailbox_name(raw_name)?;
    let folded = name.to_lowercase();
    if existing.iter().any(|(n, _)| n.to_lowercase() == folded) {
        return Err(MailError::MailboxNameTaken { name });
    }
    if role.is_unique() && existing.iter().any(|(_, r)| *r == role) {
        return Err(MailError::MailboxRoleTaken {
            role: role.as_str().to_owned(),
        });
    }
    Ok(name)
}

#[cfg(test)]
mod tests {
    use super::*;

    #[test]
    fn roles_round_trip_and_rank_in_display_order() {
        for (i, role) in MailboxRole::ALL.into_iter().enumerate() {
            assert_eq!(role.as_str().parse::<MailboxRole>().unwrap(), role);
            assert_eq!(role.rank(), i);
        }
        assert!(MailboxRole::Inbox.is_unique());
        assert!(!MailboxRole::Custom.is_unique());
        assert_eq!(
            "Inbox".parse::<MailboxRole>(),
            Err(MailError::MailboxRoleUnknown {
                value: "Inbox".into()
            })
        );
    }

    #[test]
    fn normalises_hierarchical_names() {
        assert_eq!(
            normalize_mailbox_name("  Projects /  Acme   Corp ").unwrap(),
            "Projects/Acme Corp"
        );
        assert_eq!(normalize_mailbox_name("inbox").unwrap(), "INBOX");
        assert_eq!(
            normalize_mailbox_name("Inbox/Later").unwrap(),
            "Inbox/Later"
        );
    }

    #[test]
    fn rejects_bad_names() {
        assert_eq!(
            normalize_mailbox_name("  "),
            Err(MailError::MailboxNameEmpty)
        );
        for raw in ["a//b", "/a", "a/", "a\u{7}b"] {
            assert!(
                matches!(
                    normalize_mailbox_name(raw),
                    Err(MailError::MailboxNameInvalid { .. })
                ),
                "{raw:?}"
            );
        }
        assert!(normalize_mailbox_name(&"x".repeat(256)).is_err());
        assert!(normalize_mailbox_name(&"x".repeat(255)).is_ok());
    }

    #[test]
    fn new_mailboxes_respect_unique_names_and_roles() {
        let existing = vec![
            ("INBOX".to_owned(), MailboxRole::Inbox),
            ("Receipts".to_owned(), MailboxRole::Custom),
        ];
        assert_eq!(
            validate_new_mailbox(" Projects / Acme ", MailboxRole::Custom, &existing).unwrap(),
            "Projects/Acme"
        );
        assert_eq!(
            validate_new_mailbox("receipts", MailboxRole::Custom, &existing),
            Err(MailError::MailboxNameTaken {
                name: "receipts".into()
            })
        );
        assert_eq!(
            validate_new_mailbox("Other inbox", MailboxRole::Inbox, &existing),
            Err(MailError::MailboxRoleTaken {
                role: "inbox".into()
            })
        );
        assert!(validate_new_mailbox("More", MailboxRole::Custom, &existing).is_ok());
    }

    #[test]
    fn guesses_roles_from_common_names() {
        assert_eq!(role_for_name("INBOX"), MailboxRole::Inbox);
        assert_eq!(role_for_name("Sent Items"), MailboxRole::Sent);
        assert_eq!(role_for_name("Spam"), MailboxRole::Junk);
        assert_eq!(role_for_name("Deleted Items"), MailboxRole::Trash);
        assert_eq!(role_for_name("All Mail"), MailboxRole::Archive);
        assert_eq!(role_for_name("Receipts"), MailboxRole::Custom);
    }
}
