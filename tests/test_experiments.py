"""The experiment harness behind the talk's numbers, on a toy corpus.

Not accuracy (the toy is separable) but the protocol: the leaky unit split
must not score below the honest work split on a corpus built to leak, both
classifiers run over the index's own tables, and the leak check can fire.
"""

from __future__ import annotations

import random

import pytest

from cohort import attribution as attr
from scripts.experiments._common import CLASSIFIERS, evaluate, works_per_class

VOCAB_A = [chr(c) for c in range(0x4E00, 0x4E00 + 60)]
VOCAB_B = [chr(c) for c in range(0x5000, 0x5000 + 60)]
ZIPF = [1 / (i + 1) for i in range(60)]


def _text(rng, vocab, n=2400):
    return "".join(rng.choices(vocab, weights=ZIPF)[0] for _ in range(n))


@pytest.fixture
def index(tmp_path):
    rng = random.Random(11)
    # A has one six-chapter work (leaky by construction) and two single works;
    # B is all single works; grey covers both habits for the label-free vocabulary.
    units = {f"T0001-{i}": ("A", VOCAB_A) for i in range(1, 7)}
    units.update({"T0002": ("A", VOCAB_A), "T0003": ("A", VOCAB_A)})
    units.update({f"T00{10 + i}": ("B", VOCAB_B) for i in range(1, 7)})
    units.update({"T0099": ("grey", VOCAB_A), "T0098": ("grey", VOCAB_B)})
    corpus = tmp_path / attr.CORPUS_DIR
    for uid, (_, vocab) in units.items():
        (corpus / uid).mkdir(parents=True)
        (corpus / uid / "大.txt").write_text(_text(rng, vocab), encoding="utf-8")
    blocks: dict[str, list[str]] = {}
    for uid, (label, _) in units.items():
        blocks.setdefault(label, []).append(uid)
    cat = "\r\n\r\n".join("\r\n".join(f"{u} {lab}" for u in us) for lab, us in blocks.items())
    (tmp_path / attr.CATALOGUE).write_bytes((cat + "\r\n").encode())
    grams = sorted({x + y for x in VOCAB_A for y in VOCAB_A})[:1100]
    (tmp_path / attr.MARKERS).write_text(
        "<t>" + "".join(f"<ngram>{g}</ngram>" for g in grams) + "</t>", encoding="utf-8",
    )
    return attr.AttributionIndex.load(tmp_path, use_cache=False)


def test_both_splits_run_for_both_classifiers_and_the_leaky_one_scores_no_lower(index):
    for _name, clf in CLASSIFIERS.items():
        ok_u, n_u = evaluate(index, "generic", "unit", clf)
        ok_w, n_w = evaluate(index, "generic", "work", clf)
        assert sum(n_u.values()) == 14
        assert sum(n_w.values()) == 14
        assert sum(ok_u.values()) >= sum(ok_w.values())
    assert works_per_class(index) == {"A": 3, "B": 6}


def test_the_work_split_leak_check_can_fire(index, monkeypatch):
    """The harness groups by work_of(); make one chapter of A's six-chapter work
    look like its own work and its siblings feed A's profile while it is judged.
    The invariant check must fire rather than let the number quietly inflate."""
    import scripts.experiments._common as common

    real = common.work_of
    monkeypatch.setattr(common, "work_of", lambda u: "T0001-2-alone" if u == "T0001-2" else real(u))
    with pytest.raises(RuntimeError, match="leak"):
        evaluate(index, "generic", "work", CLASSIFIERS["naive Bayes"])
