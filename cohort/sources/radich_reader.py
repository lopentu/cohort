"""The Radich Taishō corpus — one witness per edition, which is the point.

The archive (Zenodo 10.5281/zenodo.7750586, CC-BY-4.0) is laid out as
`T-stripped/{work}/{edition}.txt`: each work directory holds the same text as
it stands in up to seventeen editions — 大 (Taishō), 元 (Yuan), 宋 (Song),
明 (Ming), 麗 (Goryeo), 聖, 宮, 磧, 金藏, 房山 and so on.

**Those editions are not independent witnesses to a translator's style, and
this reader is built so the graph cannot forget it.** The seventeen files for
T0001-1 run 42,223–42,232 bytes: nine bytes apart in forty-two thousand,
~99.98% identical. Pool them into a frequency count and every observation is
multiplied seventeen-fold, and every significance test built on it is
correspondingly overconfident. That is the most likely way a stylometric
result over this corpus is wrong, and it is exactly the error
`Graph.independent_support()` exists to catch — so each edition becomes its
own `witness`, and the relation between editions of one work is left to
`parallel_of`/`descends_from` edges rather than being flattened away here.

A ref is `{work}/{edition}` — `T1595/大`. Nothing is inferred from it beyond
that split: the work id is whatever the directory is called, so
`T0664-3-三身分別品(一)` addresses a single division exactly as the P catalogue
names it, with no parsing of Taishō numbers, juan numbers or titles.

Licence differs from CBETA's and the difference is load-bearing. `note`
becomes `WitnessPayload.source_terms` (see `tools/find_attestations.py`), so
the string below is what every witness drawn from this corpus will assert
about what may be done with it. Copying the CBETA note here would assert
non-commercial and share-alike restrictions that CC-BY-4.0 does not impose —
provenance wrong in the permissive direction is still wrong.
"""
from __future__ import annotations

import sqlite3
import threading
from pathlib import Path

from .base import SearchHit, Source, SourceRecord

#: FTS5's default tokenizer treats an unbroken CJK run as one token, so
#: `MATCH "寂寞"` against running Chinese matches nothing. Indexing a
#: space-separated character-unigram copy and phrase-querying it gives exact
#: character-sequence matching with no segmenter dependency. Same trick as
#: `local_reader.py`, and the same caveat: unicode61 drops punctuation, so a
#: phrase can match across editorial punctuation.
def _unigrams(text: str) -> str:
    return " ".join(ch for ch in text if not ch.isspace())


def _phrase(query: str) -> str:
    return '"' + _unigrams(query).replace('"', '""') + '"'


class CorpusNotFound(Exception):
    """The corpus root is missing, or a requested work is not in it."""


