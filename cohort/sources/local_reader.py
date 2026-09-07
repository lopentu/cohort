"""Local text-file reader — a folder of texts you hold rights to.

Reimplements (not imports — COHORT stays standalone, design doc §2) the
character-unigram FTS5 trick from `atelier/atelier/adapters/local_corpus_adapter.py`:
FTS5's default tokenizer treats an unbroken CJK run as a single token, so
`MATCH "寂寞"` against running Chinese text matches nothing at all. Indexing
a space-separated character-unigram copy and phrase-querying it gives exact
character-sequence matching without a segmenter dependency. (One
consequence worth knowing, carried over from the same source: unicode61
drops punctuation, so a phrase query can match across editorial punctuation.)

Its governing rule, also carried over: nothing is inferred from a filename.
A record's identity (`witness_ref`, i.e. which `witness` node it becomes)
comes from a sidecar `manifest.csv` or it does not exist.
"""
from __future__ import annotations

import csv
import sqlite3
import tempfile
import threading
from pathlib import Path

from .base import SearchHit, Source, SourceRecord

MANIFEST_COLUMNS = ("path", "witness_ref", "label", "note")
REQUIRED_COLUMNS = ("path", "witness_ref")


class ManifestError(Exception):
    """The manifest is missing, malformed, or points outside the corpus root."""


def _unigrams(text: str) -> str:
    return " ".join(ch for ch in text if not ch.isspace())


def _phrase(query: str) -> str:
    return '"' + _unigrams(query).replace('"', '""') + '"'


class LocalReader(Source):
    source_name = "local_reader"
    access_mode = "local_rights_held"

    def __init__(self, root: str | Path, manifest: str | Path | None = None) -> None:
        self.root = Path(root).resolve()
        if not self.root.is_dir():
            raise ManifestError(f"corpus root is not a directory: {self.root}")
        self.manifest_path = Path(manifest) if manifest else self.root / "manifest.csv"
        self._meta: dict[str, dict] = {}
        self._tempdir_obj = tempfile.TemporaryDirectory(prefix="cohort_local_reader_")
        self.tempdir = Path(self._tempdir_obj.name)
        #: `check_same_thread=False` plus `_lock` for the same reason as
        #: `CbetaFtsIndex`: the web API serves from a threadpool and runs
        #: agents on a worker thread, so one reader is legitimately shared
        #: across threads. Every query below holds the lock.
        self.conn: sqlite3.Connection | None = sqlite3.connect(
            self.tempdir / "corpus.sqlite", check_same_thread=False
        )
        self._lock = threading.Lock()
        self.stats: dict = {}
        self._load()

    def _db(self) -> sqlite3.Connection:
        if self.conn is None:
            msg = "this reader has been closed"
            raise ManifestError(msg)
        return self.conn

    def close(self) -> None:
        """Tear down the index. The corpus files themselves are untouched."""
        if self.conn is not None:
            self.conn.close()
            self.conn = None
        if self._tempdir_obj is not None:
            self._tempdir_obj.cleanup()
            self._tempdir_obj = None

    def __enter__(self) -> LocalReader:
        return self

    def __exit__(self, *exc) -> None:
        self.close()

    def _resolve(self, rel: str) -> Path:
        candidate = (self.root / rel).resolve()
        if not candidate.is_relative_to(self.root):
            raise ManifestError(f"manifest path escapes the corpus root: {rel!r} -> {candidate}")
        if not candidate.is_file():
            raise ManifestError(f"manifest lists a missing file: {rel!r}")
        return candidate

    def _load(self) -> None:
        if not self.manifest_path.is_file():
            raise ManifestError(
                f"no manifest at {self.manifest_path}. LocalReader reads metadata "
                f"from a sidecar manifest.csv with columns {', '.join(MANIFEST_COLUMNS)} "
                f"— it does not infer metadata from filenames."
            )
        with self.manifest_path.open(encoding="utf-8-sig", newline="") as f:
            reader = csv.DictReader(f)
            header = [h.strip() for h in (reader.fieldnames or [])]
            missing = [c for c in REQUIRED_COLUMNS if c not in header]
            if missing:
                raise ManifestError(
                    f"manifest {self.manifest_path.name} is missing required "
                    f"column(s): {', '.join(missing)}."
                )
            rows = [
                {k.strip(): (v.strip() if isinstance(v, str) else v) for k, v in r.items() if k}
                for r in reader
            ]

        conn = self._db()
        conn.execute("CREATE VIRTUAL TABLE corpus_fts USING fts5(ref UNINDEXED, tokens)")
        conn.execute(
            "CREATE TABLE corpus_meta (ref TEXT PRIMARY KEY, path TEXT, witness_ref TEXT, "
            "label TEXT, note TEXT, text TEXT, chars INTEGER)"
        )

        listed: set[Path] = set()
        for row in rows:
            rel = row.get("path") or ""
            if not rel:
                raise ManifestError("manifest row has an empty `path`.")
            witness_ref = row.get("witness_ref") or ""
            if not witness_ref:
                raise ManifestError(f"manifest row for {rel!r} has an empty `witness_ref`.")
            path = self._resolve(rel)
            listed.add(path)
            text = path.read_text(encoding="utf-8")
            ref = rel.replace("\\", "/")
            meta = {
                "ref": ref,
                "path": str(path.relative_to(self.root)),
                "witness_ref": witness_ref,
                "label": row.get("label") or None,
                "note": row.get("note") or None,
                "text": text,
                "chars": len(text),
            }
            self._meta[ref] = meta
            conn.execute(
                "INSERT INTO corpus_meta VALUES "
                "(:ref, :path, :witness_ref, :label, :note, :text, :chars)", meta,
            )
            conn.execute(
                "INSERT INTO corpus_fts (ref, tokens) VALUES (?, ?)", (ref, _unigrams(text))
            )
        conn.commit()

        on_disk = {p.resolve() for p in self.root.rglob("*.txt") if p.is_file()}
        unlisted = sorted(str(p.relative_to(self.root)) for p in on_disk - listed)
        self.stats = {
            "manifest": self.manifest_path.name,
            "records": len(self._meta),
            "chars": sum(m["chars"] for m in self._meta.values()),
            "unlisted_files": len(unlisted),
            "unlisted_examples": unlisted[:5],
        }

    # --- the source interface ------------------------------------------------

    def search(self, query: str, max_results: int = 20) -> list[SearchHit]:
        assert self.conn is not None
        sql = (
            "SELECT m.ref, m.label, m.path, m.text FROM corpus_fts f "
            "JOIN corpus_meta m USING (ref) WHERE corpus_fts MATCH ? "
            "ORDER BY m.ref LIMIT ?"
        )
        with self._lock:
            rows = self.conn.execute(sql, (_phrase(query), int(max_results))).fetchall()
        hits = []
        for ref, label, path, text in rows:
            idx = text.find(query)
            snippet = text[max(0, idx - 10): idx + len(query) + 10] if idx >= 0 else None
            hits.append(SearchHit(ref=ref, title=label or path, snippet=snippet))
        return hits

    def fetch(self, ref: str) -> SourceRecord:
        meta = self._meta.get(ref)
        if meta is None:
            raise KeyError(f"no such record: {ref!r}")
        return SourceRecord(
            ref=ref, title=meta["label"] or meta["path"], text=meta["text"],
            witness_ref=meta["witness_ref"], locator=meta["path"], note=meta["note"],
        )
