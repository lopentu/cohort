"""CbetaReader: hash-verified archive extraction and TEI excerpt location,
tested against a synthetic fixture — no real CBETA archive exists on this
machine, or in the labmate's own parallel project's repo, at the time this
was written (docs/roadmap.md "Scope revision", CBETA workstream).
"""
from __future__ import annotations

import hashlib
import zipfile
from io import BytesIO

import pytest

from cohort.sources.cbeta_reader import (
    CBETA_ENTRY_PREFIX,
    CbetaArchiveError,
    CbetaReader,
    find_text_content_start,
    locate_span,
    read_verified_entry,
    verify_archive_hash,
)

ENTRY_PATH = "Bookcase/CBETA/XML/T/T02/T02n0099_001.xml"
DOCUMENT = (
    '<?xml version="1.0" encoding="UTF-8"?>\n'
    "<TEI><teiHeader><fileDesc>synthetic test fixture, mentions 諸行無常 in metadata too"
    "</fileDesc></teiHeader><text>諸行無常。是生滅法。</text></TEI>\n"
).encode()


def _build_archive(tmp_path, entries: dict[str, bytes]) -> tuple:
    buf = BytesIO()
    with zipfile.ZipFile(buf, "w") as zf:
        for name, data in entries.items():
            zf.writestr(name, data)
    archive_bytes = buf.getvalue()
    path = tmp_path / "synthetic-cbeta.zip"
    path.write_bytes(archive_bytes)
    return path, hashlib.sha256(archive_bytes).hexdigest()


@pytest.fixture
def archive(tmp_path):
    return _build_archive(tmp_path, {ENTRY_PATH: DOCUMENT})


# --- archive hash verification ----------------------------------------------

def test_verify_archive_hash_succeeds_on_match(archive):
    path, digest = archive
    verify_archive_hash(path, digest)  # should not raise


def test_verify_archive_hash_fails_on_mismatch(archive):
    path, _ = archive
    with pytest.raises(CbetaArchiveError, match="hash mismatch"):
        verify_archive_hash(path, "0" * 64)


def test_verify_archive_hash_fails_on_missing_file(tmp_path):
    with pytest.raises(CbetaArchiveError, match="not found"):
        verify_archive_hash(tmp_path / "missing.zip", "0" * 64)


# --- verified entry extraction -----------------------------------------------

def test_read_verified_entry_succeeds(archive):
    path, digest = archive
    data = read_verified_entry(path, digest, ENTRY_PATH, max_bytes=10_000)
    assert data == DOCUMENT


def test_read_verified_entry_fails_on_missing_entry(archive):
    path, digest = archive
    with pytest.raises(CbetaArchiveError, match="not found in archive"):
        read_verified_entry(path, digest, "Bookcase/CBETA/XML/T/T99/nope.xml", max_bytes=10_000)


def test_read_verified_entry_fails_on_duplicate_entry(tmp_path):
    buf = BytesIO()
    with zipfile.ZipFile(buf, "w") as zf:
        zf.writestr(ENTRY_PATH, DOCUMENT)
        with pytest.warns(UserWarning, match="Duplicate name"):
            zf.writestr(ENTRY_PATH, DOCUMENT)  # same name written twice — zipfile permits this
    archive_bytes = buf.getvalue()
    path = tmp_path / "dup.zip"
    path.write_bytes(archive_bytes)
    digest = hashlib.sha256(archive_bytes).hexdigest()
    with pytest.raises(CbetaArchiveError, match="more than once"):
        read_verified_entry(path, digest, ENTRY_PATH, max_bytes=10_000)


def test_read_verified_entry_fails_on_oversized_entry(archive):
    path, digest = archive
    with pytest.raises(CbetaArchiveError, match="exceeding"):
        read_verified_entry(path, digest, ENTRY_PATH, max_bytes=10)


# --- TEI header skip ----------------------------------------------------------

def test_find_text_content_start_succeeds():
    start = find_text_content_start(DOCUMENT)
    assert DOCUMENT[start:].startswith("諸行無常".encode())


