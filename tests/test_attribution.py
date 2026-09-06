"""A study: catalogue plus corpus plus calibration, in one object.

The type exists to stop two things. Profiles from different spaces are not
comparable, because the z-scores behind a Delta depend on which works are in
the space — so they are held together. And a work the study could not measure
must be *named*, not omitted, or the study quietly reports a smaller question
than it was asked.
"""
from __future__ import annotations

import pytest

from cohort.attribution import CAVEAT, load_study
from cohort.catalogue import CatalogueError, load_catalogue
from cohort.delta import DEFAULT_MIN_CHARS

PAD = DEFAULT_MIN_CHARS


def write(root, work, text):
    d = root / work
    d.mkdir(parents=True, exist_ok=True)
    (d / "大.txt").write_text(text, encoding="utf-8")


@pytest.fixture
def corpus(tmp_path):
    root = tmp_path / "T-stripped"
    # The benchmark varies internally — as a real one does, and as it must for
    # the null band to have any width at all. A group whose members are exactly
    # equidistant produces a band of zero width, which is not a calibration.
    for i in range(5):
        write(root, f"B{i}", ("阿黎耶" * (PAD + i * 400)) + ("甲乙丙丁戊"[i] * PAD))
    for i in range(2):
        write(root, f"D{i}", ("阿黎耶" * (PAD + i * 300)) + ("己庚"[i] * PAD))
    for i in range(2):
        write(root, f"C{i}", ("波羅蜜" * (PAD + i * 300)) + ("辛壬"[i] * PAD))
    # background works: the rest of the "canon", so neighbours have somewhere
    # to come from other than the catalogue
    for i in range(6):
        write(root, f"X{i}", ("多阿含" * PAD) + ("癸子丑寅卯辰"[i] * PAD))
    write(root, "TINY", "阿黎耶")
    return root


@pytest.fixture
def catalogue(tmp_path):
    p = tmp_path / "cat.txt"
    p.write_text(
        "B0 bench\nB1 bench\nB2 bench\nB3 bench\nB4 bench\n"
        "D0 disputed\nD1 disputed\nC0 control\nC1 control\n",
        encoding="utf-8",
    )
    return load_catalogue(p, benchmark_label="bench", control_label="control")


def test_the_reference_space_is_the_whole_corpus_not_the_catalogue(corpus, catalogue):
    """A distance computed only among catalogued works answers 'which of these
    nine is this most like', which is not the question. Radich asked whether a
    work can be associated with some other reference point *in the canon*."""
    study = load_study(corpus, catalogue)
    assert study.corpus_size > len(catalogue.works())
    neighbours = {n.work for n in study.profile("D0").neighbours}
    assert any(w.startswith("X") for w in neighbours), (
        "works outside the catalogue must be reachable as neighbours"
    )


def test_the_null_is_the_benchmarks_own_spread(corpus, catalogue):
    study = load_study(corpus, catalogue)
    assert study.null.label == "bench"
    assert study.null.n == 5
    assert study.null.minimum <= study.null.median <= study.null.maximum


def test_a_control_work_reads_as_further_out_than_the_benchmarks_own_members(corpus, catalogue):
    study = load_study(corpus, catalogue)
    assert study.profile("C0").inside_null is False
    assert study.profile("D0").inside_null is True


def test_works_below_the_floor_are_named_not_dropped(corpus, catalogue, tmp_path):
    """A study that silently omits what it could not measure reports a smaller
    question than it was asked — and the omitted works are as likely as any to
    be the interesting ones."""
    p = tmp_path / "c2.txt"
    p.write_text("B0 bench\nB1 bench\nB2 bench\nB3 bench\nB4 bench\n"
                 "D0 disputed\nTINY disputed\n", encoding="utf-8")
    study = load_study(corpus, load_catalogue(p, benchmark_label="bench"))
    assert study.unmeasurable("disputed") == ["TINY"]
    payload = study.as_json()
    assert payload["groups"]["disputed"]["unmeasurable"] == ["TINY"]


def test_a_catalogue_the_corpus_cannot_satisfy_is_refused(corpus, tmp_path):
    p = tmp_path / "c3.txt"
    p.write_text("B0 bench\nB1 bench\nB2 bench\nNOPE disputed\n", encoding="utf-8")
    with pytest.raises(CatalogueError, match="NOPE"):
        load_study(corpus, load_catalogue(p, benchmark_label="bench"))


def test_a_catalogue_with_no_benchmark_has_nothing_to_calibrate_against(corpus, tmp_path):
    p = tmp_path / "c4.txt"
    p.write_text("B0 x\nB1 x\nB2 x\nD0 y\n", encoding="utf-8")
    with pytest.raises(ValueError, match="nothing to calibrate"):
        load_study(corpus, load_catalogue(p))


# --- what the payload promises ----------------------------------------------

def test_the_benchmark_is_not_listed_as_a_group_to_be_judged(corpus, catalogue):
    """It is the yardstick. Profiling it against itself would invite reading
    the yardstick's own spread as a result."""
    payload = load_study(corpus, catalogue).as_json()
    assert set(payload["groups"]) == {"disputed", "control"}


def test_every_payload_carries_the_caveat(corpus, catalogue):
    """Rather than trusting a renderer to remember that these neighbourhoods
    track subject matter."""
    payload = load_study(corpus, catalogue).as_json()
    assert payload["caveat"] == CAVEAT
    assert "not about who wrote it" in payload["caveat"]


def test_every_profile_carries_its_null(corpus, catalogue):
    payload = load_study(corpus, catalogue).as_json()
    for group in payload["groups"].values():
        for p in group["profiles"]:
            assert p["null"]["n"] == 5, "no distance is shown without its calibration"
