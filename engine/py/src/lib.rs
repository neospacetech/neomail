//! Python bindings for `neomail-core`, importable as `neomail_core`.
//!
//! The bindings are deliberately thin: they convert between Python strings and
//! the core types and turn [`CoreError`] into `neomail_core.ItemError`,
//! which carries the stable error `code`. No logic lives here.

use neomail_core::{self as core, ItemError as CoreError, Status};
use pyo3::create_exception;
use pyo3::exceptions::PyValueError;
use pyo3::prelude::*;
use pyo3::types::{PyDict, PyTuple};

create_exception!(
    neomail_core,
    ItemError,
    PyValueError,
    "A domain rule rejected the input. `code` holds the stable error code."
);

fn to_py_err(py: Python<'_>, err: CoreError) -> PyErr {
    let py_err = ItemError::new_err(err.to_string());
    // Setting an attribute on a freshly created exception instance cannot
    // fail in practice; if it ever did, the message is still meaningful.
    let _ = py_err.value(py).setattr("code", err.code());
    py_err
}

fn parse_status(py: Python<'_>, value: &str) -> PyResult<Status> {
    value.parse().map_err(|e| to_py_err(py, e))
}

/// Normalise and validate an item title.
#[pyfunction]
fn normalize_title(py: Python<'_>, raw: &str) -> PyResult<String> {
    core::normalize_title(raw).map_err(|e| to_py_err(py, e))
}

/// Derive a URL-safe slug from a title.
#[pyfunction]
fn slugify(title: &str) -> String {
    core::slugify(title)
}

/// Whether `value` is a well-formed slug.
#[pyfunction]
fn is_valid_slug(value: &str) -> bool {
    core::is_valid_slug(value)
}

/// Return `value` unchanged if it is a well-formed slug, else raise.
#[pyfunction]
fn validate_slug(py: Python<'_>, value: &str) -> PyResult<String> {
    core::validate_slug(value)
        .map(str::to_owned)
        .map_err(|e| to_py_err(py, e))
}

/// The status that follows `current`.
#[pyfunction]
fn next_status(py: Python<'_>, current: &str) -> PyResult<&'static str> {
    let current = parse_status(py, current)?;
    core::next_status(current)
        .map(Status::as_str)
        .map_err(|e| to_py_err(py, e))
}

/// Move from `current` to `target`, enforcing the state machine.
#[pyfunction]
fn transition(py: Python<'_>, current: &str, target: &str) -> PyResult<&'static str> {
    let from = parse_status(py, current)?;
    let to = parse_status(py, target)?;
    core::transition(from, to)
        .map(Status::as_str)
        .map_err(|e| to_py_err(py, e))
}

/// A validated item.
#[pyclass(module = "neomail_core", name = "Item", eq)]
#[derive(PartialEq)]
struct PyItem {
    inner: core::Item,
}

#[pymethods]
impl PyItem {
    #[new]
    fn new(py: Python<'_>, title: &str) -> PyResult<Self> {
        core::Item::new(title)
            .map(|inner| PyItem { inner })
            .map_err(|e| to_py_err(py, e))
    }

    #[getter]
    fn title(&self) -> &str {
        self.inner.title()
    }

    #[getter]
    fn slug(&self) -> &str {
        self.inner.slug()
    }

    #[getter]
    fn status(&self) -> &'static str {
        self.inner.status().as_str()
    }

    fn rename(&mut self, py: Python<'_>, title: &str) -> PyResult<()> {
        self.inner.rename(title).map_err(|e| to_py_err(py, e))
    }

    fn advance(&mut self, py: Python<'_>) -> PyResult<&'static str> {
        self.inner
            .advance()
            .map(Status::as_str)
            .map_err(|e| to_py_err(py, e))
    }

    fn move_to(&mut self, py: Python<'_>, target: &str) -> PyResult<&'static str> {
        let to = parse_status(py, target)?;
        self.inner
            .move_to(to)
            .map(Status::as_str)
            .map_err(|e| to_py_err(py, e))
    }

    fn to_dict<'py>(&self, py: Python<'py>) -> PyResult<Bound<'py, PyDict>> {
        let dict = PyDict::new(py);
        dict.set_item("title", self.inner.title())?;
        dict.set_item("slug", self.inner.slug())?;
        dict.set_item("status", self.inner.status().as_str())?;
        Ok(dict)
    }

    fn __repr__(&self) -> String {
        format!(
            "Item(title={:?}, slug={:?}, status={:?})",
            self.inner.title(),
            self.inner.slug(),
            self.inner.status().as_str()
        )
    }
}

#[pymodule(name = "neomail_core")]
fn init(m: &Bound<'_, PyModule>) -> PyResult<()> {
    let py = m.py();
    m.add("__version__", env!("CARGO_PKG_VERSION"))?;
    m.add("TITLE_MAX_CHARS", core::TITLE_MAX_CHARS)?;
    m.add("SLUG_MAX_LEN", core::SLUG_MAX_LEN)?;
    m.add(
        "STATUSES",
        PyTuple::new(py, Status::ALL.map(Status::as_str))?,
    )?;
    m.add("ERROR_CODES", PyTuple::new(py, CoreError::CODES)?)?;
    m.add("ItemError", py.get_type::<ItemError>())?;
    m.add_class::<PyItem>()?;
    m.add_function(wrap_pyfunction!(normalize_title, m)?)?;
    m.add_function(wrap_pyfunction!(slugify, m)?)?;
    m.add_function(wrap_pyfunction!(is_valid_slug, m)?)?;
    m.add_function(wrap_pyfunction!(validate_slug, m)?)?;
    m.add_function(wrap_pyfunction!(next_status, m)?)?;
    m.add_function(wrap_pyfunction!(transition, m)?)?;
    Ok(())
}
