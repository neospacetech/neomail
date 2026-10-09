from pathlib import Path

import pytest

from neomail.cli import main


def test_migrate_apply(capsys: pytest.CaptureFixture[str]) -> None:
    assert main(["migrate", "apply"]) == 0
    assert "no migrations" in capsys.readouterr().out


def test_backup_then_restore(tmp_path: Path) -> None:
    assert main(["backup", str(tmp_path)]) == 0
    assert main(["restore", str(tmp_path)]) == 0


def test_restore_without_backup_fails(tmp_path: Path) -> None:
    assert main(["restore", str(tmp_path)]) == 1
