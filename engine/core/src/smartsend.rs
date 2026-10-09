//! Smart Send: checks a draft's claims against what the sender's calendar
//! and the draft itself say, before the message leaves.
//!
//! [`check_claims`] is a pure function from extracted claims, calendar facts
//! and the draft's recipients and attachments to findings with reasons. Claim
//! extraction from free text is mostly done upstream (NeoMind); the two claims
//! that need no language model, a mentioned attachment and a mentioned
//! recipient, are found by [`extract_local_claims`].
//!
//! Times are Unix seconds and intervals are half-open, so back-to-back
//! commitments do not overlap.

use std::collections::HashSet;
use std::fmt;
use std::str::FromStr;

use serde::{Deserialize, Serialize};

use crate::address::Address;
use crate::error::MailError;

/// Most claims checked at once.
pub const MAX_CLAIMS: usize = 100;
/// Most calendar facts considered at once.
pub const MAX_FACTS: usize = 5000;

/// A half-open span of time `[start, end)` in Unix seconds.
#[derive(Debug, Clone, Copy, PartialEq, Eq, Hash, PartialOrd, Ord, Serialize, Deserialize)]
pub struct Interval {
    pub start: i64,
    pub end: i64,
}

impl Interval {
    pub fn new(start: i64, end: i64) -> Result<Self, MailError> {
        if end <= start {
            return Err(MailError::IntervalInvalid { start, end });
        }
        Ok(Interval { start, end })
    }

    pub fn overlaps(&self, other: &Interval) -> bool {
        self.start < other.end && other.start < self.end
    }
}

macro_rules! wire_enum {
    ($(#[$meta:meta])* $name:ident, $err:ident, { $($variant:ident => $text:literal),+ $(,)? }) => {
        $(#[$meta])*
        #[derive(Debug, Clone, Copy, PartialEq, Eq, Hash, PartialOrd, Ord, Serialize, Deserialize)]
        #[serde(rename_all = "snake_case")]
        pub enum $name { $($variant),+ }

        impl $name {
            pub const ALL: &'static [$name] = &[$($name::$variant),+];

            pub fn as_str(self) -> &'static str {
                match self { $($name::$variant => $text),+ }
            }
        }

        impl fmt::Display for $name {
            fn fmt(&self, f: &mut fmt::Formatter<'_>) -> fmt::Result {
                f.write_str(self.as_str())
            }
        }

        impl FromStr for $name {
            type Err = MailError;

            fn from_str(s: &str) -> Result<Self, Self::Err> {
                match s {
                    $($text => Ok($name::$variant),)+
                    other => Err(MailError::$err { value: other.to_owned() }),
                }
            }
        }
    };
}

wire_enum!(
    /// What a claim in a draft asserts.
    ClaimKind, ClaimKindUnknown, {
        Presence => "presence",
        MeetingTime => "meeting_time",
        Availability => "availability",
        AttachmentRef => "attachment_ref",
        RecipientRef => "recipient_ref",
    }
);

wire_enum!(
    /// What a calendar fact records about the sender's time.
    FactKind, FactKindUnknown, {
        Busy => "busy",
        Travel => "travel",
        Ooo => "ooo",
        Focus => "focus",
    }
);

/// Which rule produced a finding.
#[derive(Debug, Clone, Copy, PartialEq, Eq, Hash, PartialOrd, Ord, Serialize, Deserialize)]
#[serde(rename_all = "snake_case")]
pub enum Rule {
    Overlap,
    OutOfOffice,
    FocusTime,
    ElsewhereThen,
    MissingAttachment,
    MissingRecipient,
}

/// How strongly a finding should interrupt sending. Only `conflict` stops
/// Send for confirmation; `warn` and `info` show in the sidebar.
#[derive(Debug, Clone, Copy, PartialEq, Eq, Hash, PartialOrd, Ord, Serialize, Deserialize)]
#[serde(rename_all = "snake_case")]
pub enum Severity {
    Info,
    Warn,
    Conflict,
}

/// One claim extracted from a draft.
#[derive(Debug, Clone, PartialEq, Eq, Serialize, Deserialize)]
#[serde(deny_unknown_fields)]
pub struct Claim {
    pub id: String,
    /// One of [`ClaimKind`]'s names.
    pub kind: String,
    /// Start and end (Unix seconds) for time claims.
    #[serde(default, skip_serializing_if = "Option::is_none")]
    pub start: Option<i64>,
    #[serde(default, skip_serializing_if = "Option::is_none")]
    pub end: Option<i64>,
    /// Place named by a presence claim.
    #[serde(default, skip_serializing_if = "Option::is_none")]
    pub place: Option<String>,
    /// Person named by a recipient claim.
    #[serde(default, skip_serializing_if = "Option::is_none")]
    pub name: Option<String>,
    /// `[start, end)` character offsets of the claim in the draft text.
    #[serde(default, skip_serializing_if = "Option::is_none")]
    pub span: Option<[usize; 2]>,
}

fn visible_by_default() -> bool {
    true
}

/// One entry of the sender's calendar, as visible to the sender.
#[derive(Debug, Clone, PartialEq, Eq, Serialize, Deserialize)]
#[serde(deny_unknown_fields)]
pub struct CalendarFact {
    /// Object reference the sender can open.
    pub id: String,
    /// One of [`FactKind`]'s names.
    pub kind: String,
    pub start: i64,
    pub end: i64,
    #[serde(default)]
    pub title: Option<String>,
    #[serde(default)]
    pub place: Option<String>,
    /// False when the sender may only see free/busy; the explanation then
    /// leaves out the title and place.
    #[serde(default = "visible_by_default")]
    pub visible: bool,
}

/// What the draft itself contains.
#[derive(Debug, Clone, Default, PartialEq, Eq, Serialize, Deserialize)]
#[serde(deny_unknown_fields)]
pub struct DraftContext {
    /// Raw To, Cc and Bcc entries.
    #[serde(default)]
    pub recipients: Vec<String>,
    /// File names of attachments.
    #[serde(default)]
    pub attachments: Vec<String>,
}

/// A problem with one claim.
#[derive(Debug, Clone, PartialEq, Eq, Serialize, Deserialize)]
pub struct Finding {
    pub claim: String,
    pub rule: Rule,
    pub severity: Severity,
    /// One sentence for the sender.
    pub why: String,
    /// Calendar fact ids backing the finding.
    pub evidence: Vec<String>,
    /// Where the claim is in the draft, when known.
    pub span: Option<[usize; 2]>,
}

struct Fact<'a> {
    raw: &'a CalendarFact,
    kind: FactKind,
    interval: Interval,
}

