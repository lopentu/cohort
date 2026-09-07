"""Reading a corpus laid out as one file per edition.

The reader's whole job is to *not* collapse editions. Seventeen files for one
work differ by ~0.02%; treating them as seventeen witnesses is correct, and
treating them as one text with lots of support is the error that would make
every count downstream wrong by an order of magnitude.

Hermetic: these build a miniature corpus in `tmp_path` rather than reading the
2.36 GB archive, which is gitignored and absent on any fresh checkout.
"""
from __future__ import annotations

import pytest

from cohort.sources.radich_reader import CorpusNotFound, RadichReader

#: work -> edition -> text. Deliberately near-identical across editions, the
#: way the real corpus is.
FIXTURE = {
    "T0001": {
        "大": "如是我聞一時佛在舍衛國祇樹給孤獨園",
        "元": "如是我聞一時佛在舍衛國祇樹給孤獨園",
        "宋": "如是我聞一時佛在舍衛國祇樹給孤園",   # one character short
    },
    "T0002-1-序品": {
        "大": "阿黎耶識為依止",
        "CB": "阿黎耶識為依止",
    },
    "T0003": {"麗-CB": "無此語"},
}


@pytest.fixture
def corpus(tmp_path):
    for work, editions in FIXTURE.items():
        d = tmp_path / work
        d.mkdir()
        for edition, text in editions.items():
            (d / f"{edition}.txt").write_text(text, encoding="utf-8")
    r = RadichReader(tmp_path)
    yield r
    r.close()


# --- what a ref is -----------------------------------------------------------

def test_each_edition_is_its_own_record(corpus):
    """Three editions of one work are three records, not one. This is the
    reader's central commitment: `independent_support()` can only discount
    transmissional agreement if the graph can see it as separate witnesses."""
    assert corpus.stats["works"] == 3
    assert corpus.stats["records"] == 6
    assert corpus.editions("T0001") == ["元", "大", "宋"]


def test_a_work_id_is_taken_verbatim(corpus):
    """`T0002-1-序品` names a single division exactly as a catalogue would.
    Nothing parses Taishō numbers, juan numbers or titles out of it — a reader
    that inferred structure from filenames would have to be right about every
    naming convention in a 4,662-directory archive."""
    assert "T0002-1-序品" in corpus.works()
    assert corpus.fetch("T0002-1-序品/大").text == "阿黎耶識為依止"


def test_the_witness_ref_keeps_the_edition(corpus):
    """If two editions became one witness, seventeen near-identical copies
    would read as one well-supported text — the inverse of the truth."""
    a = corpus.fetch("T0001/大")
    b = corpus.fetch("T0001/宋")
    assert a.witness_ref == "T0001/大"
    assert b.witness_ref == "T0001/宋"
    assert a.witness_ref != b.witness_ref


def test_an_unknown_ref_says_what_a_ref_looks_like(corpus):
    with pytest.raises(KeyError, match=r"\{work\}/\{edition\}"):
        corpus.fetch("T0001")


# --- the licence travels with the text ---------------------------------------

def test_the_note_states_cc_by_not_cbetas_terms(corpus):
    """`note` becomes `WitnessPayload.source_terms`, so this string is what
    every witness from this corpus asserts about its own reuse. Copying
    CBETA's note here would assert non-commercial and share-alike restrictions
    that CC-BY-4.0 does not impose."""
    note = corpus.fetch("T0001/大").note
    assert "CC-BY-4.0" in note
    assert "zenodo.7750586" in note
    assert "non-commercial" in note and "no non-commercial" in note
    assert "NC-SA" not in note


# --- search ------------------------------------------------------------------

def test_search_matches_cjk_without_a_segmenter(corpus):
    """FTS5's default tokenizer treats an unbroken CJK run as one token, so a
    phrase query against running Chinese matches nothing without the
    character-unigram trick."""
    hits = corpus.search("阿黎耶識")
    assert {h.ref for h in hits} == {"T0002-1-序品/大", "T0002-1-序品/CB"}


def test_a_hit_in_every_edition_is_still_one_work(corpus):
    """The reader reports what is there and does not decide this question, but
    the shape of the answer has to make the redundancy visible: two hits, one
    work. Anything measuring must group by work."""
    hits = corpus.search("阿黎耶識")
    assert len(hits) == 2
    assert len({h.ref.split("/")[0] for h in hits}) == 1


def test_search_is_corpus_ordered_not_ranked(corpus):
    refs = [h.ref for h in corpus.search("如是我聞")]
    assert refs == sorted(refs)


# --- scoping -----------------------------------------------------------------

def test_it_can_index_named_works_only(tmp_path, corpus):
    """38,369 files is minutes of indexing to ask about thirty-three works."""
    r = RadichReader(corpus.root, works=["T0001"])
    assert r.works() == ["T0001"]
    assert r.stats["records"] == 3
    r.close()


def test_a_missing_work_is_refused_not_skipped(corpus):
    """Silently dropping it would shrink a benchmark without saying so."""
    with pytest.raises(CorpusNotFound, match="T9999"):
        RadichReader(corpus.root, works=["T0001", "T9999"])
