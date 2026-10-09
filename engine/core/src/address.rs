use std::fmt;

use crate::error::MailError;

/// Maximum length of `local@domain` in bytes (RFC 5321 path limit minus the brackets).
pub const EMAIL_MAX_LEN: usize = 254;

/// Maximum length of the local part in bytes (RFC 5321).
pub const LOCAL_MAX_LEN: usize = 64;

const DOMAIN_MAX_LEN: usize = 253;
const LABEL_MAX_LEN: usize = 63;

/// Characters allowed in a dot-atom besides letters and digits (RFC 5322 `atext`).
const ATEXT_SPECIALS: &str = "!#$%&'*+-/=?^_`{|}~";

/// Characters that force a display name to be quoted (RFC 5322 `specials`).
const NAME_SPECIALS: &str = "()<>[]:;@\\,.\"";

/// A parsed mailbox address: an optional display name plus `local@domain`.
///
/// The domain is stored in lower case. The local part keeps its case, because
/// RFC 5321 lets servers treat it case-sensitively, but [`canonical`](Address::canonical)
/// folds it too, which is what NeoMail uses to compare and deduplicate people.
/// Non-ASCII local parts and domains (RFC 6531 / IDN U-labels) are accepted.
#[derive(Debug, Clone, PartialEq, Eq)]
pub struct Address {
    name: Option<String>,
    local: String,
    domain: String,
}

impl Address {
    /// Parse `addr@example.com`, `<addr@example.com>`, `Name <addr@example.com>`
    /// or `"Last, First" <addr@example.com>`.
    pub fn parse(raw: &str) -> Result<Self, MailError> {
        let trimmed = raw.trim();
        if trimmed.is_empty() {
            return Err(MailError::AddressEmpty);
        }
        let invalid = |reason| MailError::AddressInvalid {
            value: trimmed.to_owned(),
            reason,
        };

        let (name, spec) = match find_angle_open(trimmed) {
            Some(open) => {
                let rest = &trimmed[open + 1..];
                let close = rest
                    .find('>')
                    .ok_or_else(|| invalid("unterminated angle bracket"))?;
                if !rest[close + 1..].trim().is_empty() {
                    return Err(invalid("unexpected text after the address"));
                }
                let name = parse_display_name(&trimmed[..open]).map_err(invalid)?;
                (name, rest[..close].trim())
            }
            None => (None, trimmed),
        };

        let (local, domain) = spec.rsplit_once('@').ok_or_else(|| invalid("missing @"))?;
        validate_local(local).map_err(invalid)?;
        let domain = normalize_domain(domain).map_err(invalid)?;

        let len = local.len() + 1 + domain.len();
        if len > EMAIL_MAX_LEN {
            return Err(MailError::AddressTooLong {
                len,
                max: EMAIL_MAX_LEN,
            });
        }
        Ok(Address {
            name,
            local: local.to_owned(),
            domain,
        })
    }

    /// Display name, whitespace-collapsed and unquoted, if one was given.
    pub fn name(&self) -> Option<&str> {
        self.name.as_deref()
    }

    pub fn local(&self) -> &str {
        &self.local
    }

    /// Domain in lower case, without a trailing dot.
    pub fn domain(&self) -> &str {
        &self.domain
    }

    /// `local@domain` as it should be written on the wire.
    pub fn email(&self) -> String {
        format!("{}@{}", self.local, self.domain)
    }

    /// Case-folded `local@domain`, used to compare and deduplicate addresses.
    pub fn canonical(&self) -> String {
        self.email().to_lowercase()
    }
}

impl fmt::Display for Address {
    /// RFC 5322 `name-addr` when there is a name, else the bare address.
    fn fmt(&self, f: &mut fmt::Formatter<'_>) -> fmt::Result {
        match &self.name {
            Some(name) if name.chars().any(|c| NAME_SPECIALS.contains(c)) => {
                let escaped = name.replace('\\', "\\\\").replace('"', "\\\"");
                write!(f, "\"{escaped}\" <{}>", self.email())
            }
            Some(name) => write!(f, "{name} <{}>", self.email()),
            None => f.write_str(&self.email()),
        }
    }
}