fn claim_invalid(reason: impl Into<String>) -> MailError {
    MailError::ClaimInvalid {
        reason: reason.into(),
    }
}

fn fold(text: &str) -> String {
    text.split_whitespace()
        .collect::<Vec<_>>()
        .join(" ")
        .to_lowercase()
}

/// Two place names refer to different places when neither contains the other
/// ("Chennai" and "Chennai airport" are the same place for this rule).
fn different_places(a: &str, b: &str) -> bool {
    let (a, b) = (fold(a), fold(b));
    !a.is_empty() && !b.is_empty() && !a.contains(&b) && !b.contains(&a)
}

fn what(fact: &CalendarFact) -> String {
    match (&fact.title, fact.visible) {
        (Some(title), true) => format!(" (\"{title}\")"),
        _ => String::new(),
    }
}

fn recipient_matches(name: &str, recipients: &[Address]) -> bool {
    let wanted: Vec<String> = name.split_whitespace().map(str::to_lowercase).collect();
    let Some(first) = wanted.first() else {
        return true;
    };
    recipients.iter().any(|r| {
        let display = r.name().map(str::to_lowercase).unwrap_or_default();
        let tokens: Vec<&str> = display
            .split(|c: char| !c.is_alphanumeric())
            .filter(|t| !t.is_empty())
            .collect();
        tokens.contains(&first.as_str()) || r.local().to_lowercase().contains(first.as_str())
    })
}

