"""A persistent full-corpus search index over the CBETA archive.

Reimplements (not imports — COHORT stays standalone, docs/design.md §2) the
character-unigram FTS5 trick `local_reader.py` already uses: FTS5's default
tokenizer treats an unbroken CJK run as one token, so `MATCH "寂寞"` against
running Chinese matches nothing. Indexing a space-separated unigram copy and
phrase-querying it gives exact character-sequence matching with no segmenter
dependency.

**What is indexed, and why it is the only honest choice.** Not the document
text, but its maximal *tag-free contiguous runs* — and of those, only the ones
occurring exactly once in the document body. The reason is
`CbetaReader.fetch()`: a ref is `"entry_path::excerpt"`, and `locate_span()`
resolves it only if the excerpt is a unique, contiguous substring of the body.
An index that could return anything else would hand callers search hits that
`fetch()` then refuses — a result you cannot cite, which is worse than no
result. So the index stores exactly the spans this reader can cite, and every
hit it returns is fetchable by construction.

The practical consequence, stated plainly because it will surprise someone:
CBETA marks line beginnings with `<lb/>` roughly every ten to twenty
characters, so a query longer than a line generally matches nothing. That is
not a defect in the index; it is the same boundary `fetch()` already imposes.

**Archive identity is carried in the index.** A build records the archive's
SHA-256, and `CbetaReader` refuses an index whose recorded hash differs from
the one it was constructed with. Otherwise an index built from one archive
version could silently answer queries about another — provenance claims
resting on offsets into a file nobody checked.

Build cost is real: the whole archive is read once (the hash is verified once
for the pass, not per entry — `read_verified_entry` re-hashes the archive
twice per call, which is correct for a single evidentiary fetch and hopeless
across twenty thousand). Indexing is therefore an explicit, manual step
(`scripts/build_cbeta_index.py`), never something a constructor does.
"""
from __future__ import annotations

import re
import sqlite3
import threading
import zipfile
from collections.abc import Callable, Iterator
from pathlib import Path

from pydantic import BaseModel, ConfigDict

from .cbeta_reader import (
    CBETA_ENTRY_PREFIX,
    CbetaArchiveError,
    find_text_content_start,
    verify_archive_hash,
)

SCHEMA_VERSION = 1
_TAG_RE = re.compile(r"<[^>]+>")
#: a run must carry at least one CJK ideograph to be worth indexing;
#: punctuation- or digit-only runs are structural noise, not citable text.
_CJK_RE = re.compile(r"[㐀-鿿豈-﫿]")
#: runs this short are rarely unique and rarely useful as a citation.
MIN_RUN_CHARS = 2


class BuildReport(BaseModel):
    model_config = ConfigDict(extra="forbid")

    entries_indexed: int = 0
    entries_skipped: int = 0
    runs_indexed: int = 0
    #: runs dropped because they occur more than once in their own document,
    #: so `locate_span()` could not resolve them unambiguously.
    runs_not_unique: int = 0
    runs_too_short: int = 0


def _unigrams(text: str) -> str:
    return " ".join(ch for ch in text if not ch.isspace())


def _phrase(query: str) -> str:
    return '"' + _unigrams(query).replace('"', '""') + '"'


def citable_runs(body: str) -> tuple[list[str], int, int]:
    """Maximal tag-free runs of `body` that `locate_span()` could resolve.

    Returns `(runs, not_unique, too_short)`. Uniqueness is tested as
    *substring occurrence in the whole body*, not as distinctness among the
    runs: a run nested inside a longer one occurs twice in the body and is
    just as unresolvable, so comparing runs to each other would quietly admit
    exactly the refs `fetch()` rejects."""
    runs: list[str] = []
    not_unique = too_short = 0
    seen: set[str] = set()
    for chunk in _TAG_RE.split(body):
        run = chunk.strip()
        if not run or run in seen:
            continue
        seen.add(run)
        if len(run) < MIN_RUN_CHARS or not _CJK_RE.search(run):
            too_short += 1
            continue
        first = body.find(run)
        if first == -1 or body.find(run, first + 1) != -1:
            not_unique += 1
            continue
        runs.append(run)
    return runs, not_unique, too_short


