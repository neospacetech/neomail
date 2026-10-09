"""The extension module behaves as its stub promises."""

import neomail_core as core
import pytest


def test_constants() -> None:
    assert core.TITLE_MAX_CHARS == 200
    assert core.STATUSES == ("todo", "doing", "done")
    assert "title_empty" in core.ERROR_CODES


def test_item_error_is_value_error_with_code() -> None:
    with pytest.raises(ValueError, match="must not be empty") as info:
        core.normalize_title("  ")
    assert isinstance(info.value, core.ItemError)
    assert info.value.code == "title_empty"


def test_item_lifecycle() -> None:
    item = core.Item("  Write   docs ")
    assert (item.title, item.slug, item.status) == ("Write docs", "write-docs", "todo")
    assert item.advance() == "doing"
    with pytest.raises(core.ItemError) as info:
        item.move_to("todo")
    assert info.value.code == "transition_invalid"
    assert item.move_to("done") == "done"
    assert item.to_dict() == {"title": "Write docs", "slug": "write-docs", "status": "done"}