/// Check `claims` against the sender's calendar `facts` and the `draft`.
///
/// * `meeting_time`: a busy or travel fact overlapping it is a conflict, as is
///   being out of office; focus time is a warning.
/// * `availability`: any busy, travel or out-of-office fact overlapping the
///   stated free time is a conflict; focus time is informational.
/// * `presence`: a located fact overlapping the claim at a different place is
///   a conflict.
/// * `attachment_ref`: a warning when nothing is attached.
/// * `recipient_ref`: a warning when no recipient matches the named person.
///
/// Findings are ordered by claim, most severe first, then by rule and
/// evidence, so the same input always gives the same output.
pub fn check_claims(
    claims: &[Claim],
    facts: &[CalendarFact],
    draft: &DraftContext,
) -> Result<Vec<Finding>, MailError> {
    if claims.len() > MAX_CLAIMS {
        return Err(claim_invalid(format!(
            "at most {MAX_CLAIMS} claims are checked at once"
        )));
    }
    if facts.len() > MAX_FACTS {
        return Err(MailError::PayloadInvalid {
            reason: format!("at most {MAX_FACTS} calendar facts are checked at once"),
        });
    }
    let facts = facts
        .iter()
        .map(|raw| {
            Ok(Fact {
                raw,
                kind: raw.kind.parse()?,
                interval: Interval::new(raw.start, raw.end)?,
            })
        })
        .collect::<Result<Vec<_>, MailError>>()?;
    // Recipients that do not parse cannot match anyone; address validation
    // reports them separately.
    let recipients: Vec<Address> = draft
        .recipients
        .iter()
        .flat_map(|entry| crate::address::parse_address_list(entry).unwrap_or_default())
        .collect();

    let mut seen = HashSet::new();
    let mut findings = Vec::new();
    for claim in claims {
        let id = claim.id.trim();
        if id.is_empty() {
            return Err(claim_invalid("claim ids must not be empty"));
        }
        if !seen.insert(id) {
            return Err(claim_invalid(format!("claim id {id:?} is used twice")));
        }
        let kind: ClaimKind = claim.kind.parse()?;
        let mut found = Vec::new();
        let mut push = |rule: Rule, severity: Severity, why: String, evidence: Vec<String>| {
            found.push(Finding {
                claim: id.to_owned(),
                rule,
                severity,
                why,
                evidence,
                span: claim.span,
            });
        };
        match kind {
            ClaimKind::MeetingTime | ClaimKind::Availability | ClaimKind::Presence => {
                let (Some(start), Some(end)) = (claim.start, claim.end) else {
                    return Err(claim_invalid(format!("claim {id:?} needs start and end")));
                };
                let interval = Interval::new(start, end)?;
                let place = claim
                    .place
                    .as_deref()
                    .map(str::trim)
                    .filter(|p| !p.is_empty());
                if kind == ClaimKind::Presence && place.is_none() {
                    return Err(claim_invalid(format!(
                        "presence claim {id:?} needs a place"
                    )));
                }
                for fact in facts.iter().filter(|f| f.interval.overlaps(&interval)) {
                    let evidence = vec![fact.raw.id.clone()];
                    let detail = what(fact.raw);
                    match (kind, fact.kind) {
                        (ClaimKind::Presence, _) => {
                            let Some(there) = fact.raw.place.as_deref() else {
                                continue;
                            };
                            let here = place.unwrap_or_default();
                            if fact.raw.visible && different_places(there, here) {
                                push(
                                    Rule::ElsewhereThen,
                                    Severity::Conflict,
                                    format!("Your calendar has you in {there} then{detail}, not {here}."),
                                    evidence,
                                );
                            }
                        }
                        (_, FactKind::Ooo) => push(
                            Rule::OutOfOffice,
                            Severity::Conflict,
                            format!("You are out of office then{detail}."),
                            evidence,
                        ),
                        (ClaimKind::MeetingTime, FactKind::Focus) => push(
                            Rule::FocusTime,
                            Severity::Warn,
                            format!("This falls in your focus time{detail}."),
                            evidence,
                        ),
                        (_, FactKind::Focus) => push(
                            Rule::FocusTime,
                            Severity::Info,
                            format!("You have focus time then{detail}."),
                            evidence,
                        ),
                        (ClaimKind::Availability, kind) => {
                            push(
                                Rule::Overlap,
                                Severity::Conflict,
                                if kind == FactKind::Travel {
                                    format!("You said you are free, but you are travelling then{detail}.")
                                } else {
                                    format!("You said you are free, but you are busy then{detail}.")
                                },
                                evidence,
                            )
                        }
                        (_, FactKind::Travel) => push(
                            Rule::Overlap,
                            Severity::Conflict,
                            format!("You are travelling then{detail}."),
                            evidence,
                        ),
                        (_, FactKind::Busy) => push(
                            Rule::Overlap,
                            Severity::Conflict,
                            if detail.is_empty() {
                                "You are busy then.".to_owned()
                            } else {
                                format!("This overlaps{detail}.")
                            },
                            evidence,
                        ),
                    }
                }
            }
            ClaimKind::AttachmentRef => {
                if draft.attachments.is_empty() {
                    push(
                        Rule::MissingAttachment,
                        Severity::Warn,
                        "The message mentions an attachment, but nothing is attached.".to_owned(),
                        Vec::new(),
                    );
                }
            }
            ClaimKind::RecipientRef => {
                let name = claim
                    .name
                    .as_deref()
                    .map(str::trim)
                    .filter(|n| !n.is_empty())
                    .ok_or_else(|| claim_invalid(format!("recipient claim {id:?} needs a name")))?;
                if !recipient_matches(name, &recipients) {
                    push(
                        Rule::MissingRecipient,
                        Severity::Warn,
                        format!("The message mentions {name}, but no recipient matches."),
                        Vec::new(),
                    );
                }
            }
        }
        found.sort_by(|a, b| {
            b.severity
                .cmp(&a.severity)
                .then(a.rule.cmp(&b.rule))
                .then_with(|| a.evidence.cmp(&b.evidence))
        });
        findings.extend(found);
    }
    Ok(findings)
}

