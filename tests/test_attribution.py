"""The attribution index against a corpus small enough to reason about.

Three translators with distinct habits, each with one multi-chapter work
and two single-unit works, a grey text written in the first's vocabulary, a
grey chapter belonging to a labelled work, and a unit consisting of nothing
in the vocabulary at all. What the tests pin down is not accuracy (the toy is
trivially separable) but the rules that made the real numbers honest: the
ledger counts every discard and adds up, a text's own work is withheld before
it is judged, the leak check can actually fail, the generic vocabulary is
drawn from grey text only, zero hits means no verdict, supplementary-plane
characters stay aligned, and the cache is keyed to the bytes it was built
from.
"""

from __future__ import annotations

import pickle
import random

import pytest

from cohort import attribution as attr

VOCAB_A = [chr(c) for c in range(0x4E00, 0x4E00 + 60)]
VOCAB_B = [chr(c) for c in range(0x5000, 0x5000 + 60)]
#: A third translator writing in B's characters but with a different habit --
#: the same characters ranked differently -- so that B and D are separable by
#: frequency and not by character set.
VOCAB_D = list(reversed(VOCAB_B))
ZIPF = [1 / (i + 1) for i in range(60)]
#: A supplementary-plane Han character (CJK Extension B), as the real corpus has.
ASTRAL = "\U00020000"


def _text(rng: random.Random, vocab: list[str], n: int = 2400, leak: list[str] | None = None) -> str:
    """Zipf-weighted characters, so a profile is informative the way real text
    is; `leak` mixes in 3% of another vocabulary, uniformly, the way the
    earliest translators show a few hits in a Dharmarakṣa harvest."""
    out = []
    for _ in range(n):
        if leak is not None and rng.random() < 0.03:
            out.append(rng.choice(leak))
        else:
            out.append(rng.choices(vocab, weights=ZIPF[: len(vocab)])[0])
    return "".join(out)


@pytest.fixture
def corpus(tmp_path):
    rng = random.Random(7)
    units = {
        # A: one three-chapter work and two single works
        "T0001-1": ("A", VOCAB_A), "T0001-2": ("A", VOCAB_A), "T0001-3": ("A", VOCAB_A),
        "T0002": ("A", VOCAB_A), "T0003": ("A", VOCAB_A),
        # B likewise, with a 3% leak of A's characters
        "T0011-1": ("B", VOCAB_B), "T0011-2": ("B", VOCAB_B), "T0011-3": ("B", VOCAB_B),
        "T0012": ("B", VOCAB_B), "T0013": ("B", VOCAB_B),
        # D: B's characters, a different habit, and not one of A's characters
        "T0041-1": ("D", VOCAB_D), "T0041-2": ("D", VOCAB_D), "T0041-3": ("D", VOCAB_D),
        "T0042": ("D", VOCAB_D), "T0043": ("D", VOCAB_D),
        # grey: a text in each vocabulary (the label-free feature set is drawn
        # from grey text, so grey must cover every habit), and a grey chapter of
        # A's labelled work T0001
        "T0099": ("grey", VOCAB_A),
        "T0098": ("grey", VOCAB_B),
        "T0097": ("grey", VOCAB_D),
        "T0001-9": ("grey", VOCAB_A),
        # a short A text under the floor, a class too small to profile, and a
        # catalogue entry with no directory
        "T0004": ("A", VOCAB_A),
        "T0021": ("C", VOCAB_B),
        "T0031": ("A", None),
        # a unit made of characters outside every vocabulary: zero hits
        "T0088": ("grey", ["あ", "い", "う"]),
    }
    corpus_dir = tmp_path / attr.CORPUS_DIR
    for uid, (label, vocab) in units.items():
        if vocab is None:
            continue
        d = corpus_dir / uid
        d.mkdir(parents=True)
        n = 500 if uid == "T0004" else 2400
        leak = VOCAB_A if label == "B" else None
        text = _text(rng, vocab, n, leak)
        if uid == "T0099":
            # an astral character early on, and line breaks, as in the real files
            text = ASTRAL + text[:100] + "\n" + text[100:]
        (d / "大.txt").write_text(text, encoding="utf-8")
    # T0005 has a directory but no base text file
    (corpus_dir / "T0005").mkdir()
    units["T0005"] = ("A", None)

    blocks = {}
    for uid, (label, _) in units.items():
        blocks.setdefault(label, []).append(uid)
    cat = "\r\n\r\n".join("\r\n".join(f"{u} {lab}" for u in us) for lab, us in blocks.items())
    (tmp_path / attr.CATALOGUE).write_bytes((cat + "\r\n").encode("utf-8"))

    # "Radich's" markers: 1,100 bigrams, all from A's vocabulary -- the same
    # one-translator harvest bias the real Table 1 has.
    grams = sorted({a + b for a in VOCAB_A for b in VOCAB_A})[:1100]
    xml = "<table>" + "".join(f"<row><ngram>{g}</ngram></row>" for g in grams) + "</table>"
    (tmp_path / attr.MARKERS).write_text(xml, encoding="utf-8")
    return tmp_path