class RadichReader(Source):
    source_name = "radich_taisho"
    #: No non-commercial clause, unlike CBETA — the access mode says so rather
    #: than defaulting to the stricter label out of caution, because a reader
    #: that overstates its restrictions is as wrong as one that understates
    #: them, and this one is quoted into every witness it produces.
    access_mode = "local_rights_held"

    LICENSE_NOTE = (
        "Radich Taishō corpus (Zenodo 10.5281/zenodo.7750586, v1.0) — "
        "CC-BY-4.0: attribution required; no non-commercial or share-alike "
        "restriction"
    )

    def __init__(self, root: str | Path, *, works: list[str] | None = None) -> None:
        """`works` scopes the index to named work directories.

        The whole corpus is 38,369 files and 2.36 GB, most of it near-duplicate
        editions, so indexing all of it to ask about thirty-three works is
        minutes of work for nothing. `works=None` still indexes everything —
        the comparison set for an attribution question is legitimately the rest
        of the canon — but the caller has to ask for it rather than get it by
        default.
        """
        self.root = Path(root).resolve()
        if not self.root.is_dir():
            raise CorpusNotFound(f"corpus root is not a directory: {self.root}")

        self._lock = threading.Lock()
        self.conn = sqlite3.connect(":memory:", check_same_thread=False)
        self._meta: dict[str, dict] = {}
        self._works: dict[str, list[str]] = {}
        self._build(works)

    # --- construction --------------------------------------------------------

    def _build(self, works: list[str] | None) -> None:
        if works is None:
            selected = sorted(p for p in self.root.iterdir() if p.is_dir())
        else:
            selected = []
            for w in works:
                d = self.root / w
                if not d.is_dir():
                    raise CorpusNotFound(f"no work {w!r} under {self.root}")
                selected.append(d)

        self.conn.execute(
            "CREATE VIRTUAL TABLE corpus_fts USING fts5(ref UNINDEXED, tokens)"
        )
        for d in selected:
            editions = []
            for f in sorted(d.glob("*.txt")):
                edition = f.stem
                ref = f"{d.name}/{edition}"
                text = f.read_text(encoding="utf-8", errors="replace")
                self._meta[ref] = {
                    "work": d.name,
                    "edition": edition,
                    "path": str(f.relative_to(self.root)),
                    "text": text,
                    "chars": len(text),
                }
                editions.append(edition)
                self.conn.execute(
                    "INSERT INTO corpus_fts (ref, tokens) VALUES (?, ?)",
                    (ref, _unigrams(text)),
                )
            self._works[d.name] = editions
        self.conn.commit()

        self.stats = {
            "root": str(self.root),
            "works": len(self._works),
            "records": len(self._meta),
            "chars": sum(m["chars"] for m in self._meta.values()),
        }

    def close(self) -> None:
        if self.conn is not None:
            self.conn.close()
            self.conn = None

    def __enter__(self) -> "RadichReader":
        return self

    def __exit__(self, *exc) -> None:
        self.close()

    # --- what is in here -----------------------------------------------------

    def works(self) -> list[str]:
        return sorted(self._works)

    def editions(self, work: str) -> list[str]:
        """The editions this work survives in — the count that says how much of
        a work's apparent support is transmissional redundancy rather than
        independent evidence."""
        if work not in self._works:
            raise CorpusNotFound(f"no work {work!r} in this index")
        return list(self._works[work])

    # --- the source interface ------------------------------------------------

    def search(self, query: str, max_results: int = 20) -> list[SearchHit]:
        """Corpus order, no relevance ranking — the same contract the other
        readers keep, so a count means a count.

        Note that a hit in every edition of one work is one finding reported
        many times. Callers measuring anything should group by work and consult
        `editions()`; this method reports what is there, and does not decide
        that question for them.
        """
        assert self.conn is not None
        sql = (
            "SELECT ref FROM corpus_fts WHERE corpus_fts MATCH ? "
            "ORDER BY ref LIMIT ?"
        )
        with self._lock:
            rows = self.conn.execute(sql, (_phrase(query), int(max_results))).fetchall()
        hits = []
        for (ref,) in rows:
            meta = self._meta[ref]
            idx = meta["text"].find(query)
            snippet = (
                meta["text"][max(0, idx - 10): idx + len(query) + 10]
                if idx >= 0 else None
            )
            hits.append(
                SearchHit(
                    ref=ref,
                    title=f"{meta['work']} ({meta['edition']})",
                    snippet=snippet,
                )
            )
        return hits

    def fetch(self, ref: str) -> SourceRecord:
        meta = self._meta.get(ref)
        if meta is None:
            raise KeyError(
                f"no record {ref!r}. Refs are `{{work}}/{{edition}}`, e.g. "
                f"'T1595/大'; this index holds {len(self._meta)} records "
                f"across {len(self._works)} work(s)."
            )
        return SourceRecord(
            ref=ref,
            title=f"{meta['work']} ({meta['edition']})",
            text=meta["text"],
            # Each edition is its own witness. Collapsing them onto the work
            # would make seventeen near-identical copies look like one text
            # with lots of support, which is the inverse of the truth.
            witness_ref=ref,
            locator=meta["path"],
            note=f"{self.LICENSE_NOTE}; {meta['path']}",
        )
