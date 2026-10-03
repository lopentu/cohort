"""Recovery copies must include WAL changes and refuse an active writer."""
import hashlib
import json
import runpy
import sqlite3
from pathlib import Path

import pytest

from cohort.graph import Graph
from cohort.schemas import RESEARCHER, QuestionPayload


def snapshot_function():
    return runpy.run_path(str(Path(__file__).resolve().parents[1] / 'scripts/snapshot_ui.py'))['snapshot']


def test_snapshot_preserves_wal_and_replays_from_saved_log(tmp_path):
    db, log = tmp_path / 'source.sqlite', tmp_path / 'source.jsonl'
    graph = Graph.open(db, log)
    question = graph.ask_question(QuestionPayload(text='Synthetic recovery question', answerable_by='A saved record.'),
                                  authored_by=RESEARCHER)
    keeper = sqlite3.connect(db)
    keeper.execute('SELECT count(*) FROM nodes').fetchone()
    graph.close()
    try:
        assert db.with_suffix('.sqlite-wal').stat().st_size > 0
        destination = tmp_path / 'snapshot'
        report = snapshot_function()(db, log, destination)
        assert report['rebuild']['nodes'] == 1
        with Graph.open_read_only(destination / 'research.sqlite') as restored:
            assert restored.get_node(question).payload['text'] == 'Synthetic recovery question'
            assert restored.rebuild(log_path=destination / 'research.jsonl').ok
        manifest = json.loads((destination / 'snapshot.json').read_text())
        for name, expected in manifest['files'].items():
            assert hashlib.sha256((destination / name).read_bytes()).hexdigest() == expected
            assert (destination / name).stat().st_mode & 0o777 == 0o600
        assert destination.stat().st_mode & 0o777 == 0o700
    finally:
        keeper.close()


def test_snapshot_refuses_writer_and_existing_destination(tmp_path):
    db, log = tmp_path / 'source.sqlite', tmp_path / 'source.jsonl'
    with Graph.open(db, log), pytest.raises(BlockingIOError):
        snapshot_function()(db, log, tmp_path / 'blocked')
    destination = tmp_path / 'existing'
    destination.mkdir()
    sentinel = destination / 'preserve.txt'
    sentinel.write_text('preserve')
    with pytest.raises(FileExistsError):
        snapshot_function()(db, log, destination)
    assert sentinel.read_text() == 'preserve'


def test_snapshot_uses_the_writer_lock_for_a_symlink_filename(tmp_path):
    db, log = tmp_path / 'source.sqlite', tmp_path / 'source.jsonl'
    Graph.open(db, log).close()
    alias = tmp_path / 'alias.sqlite'
    alias.symlink_to(db)
    with Graph.open(alias, log), pytest.raises(BlockingIOError):
        snapshot_function()(alias, log, tmp_path / 'blocked-alias')
    assert not (tmp_path / 'blocked-alias').exists()