/// Parse a header-style list of addresses separated by commas or semicolons.
///
/// Separators inside quoted display names and angle brackets are ignored.
/// Empty entries (`a@x.org,,b@y.org`) are skipped; an empty input gives an
/// empty list. Any malformed entry fails the whole list.
pub fn parse_address_list(raw: &str) -> Result<Vec<Address>, MailError> {
    split_top_level(raw)
        .into_iter()
        .filter(|part| !part.trim().is_empty())
        .map(Address::parse)
        .collect()
}

/// Parse one address and return its canonical `local@domain` form.
pub fn normalize_email(raw: &str) -> Result<String, MailError> {
    Address::parse(raw).map(|a| a.canonical())
}

/// Position of the `<` that opens the address, ignoring any inside a quoted name.
fn find_angle_open(s: &str) -> Option<usize> {
    let mut in_quote = false;
    let mut escaped = false;
    for (i, c) in s.char_indices() {
        match c {
            _ if escaped => escaped = false,
            '\\' if in_quote => escaped = true,
            '"' => in_quote = !in_quote,
            '<' if !in_quote => return Some(i),
            _ => {}
        }
    }
    None
}

fn parse_display_name(raw: &str) -> Result<Option<String>, &'static str> {
    let raw = raw.trim();
    let unquoted = if let Some(inner) = raw.strip_prefix('"') {
        let inner = inner.strip_suffix('"').ok_or("unterminated quote")?;
        let mut out = String::with_capacity(inner.len());
        let mut chars = inner.chars();
        while let Some(c) = chars.next() {
            if c == '\\' {
                out.extend(chars.next());
            } else {
                out.push(c);
            }
        }
        out
    } else {
        raw.to_owned()
    };
    let collapsed = unquoted.split_whitespace().collect::<Vec<_>>().join(" ");
    Ok((!collapsed.is_empty()).then_some(collapsed))
}

fn validate_local(local: &str) -> Result<(), &'static str> {
    if local.is_empty() {
        return Err("empty local part");
    }
    if local.len() > LOCAL_MAX_LEN {
        return Err("local part longer than 64 bytes");
    }
    if let Some(inner) = local.strip_prefix('"') {
        let inner = inner.strip_suffix('"').ok_or("unterminated quote")?;
        return if inner.chars().all(|c| !c.is_control()) {
            Ok(())
        } else {
            Err("control character in local part")
        };
    }
    let atom_ok = |atom: &str| {
        !atom.is_empty()
            && atom
                .chars()
                .all(|c| c.is_alphanumeric() || ATEXT_SPECIALS.contains(c))
    };
    if local.split('.').all(atom_ok) {
        Ok(())
    } else {
        Err("local part has a character that needs quoting or misplaced dots")
    }
}

fn normalize_domain(domain: &str) -> Result<String, &'static str> {
    let domain = domain.strip_suffix('.').unwrap_or(domain).to_lowercase();
    if domain.is_empty() {
        return Err("empty domain");
    }
    if domain.starts_with('[') {
        return Err("address literals are not supported");
    }
    if domain.len() > DOMAIN_MAX_LEN {
        return Err("domain longer than 253 bytes");
    }
    let label_ok = |label: &str| {
        !label.is_empty()
            && label.len() <= LABEL_MAX_LEN
            && !label.starts_with('-')
            && !label.ends_with('-')
            && label.chars().all(|c| c.is_alphanumeric() || c == '-')
    };
    if domain.split('.').all(label_ok) {
        Ok(domain)
    } else {
        Err("domain has an invalid label")
    }
}

/// Split on `,` and `;` that are outside quotes and angle brackets.
fn split_top_level(raw: &str) -> Vec<&str> {
    let mut parts = Vec::new();
    let mut start = 0;
    let mut in_quote = false;
    let mut escaped = false;
    let mut in_angle = false;
    for (i, c) in raw.char_indices() {
        match c {
            _ if escaped => escaped = false,
            '\\' if in_quote => escaped = true,
            '"' if !in_angle => in_quote = !in_quote,
            '<' if !in_quote => in_angle = true,
            '>' if !in_quote => in_angle = false,
            ',' | ';' if !in_quote && !in_angle => {
                parts.push(&raw[start..i]);
                start = i + 1;
            }
            _ => {}
        }
    }
    parts.push(&raw[start..]);
    parts
}

#[cfg(test)]
mod tests {
    use super::*;