/// Words that mark an attachment mention.
const ATTACHMENT_WORDS: [&str; 3] = ["attach", "enclosed", "enclosing"];
/// Phrases followed by the name of someone being added to the conversation.
const RECIPIENT_PHRASES: [&str; 5] = [
    "looping in ",
    "cc'ing ",
    "ccing ",
    "copying in ",
    "copying ",
];

fn char_offset(text: &str, byte: usize) -> usize {
    text[..byte].chars().count()
}

/// Find attachment and recipient mentions in a draft's own text.
///
/// Quoted lines (starting with `>`) are skipped, so a reply quoting "see
/// attached" does not count. Recipient mentions take the capitalised word
/// after phrases such as "looping in". Claim ids are `attachment` and
/// `recipient-<n>`; spans are character offsets into `text`.
pub fn extract_local_claims(text: &str) -> Vec<Claim> {
    let mut claims = Vec::new();
    let mut attachment_found = false;
    let mut line_start = 0;
    for line in text.split_inclusive('\n') {
        let offset = line_start;
        line_start += line.len();
        if line.trim_start().starts_with('>') {
            continue;
        }
        let lower = line.to_lowercase();
        if lower.len() != line.len() {
            // Case folding changed byte lengths; offsets would not line up.
            continue;
        }
        if !attachment_found {
            if let Some((at, word)) = ATTACHMENT_WORDS
                .iter()
                .filter_map(|w| lower.find(w).map(|at| (at, *w)))
                .min()
            {
                let start = offset + at;
                claims.push(Claim {
                    id: "attachment".into(),
                    kind: ClaimKind::AttachmentRef.as_str().into(),
                    start: None,
                    end: None,
                    place: None,
                    name: None,
                    span: Some([
                        char_offset(text, start),
                        char_offset(text, start + word.len()),
                    ]),
                });
                attachment_found = true;
            }
        }
        for phrase in RECIPIENT_PHRASES {
            let mut from = 0;
            while let Some(at) = lower[from..].find(phrase) {
                let name_start = from + at + phrase.len();
                from = name_start;
                let name: String = line[name_start..]
                    .chars()
                    .take_while(|c| c.is_alphabetic() || *c == '-' || *c == '\'')
                    .collect();
                if !name.chars().next().is_some_and(char::is_uppercase) {
                    continue;
                }
                let phrase_start = offset + name_start - phrase.len();
                let end = offset + name_start + name.len();
                if claims
                    .iter()
                    .any(|c: &Claim| c.name.as_deref() == Some(name.as_str()))
                {
                    continue;
                }
                claims.push(Claim {
                    id: format!(
                        "recipient-{}",
                        claims.iter().filter(|c| c.kind == "recipient_ref").count() + 1
                    ),
                    kind: ClaimKind::RecipientRef.as_str().into(),
                    start: None,
                    end: None,
                    place: None,
                    name: Some(name),
                    span: Some([char_offset(text, phrase_start), char_offset(text, end)]),
                });
            }
        }
    }
    claims
}

#[cfg(test)]
mod tests {
    use super::*;

    const HOUR: i64 = 3600;
    const T: i64 = 1_791_000_000; // a fixed instant; only differences matter