@pytest.fixture
def index(corpus):
    return attr.AttributionIndex.load(corpus, use_cache=False)


def test_ledger_counts_every_discard_and_adds_up(index):
    led = index.units()["ledger"]
    assert led["catalogue units, non-grey"] == 19
    assert led["catalogue units, grey"] == 5
    assert led["dropped (non-grey): no such directory"] == 1
    assert led["dropped (non-grey): directory has no base text"] == 1
    assert led["dropped: under the 2,000-character floor"] == 1
    assert led["dropped: class too small to profile (C, 1 units)"] == 1
    assert led["kept for profiling"] == 15
    assert led["classes profiled"] == 3
    dropped = sum(v for k, v in led.items() if k.startswith("dropped") and "(grey)" not in k)
    assert led["catalogue units, non-grey"] - dropped == led["kept for profiling"]


def test_a_labelled_text_is_judged_without_its_own_work(index):
    ev = index.evidence("T0001-2", "radich")
    assert ev["withheld_units"] == 3
    assert ev["first"] == "A"
    assert ev["profiles"]["A"]["units"] == 2
    assert ev["profiles"]["A"]["units_before_withholding"] == 5
    assert ev["profiles"]["A"]["thin"] is True
    # The toy markers are all A's strings. B leaks a few, so it has a thin
    # profile and is ranked; D has none and is named as unjudged.
    assert ev["profiles"]["B"]["units"] == 5
    assert ev["no_profile"] == [{"label": "D", "reason": "no hits in this vocabulary"}]
    ev = index.evidence("T0001-2", "generic")
    assert ev["first"] == "A"
    assert ev["no_profile"] == []
    assert set(ev["profiles"]) == {"A", "B", "D"}


def test_a_grey_chapter_of_a_labelled_work_withholds_its_siblings(index):
    ev = index.evidence("T0001-9", "generic")
    assert ev["withheld_units"] == 3
    assert ev["profiles"]["A"]["units"] == 2


def test_grey_text_is_judged_against_everything(index):
    ev = index.evidence("T0099", "generic")
    assert ev["withheld_units"] == 0
    assert ev["verdict"] == "leans"
    assert ev["first"] == "A"
    assert ev["margin"] > 0
    assert len(ev["excerpt"]["evidence"]) == len(ev["excerpt"]["text"])
    assert ev["strip"][0]["start"] == 0
    assert ev["strip"][-1]["end"] == ev["code_points"]
    assert ev["han_chars"] < ev["code_points"]  # the line break and the astral char


def test_astral_characters_stay_aligned_with_the_evidence(index):
    """The excerpt is sliced by code point on the server; a client iterating by
    code point (Array.from) sees the same positions. One astral character at
    position 0 must not shift the painted evidence by one."""
    ev = index.evidence("T0099", "generic")
    text = ev["excerpt"]["text"]
    assert text[0] == ASTRAL
    assert ev["excerpt"]["evidence"][0] == 0.0  # nothing in the vocabulary spans it
    assert len(text) == len(ev["excerpt"]["evidence"])


def test_zero_hits_is_no_evidence_not_a_verdict(index):
    ev = index.evidence("T0088", "radich")
    assert ev["verdict"] == "no evidence"
    assert ev["first"] is None
    assert ev["second"] is None
    assert ev["ranking"] == []
    assert ev["for"] == []
    assert ev["against"] == []


def test_withholding_further_units_is_the_sensitivity_test(index):
    base = index.evidence("T0099", "generic")
    ev = index.evidence("T0099", "generic", withhold=["T0002", "T0003"])
    assert ev["withheld_extra"] == ["T0002", "T0003"]
    assert ev["profiles"]["A"]["units"] == base["profiles"]["A"]["units"] - 2
    with pytest.raises(ValueError, match="not profiled"):
        index.evidence("T0099", "generic", withhold=["T9999"])


def test_the_painted_pair_defaults_to_the_label_and_can_be_pinned(index):
    ev = index.evidence("T0012", "generic")
    assert ev["pair"]["a"] == "B"  # the catalogue label, whichever class leads
    assert ev["pair"]["pinned"] is False
    ev = index.evidence("T0012", "generic", pair=("D", "A"))
    assert (ev["pair"]["a"], ev["pair"]["b"], ev["pair"]["pinned"]) == ("D", "A", True)
    with pytest.raises(ValueError, match="pair"):
        index.evidence("T0012", "generic", pair=("A", "A"))


