use crate::error::ItemError;
use crate::slug::slugify;
use crate::status::{next_status, transition, Status};
use crate::title::normalize_title;

/// A validated item.
///
/// Fields are private so an `Item` can only exist in a valid state: the title
/// is normalised, the slug is derived from it and the status only changes
/// through the state machine.
#[derive(Debug, Clone, PartialEq, Eq)]
pub struct Item {
    title: String,
    slug: String,
    status: Status,
}

impl Item {
    /// Create a new item in status `todo` from a raw, user-supplied title.
    pub fn new(raw_title: &str) -> Result<Self, ItemError> {
        let title = normalize_title(raw_title)?;
        let slug = slugify(&title);
        Ok(Item {
            title,
            slug,
            status: Status::Todo,
        })
    }

    pub fn title(&self) -> &str {
        &self.title
    }

    pub fn slug(&self) -> &str {
        &self.slug
    }

    pub fn status(&self) -> Status {
        self.status
    }

    /// Replace the title, re-deriving the slug.
    pub fn rename(&mut self, raw_title: &str) -> Result<(), ItemError> {
        let title = normalize_title(raw_title)?;
        self.slug = slugify(&title);
        self.title = title;
        Ok(())
    }

    /// Advance one step through the lifecycle.
    pub fn advance(&mut self) -> Result<Status, ItemError> {
        self.status = next_status(self.status)?;
        Ok(self.status)
    }

    /// Move to `to`, enforcing the state machine.
    pub fn move_to(&mut self, to: Status) -> Result<Status, ItemError> {
        self.status = transition(self.status, to)?;
        Ok(self.status)
    }
}

#[cfg(test)]
mod tests {
    use super::*;

    #[test]
    fn new_item_is_normalised_and_todo() {
        let item = Item::new("  Plan   the launch ").unwrap();
        assert_eq!(item.title(), "Plan the launch");
        assert_eq!(item.slug(), "plan-the-launch");
        assert_eq!(item.status(), Status::Todo);
    }

    #[test]
    fn new_item_rejects_bad_titles() {
        assert_eq!(Item::new("   "), Err(ItemError::TitleEmpty));
    }

    #[test]
    fn rename_updates_slug_and_keeps_status() {
        let mut item = Item::new("First").unwrap();
        item.advance().unwrap();
        item.rename("Second  title").unwrap();
        assert_eq!(item.title(), "Second title");
        assert_eq!(item.slug(), "second-title");
        assert_eq!(item.status(), Status::Doing);
    }

    #[test]
    fn failed_rename_leaves_item_unchanged() {
        let mut item = Item::new("Keep me").unwrap();
        let before = item.clone();
        assert!(item.rename("").is_err());
        assert_eq!(item, before);
    }

    #[test]
    fn advance_to_done_then_stops() {
        let mut item = Item::new("Ship").unwrap();
        assert_eq!(item.advance(), Ok(Status::Doing));
        assert_eq!(item.advance(), Ok(Status::Done));
        assert_eq!(
            item.advance(),
            Err(ItemError::StatusTerminal {
                status: Status::Done
            })
        );
        assert_eq!(item.status(), Status::Done);
    }

    #[test]
    fn invalid_move_leaves_status_unchanged() {
        let mut item = Item::new("Skip ahead").unwrap();
        assert_eq!(
            item.move_to(Status::Done),
            Err(ItemError::TransitionInvalid {
                from: Status::Todo,
                to: Status::Done
            })
        );
        assert_eq!(item.status(), Status::Todo);
        assert_eq!(item.move_to(Status::Doing), Ok(Status::Doing));
    }
}