    fn claim(id: &str, kind: &str, start: i64, end: i64) -> Claim {
        Claim {
            id: id.into(),
            kind: kind.into(),
            start: Some(start),
            end: Some(end),
            place: None,
            name: None,
            span: None,
        }
    }

    fn fact(id: &str, kind: &str, start: i64, end: i64, title: &str) -> CalendarFact {
        CalendarFact {
            id: id.into(),
            kind: kind.into(),
            start,
            end,
            title: (!title.is_empty()).then(|| title.into()),
            place: None,
            visible: true,
        }
    }

    fn rules(findings: &[Finding]) -> Vec<(&str, Rule, Severity)> {
        findings
            .iter()
            .map(|f| (f.claim.as_str(), f.rule, f.severity))
            .collect()
    }

    #[test]
    fn meeting_time_overlapping_a_busy_event_conflicts() {
        let facts = [fact("ev1", "busy", T, T + HOUR, "Design review")];
        let found = check_claims(
            &[claim("c1", "meeting_time", T + HOUR / 2, T + 2 * HOUR)],
            &facts,
            &DraftContext::default(),
        )
        .unwrap();
        assert_eq!(rules(&found), [("c1", Rule::Overlap, Severity::Conflict)]);
        assert_eq!(found[0].why, "This overlaps (\"Design review\").");
        assert_eq!(found[0].evidence, ["ev1"]);
    }

    #[test]
    fn back_to_back_is_fine() {
        let facts = [fact("ev1", "busy", T, T + HOUR, "Design review")];
        let found = check_claims(
            &[claim("c1", "meeting_time", T + HOUR, T + 2 * HOUR)],
            &facts,
            &DraftContext::default(),
        )
        .unwrap();
        assert!(found.is_empty());
    }

    #[test]
    fn hidden_facts_do_not_leak_titles() {
        let mut hidden = fact("ev1", "busy", T, T + HOUR, "Secret interview");
        hidden.visible = false;
        let found = check_claims(
            &[claim("c1", "meeting_time", T, T + HOUR)],
            &[hidden],
            &DraftContext::default(),
        )
        .unwrap();
        assert_eq!(found[0].why, "You are busy then.");
    }

    #[test]
    fn severity_depends_on_claim_and_fact() {
        let facts = [
            fact("focus", "focus", T, T + 2 * HOUR, "Deep work"),
            fact("ooo", "ooo", T + 3 * HOUR, T + 5 * HOUR, ""),
            fact(
                "trip",
                "travel",
                T + 6 * HOUR,
                T + 8 * HOUR,
                "Flight to BLR",
            ),
        ];
        let found = check_claims(
            &[
                claim("meet", "meeting_time", T, T + HOUR),
                claim("free", "availability", T, T + 9 * HOUR),
            ],
            &facts,
            &DraftContext::default(),
        )
        .unwrap();
        assert_eq!(
            rules(&found),
            [
                ("meet", Rule::FocusTime, Severity::Warn),
                ("free", Rule::Overlap, Severity::Conflict),
                ("free", Rule::OutOfOffice, Severity::Conflict),
                ("free", Rule::FocusTime, Severity::Info),
            ]
        );
        assert!(found[1].why.contains("travelling"));
    }

    #[test]
    fn presence_elsewhere_conflicts() {
        let mut offsite = fact("ev1", "busy", T, T + 8 * HOUR, "Offsite");
        offsite.place = Some("Bangalore, Whitefield".into());
        let mut lunch = fact("ev2", "busy", T + 9 * HOUR, T + 10 * HOUR, "Lunch");
        lunch.place = Some("chennai".into());
        let mut c = claim("c1", "presence", T, T + 24 * HOUR);
        c.place = Some("Chennai".into());
        let found = check_claims(&[c], &[offsite, lunch], &DraftContext::default()).unwrap();
        assert_eq!(
            rules(&found),
            [("c1", Rule::ElsewhereThen, Severity::Conflict)]
        );
        assert_eq!(
            found[0].why,
            "Your calendar has you in Bangalore, Whitefield then (\"Offsite\"), not Chennai."
        );
    }

