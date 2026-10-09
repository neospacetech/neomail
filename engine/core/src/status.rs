use std::fmt;
use std::str::FromStr;

use crate::error::ItemError;

/// Lifecycle status of an item.
///
/// The state machine is linear: `todo -> doing -> done`. `done` is final.
#[derive(Debug, Clone, Copy, PartialEq, Eq, Hash, PartialOrd, Ord)]
pub enum Status {
    Todo,
    Doing,
    Done,
}

impl Status {
    /// All statuses in lifecycle order.
    pub const ALL: [Status; 3] = [Status::Todo, Status::Doing, Status::Done];

    /// Wire name of the status.
    pub fn as_str(self) -> &'static str {
        match self {
            Status::Todo => "todo",
            Status::Doing => "doing",
            Status::Done => "done",
        }
    }

    /// The status that follows this one, if any.
    pub fn successor(self) -> Option<Status> {
        match self {
            Status::Todo => Some(Status::Doing),
            Status::Doing => Some(Status::Done),
            Status::Done => None,
        }
    }

    /// Whether the status has no successor.
    pub fn is_terminal(self) -> bool {
        self.successor().is_none()
    }
}

impl fmt::Display for Status {
    fn fmt(&self, f: &mut fmt::Formatter<'_>) -> fmt::Result {
        f.write_str(self.as_str())
    }
}

impl FromStr for Status {
    type Err = ItemError;

    fn from_str(s: &str) -> Result<Self, Self::Err> {
        match s {
            "todo" => Ok(Status::Todo),
            "doing" => Ok(Status::Doing),
            "done" => Ok(Status::Done),
            other => Err(ItemError::StatusUnknown {
                value: other.to_owned(),
            }),
        }
    }
}

/// Advance `current` by one step.
///
/// Fails with [`ItemError::StatusTerminal`] when `current` is `done`.
pub fn next_status(current: Status) -> Result<Status, ItemError> {
    current
        .successor()
        .ok_or(ItemError::StatusTerminal { status: current })
}

/// Move from `from` to `to`, enforcing the state machine.
///
/// Only single forward steps are allowed. Anything else, including staying in
/// the same status, fails with [`ItemError::TransitionInvalid`].
pub fn transition(from: Status, to: Status) -> Result<Status, ItemError> {
    if from.successor() == Some(to) {
        Ok(to)
    } else {
        Err(ItemError::TransitionInvalid { from, to })
    }
}

#[cfg(test)]
mod tests {
    use super::*;

    #[test]
    fn parses_and_prints_round_trip() {
        for status in Status::ALL {
            assert_eq!(status.as_str().parse::<Status>().unwrap(), status);
            assert_eq!(status.to_string(), status.as_str());
        }
    }

    #[test]
    fn rejects_unknown_names() {
        assert_eq!(
            "Todo".parse::<Status>(),
            Err(ItemError::StatusUnknown {
                value: "Todo".into()
            })
        );
        assert!("".parse::<Status>().is_err());
        assert!("archived".parse::<Status>().is_err());
    }

    #[test]
    fn next_status_walks_the_lifecycle() {
        assert_eq!(next_status(Status::Todo), Ok(Status::Doing));
        assert_eq!(next_status(Status::Doing), Ok(Status::Done));
        assert_eq!(
            next_status(Status::Done),
            Err(ItemError::StatusTerminal {
                status: Status::Done
            })
        );
    }

    #[test]
    fn only_done_is_terminal() {
        assert!(!Status::Todo.is_terminal());
        assert!(!Status::Doing.is_terminal());
        assert!(Status::Done.is_terminal());
    }

    #[test]
    fn transition_allows_exactly_the_forward_steps() {
        for from in Status::ALL {
            for to in Status::ALL {
                let allowed = matches!(
                    (from, to),
                    (Status::Todo, Status::Doing) | (Status::Doing, Status::Done)
                );
                let result = transition(from, to);
                if allowed {
                    assert_eq!(result, Ok(to), "{from} -> {to}");
                } else {
                    assert_eq!(
                        result,
                        Err(ItemError::TransitionInvalid { from, to }),
                        "{from} -> {to}"
                    );
                }
            }
        }
    }

    #[test]
    fn transition_agrees_with_next_status() {
        for from in Status::ALL {
            if let Ok(to) = next_status(from) {
                assert_eq!(transition(from, to), Ok(to));
            }
        }
    }
}
