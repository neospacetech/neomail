use std::fmt;

use crate::status::Status;

/// Every way the domain rules can reject an input.
///
/// Each variant has a stable, snake_case [`code`](ItemError::code). Codes are
/// part of the public API: the backend returns them in RFC 9457 problem
/// documents and clients branch on them, so they never change meaning.
#[derive(Debug, Clone, PartialEq, Eq)]
pub enum ItemError {
    /// The title is empty after whitespace normalisation.
    TitleEmpty,
    /// The normalised title has more than `max` characters.
    TitleTooLong { len: usize, max: usize },
    /// A string is not one of the known status names.
    StatusUnknown { value: String },
    /// The requested status change is not allowed by the state machine.
    TransitionInvalid { from: Status, to: Status },
    /// The status has no successor.
    StatusTerminal { status: Status },
    /// A string is not a well-formed slug.
    SlugInvalid { value: String },
}

impl ItemError {
    /// Stable machine-readable error code.
    pub fn code(&self) -> &'static str {
        match self {
            ItemError::TitleEmpty => "title_empty",
            ItemError::TitleTooLong { .. } => "title_too_long",
            ItemError::StatusUnknown { .. } => "status_unknown",
            ItemError::TransitionInvalid { .. } => "transition_invalid",
            ItemError::StatusTerminal { .. } => "status_terminal",
            ItemError::SlugInvalid { .. } => "slug_invalid",
        }
    }

    /// Every code this crate can produce, for documentation and tests.
    pub const CODES: [&'static str; 6] = [
        "title_empty",
        "title_too_long",
        "status_unknown",
        "transition_invalid",
        "status_terminal",
        "slug_invalid",
    ];
}

impl fmt::Display for ItemError {
    fn fmt(&self, f: &mut fmt::Formatter<'_>) -> fmt::Result {
        match self {
            ItemError::TitleEmpty => write!(f, "title must not be empty"),
            ItemError::TitleTooLong { len, max } => {
                write!(f, "title has {len} characters; the maximum is {max}")
            }
            ItemError::StatusUnknown { value } => {
                write!(f, "unknown status {value:?}; expected todo, doing or done")
            }
            ItemError::TransitionInvalid { from, to } => {
                write!(f, "cannot move an item from {from} to {to}")
            }
            ItemError::StatusTerminal { status } => {
                write!(f, "status {status} is final and has no next status")
            }
            ItemError::SlugInvalid { value } => write!(
                f,
                "{value:?} is not a valid slug; use lowercase letters, digits and single hyphens"
            ),
        }
    }
}

impl std::error::Error for ItemError {}

#[cfg(test)]
mod tests {
    use super::*;

    #[test]
    fn codes_are_stable_and_listed() {
        let all = [
            ItemError::TitleEmpty,
            ItemError::TitleTooLong { len: 201, max: 200 },
            ItemError::StatusUnknown { value: "x".into() },
            ItemError::TransitionInvalid {
                from: Status::Todo,
                to: Status::Done,
            },
            ItemError::StatusTerminal {
                status: Status::Done,
            },
            ItemError::SlugInvalid { value: "A".into() },
        ];
        let codes: Vec<_> = all.iter().map(ItemError::code).collect();
        assert_eq!(codes, ItemError::CODES);
    }

    #[test]
    fn messages_are_human_readable() {
        assert_eq!(ItemError::TitleEmpty.to_string(), "title must not be empty");
        assert_eq!(
            ItemError::TitleTooLong { len: 250, max: 200 }.to_string(),
            "title has 250 characters; the maximum is 200"
        );
        assert_eq!(
            ItemError::TransitionInvalid {
                from: Status::Todo,
                to: Status::Done
            }
            .to_string(),
            "cannot move an item from todo to done"
        );
    }
}
