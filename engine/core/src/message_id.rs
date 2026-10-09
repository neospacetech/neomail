use crate::error::MailError;

/// Validate a Message-ID and return it without angle brackets.
///
/// Accepts `<left@right>` or `left@right`. Both sides must be non-empty and
/// the identifier must not contain whitespace or further brackets.
pub fn parse_message_id(raw: &str) -> Result<String, MailError> {
    let trimmed = raw.trim();
    let inner = match (trimmed.strip_prefix('<'), trimmed.ends_with('>')) {
        (Some(rest), true) => &rest[..rest.len() - 1],
        (None, false) => trimmed,
        _ => {
            return Err(MailError::MessageIdInvalid {
                value: trimmed.to_owned(),
            })
        }
    };
    let well_formed = inner
        .rsplit_once('@')
        .is_some_and(|(left, right)| !left.is_empty() && !right.is_empty())
        && !inner
            .chars()
            .any(|c| c.is_whitespace() || c.is_control() || c == '<' || c == '>');
    if well_formed {
        Ok(inner.to_owned())
    } else {
        Err(MailError::MessageIdInvalid {
            value: trimmed.to_owned(),
        })
    }
}

/// Every Message-ID in a `References` or `In-Reply-To` header, in order.
///
/// Identifiers are taken from `<...>` groups, so comments and stray words
/// that some clients add are ignored. A header without brackets is read as
/// whitespace-separated identifiers. Duplicates are dropped (first wins) and
/// malformed entries are skipped: threading should degrade, not fail.
pub fn extract_message_ids(header: &str) -> Vec<String> {
    let mut ids: Vec<String> = Vec::new();
    let mut push = |candidate: &str| {
        if let Ok(id) = parse_message_id(candidate) {
            if !ids.contains(&id) {
                ids.push(id);
            }
        }
    };
    if header.contains('<') {
        let mut rest = header;
        while let Some(open) = rest.find('<') {
            let after = &rest[open + 1..];
            match after.find('>') {
                Some(close) => {
                    push(&after[..close]);
                    rest = &after[close + 1..];
                }
                None => break,
            }
        }
    } else {
        header.split_whitespace().for_each(&mut push);
    }
    ids
}

#[cfg(test)]
mod tests {
    use super::*;

    #[test]
    fn parses_bracketed_and_bare_ids() {
        assert_eq!(
            parse_message_id(" <abc@host.example> ").unwrap(),
            "abc@host.example"
        );
        assert_eq!(parse_message_id("abc@host").unwrap(), "abc@host");
    }

    #[test]
    fn rejects_malformed_ids() {
        for raw in [
            "",
            "<>",
            "abc",
            "<abc@host",
            "abc@host>",
            "a b@host",
            "@host",
            "abc@",
        ] {
            assert!(
                matches!(
                    parse_message_id(raw),
                    Err(MailError::MessageIdInvalid { .. })
                ),
                "{raw:?}"
            );
        }
    }

    #[test]
    fn extracts_ids_in_order_without_duplicates() {
        let header = "<a@x>\r\n <b@x> (comment) <a@x>\t<c@x>";
        assert_eq!(extract_message_ids(header), ["a@x", "b@x", "c@x"]);
    }

    #[test]
    fn skips_garbage_and_handles_unbracketed_headers() {
        assert_eq!(
            extract_message_ids("<bad> <ok@x> <unterminated@x"),
            ["ok@x"]
        );
        assert_eq!(extract_message_ids("a@x b@x junk"), ["a@x", "b@x"]);
        assert!(extract_message_ids("").is_empty());
    }
}
