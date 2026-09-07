"""The full-corpus FTS index, against a synthetic archive.

The invariant every test here defends: **a search hit is always fetchable.**
`CbetaReader.fetch()` resolves a ref only if its excerpt is a unique
contiguous substring of the document body, so an index that returned anything
else would produce results nobody can cite.
"""
from __future__ import annotations

import hashlib
import zipfile
from io import BytesIO

import pytest

from cohort.sources.cbeta_fts import (
    CbetaFtsIndex,
    build_index,
    citable_runs,
)
from cohort.sources.cbeta_reader import CbetaArchiveError, CbetaReader

PREFIX = "Bookcase/CBETA/XML"
ENTRY_T = f"{PREFIX}/T/T08/T08n0251_001.xml"
ENTRY_X = f"{PREFIX}/X/X10/X10n0249_001.xml"


def _document(*runs: str) -> bytes:
    """A document whose text runs are separated by <lb/> markers, exactly as
    CBETA breaks lines — which is what makes runs, not sentences, the unit
    that can be cited."""
    body = "".join(f'<lb n="{i:04d}"/>{run}' for i, run in enumerate(runs, 1))
    return (
        '<?xml version="1.0" encoding="UTF-8"?>\n'
        "<TEI><teiHeader><fileDesc>synthetic fixture</fileDesc></teiHeader>"
        f"<text><p>{body}</p></text></TEI>\n"
    ).encode()


ENTRIES = {
    ENTRY_T: _document("色即是空空即是色", "是諸法空相不生不滅", "重複的句子", "重複的句子"),
    ENTRY_X: _document("色即是空空即是色", "般若波羅蜜多心經"),
}


@pytest.fixture
def archive(tmp_path):
    buf = BytesIO()
    with zipfile.ZipFile(buf, "w") as zf:
        for name, data in ENTRIES.items():
            zf.writestr(name, data)
    raw = buf.getvalue()
    path = tmp_path / "synthetic-cbeta.zip"
    path.write_bytes(raw)
    return path, hashlib.sha256(raw).hexdigest()


@pytest.fixture
def built(archive, tmp_path):
    path, digest = archive
    db = tmp_path / "fts.sqlite"
    report = build_index(path, digest, db, prefix=f"{PREFIX}/")
    return path, digest, db, report


# --- citable_runs ------------------------------------------------------------

def test_citable_runs_keeps_unique_runs_and_drops_repeats():
    body = '<lb/>甲乙丙丁<lb/>重複的句子<lb/>重複的句子'
    runs, not_unique, _ = citable_runs(body)
    assert "甲乙丙丁" in runs
    assert "重複的句子" not in runs  # occurs twice: locate_span could not resolve it
    assert not_unique == 1


def test_citable_runs_drops_a_run_nested_inside_a_longer_one():
    """Uniqueness must be substring occurrence in the body, not distinctness
    among runs: 甲乙 appears both alone and inside 甲乙丙, so it occurs twice
    in the body and is unresolvable."""
    runs, not_unique, _ = citable_runs('<lb/>甲乙丙<lb/>甲乙')
    assert runs == ["甲乙丙"]
    assert not_unique == 1


def test_citable_runs_skips_runs_without_cjk():
    runs, _, too_short = citable_runs('<lb/>12345<lb/>甲乙丙丁')
    assert runs == ["甲乙丙丁"]
    assert too_short == 1


# --- building ----------------------------------------------------------------

def test_build_indexes_every_entry_and_reports_what_it_dropped(built):
    _, _, _, report = built
    assert report.entries_indexed == 2
    assert report.runs_indexed > 0
    assert report.runs_not_unique == 1  # the duplicated line in ENTRY_T


def test_build_refuses_a_hash_mismatch(archive, tmp_path):
    path, _ = archive
    with pytest.raises(CbetaArchiveError, match="hash mismatch"):
        build_index(path, "0" * 64, tmp_path / "fts.sqlite")


