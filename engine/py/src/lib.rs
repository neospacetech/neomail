//! Python bindings for `neomail-core`, importable as `neomail_core`.
//!
//! The bindings are deliberately thin: strings and small dictionaries for
//! addresses, envelopes and mailboxes, JSON text for the batch operations
//! (threading and Smart Send), and every [`CoreError`] becomes
//! `neomail_core.MailError`, which carries the stable error `code`. No logic
//! lives here.

use neomail_core::{self as core, Address, MailError as CoreError, MailboxRole};
use pyo3::create_exception;
use pyo3::exceptions::PyValueError;
use pyo3::prelude::*;
use pyo3::types::{PyDict, PyList, PyTuple};
use serde::de::DeserializeOwned;
use serde::{Deserialize, Serialize};

create_exception!(
    neomail_core,
    MailError,
    PyValueError,
    "A domain rule rejected the input. `code` holds the stable error code."
);

fn to_py_err(py: Python<'_>, err: CoreError) -> PyErr {
    let py_err = MailError::new_err(err.to_string());
    // Setting an attribute on a freshly created exception instance cannot
    // fail in practice; if it ever did, the message is still meaningful.
    let _ = py_err.value(py).setattr("code", err.code());
    py_err
}

fn payload_err(py: Python<'_>, err: serde_json::Error) -> PyErr {
    to_py_err(
        py,
        CoreError::PayloadInvalid {
            reason: err.to_string(),
        },
    )
}

fn from_json<T: DeserializeOwned>(py: Python<'_>, json: &str) -> PyResult<T> {
    serde_json::from_str(json).map_err(|e| payload_err(py, e))
}

fn to_json<T: Serialize>(py: Python<'_>, value: &T) -> PyResult<String> {
    serde_json::to_string(value).map_err(|e| payload_err(py, e))
}

fn address_dict<'py>(py: Python<'py>, address: &Address) -> PyResult<Bound<'py, PyDict>> {
    let dict = PyDict::new(py);
    dict.set_item("name", address.name())?;
    dict.set_item("email", address.email())?;
    dict.set_item("canonical", address.canonical())?;
    dict.set_item("display", address.to_string())?;
    Ok(dict)
}

fn address_list<'py>(py: Python<'py>, list: &[Address]) -> PyResult<Bound<'py, PyList>> {
    let items = list
        .iter()
        .map(|a| address_dict(py, a))
        .collect::<PyResult<Vec<_>>>()?;
    PyList::new(py, items)
}

fn parse_role(py: Python<'_>, role: &str) -> PyResult<MailboxRole> {
    role.parse().map_err(|e| to_py_err(py, e))
}

/// Parse one address into `{name, email, canonical, display}`.
#[pyfunction]
fn parse_address<'py>(py: Python<'py>, raw: &str) -> PyResult<Bound<'py, PyDict>> {
    let address = Address::parse(raw).map_err(|e| to_py_err(py, e))?;
    address_dict(py, &address)
}

/// Parse a comma- or semicolon-separated address list.
#[pyfunction]
fn parse_address_list<'py>(py: Python<'py>, raw: &str) -> PyResult<Bound<'py, PyList>> {
    let list = core::parse_address_list(raw).map_err(|e| to_py_err(py, e))?;
    address_list(py, &list)
}

/// Canonical (case-folded) `local@domain` of one address.
#[pyfunction]
fn normalize_email(py: Python<'_>, raw: &str) -> PyResult<String> {
    core::normalize_email(raw).map_err(|e| to_py_err(py, e))
}

/// Validate sender, recipients and subject; recipients are deduplicated.
#[pyfunction]
fn validate_envelope<'py>(
    py: Python<'py>,
    sender: &str,
    to: Vec<String>,
    cc: Vec<String>,
    bcc: Vec<String>,
    subject: &str,
) -> PyResult<Bound<'py, PyDict>> {
    let envelope =
        core::Envelope::new(sender, &to, &cc, &bcc, subject).map_err(|e| to_py_err(py, e))?;
    let dict = PyDict::new(py);
    dict.set_item("from", address_dict(py, envelope.from())?)?;
    dict.set_item("to", address_list(py, envelope.to())?)?;
    dict.set_item("cc", address_list(py, envelope.cc())?)?;
    dict.set_item("bcc", address_list(py, envelope.bcc())?)?;
    dict.set_item("subject", envelope.subject())?;
    Ok(dict)
}

/// Collapse whitespace and check the subject length.
#[pyfunction]
fn validate_subject(py: Python<'_>, raw: &str) -> PyResult<String> {
    core::validate_subject(raw).map_err(|e| to_py_err(py, e))
}

/// Base subject without reply/forward prefixes and list tags.
#[pyfunction]
fn normalize_subject(raw: &str) -> String {
    core::normalize_subject(raw)
}

/// Whether the subject starts with a reply or forward prefix.
#[pyfunction]
fn is_reply_subject(raw: &str) -> bool {
    core::is_reply_subject(raw)
}

/// Validate a Message-ID; returns it without angle brackets.
#[pyfunction]
fn parse_message_id(py: Python<'_>, raw: &str) -> PyResult<String> {
    core::parse_message_id(raw).map_err(|e| to_py_err(py, e))
}

