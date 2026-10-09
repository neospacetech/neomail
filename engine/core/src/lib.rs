//! Domain logic for NeoMail.
//!
//! This crate holds every domain decision the product makes: what a valid
//! item title is, how slugs are derived, and which status changes are allowed.
//! It is pure: no I/O, no clock, no randomness. The FastAPI backend calls it
//! through the `neomail_core` Python extension built from `engine/py`.

mod error;
mod item;
mod slug;
mod status;
mod title;

pub use error::ItemError;
pub use item::Item;
pub use slug::{is_valid_slug, slugify, validate_slug, SLUG_MAX_LEN};
pub use status::{next_status, transition, Status};
pub use title::{normalize_title, TITLE_MAX_CHARS};