def test_rows_absent_from_both_profiles_are_not_shown_as_evidence(index):
    ev = index.evidence("T0012", "generic")
    for r in ev["for"] + ev["against"]:
        assert r["count_a"] > 0 or r["count_b"] > 0


def test_generic_vocabulary_is_drawn_from_grey_text_and_matches_the_curated_shape(index):
    led = index.units()["ledger"]
    assert led["features: generic"] == led["features: radich"] == 1100
    assert led["grey texts the generic vocabulary was drawn from"] == 5
    # Drawn from all three habits, so it overlaps the all-A curated list only partly.
    assert 0 < led["features: shared by both"] < 1100


def test_curated_bias_is_visible_as_a_difference_between_vocabularies(index):
    """The toy markers are all A's strings, so under them a B text has almost
    nothing to be recognised by -- the real Table 1 does this to An Shigao."""
    curated = index.evidence("T0012", "radich")
    generic = index.evidence("T0012", "generic")
    assert curated["hits"] < generic["hits"] / 10


def test_the_leak_check_can_fail(index):
    """The check asserts the invariant (no contributor shares the target's
    work), not a recomputation of the same arithmetic. Corrupt the membership
    table so a sibling is not withheld, and it must fire."""
    ix = index._ix
    ix.members["T0001"] = ["T0001-1", "T0001-2"]  # T0001-3 now leaks into A's profile
    with pytest.raises(RuntimeError, match="leak"):
        index.evidence("T0001-2", "radich")


def test_unknown_unit_and_bad_vocabulary_are_errors(index):
    with pytest.raises(KeyError):
        index.evidence("T9999")
    with pytest.raises(KeyError):
        index.evidence("T0031")  # in the catalogue, no directory
    with pytest.raises(ValueError, match="features"):
        index.evidence("T0099", "embeddings")


def test_cache_is_keyed_to_file_contents_and_survives_corruption(corpus):
    first = attr.AttributionIndex.load(corpus)
    cache = corpus / f"{attr.CACHE_NAME}.pkl"
    key = cache.with_suffix(".key")
    assert cache.is_file()
    assert key.is_file()
    second = attr.AttributionIndex.load(corpus)
    assert second.units()["ledger"] == first.units()["ledger"]
    # Same size, different bytes: an mtime/size key would miss this.
    p = corpus / attr.CORPUS_DIR / "T0002" / "大.txt"
    text = p.read_text(encoding="utf-8")
    p.write_text(text[::-1], encoding="utf-8")
    third = attr.AttributionIndex.load(corpus)
    assert third._ix.file_hashes != first._ix.file_hashes
    # A truncated pickle is rebuilt, not raised.
    cache.write_bytes(pickle.dumps(("garbage",))[:10])
    fourth = attr.AttributionIndex.load(corpus)
    assert fourth.units()["ledger"]["kept for profiling"] == 15


def test_provenance_travels_with_every_answer(index):
    ev = index.evidence("T0099", "generic")
    prov = ev["provenance"]
    assert prov["catalogue"]["file"] == attr.CATALOGUE
    assert len(prov["catalogue"]["sha256"]) == 64
    assert prov["base_text"]["file"].endswith("T0099/大.txt")
    assert len(prov["base_text"]["sha256"]) == 64
    assert prov["code_version"] == attr.CODE_VERSION


def test_catalogue_irregularities_are_reported_not_hidden(tmp_path):
    p = tmp_path / "c.txt"
    p.write_bytes(b"T0001 A\r\nT0002 grey\r\nT0003 A\r\n\r\nT0011 B\r\n")
    labels, sequence, notes = attr.read_catalogue(p)
    assert labels["T0002"] == "grey"
    assert sequence == ["A", "B"]
    assert notes == ["the A block also contains 1 line(s) labelled grey; the block keeps its majority label"]
    p.write_bytes(b"T0001 A\nT0002 A\n")
    with pytest.raises(ValueError, match="CRLF"):
        attr.read_catalogue(p)


def test_han_predicate_covers_the_supplementary_plane():
    assert attr.is_han("佛")
    assert attr.is_han(ASTRAL)
    assert attr.is_han("㐀")
    assert not attr.is_han("。")
    assert not attr.is_han("a")


def test_work_of_requires_exactly_four_digits():
    assert attr.work_of("T0603") == "T0603"
    assert attr.work_of("T0150A-12") == "T0150"
    assert attr.work_of("T1331-佛說灌頂拔除過罪生死得度經") == "T1331"
    with pytest.raises(ValueError, match="Taishō number"):
        attr.work_of("T06030")
    with pytest.raises(ValueError, match="Taishō number"):
        attr.work_of("X0603")


def test_excerpt_reports_its_own_end(index):
    ev = index.evidence("T0099", "generic", offset=100)
    assert ev["excerpt"]["start"] == 100
    assert ev["excerpt"]["end"] == 100 + len(ev["excerpt"]["text"])
