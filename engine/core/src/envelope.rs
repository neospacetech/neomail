use std::collections::HashSet;

use crate::address::Address;
use crate::error::MailError;
use crate::subject::validate_subject;

/// Maximum number of distinct recipients across To, Cc and Bcc.
pub const RECIPIENTS_MAX: usize = 500;

/// A validated message envelope: sender, recipients and subject.
///
/// Recipients are deduplicated by canonical address across all three lists;
/// the first occurrence wins in the order To, Cc, Bcc, so a person listed in
/// both To and Bcc stays visible in To only.
#[derive(Debug, Clone, PartialEq, Eq)]
pub struct Envelope {
    from: Address,
    to: Vec<Address>,
    cc: Vec<Address>,
    bcc: Vec<Address>,
    subject: String,
}

impl Envelope {
    /// Validate raw header values. Each recipient entry may itself be a list
    /// (`"a@x.org, b@y.org"`), as users paste them.
    pub fn new<S: AsRef<str>>(
        from: &str,
        to: &[S],
        cc: &[S],
        bcc: &[S],
        subject: &str,
    ) -> Result<Self, MailError> {
        let from = Address::parse(from)?;
        let mut seen = HashSet::new();
        let mut take = |entries: &[S]| -> Result<Vec<Address>, MailError> {
            let mut out = Vec::new();
            for entry in entries {
                for address in crate::address::parse_address_list(entry.as_ref())? {
                    if seen.insert(address.canonical()) {
                        out.push(address);
                    }
                }
            }
            Ok(out)
        };
        let to = take(to)?;
        let cc = take(cc)?;
        let bcc = take(bcc)?;

        let count = to.len() + cc.len() + bcc.len();
        if count == 0 {
            return Err(MailError::RecipientsEmpty);
        }
        if count > RECIPIENTS_MAX {
            return Err(MailError::RecipientsTooMany {
                count,
                max: RECIPIENTS_MAX,
            });
        }
        let subject = validate_subject(subject)?;
        Ok(Envelope {
            from,
            to,
            cc,
            bcc,
            subject,
        })
    }

    pub fn from(&self) -> &Address {
        &self.from
    }

    pub fn to(&self) -> &[Address] {
        &self.to
    }

    pub fn cc(&self) -> &[Address] {
        &self.cc
    }

    pub fn bcc(&self) -> &[Address] {
        &self.bcc
    }

    pub fn subject(&self) -> &str {
        &self.subject
    }

    /// Every recipient in To, Cc, Bcc order.
    pub fn recipients(&self) -> impl Iterator<Item = &Address> {
        self.to.iter().chain(&self.cc).chain(&self.bcc)
    }
}

#[cfg(test)]
mod tests {
    use super::*;

    fn emails(list: &[Address]) -> Vec<String> {
        list.iter().map(Address::email).collect()
    }

    #[test]
    fn validates_and_deduplicates_recipients() {
        let env = Envelope::new(
            "Me <me@example.org>",
            &["a@x.org, B@X.org", "b@x.org"],
            &["A@x.org", "c@x.org"],
            &["c@X.ORG", "d@x.org"],
            "  Plan \t review ",
        )
        .unwrap();
        assert_eq!(env.from().email(), "me@example.org");
        assert_eq!(emails(env.to()), ["a@x.org", "B@x.org"]);
        assert_eq!(emails(env.cc()), ["c@x.org"]);
        assert_eq!(emails(env.bcc()), ["d@x.org"]);
        assert_eq!(env.subject(), "Plan review");
        assert_eq!(env.recipients().count(), 4);
    }

    #[test]
    fn requires_a_recipient() {
        let none: [&str; 0] = [];
        assert_eq!(
            Envelope::new("me@x.org", &none, &none, &["  "], "Hi"),
            Err(MailError::RecipientsEmpty)
        );
    }

    #[test]
    fn caps_recipients() {
        let many: Vec<String> = (0..=RECIPIENTS_MAX)
            .map(|i| format!("u{i}@x.org"))
            .collect();
        let none: [String; 0] = [];
        assert_eq!(
            Envelope::new("me@x.org", &many, &none, &none, ""),
            Err(MailError::RecipientsTooMany {
                count: RECIPIENTS_MAX + 1,
                max: RECIPIENTS_MAX
            })
        );
    }

    #[test]
    fn reports_the_first_bad_field() {
        assert_eq!(
            Envelope::new("", &["a@x.org"], &[], &[], "Hi"),
            Err(MailError::AddressEmpty)
        );
        assert!(matches!(
            Envelope::new("me@x.org", &["nope"], &[], &[], "Hi"),
            Err(MailError::AddressInvalid { .. })
        ));
        assert!(matches!(
            Envelope::new("me@x.org", &["a@x.org"], &[], &[], &"s".repeat(999)),
            Err(MailError::SubjectTooLong { .. })
        ));
    }
}