def test_index_records_the_archive_hash_it_was_built_from(built):
    _, digest, db, _ = built
    with CbetaFtsIndex(db, digest) as idx:
        assert idx.meta["archive_sha256"] == digest


def test_index_refuses_to_serve_a_different_archive(built):
    """An index paired with the wrong archive would answer queries with
    offsets into a file nobody verified."""
    _, _, db, _ = built
    with pytest.raises(CbetaArchiveError, match="was built from archive"):
        CbetaFtsIndex(db, "0" * 64)


def test_missing_index_file_is_a_clear_error(tmp_path):
    with pytest.raises(CbetaArchiveError, match="no CBETA search index"):
        CbetaFtsIndex(tmp_path / "absent.sqlite")


# --- searching ---------------------------------------------------------------

def test_search_finds_the_phrase_across_collections(built):
    _, digest, db, _ = built
    with CbetaFtsIndex(db, digest) as idx:
        hits = idx.search("色即是空")
    assert {entry for entry, _ in hits} == {ENTRY_T, ENTRY_X}


def test_search_returns_the_containing_run_as_the_excerpt(built):
    _, digest, db, _ = built
    with CbetaFtsIndex(db, digest) as idx:
        hits = idx.search("不生不滅")
    assert hits == [(ENTRY_T, "是諸法空相不生不滅")]


def test_search_does_not_match_across_a_line_boundary(built):
    """The indexed token stream concatenates a document's runs, so FTS5 alone
    would match this; the Python re-check must reject it. Otherwise the hit
    would name an excerpt that exists nowhere contiguously and fetch() would
    refuse it."""
    _, digest, db, _ = built
    with CbetaFtsIndex(db, digest) as idx:
        assert idx.search("空即是色是諸法空相") == []


def test_search_never_returns_a_non_unique_run(built):
    _, digest, db, _ = built
    with CbetaFtsIndex(db, digest) as idx:
        assert idx.search("重複的句子") == []


def test_empty_query_returns_nothing(built):
    _, digest, db, _ = built
    with CbetaFtsIndex(db, digest) as idx:
        assert idx.search("   ") == []


@pytest.mark.parametrize(
    "query", ["，", "。！", '"', "AND", "a OR b", "菩薩*", "(菩薩", "NEAR(甲 乙)", "*"]
)
def test_fts_operators_in_a_query_are_inert_not_errors(built, query):
    """A user's query is text to match, never FTS5 syntax to execute. The
    unigram phrase is quoted and its quotes escaped, so operators and
    unbalanced punctuation match nothing instead of raising or, worse, being
    interpreted."""
    _, digest, db, _ = built
    with CbetaFtsIndex(db, digest) as idx:
        assert idx.search(query) == []


# --- the invariant, end to end ----------------------------------------------

def test_every_search_hit_is_fetchable(built):
    path, digest, db, _ = built
    with CbetaFtsIndex(db, digest) as idx:
        reader = CbetaReader(path, digest, fts=idx)
        for query in ("色即是空", "不生不滅", "般若波羅蜜多"):
            hits = reader.search(query)
            assert hits, f"expected hits for {query}"
            for hit in hits:
                record = reader.fetch(hit.ref)  # raises if not unique/contiguous
                assert hit.snippet in record.text


def test_fts_takes_precedence_over_a_hand_index(built):
    """Both supplied: results must not depend on construction order, and the
    corpus-wide index subsumes the hand-listed one."""
    path, digest, db, _ = built
    with CbetaFtsIndex(db, digest) as idx:
        reader = CbetaReader(
            path, digest, fts=idx, index={ENTRY_T: ["色即是空空即是色"]},
        )
        assert {h.title for h in reader.search("色即是空")} == {"T08n0251", "X10n0249"}


def test_reader_without_any_index_still_refuses(archive):
    path, digest = archive
    reader = CbetaReader(path, digest)
    with pytest.raises(NotImplementedError, match="no search index"):
        reader.search("色即是空")