def _iter_entries(
    archive_path: Path, prefix: str, limit: int | None
) -> Iterator[tuple[str, bytes]]:
    with zipfile.ZipFile(archive_path) as zf:
        names = sorted(
            n for n in zf.namelist() if n.startswith(prefix) and n.endswith(".xml")
        )
        if limit is not None:
            names = names[:limit]
        for name in names:
            yield name, zf.read(name)


def build_index(
    archive_path: str | Path,
    expected_sha256: str,
    db_path: str | Path,
    *,
    prefix: str = CBETA_ENTRY_PREFIX,
    limit: int | None = None,
    progress: Callable[[int, str], None] | None = None,
) -> BuildReport:
    """Build the index at `db_path`, replacing any existing file.

    The archive hash is verified **once** for the whole pass and recorded in
    the index; see this module's docstring for why that differs from
    `read_verified_entry`'s per-call double check."""
    archive_path = Path(archive_path)
    db_path = Path(db_path)
    verify_archive_hash(archive_path, expected_sha256)

    if db_path.exists():
        db_path.unlink()
    db_path.parent.mkdir(parents=True, exist_ok=True)

    conn = sqlite3.connect(db_path)
    try:
        conn.executescript(
            """
            PRAGMA journal_mode=OFF;
            PRAGMA synchronous=OFF;
            CREATE TABLE meta (key TEXT PRIMARY KEY, value TEXT);
            CREATE TABLE entries (
                id INTEGER PRIMARY KEY,
                entry_path TEXT UNIQUE NOT NULL,
                runs TEXT NOT NULL
            );
            -- contentless: FTS5 keeps only its index, never a second copy of
            -- the token text, which would roughly double the file for nothing.
            CREATE VIRTUAL TABLE entries_fts USING fts5(tokens, content='');
            """
        )
        conn.executemany(
            "INSERT INTO meta VALUES (?, ?)",
            [
                ("schema_version", str(SCHEMA_VERSION)),
                ("archive_sha256", expected_sha256),
                ("archive_name", archive_path.name),
                ("entry_prefix", prefix),
            ],
        )

        report = BuildReport()
        for index, (name, data) in enumerate(_iter_entries(archive_path, prefix, limit), 1):
            try:
                # strict decoding on purpose, matching `CbetaReader.fetch()`.
                # Decoding with errors="replace" here would index replacement
                # characters that are not in the archive's bytes, yielding hits
                # whose refs `fetch()` cannot resolve — the one thing this index
                # must never do.
                body = data[find_text_content_start(data):].decode("utf-8")
            except (CbetaArchiveError, UnicodeDecodeError):
                report.entries_skipped += 1  # not a document `fetch()` could serve
                continue

            runs, not_unique, too_short = citable_runs(body)
            report.runs_not_unique += not_unique
            report.runs_too_short += too_short
            if not runs:
                report.entries_skipped += 1
                continue

            cur = conn.execute(
                "INSERT INTO entries (entry_path, runs) VALUES (?, ?)",
                (name, "\n".join(runs)),
            )
            conn.execute(
                "INSERT INTO entries_fts (rowid, tokens) VALUES (?, ?)",
                (cur.lastrowid, _unigrams(" ".join(runs))),
            )
            report.entries_indexed += 1
            report.runs_indexed += len(runs)

            if progress is not None and index % 500 == 0:
                progress(index, name)
            if index % 2000 == 0:
                conn.commit()

        conn.commit()
        conn.execute("INSERT INTO meta VALUES (?, ?)", ("entries", str(report.entries_indexed)))
        conn.commit()
        return report
    finally:
        conn.close()