def test_find_text_content_start_fails_without_header():
    with pytest.raises(CbetaArchiveError, match="teiHeader"):
        find_text_content_start(b"<TEI><text>no header here</text></TEI>")


# --- span location -------------------------------------------------------------

def test_locate_span_succeeds():
    body = "諸行無常。是生滅法。".encode()
    start, end = locate_span(body, "諸行無常")
    assert body[start:end] == "諸行無常".encode()


def test_locate_span_fails_when_absent():
    with pytest.raises(CbetaArchiveError, match="not found"):
        locate_span("諸行無常".encode(), "不存在")


def test_locate_span_fails_when_not_unique():
    body = "諸行無常，諸行無常".encode()
    with pytest.raises(CbetaArchiveError, match="not unique"):
        locate_span(body, "諸行無常")


# --- CbetaReader end-to-end ----------------------------------------------------

def test_cbeta_reader_construction_fails_on_hash_mismatch(archive):
    path, _ = archive
    with pytest.raises(CbetaArchiveError, match="hash mismatch"):
        CbetaReader(path, "0" * 64)


def test_cbeta_reader_search_raises_not_implemented(archive):
    path, digest = archive
    reader = CbetaReader(path, digest)
    with pytest.raises(NotImplementedError, match="no search index"):
        reader.search("諸行無常")


def test_cbeta_reader_search_uses_supplied_index(archive):
    path, digest = archive
    reader = CbetaReader(path, digest, index={ENTRY_PATH: ["諸行無常", "是生滅法"]})
    hits = reader.search("諸行無常")
    assert len(hits) == 1
    assert hits[0].ref == f"{ENTRY_PATH}::諸行無常"
    assert hits[0].title == "T02n0099"
    assert hits[0].snippet == "諸行無常"

    record = reader.fetch(hits[0].ref)
    assert record.witness_ref == "T02n0099"


def test_cbeta_reader_search_respects_max_results(archive):
    path, digest = archive
    reader = CbetaReader(
        path, digest,
        index={ENTRY_PATH: ["諸行無常", "諸行", "諸行無常，是生滅法"]},
    )
    hits = reader.search("諸行", max_results=2)
    assert len(hits) == 2


def test_cbeta_reader_fetch_end_to_end(archive):
    path, digest = archive
    reader = CbetaReader(path, digest)
    record = reader.fetch(f"{ENTRY_PATH}::諸行無常")
    assert record.witness_ref == "T02n0099"
    assert record.title == "T02n0099"
    # record.text is everything from <text>'s opening tag onward — a minimal
    # hand-rolled scan finds where text content *starts*, not where it ends,
    # so the closing </text></TEI> tags are included; that's fine, since the
    # point is a searchable haystack for verify_exact_span, not clean prose.
    assert record.text.startswith("諸行無常。是生滅法。")
    assert "CC BY-NC-SA-equivalent" in record.note
    assert ENTRY_PATH in record.note


def test_cbeta_reader_rejects_a_non_canonical_entry_path(archive):
    path, digest = archive
    reader = CbetaReader(path, digest)
    with pytest.raises(CbetaArchiveError, match="outside the expected CBETA layout"):
        reader.fetch("some/other/path.xml::諸行無常")


def test_cbeta_reader_rejects_a_path_traversal_attempt(archive):
    path, digest = archive
    reader = CbetaReader(path, digest)
    with pytest.raises(CbetaArchiveError, match="outside the expected CBETA layout"):
        reader.fetch(f"{CBETA_ENTRY_PREFIX}../../etc/passwd::x")


def test_cbeta_reader_rejects_an_excerpt_found_only_in_the_header(archive):
    path, digest = archive
    reader = CbetaReader(path, digest)
    with pytest.raises(CbetaArchiveError, match="not found in source text"):
        reader.fetch(f"{ENTRY_PATH}::synthetic test fixture")


def test_cbeta_reader_rejects_a_malformed_ref(archive):
    path, digest = archive
    reader = CbetaReader(path, digest)
    with pytest.raises(CbetaArchiveError, match="malformed ref"):
        reader.fetch("no-separator-here")
