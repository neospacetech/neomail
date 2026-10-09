use crate::error::ItemError;

/// Maximum length of a normalised title, in Unicode scalar values.
pub const TITLE_MAX_CHARS: usize = 200;

/// Normalise and validate an item title.
///
/// Leading and trailing whitespace is removed and every internal run of
/// whitespace (spaces, tabs, newlines, any Unicode whitespace) becomes a single
/// ASCII space. The result must be between 1 and [`TITLE_MAX_CHARS`]
/// characters long.
pub fn normalize_title(raw: &str) -> Result<String, ItemError> {
    let normalized = raw.split_whitespace().collect::<Vec<_>>().join(" ");
    let len = normalized.chars().count();
    if len == 0 {
        return Err(ItemError::TitleEmpty);
    }
    if len > TITLE_MAX_CHARS {
        return Err(ItemError::TitleTooLong {
            len,
            max: TITLE_MAX_CHARS,
        });
    }
    Ok(normalized)
}

#[cfg(test)]
mod tests {
    use super::*;

    #[test]
    fn trims_and_collapses_whitespace() {
        assert_eq!(
            normalize_title("  Plan \t the\n\nlaunch  ").unwrap(),
            "Plan the launch"
        );
    }

    #[test]
    fn collapses_unicode_whitespace() {
        // U+00A0 no-break space and U+3000 ideographic space.
        assert_eq!(normalize_title("a\u{00A0}\u{3000}b").unwrap(), "a b");
    }

    #[test]
    fn keeps_already_clean_titles() {
        assert_eq!(normalize_title("Ship it").unwrap(), "Ship it");
    }

    #[test]
    fn rejects_empty_and_blank() {
        assert_eq!(normalize_title(""), Err(ItemError::TitleEmpty));
        assert_eq!(normalize_title(" \t\n "), Err(ItemError::TitleEmpty));
    }

    #[test]
    fn accepts_exactly_max_chars() {
        let title = "x".repeat(TITLE_MAX_CHARS);
        assert_eq!(normalize_title(&title).unwrap(), title);
    }

    #[test]
    fn rejects_over_max_chars() {
        let title = "x".repeat(TITLE_MAX_CHARS + 1);
        assert_eq!(
            normalize_title(&title),
            Err(ItemError::TitleTooLong {
                len: TITLE_MAX_CHARS + 1,
                max: TITLE_MAX_CHARS
            })
        );
    }

    #[test]
    fn length_is_measured_after_normalisation() {
        let padded = format!("   {}   ", "x".repeat(TITLE_MAX_CHARS));
        assert!(normalize_title(&padded).is_ok());
    }

    #[test]
    fn length_counts_characters_not_bytes() {
        // 200 multi-byte characters is still within the limit.
        let title = "é".repeat(TITLE_MAX_CHARS);
        assert_eq!(normalize_title(&title).unwrap().chars().count(), 200);
    }
}
