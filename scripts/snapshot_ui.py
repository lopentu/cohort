"""Create a private, replay-verified graph snapshot without omitting SQLite WAL."""
from __future__ import annotations

import argparse
import fcntl
import hashlib
import json
import os
import shutil
import sqlite3
import sys
from contextlib import closing
from pathlib import Path
from typing import Any

sys.path.insert(0, str(Path(__file__).resolve().parents[1]))

from cohort.errors import CohortError
from cohort.graph import Graph


def snapshot(db: Path, log: Path, destination: Path) -> dict[str, Any]:
    # Graph derives its lock from the supplied filename, including symlinks.
    # Resolving only here would let a snapshot bypass that writer's lock.
    db, log, destination = db.absolute(), log.absolute(), destination.absolute()
    if not db.is_file() or not log.is_file():
        raise FileNotFoundError('both the database and event log must exist')
    # The same lock used by Graph excludes all supported writers while the
    # SQLite backup and log copy are captured. A busy run is refused, not killed.
    with db.with_suffix(db.suffix + '.lock').open('a') as lock:
        fcntl.flock(lock, fcntl.LOCK_EX | fcntl.LOCK_NB)
        destination.mkdir(mode=0o700, exist_ok=False)
        copied_db, copied_log = destination / 'research.sqlite', destination / 'research.jsonl'
        with (
            closing(sqlite3.connect(db.as_uri() + '?mode=ro', uri=True)) as source,
            closing(sqlite3.connect(copied_db)) as target,
        ):
            source.backup(target)
        copied_db.chmod(0o600)
        shutil.copyfile(log, copied_log)
        copied_log.chmod(0o600)
    # No completion manifest is written unless independent replay agrees with
    # the copied projection. A failed snapshot remains private for diagnosis.
    with Graph.open_read_only(copied_db) as restored:
        if restored.conn.execute('PRAGMA integrity_check').fetchone()[0] != 'ok':
            raise ValueError('snapshot failed SQLite integrity verification')
        rebuild = restored.rebuild(log_path=copied_log)
    hashes = {}
    for path in (copied_db, copied_log):
        with path.open('rb') as handle:
            hashes[path.name] = hashlib.file_digest(handle, 'sha256').hexdigest()
            os.fsync(handle.fileno())
    report = {'version': 1, 'files': hashes, 'rebuild': rebuild.model_dump()}
    manifest = destination / 'snapshot.json'
    with manifest.open('x', encoding='utf-8') as handle:
        os.fchmod(handle.fileno(), 0o600)
        json.dump(report, handle, indent=2)
        handle.write('\n')
        handle.flush()
        os.fsync(handle.fileno())
    # Persist both the contents and the newly created directory's parent entry.
    for directory in (destination, destination.parent):
        directory_fd = os.open(directory, os.O_RDONLY | os.O_DIRECTORY)
        try:
            os.fsync(directory_fd)
        finally:
            os.close(directory_fd)
    return report


def main() -> None:
    parser = argparse.ArgumentParser(description=__doc__)
    parser.add_argument('--db', type=Path, required=True)
    parser.add_argument('--log', type=Path, required=True)
    parser.add_argument('--destination', type=Path, required=True, help='new directory; never overwrite')
    args = parser.parse_args()
    try:
        report = snapshot(args.db, args.log, args.destination)
    except (OSError, ValueError, sqlite3.Error, CohortError):
        parser.exit(1, 'Snapshot failed: check input files, writer activity and replay integrity. '
                      'Any incomplete destination remains private; use a new destination after diagnosis.\n')
    print(json.dumps(report['rebuild']))


if __name__ == '__main__':
    main()
