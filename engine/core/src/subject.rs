use crate::error::MailError;

/// Maximum subject length in characters (the RFC 5322 line limit).
pub const SUBJECT_MAX_CHARS: usize = 998;

/// Reply and forward prefixes in common mail clients, compared case-insensitively.
/// English, German (AW/WG), Scandinavian (SV/VS), Dutch (Antw/Doorst), French (TR),
/// Italian (R/RIF/I), Spanish (RE/RV) and Portuguese (ENC).
const PREFIXES: [&str; 16] = [
    "re", "fw", "fwd", "aw", "wg", "sv", "vs", "antw", "doorst", "tr", "rif", "r", "i", "rv",
    "enc", "ref",
];

/// Collapse whitespace and enforce [`SUBJECT_MAX_CHARS`]. An empty subject is allowed.
pub fn validate_subject(raw: &str) -> Result<String, MailError> {
    let collapsed = collapse(raw);
    let len = collapsed.chars().count();
    if len > SUBJECT_MAX_CHARS {
        return Err(MailError::SubjectTooLong {
            len,
            max: SUBJECT_MAX_CHARS,
        });
    }
    Ok(collapsed)
}

/// The base subject used for threading and display: whitespace collapsed and
/// every leading reply/forward prefix (`Re:`, `Fwd:`, `AW:`, `Re[2]:`, ...)
/// and mailing-list tag (`[team]`) removed, in any order and repetition.
pub fn normalize_subject(raw: &str) -> String {
    strip(raw).0
}

/// Case-folded [`normalize_subject`], the key subjects are compared by.
pub fn subject_key(raw: &str) -> String {
    normalize_subject(raw).to_lowercase()
}

/// Whether the subject starts with a reply or forward prefix.
pub fn is_reply_subject(raw: &str) -> bool {
    strip(raw).1
}

fn collapse(raw: &str) -> String {
    raw.split_whitespace().collect::<Vec<_>>().join(" ")
}

/// Strip prefixes; returns the base subject and whether a reply/forward prefix was seen.
fn strip(raw: &str) -> (String, bool) {
    let mut rest = collapse(raw);
    let mut replied = false;
    loop {
        if let Some(after) = strip_list_tag(&rest) {
            rest = after;
        } else if let Some(after) = strip_reply_prefix(&rest) {
            rest = after;
            replied = true;
        } else {
            return (rest, replied);
        }
    }
}

/// `[tag] rest` -> `rest`, but only when something follows the tag.
fn strip_list_tag(s: &str) -> Option<String> {
    let inner = s.strip_prefix('[')?;
    let close = inner.find(']')?;
    let after = inner[close + 1..].trim_start();
    (close > 0 && !after.is_empty()).then(|| after.to_owned())
}

/// `Re: rest`, `RE[3]: rest`, `Fwd(2): rest` or `Re : rest` -> `rest`.
fn strip_reply_prefix(s: &str) -> Option<String> {
    let word_end = s
        .char_indices()
        .find(|(_, c)| !c.is_alphabetic())
        .map_or(s.len(), |(i, _)| i);
    let word = s[..word_end].to_lowercase();
    if !PREFIXES.contains(&word.as_str()) {
        return None;
    }
    let mut rest = &s[word_end..];
    for (open, close) in [('[', ']'), ('(', ')')] {
        if let Some(inner) = rest.strip_prefix(open) {
            let end = inner.find(close)?;
            if !inner[..end].chars().all(|c| c.is_ascii_digit()) {
                return None;
            }
            rest = &inner[end + 1..];
            break;
        }
    }
    let after = rest.trim_start().strip_prefix(':')?;
    Some(after.trim_start().to_owned())
}

#[cfg(test)]
mod tests {
    use super::*;

    #[test]
    fn strips_reply_and_forward_prefixes() {
        assert_eq!(normalize_subject("Re: Budget"), "Budget");
        assert_eq!(normalize_subject("RE: Fwd: re:  Budget  Q3"), "Budget Q3");
        assert_eq!(normalize_subject("AW: WG: Angebot"), "Angebot");
        assert_eq!(normalize_subject("Re[2]: Budget"), "Budget");
        assert_eq!(normalize_subject("Re(3) : Budget"), "Budget");
        assert_eq!(normalize_subject("SV: VS: Möte"), "Möte");
    }

    #[test]
    fn strips_list_tags_anywhere_in_the_prefix_run() {
        assert_eq!(normalize_subject("[ops] Re: [ops] Disk full"), "Disk full");
        assert_eq!(normalize_subject("Re: [dev-list] Build"), "Build");
    }

    #[test]
    fn keeps_words_that_only_look_like_prefixes() {
        assert_eq!(
            normalize_subject("Regarding: the plan"),
            "Regarding: the plan"
        );
        assert_eq!(normalize_subject("Re-org update"), "Re-org update");
        assert_eq!(normalize_subject("Re[x]: odd"), "Re[x]: odd");
        assert_eq!(normalize_subject("[only-a-tag]"), "[only-a-tag]");
        assert_eq!(normalize_subject("Re:"), "");
    }

    #[test]
    fn detects_replies() {
        assert!(is_reply_subject("Re: Budget"));
        assert!(is_reply_subject("[x] Fwd: Budget"));
        assert!(!is_reply_subject("[x] Budget"));
        assert!(!is_reply_subject("Budget"));
    }

    #[test]
    fn key_is_case_folded() {
        assert_eq!(subject_key("RE: BUDGET q3"), subject_key("budget Q3"));
    }

    #[test]
    fn validates_length_after_collapsing() {
        assert_eq!(
            validate_subject("  Hello \n world ").unwrap(),
            "Hello world"
        );
        assert_eq!(validate_subject("").unwrap(), "");
        assert!(validate_subject(&"é".repeat(SUBJECT_MAX_CHARS)).is_ok());
        assert_eq!(
            validate_subject(&"x".repeat(SUBJECT_MAX_CHARS + 1)),
            Err(MailError::SubjectTooLong {
                len: SUBJECT_MAX_CHARS + 1,
                max: SUBJECT_MAX_CHARS
            })
        );
    }
}
