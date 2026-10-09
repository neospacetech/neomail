use crate::error::ItemError;

/// Maximum slug length in bytes (slugs are ASCII, so also in characters).
pub const SLUG_MAX_LEN: usize = 64;

/// Slug used when a title has no ASCII letters or digits at all.
const FALLBACK_SLUG: &str = "item";

/// Derive a URL-safe slug from a title.
///
/// ASCII letters are lower-cased and kept, ASCII digits are kept, and every
/// other run of characters becomes a single hyphen. Leading and trailing
/// hyphens are removed and the result is cut to [`SLUG_MAX_LEN`] at a hyphen
/// boundary when possible. A title with no usable characters yields `"item"`.
/// The output always satisfies [`is_valid_slug`].
pub fn slugify(title: &str) -> String {
    let mut slug = String::with_capacity(title.len().min(SLUG_MAX_LEN));
    let mut pending_hyphen = false;
    for c in title.chars() {
        if c.is_ascii_alphanumeric() {
            if pending_hyphen && !slug.is_empty() {
                slug.push('-');
            }
            pending_hyphen = false;
            slug.push(c.to_ascii_lowercase());
        } else {
            pending_hyphen = true;
        }
    }

    if slug.len() > SLUG_MAX_LEN {
        slug.truncate(SLUG_MAX_LEN);
        if let Some(cut) = slug.rfind('-') {
            // Prefer a word boundary unless that would throw away most of it.
            if cut >= SLUG_MAX_LEN / 2 {
                slug.truncate(cut);
            }
        }
        while slug.ends_with('-') {
            slug.pop();
        }
    }

    if slug.is_empty() {
        FALLBACK_SLUG.to_owned()
    } else {
        slug
    }
}

/// Check that `value` is a well-formed slug, returning it unchanged.
///
/// Fails with [`ItemError::SlugInvalid`] otherwise.
pub fn validate_slug(value: &str) -> Result<&str, ItemError> {
    if is_valid_slug(value) {
        Ok(value)
    } else {
        Err(ItemError::SlugInvalid {
            value: value.to_owned(),
        })
    }
}

/// Whether `value` is a well-formed slug: 1..=[`SLUG_MAX_LEN`] bytes of
/// lowercase ASCII letters and digits separated by single hyphens.
pub fn is_valid_slug(value: &str) -> bool {
    !value.is_empty()
        && value.len() <= SLUG_MAX_LEN
        && value.split('-').all(|part| {
            !part.is_empty()
                && part
                    .bytes()
                    .all(|b| b.is_ascii_lowercase() || b.is_ascii_digit())
        })
}

#[cfg(test)]
mod tests {
    use super::*;

    #[test]
    fn lowercases_and_hyphenates() {
        assert_eq!(slugify("Plan the Launch"), "plan-the-launch");
    }

    #[test]
    fn collapses_separators_and_trims() {
        assert_eq!(slugify("  --Hello,   World!!  "), "hello-world");
    }

    #[test]
    fn keeps_digits() {
        assert_eq!(slugify("Q3 2026 review"), "q3-2026-review");
    }

    #[test]
    fn drops_non_ascii() {
        assert_eq!(slugify("Café déjà vu"), "caf-d-j-vu");
    }

    #[test]
    fn falls_back_when_nothing_usable() {
        assert_eq!(slugify("¿¡!?"), "item");
        assert_eq!(slugify(""), "item");
    }

    #[test]
    fn truncates_at_word_boundary() {
        let title = "alpha ".repeat(20);
        let slug = slugify(&title);
        assert!(slug.len() <= SLUG_MAX_LEN);
        assert!(slug.ends_with("alpha"));
        assert!(is_valid_slug(&slug));
    }

    #[test]
    fn truncates_long_single_word() {
        let slug = slugify(&"x".repeat(100));
        assert_eq!(slug, "x".repeat(SLUG_MAX_LEN));
    }

    #[test]
    fn is_deterministic() {
        assert_eq!(slugify("Same input"), slugify("Same input"));
    }

    #[test]
    fn output_is_always_valid() {
        for title in ["A", "a b c", "--", "Ünïcödé", "x-y_z", &"ab ".repeat(40)] {
            let slug = slugify(title);
            assert!(is_valid_slug(&slug), "{title:?} -> {slug:?}");
        }
    }

    #[test]
    fn validates_slugs() {
        assert!(is_valid_slug("plan-the-launch"));
        assert!(is_valid_slug("a1"));
        assert!(!is_valid_slug(""));
        assert!(!is_valid_slug("Plan"));
        assert!(!is_valid_slug("-plan"));
        assert!(!is_valid_slug("plan-"));
        assert!(!is_valid_slug("plan--it"));
        assert!(!is_valid_slug("plan_it"));
        assert!(!is_valid_slug(&"a".repeat(SLUG_MAX_LEN + 1)));
    }

    #[test]
    fn validate_slug_reports_the_value() {
        assert_eq!(validate_slug("ok-slug"), Ok("ok-slug"));
        assert_eq!(
            validate_slug("Not OK"),
            Err(ItemError::SlugInvalid {
                value: "Not OK".into()
            })
        );
    }
}
