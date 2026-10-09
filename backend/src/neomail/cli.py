"""``neomail`` command: lifecycle hooks called by the installer.

Mail data lives in NeoDB behind the storage adapter, which owns its schema,
backup and restore; this process keeps nothing on disk. The commands exist so
the installer can treat every component the same way.
"""

import argparse
import json
import sys
from collections.abc import Sequence
from pathlib import Path

from neomail import COMPONENT, __version__

BACKUP_MARKER = f"{COMPONENT}-backup.json"


def _migrate_apply(_: argparse.Namespace) -> int:
    print(f"{COMPONENT}: no migrations to apply")
    return 0


def _backup(args: argparse.Namespace) -> int:
    target = Path(args.directory)
    target.mkdir(parents=True, exist_ok=True)
    marker = {"component": COMPONENT, "version": __version__, "contents": []}
    (target / BACKUP_MARKER).write_text(json.dumps(marker, indent=2) + "\n", encoding="utf-8")
    print(f"{COMPONENT}: backup written to {target}")
    return 0


def _restore(args: argparse.Namespace) -> int:
    marker_path = Path(args.directory) / BACKUP_MARKER
    if not marker_path.is_file():
        print(f"{COMPONENT}: no backup found at {marker_path}", file=sys.stderr)
        return 1
    marker = json.loads(marker_path.read_text(encoding="utf-8"))
    if marker.get("component") != COMPONENT:
        print(f"{COMPONENT}: {marker_path} belongs to another component", file=sys.stderr)
        return 1
    print(f"{COMPONENT}: restored backup from version {marker.get('version')}")
    return 0


def build_parser() -> argparse.ArgumentParser:
    parser = argparse.ArgumentParser(prog=COMPONENT, description=__doc__)
    parser.add_argument("--version", action="version", version=f"%(prog)s {__version__}")
    commands = parser.add_subparsers(dest="command", required=True)

    migrate = commands.add_parser("migrate", help="schema migrations")
    migrate_commands = migrate.add_subparsers(dest="migrate_command", required=True)
    migrate_commands.add_parser("apply", help="apply pending migrations").set_defaults(
        func=_migrate_apply
    )

    backup = commands.add_parser("backup", help="write a backup into DIRECTORY")
    backup.add_argument("directory")
    backup.set_defaults(func=_backup)

    restore = commands.add_parser("restore", help="restore a backup from DIRECTORY")
    restore.add_argument("directory")
    restore.set_defaults(func=_restore)
    return parser


def main(argv: Sequence[str] | None = None) -> int:
    args = build_parser().parse_args(argv)
    code: int = args.func(args)
    return code


if __name__ == "__main__":
    raise SystemExit(main())
