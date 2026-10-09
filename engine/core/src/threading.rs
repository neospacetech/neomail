use std::collections::{BTreeMap, HashMap};

use serde::{Deserialize, Serialize};

use crate::message_id::{extract_message_ids, parse_message_id};
use crate::subject::{is_reply_subject, normalize_subject, subject_key};

/// The headers threading needs from one message.
///
/// `key` is the caller's identifier for the message (an object id); it is
/// what the resulting threads list. `date` is any monotonic timestamp, such as
/// Unix seconds; it only orders messages.
#[derive(Debug, Clone, PartialEq, Eq, Serialize, Deserialize)]
#[serde(deny_unknown_fields)]
pub struct MessageHeaders {
    pub key: String,
    #[serde(default)]
    pub message_id: Option<String>,
    #[serde(default)]
    pub in_reply_to: Option<String>,
    #[serde(default)]
    pub references: Option<String>,
    pub subject: String,
    pub date: i64,
}

/// One conversation.
#[derive(Debug, Clone, PartialEq, Eq, Serialize, Deserialize)]
pub struct ThreadGroup {
    /// Key of the earliest message; stable while the thread only grows.
    pub root: String,
    /// Message keys, oldest first (ties broken by key).
    pub messages: Vec<String>,
    /// Base subject of the root message.
    pub subject: String,
    /// Date of the newest message.
    pub last_date: i64,
}

struct UnionFind {
    parent: Vec<usize>,
}

impl UnionFind {
    fn find(&mut self, mut x: usize) -> usize {
        while self.parent[x] != x {
            self.parent[x] = self.parent[self.parent[x]];
            x = self.parent[x];
        }
        x
    }

    fn union(&mut self, a: usize, b: usize) {
        let (ra, rb) = (self.find(a), self.find(b));
        if ra != rb {
            // Keep the smaller index as the representative so results never
            // depend on hash order.
            let (lo, hi) = if ra < rb { (ra, rb) } else { (rb, ra) };
            self.parent[hi] = lo;
        }
    }
}

/// Group messages into threads.
///
/// 1. **References.** A message joins the thread of every Message-ID in its
///    `References` and `In-Reply-To` headers, even ids of messages that are
///    not in the input, so two replies to a missing message still group.
/// 2. **Subjects.** A message with no reference headers whose subject is a
///    reply (`Re: Budget`) joins the earliest thread whose root has the same
///    base subject, for clients that drop `References`. Messages that are not
///    replies never merge by subject, so unrelated "Hello" mails stay apart.
///
/// Messages repeating a Message-ID that was already seen are kept as their
/// own nodes but join the same thread. The output is deterministic: threads are
/// ordered newest activity first, then by root key.
pub fn build_threads(messages: &[MessageHeaders]) -> Vec<ThreadGroup> {
    let mut nodes: HashMap<String, usize> = HashMap::new();
    let mut uf = UnionFind {
        parent: (0..messages.len()).collect(),
    };
    let mut node_for = |id: String, uf: &mut UnionFind| -> usize {
        *nodes.entry(id).or_insert_with(|| {
            uf.parent.push(uf.parent.len());
            uf.parent.len() - 1
        })
    };

    // Index 0..n are the messages themselves; Message-IDs get extra nodes.
    let mut has_refs = vec![false; messages.len()];
    for (i, m) in messages.iter().enumerate() {
        if let Some(own) = m
            .message_id
            .as_deref()
            .and_then(|id| parse_message_id(id).ok())
        {
            let node = node_for(own, &mut uf);
            uf.union(i, node);
        }
        let refs = m
            .references
            .iter()
            .chain(&m.in_reply_to)
            .flat_map(|header| extract_message_ids(header));
        for id in refs {
            has_refs[i] = true;
            let node = node_for(id, &mut uf);
            uf.union(i, node);
        }
    }

    // Order of messages by (date, key) decides roots.
    let mut order: Vec<usize> = (0..messages.len()).collect();
    order.sort_by(|&a, &b| {
        (messages[a].date, &messages[a].key).cmp(&(messages[b].date, &messages[b].key))
    });

    // Subject fallback: a reference-less reply joins the earliest component
    // whose root (first message in date order) has the same base subject.
    let mut root_of_component: BTreeMap<usize, usize> = BTreeMap::new();
    for &i in &order {
        let c = uf.find(i);
        root_of_component.entry(c).or_insert(i);
    }
    let mut first_by_subject: HashMap<String, usize> = HashMap::new();
    for &i in &order {
        let c = uf.find(i);
        if root_of_component.get(&c) != Some(&i) {
            continue;
        }
        let key = subject_key(&messages[i].subject);
        if key.is_empty() {
            continue;
        }
        match first_by_subject.get(&key) {
            Some(&target) if !has_refs[i] && is_reply_subject(&messages[i].subject) => {
                uf.union(target, i);
            }
            Some(_) => {}
            None => {
                first_by_subject.insert(key, i);
            }
        }
    }

    let mut groups: BTreeMap<usize, Vec<usize>> = BTreeMap::new();
    for &i in &order {
        groups.entry(uf.find(i)).or_default().push(i);
    }
    let mut threads: Vec<ThreadGroup> = groups
        .into_values()
        .map(|members| {
            let root = &messages[members[0]];
            ThreadGroup {
                root: root.key.clone(),
                subject: normalize_subject(&root.subject),
                last_date: members
                    .iter()
                    .map(|&i| messages[i].date)
                    .max()
                    .unwrap_or(root.date),
                messages: members.iter().map(|&i| messages[i].key.clone()).collect(),
            }
        })
        .collect();
    threads.sort_by(|a, b| {
        b.last_date
            .cmp(&a.last_date)
            .then_with(|| a.root.cmp(&b.root))
    });
    threads
}