    #[test]
    fn parses_bare_address_and_lowercases_domain() {
        let a = Address::parse("  Jane.Doe@Example.COM ").unwrap();
        assert_eq!(a.name(), None);
        assert_eq!(a.local(), "Jane.Doe");
        assert_eq!(a.domain(), "example.com");
        assert_eq!(a.email(), "Jane.Doe@example.com");
        assert_eq!(a.canonical(), "jane.doe@example.com");
        assert_eq!(a.to_string(), "Jane.Doe@example.com");
    }

    #[test]
    fn parses_name_addr() {
        let a = Address::parse("Jane   Doe <jane@example.org>").unwrap();
        assert_eq!(a.name(), Some("Jane Doe"));
        assert_eq!(a.to_string(), "Jane Doe <jane@example.org>");
        let bare = Address::parse("<jane@example.org>").unwrap();
        assert_eq!(bare.name(), None);
    }

    #[test]
    fn parses_quoted_names_with_specials() {
        let a = Address::parse(r#""Doe, Jane \"JD\"" <jane@example.org>"#).unwrap();
        assert_eq!(a.name(), Some(r#"Doe, Jane "JD""#));
        assert_eq!(a.to_string(), r#""Doe, Jane \"JD\"" <jane@example.org>"#);
        let lt = Address::parse(r#""a <b>" <c@d.io>"#).unwrap();
        assert_eq!(lt.name(), Some("a <b>"));
        assert_eq!(lt.email(), "c@d.io");
    }

    #[test]
    fn accepts_plus_tags_quoted_locals_and_unicode() {
        assert!(Address::parse("ops+alerts@example.net").is_ok());
        assert!(Address::parse(r#""john smith"@example.net"#).is_ok());
        let u = Address::parse("用户@例子.广告").unwrap();
        assert_eq!(u.domain(), "例子.广告");
        assert_eq!(
            Address::parse("root@Example.org.").unwrap().domain(),
            "example.org"
        );
    }

    #[test]
    fn rejects_malformed_addresses() {
        let reason = |raw: &str| match Address::parse(raw) {
            Err(MailError::AddressInvalid { reason, .. }) => reason,
            other => panic!("{raw:?} -> {other:?}"),
        };
        assert_eq!(reason("jane"), "missing @");
        assert_eq!(reason("@example.org"), "empty local part");
        assert_eq!(reason("jane@"), "empty domain");
        assert_eq!(
            reason("Jane <jane@example.org"),
            "unterminated angle bracket"
        );
        assert_eq!(
            reason("Jane <jane@example.org> extra"),
            "unexpected text after the address"
        );
        let bad_local = "local part has a character that needs quoting or misplaced dots";
        assert_eq!(reason("a..b@example.org"), bad_local);
        assert_eq!(reason("a b@example.org"), bad_local);
        assert_eq!(reason("a@-bad.org"), "domain has an invalid label");
        assert_eq!(reason("a@exa_mple.org"), "domain has an invalid label");
        assert_eq!(
            reason("a@[192.0.2.1]"),
            "address literals are not supported"
        );
        assert_eq!(Address::parse("   "), Err(MailError::AddressEmpty));
    }

    #[test]
    fn enforces_length_limits() {
        let local = "a".repeat(65);
        assert!(matches!(
            Address::parse(&format!("{local}@example.org")),
            Err(MailError::AddressInvalid { .. })
        ));
        let domain = format!(
            "{}.{}.{}.org",
            "b".repeat(63),
            "c".repeat(63),
            "d".repeat(63)
        );
        let long = format!("{}@{domain}", "a".repeat(64));
        assert!(matches!(
            Address::parse(&long),
            Err(MailError::AddressTooLong { max: 254, .. })
        ));
    }

    #[test]
    fn parses_lists_respecting_quotes_and_brackets() {
        let list =
            parse_address_list(r#""Doe, Jane" <jane@example.org>, bob@example.org; <c@x.io>,, "#)
                .unwrap();
        let emails: Vec<_> = list.iter().map(Address::email).collect();
        assert_eq!(emails, ["jane@example.org", "bob@example.org", "c@x.io"]);
        assert_eq!(parse_address_list("  ").unwrap(), vec![]);
        assert!(parse_address_list("ok@x.io, broken").is_err());
    }

    #[test]
    fn normalize_email_is_canonical() {
        assert_eq!(
            normalize_email("Bob <Bob@Example.ORG>").unwrap(),
            "bob@example.org"
        );
    }
}