    #[test]
    fn local_claims_check_the_draft() {
        let draft = DraftContext {
            recipients: vec!["Priya Raman <priya@example.org>, bob@example.org".into()],
            attachments: vec![],
        };
        let mut priya = claim("r1", "recipient_ref", 0, 0);
        priya.start = None;
        priya.end = None;
        priya.name = Some("Priya".into());
        let mut john = priya.clone();
        john.id = "r2".into();
        john.name = Some("John".into());
        let attach = Claim {
            id: "a".into(),
            kind: "attachment_ref".into(),
            start: None,
            end: None,
            place: None,
            name: None,
            span: Some([10, 18]),
        };
        let found = check_claims(&[priya, john, attach], &[], &draft).unwrap();
        assert_eq!(
            rules(&found),
            [
                ("r2", Rule::MissingRecipient, Severity::Warn),
                ("a", Rule::MissingAttachment, Severity::Warn),
            ]
        );
        assert_eq!(found[1].span, Some([10, 18]));
        let with_file = DraftContext {
            attachments: vec!["deck.pdf".into()],
            ..draft
        };
        let attach_only = vec![Claim {
            id: "a".into(),
            kind: "attachment_ref".into(),
            start: None,
            end: None,
            place: None,
            name: None,
            span: None,
        }];
        assert!(check_claims(&attach_only, &[], &with_file)
            .unwrap()
            .is_empty());
    }

    #[test]
    fn rejects_malformed_claims_and_facts() {
        let draft = DraftContext::default();
        let code = |claims: &[Claim], facts: &[CalendarFact]| {
            check_claims(claims, facts, &draft).unwrap_err().code()
        };
        assert_eq!(
            code(&[claim("c", "gossip", T, T + 1)], &[]),
            "claim_kind_unknown"
        );
        assert_eq!(
            code(&[claim("c", "meeting_time", T, T)], &[]),
            "interval_invalid"
        );
        assert_eq!(
            code(
                &[
                    claim("c", "meeting_time", T, T + 1),
                    claim("c", "availability", T, T + 1)
                ],
                &[]
            ),
            "claim_invalid"
        );
        assert_eq!(
            code(&[claim(" ", "meeting_time", T, T + 1)], &[]),
            "claim_invalid"
        );
        assert_eq!(
            code(&[claim("p", "presence", T, T + 1)], &[]),
            "claim_invalid"
        );
        let mut no_time = claim("m", "meeting_time", T, T + 1);
        no_time.end = None;
        assert_eq!(code(&[no_time], &[]), "claim_invalid");
        assert_eq!(
            code(
                &[claim("c", "meeting_time", T, T + 1)],
                &[fact("f", "nap", T, T + 1, "")]
            ),
            "fact_kind_unknown"
        );
    }

    #[test]
    fn extracts_attachment_and_recipient_mentions() {
        let text = "Hi all,\nLooping in Priya and cc'ing Ravi. Please see the attached deck.\n> I attached it before\n";
        let claims = extract_local_claims(text);
        let summary: Vec<(&str, &str, Option<&str>)> = claims
            .iter()
            .map(|c| (c.id.as_str(), c.kind.as_str(), c.name.as_deref()))
            .collect();
        assert_eq!(
            summary,
            [
                ("attachment", "attachment_ref", None),
                ("recipient-1", "recipient_ref", Some("Priya")),
                ("recipient-2", "recipient_ref", Some("Ravi")),
            ]
        );
        let [start, end] = claims[0].span.unwrap();
        assert_eq!(
            &text
                .chars()
                .skip(start)
                .take(end - start)
                .collect::<String>(),
            "attach"
        );
        let [start, end] = claims[1].span.unwrap();
        assert_eq!(
            &text
                .chars()
                .skip(start)
                .take(end - start)
                .collect::<String>(),
            "Looping in Priya"
        );
    }

    #[test]
    fn extraction_ignores_quotes_and_lowercase_words() {
        assert!(extract_local_claims("> see attached\n> looping in Priya").is_empty());
        assert!(extract_local_claims("I'm copying the notes below").is_empty());
        assert!(extract_local_claims("").is_empty());
    }

    #[test]
    fn findings_are_deterministic() {
        let facts = [
            fact("b", "busy", T, T + HOUR, "B"),
            fact("a", "busy", T, T + HOUR, "A"),
        ];
        let claims = [claim("c", "meeting_time", T, T + HOUR)];
        let draft = DraftContext::default();
        let first = check_claims(&claims, &facts, &draft).unwrap();
        let mut reversed = facts.to_vec();
        reversed.reverse();
        assert_eq!(first, check_claims(&claims, &reversed, &draft).unwrap());
        assert_eq!(first[0].evidence, ["a"]);
    }
}