#[cfg(test)]
mod tests {
    use super::*;

    fn msg(key: &str, id: &str, refs: &str, subject: &str, date: i64) -> MessageHeaders {
        MessageHeaders {
            key: key.into(),
            message_id: (!id.is_empty()).then(|| format!("<{id}>")),
            in_reply_to: None,
            references: (!refs.is_empty()).then(|| refs.into()),
            subject: subject.into(),
            date,
        }
    }

    fn keys(threads: &[ThreadGroup]) -> Vec<Vec<&str>> {
        threads
            .iter()
            .map(|t| t.messages.iter().map(String::as_str).collect())
            .collect()
    }

    #[test]
    fn groups_by_references_and_orders_by_date() {
        let threads = build_threads(&[
            msg("m3", "3@x", "<1@x> <2@x>", "Re: Plan", 30),
            msg("m1", "1@x", "", "Plan", 10),
            msg("m2", "2@x", "<1@x>", "Re: Plan", 20),
            msg("o1", "9@x", "", "Other", 15),
        ]);
        assert_eq!(keys(&threads), [vec!["m1", "m2", "m3"], vec!["o1"]]);
        assert_eq!(threads[0].root, "m1");
        assert_eq!(threads[0].subject, "Plan");
        assert_eq!(threads[0].last_date, 30);
    }

    #[test]
    fn uses_in_reply_to_when_references_are_missing() {
        let mut reply = msg("b", "2@x", "", "Re: Hi", 2);
        reply.in_reply_to = Some("<1@x>".into());
        let threads = build_threads(&[msg("a", "1@x", "", "Hi", 1), reply]);
        assert_eq!(keys(&threads), [vec!["a", "b"]]);
    }

    #[test]
    fn replies_to_a_missing_parent_still_group() {
        let threads = build_threads(&[
            msg("b", "2@x", "<missing@x>", "Re: Q", 2),
            msg("c", "3@x", "<missing@x>", "Re: Q", 3),
        ]);
        assert_eq!(keys(&threads), [vec!["b", "c"]]);
    }

    #[test]
    fn falls_back_to_subject_only_for_reference_less_replies() {
        let threads = build_threads(&[
            msg("a", "1@x", "", "Budget", 1),
            msg("b", "2@x", "", "RE: [fin] budget", 2),
            msg("c", "3@x", "", "Budget", 3),
            msg("d", "4@x", "", "Hello", 4),
            msg("e", "5@x", "", "Hello", 5),
        ]);
        // b is a reply without references and joins a; c and e are new
        // conversations that merely share a subject.
        assert_eq!(
            keys(&threads),
            [vec!["e"], vec!["d"], vec!["c"], vec!["a", "b"]]
        );
    }

    #[test]
    fn reply_with_unrelated_references_does_not_merge_by_subject() {
        let threads = build_threads(&[
            msg("a", "1@x", "", "Status", 1),
            msg("b", "2@x", "<elsewhere@x>", "Re: Status", 2),
        ]);
        assert_eq!(threads.len(), 2);
    }

    #[test]
    fn tolerates_duplicates_missing_ids_and_garbage() {
        let threads = build_threads(&[
            msg("a", "1@x", "", "Hi", 1),
            msg("a-copy", "1@x", "", "Hi", 1),
            msg("n", "", "", "No id", 2),
            msg("g", "not an id", "<<<", "Junk", 3),
        ]);
        assert_eq!(keys(&threads), [vec!["g"], vec!["n"], vec!["a", "a-copy"]]);
    }

    #[test]
    fn is_independent_of_input_order() {
        let mut input = vec![
            msg("m1", "1@x", "", "Plan", 10),
            msg("m2", "2@x", "<1@x>", "Re: Plan", 20),
            msg("m3", "3@x", "<2@x>", "Re: Plan", 30),
            msg("o", "o@x", "", "Other", 25),
        ];
        let expected = build_threads(&input);
        input.reverse();
        assert_eq!(build_threads(&input), expected);
        input.swap(0, 2);
        assert_eq!(build_threads(&input), expected);
    }

    #[test]
    fn empty_input_gives_no_threads() {
        assert!(build_threads(&[]).is_empty());
    }
}