class CbetaFtsIndex:
    """Read-only handle on a built index. Construct with the same
    `expected_sha256` the reader uses; a mismatch is refused rather than
    silently answered from the wrong archive version."""

    def __init__(self, db_path: str | Path, expected_sha256: str | None = None) -> None:
        self.db_path = Path(db_path)
        if not self.db_path.is_file():
            raise CbetaArchiveError(f"no CBETA search index at {self.db_path}")
        #: `check_same_thread=False` plus `_lock`, not carelessness: the web
        #: API serves sync endpoints from a threadpool and runs agents on a
        #: worker thread, so one long-lived index handle is legitimately used
        #: from several threads. The connection is `mode=ro`, so there are no
        #: writes to serialise — the lock exists because a sqlite3 connection
        #: multiplexes one cursor-bearing protocol, and two concurrent
        #: `execute`/`fetchall` pairs on the same connection can interleave
        #: and return each other's rows.
        self.conn = sqlite3.connect(
            f"file:{self.db_path}?mode=ro", uri=True, check_same_thread=False
        )
        self.conn.row_factory = sqlite3.Row
        self._lock = threading.Lock()
        self.meta = {
            r["key"]: r["value"] for r in self.conn.execute("SELECT key, value FROM meta")
        }
        version = self.meta.get("schema_version")
        if version != str(SCHEMA_VERSION):
            raise CbetaArchiveError(
                f"index at {self.db_path} has schema version {version}, expected "
                f"{SCHEMA_VERSION}; rebuild it"
            )
        recorded = self.meta.get("archive_sha256")
        if expected_sha256 is not None and recorded != expected_sha256:
            raise CbetaArchiveError(
                f"index at {self.db_path} was built from archive {recorded}, but this "
                f"reader expects {expected_sha256}; rebuild the index for this archive"
            )

    def close(self) -> None:
        self.conn.close()

    def __enter__(self) -> CbetaFtsIndex:
        return self

    def __exit__(self, *exc) -> None:
        self.close()

    def search(self, query: str, max_results: int = 20) -> list[tuple[str, str]]:
        """`(entry_path, excerpt)` pairs, each excerpt a citable run
        containing `query`.

        FTS5 is a *candidate filter* only: the indexed token stream
        concatenates a document's runs, so a phrase straddling two runs can
        match the index while existing nowhere contiguously. Every candidate
        is therefore re-checked in Python against the runs themselves, and a
        document that only matched across a boundary is dropped. Over-fetching
        candidates keeps that filtering from starving the result set.

        **Results are in corpus order, and `max_results` therefore truncates
        arbitrarily — this is a selection risk, not a ranking.** Common
        phrases are genuinely common: 色即是空 occurs in 412 documents,
        如是我聞 in 1,462. Corpus order means the alphabetically-earliest
        collections answer first, so a caller taking the top five gets five
        arbitrary witnesses rather than the five most pertinent.

        No relevance ranking is applied on purpose. BM25 would rank by term
        density and document length, which in this corpus favours short
        commentaries over the canonical scriptures they quote — a scholarly
        judgement about which witnesses matter, silently encoded in
        infrastructure. docs/design.md §5 principle 2 refuses exactly that kind of
        smuggled assertion, and corpus order at least has the virtue of being
        neutral and reproducible.

        The consequence for callers is real and belongs in
        `ConjecturePayload.selection_risks` whenever a conjecture rests on a
        truncated result set: widen `max_results` and filter deliberately, or
        state that the sample was arbitrary."""
        if not query.strip():
            return []
        with self._lock:
            rows = self.conn.execute(
                "SELECT e.entry_path, e.runs FROM entries_fts f "
                "JOIN entries e ON e.id = f.rowid "
                "WHERE entries_fts MATCH ? ORDER BY e.id LIMIT ?",
                (_phrase(query), max(int(max_results) * 8, 64)),
            ).fetchall()

        hits: list[tuple[str, str]] = []
        for row in rows:
            for run in row["runs"].split("\n"):
                if query in run:
                    hits.append((row["entry_path"], run))
                    break
            if len(hits) >= max_results:
                break
        return hits
