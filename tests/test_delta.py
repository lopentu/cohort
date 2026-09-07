"""Exploratory distances that cannot be shown without their calibration.

Delta produces a number, numbers sort, and a sorted list looks like a verdict.
So most of what follows tests the guardrails rather than the arithmetic: the
null band is required, it is computed leave-one-out, and a group too small to
have a spread refuses to report one.

Both artifacts that fooled this project on 2026-09-06 — a group scored against
a range it defined, and a comparison against 16 references calibrated on 15 —
are pinned here as regression tests, because both looked like findings.
"""
from __future__ import annotations

import pytest

from cohort.delta import DEFAULT_MIN_CHARS, NullBand, build_space

#: Two "authors". A-works share a bigram habit; B-works share a different one.
#: Padding differs per work so no two are identical, which would make every
#: distance zero and every test vacuous.
def work(marker: str, seed: int, n: int = 4_000) -> str:
    return (marker * n) + ("甲乙丙丁戊己庚辛"[seed % 8] * (DEFAULT_MIN_CHARS // 2))


@pytest.fixture
def space():
    texts = {f"A{i}": work("阿黎", i) for i in range(5)}
    texts.update({f"B{i}": work("波羅", i + 3) for i in range(4)})
    labels = {**{f"A{i}": "bench" for i in range(5)},
              **{f"B{i}": "other" for i in range(4)}}
    return build_space(texts, labels=labels)


BENCH = [f"A{i}" for i in range(5)]


# --- the null is not optional ------------------------------------------------

def test_a_profile_cannot_be_built_without_a_null(space):
    """Not a style preference — a distance with no spread beside it is a number
    that gets over-read. The type makes it impossible rather than discouraged."""
    with pytest.raises(TypeError):
        space.profile("B0", benchmark=BENCH)  # no null=


def test_the_null_is_leave_one_out(space):
    """A band computed with the work included is a band the work helped define,
    and everything falls inside it. This is the first of the two artifacts that
    fooled us."""
    null = space.null_band(BENCH, label="bench")
    assert null.n == len(BENCH)
    # each member's own distance is to the *others*, so a member can sit at the
    # edge of the band rather than trivially inside it
    for w in BENCH:
        assert space.mean_distance(w, BENCH) == space.mean_distance(
            w, [x for x in BENCH if x != w]
        )


def test_a_group_too_small_refuses_to_report_a_spread(space):
    """Two works have exactly one distance between them, and calling that a
    band would report an accident as a range."""
    with pytest.raises(ValueError, match="at least 3"):
        space.null_band(["A0", "A1"], label="bench")


def test_a_distance_to_an_empty_group_is_refused_not_zero(space):
    with pytest.raises(ValueError, match="not a small distance"):
        space.mean_distance("A0", ["A0"])


# --- what a profile says -----------------------------------------------------

def test_a_work_from_the_benchmark_reads_as_indistinguishable(space):
    null = space.null_band(BENCH, label="bench")
    p = space.profile("A0", benchmark=BENCH, null=null)
    assert p.inside_null is True
    assert "not distinguishable" in p.as_json()["reading"]


def test_a_work_from_elsewhere_sits_outside(space):
    null = space.null_band(BENCH, label="bench")
    p = space.profile("B0", benchmark=BENCH, null=null)
    assert p.mean_delta_to_benchmark > null.maximum
    assert p.inside_null is False


def test_neighbours_are_ranked_nearest_first_and_carry_their_labels(space):
    null = space.null_band(BENCH, label="bench")
    p = space.profile("B0", benchmark=BENCH, null=null, top=4)
    deltas = [n.delta for n in p.neighbours]
    assert deltas == sorted(deltas)
    assert all(n.work != "B0" for n in p.neighbours), "a work is not its own neighbour"
    assert {n.label for n in p.neighbours} <= {"bench", "other", None}


def test_the_null_travels_with_the_profile_into_json(space):
    """So no renderer can show a distance and drop the calibration."""
    null = space.null_band(BENCH, label="bench")
    payload = space.profile("B0", benchmark=BENCH, null=null).as_json()
    assert payload["null"]["n"] == 5
    assert set(payload["null"]) == {"label", "n", "min", "median", "max"}


def test_it_reports_no_score_or_verdict(space):
    null = space.null_band(BENCH, label="bench")
    payload = space.profile("B0", benchmark=BENCH, null=null).as_json()
    assert set(payload) & {"score", "confidence", "author", "verdict", "probability"} == set()


# --- features come from the corpus ------------------------------------------

def test_features_are_chosen_by_the_corpus_not_the_caller(space):
    """The argument for Delta here: a hand-picked feature list has to be
    defended by whoever picked it."""
    assert "阿黎" in space.features or "波羅" in space.features
    assert len(space.features) <= 300


def test_short_works_are_excluded_and_named(space):
    texts = {f"A{i}": work("阿黎", i) for i in range(4)}
    texts["tiny"] = "阿黎"
    s = build_space(texts)
    assert s.skipped == ("tiny",)
    assert "tiny" not in s.works()


def test_a_corpus_too_small_to_normalise_is_refused():
    with pytest.raises(ValueError, match="not a normalisation"):
        build_space({"A": work("阿黎", 0), "B": work("阿黎", 1)})


def test_distance_is_symmetric_and_zero_to_itself(space):
    assert space.distance("A0", "B0") == pytest.approx(space.distance("B0", "A0"))
    assert space.distance("A0", "A0") == 0.0