/// Every Message-ID in a References or In-Reply-To header, in order.
#[pyfunction]
fn extract_message_ids(header: &str) -> Vec<String> {
    core::extract_message_ids(header)
}

/// Normalise a hierarchical mailbox name.
#[pyfunction]
fn normalize_mailbox_name(py: Python<'_>, raw: &str) -> PyResult<String> {
    core::normalize_mailbox_name(raw).map_err(|e| to_py_err(py, e))
}

/// Role suggested by a mailbox name.
#[pyfunction]
fn role_for_name(name: &str) -> &'static str {
    core::role_for_name(name).as_str()
}

/// Display rank of a role (inbox first, custom last).
#[pyfunction]
fn role_rank(py: Python<'_>, role: &str) -> PyResult<usize> {
    parse_role(py, role).map(MailboxRole::rank)
}

/// Check a new mailbox against the owner's existing `(name, role)` pairs.
#[pyfunction]
fn validate_new_mailbox(
    py: Python<'_>,
    name: &str,
    role: &str,
    existing: Vec<(String, String)>,
) -> PyResult<String> {
    let role = parse_role(py, role)?;
    let existing = existing
        .into_iter()
        .map(|(n, r)| Ok((n, parse_role(py, &r)?)))
        .collect::<PyResult<Vec<_>>>()?;
    core::validate_new_mailbox(name, role, &existing).map_err(|e| to_py_err(py, e))
}

/// Group messages into threads: JSON list of headers -> JSON list of threads.
#[pyfunction]
fn build_threads(py: Python<'_>, messages: &str) -> PyResult<String> {
    let messages: Vec<core::MessageHeaders> = from_json(py, messages)?;
    to_json(py, &core::build_threads(&messages))
}

#[derive(Deserialize)]
#[serde(deny_unknown_fields)]
struct SmartSendRequest {
    claims: Vec<core::Claim>,
    #[serde(default)]
    facts: Vec<core::CalendarFact>,
    #[serde(default)]
    draft: core::DraftContext,
}

/// Smart Send: JSON `{claims, facts, draft}` -> JSON list of findings.
#[pyfunction]
fn check_smart_send(py: Python<'_>, request: &str) -> PyResult<String> {
    let request: SmartSendRequest = from_json(py, request)?;
    let findings = core::check_claims(&request.claims, &request.facts, &request.draft)
        .map_err(|e| to_py_err(py, e))?;
    to_json(py, &findings)
}

/// Attachment and recipient mentions in a draft's text, as JSON claims.
#[pyfunction]
fn extract_local_claims(py: Python<'_>, text: &str) -> PyResult<String> {
    to_json(py, &core::extract_local_claims(text))
}

#[pymodule(name = "neomail_core")]
fn init(m: &Bound<'_, PyModule>) -> PyResult<()> {
    let py = m.py();
    m.add("__version__", env!("CARGO_PKG_VERSION"))?;
    m.add("EMAIL_MAX_LEN", core::EMAIL_MAX_LEN)?;
    m.add("SUBJECT_MAX_CHARS", core::SUBJECT_MAX_CHARS)?;
    m.add("MAILBOX_NAME_MAX_CHARS", core::MAILBOX_NAME_MAX_CHARS)?;
    m.add("RECIPIENTS_MAX", core::RECIPIENTS_MAX)?;
    m.add("MAX_CLAIMS", core::MAX_CLAIMS)?;
    m.add(
        "MAILBOX_ROLES",
        PyTuple::new(py, MailboxRole::ALL.map(MailboxRole::as_str))?,
    )?;
    m.add(
        "CLAIM_KINDS",
        PyTuple::new(py, core::ClaimKind::ALL.iter().map(|k| k.as_str()))?,
    )?;
    m.add(
        "FACT_KINDS",
        PyTuple::new(py, core::FactKind::ALL.iter().map(|k| k.as_str()))?,
    )?;
    m.add("ERROR_CODES", PyTuple::new(py, CoreError::CODES)?)?;
    m.add("MailError", py.get_type::<MailError>())?;
    m.add_function(wrap_pyfunction!(parse_address, m)?)?;
    m.add_function(wrap_pyfunction!(parse_address_list, m)?)?;
    m.add_function(wrap_pyfunction!(normalize_email, m)?)?;
    m.add_function(wrap_pyfunction!(validate_envelope, m)?)?;
    m.add_function(wrap_pyfunction!(validate_subject, m)?)?;
    m.add_function(wrap_pyfunction!(normalize_subject, m)?)?;
    m.add_function(wrap_pyfunction!(is_reply_subject, m)?)?;
    m.add_function(wrap_pyfunction!(parse_message_id, m)?)?;
    m.add_function(wrap_pyfunction!(extract_message_ids, m)?)?;
    m.add_function(wrap_pyfunction!(normalize_mailbox_name, m)?)?;
    m.add_function(wrap_pyfunction!(role_for_name, m)?)?;
    m.add_function(wrap_pyfunction!(role_rank, m)?)?;
    m.add_function(wrap_pyfunction!(validate_new_mailbox, m)?)?;
    m.add_function(wrap_pyfunction!(build_threads, m)?)?;
    m.add_function(wrap_pyfunction!(check_smart_send, m)?)?;
    m.add_function(wrap_pyfunction!(extract_local_claims, m)?)?;
    Ok(())
}
