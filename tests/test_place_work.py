"""A Delta placement, recorded with the band that makes it readable.

The distance is not the finding. Twice on 2026-09-06 an apparent separation in
this study turned out to be an artifact — a work scored against a range it
helped define, and a null band calibrated on fifteen works while distances were
taken against sixteen — and both would have been obvious at a glance against
the benchmark's own spread. So these check that the band travels in the payload
and that the caveat travels with it, not only that the arithmetic runs.
"""
from __future__ import annotations

import pytest

from cohort.attribution import CAVEAT, load_study
from cohort.catalogue import load_catalogue
from cohort.delta import DEFAULT_MIN_CHARS
from cohort.errors import WrongNodeType
from cohort.schemas import (
    AssuranceLevel,
    ClaimPayload,
    QuestionPayload,
    RESEARCHER,
    VerificationMethod,
    VerificationResult,
)
from cohort.tools.place_work import PlaceWorkInput, place_work

AGENT = "agent:worker-1"
PAD = DEFAULT_MIN_CHARS


def write(root, work, text):
    d = root / work
    d.mkdir(parents=True, exist_ok=True)
    (d / "大.txt").write_text(text, encoding="utf-8")


@pytest.fixture
def study(tmp_path):
    root = tmp_path / "T-stripped"
    # The benchmark has to vary internally or the null band has zero width,
    # which is not a calibration.
    for i in range(5):
        write(root, f"B{i}", ("阿黎耶" * (PAD + i * 400)) + ("甲乙丙丁戊"[i] * PAD))
    for i in range(2):
        write(root, f"D{i}", ("阿黎耶" * (PAD + i * 300)) + ("己庚"[i] * PAD))
    for i in range(6):
        write(root, f"X{i}", ("多阿含" * PAD) + ("癸子丑寅卯辰"[i] * PAD))
    write(root, "TINY", "阿黎耶")

    cat = tmp_path / "cat.txt"
    cat.write_text(
        "B0 bench\nB1 bench\nB2 bench\nB3 bench\nB4 bench\n"
        "D0 disputed\nD1 disputed\nTINY disputed\n",
        encoding="utf-8",
    )
    s = load_study(root, load_catalogue(cat, benchmark_label="bench"))
    yield s
    s.corpus.close()


def a_claim(graph):
    return graph.propose_claim(
        ClaimPayload(text="D0 belongs with the bench group"), authored_by=AGENT,
    )


def place(graph, study, node_id, work="D0"):
    return place_work(
        graph, study, PlaceWorkInput(claim_or_conjecture_id=node_id, work=work),
        authored_by=AGENT,
    )


# --- what gets written ------------------------------------------------------

def test_the_placement_is_recorded_as_a_measurement_not_a_verdict(graph, study):
    node = a_claim(graph)
    out = place(graph, study, node)

    v = graph.get_node(out["verification_id"])
    assert v.payload["method"] == VerificationMethod.CORPUS_MEASUREMENT
    # A distance grades nothing about how well the claim's citations stand up,
    # so it must grant no rung on the ladder.
    assert v.payload["assurance_level"] == AssuranceLevel.A0_UNCHECKED


def test_the_band_travels_in_the_detail_beside_the_distance(graph, study):
    """A Δ with its calibration one click away is a Δ that will be over-read."""
    node = a_claim(graph)
    out = place(graph, study, node)
    detail = graph.get_node(out["verification_id"]).payload["detail"]

    band = out["placement"]["null"]
    assert str(band["min"]) in detail and str(band["max"]) in detail
    assert str(out["placement"]["mean_delta_to_benchmark"]) in detail


def test_the_caveat_lands_in_the_field_a_reader_already_sees(graph, study):
    """`limitations` renders under 'Does not establish' in both front ends. A
    caveat kept anywhere else is one the presentation can quietly drop, and
    this one — that character n-grams track subject matter — is the difference
    between a resemblance and an ascription."""
    node = a_claim(graph)
    out = place(graph, study, node)
    assert graph.get_node(out["verification_id"]).payload["limitations"] == CAVEAT


def test_a_work_inside_the_band_is_reported_as_not_distinguishable(graph, study):
    node = a_claim(graph)
    body = place(graph, study, node)["placement"]
    if body["inside_null"]:
        assert "not distinguishable" in body["reading"]
    else:
        assert "further from the benchmark" in body["reading"]


# --- first call records, later calls check ----------------------------------

def test_the_first_call_is_indeterminate_because_it_is_the_baseline(graph, study):
    node = a_claim(graph)
    assert place(graph, study, node)["result"] == VerificationResult.INDETERMINATE


def test_a_second_call_against_the_same_space_reproduces(graph, study):
    node = a_claim(graph)
    place(graph, study, node)
    assert place(graph, study, node)["result"] == VerificationResult.PASS


def test_a_placement_of_another_work_is_not_compared_against_this_ones_baseline(
    graph, study,
):
    """Two works on one hypothesis are two baselines. Comparing D1's distance
    against D0's fingerprint would FAIL every time while looking like a
    finding — the same trap `measure_claim` avoids by filtering on feature."""
    node = a_claim(graph)
    place(graph, study, node, work="D0")
    assert place(graph, study, node, work="D1")["result"] == VerificationResult.INDETERMINATE
    assert place(graph, study, node, work="D0")["result"] == VerificationResult.PASS


def test_a_space_that_moved_breaks_the_baseline(graph, study, tmp_path):
    """Every distance in a Delta space moves when its membership does, because
    the z-scores are computed across the members. A placement that silently
    followed the new space would let a claim keep numbers it no longer has."""
    node = a_claim(graph)
    place(graph, study, node)

    # The same corpus with one more background work, which shifts every
    # feature's mean and standard deviation and so moves every distance.
    root = tmp_path / "moved"
    src = tmp_path / "T-stripped"
    for d in sorted(src.iterdir()):
        write(root, d.name, (d / "大.txt").read_text(encoding="utf-8"))
    write(root, "X9", ("波羅蜜" * PAD) + ("辰" * PAD))
    cat = tmp_path / "cat.txt"
    moved = load_study(root, load_catalogue(cat, benchmark_label="bench"))
    try:
        assert place(graph, moved, node)["result"] == VerificationResult.FAIL
    finally:
        moved.corpus.close()


# --- what it refuses --------------------------------------------------------

def test_only_a_claim_or_conjecture_can_carry_a_placement(graph, study):
    """A distance recorded against a question would be a number with nothing
    staked on it — no assertion it could bear on, and none it could break."""
    question = graph.ask_question(
        QuestionPayload(
            text="Where does D0 sit?",
            answerable_by="a Delta placement over the fixture corpus",
        ),
        authored_by=RESEARCHER,
    )
    with pytest.raises(WrongNodeType, match="only a claim or"):
        place(graph, study, question)


def test_a_work_below_the_floor_is_refused_with_the_reason(graph, study):
    """'This method cannot speak to that text' is a result, and the refusal has
    to say which of the two reasons it is — absent, or too short."""
    node = a_claim(graph)
    with pytest.raises(WrongNodeType, match="character floor"):
        place(graph, study, node, work="TINY")


def test_a_work_the_corpus_does_not_hold_is_refused(graph, study):
    node = a_claim(graph)
    with pytest.raises(WrongNodeType, match="no profile in this space"):
        place(graph, study, node, work="T9999")


# --- the two measures answer different questions ----------------------------

def test_the_band_says_not_distinguishable_for_almost_everything(graph, study):
    """Why `associate_work` exists beside this.

    A null band's ceiling is the distance of the group's most eccentric member,
    so it is a threshold almost nothing fails — on the real Paramārtha corpus
    every disputed work and every interloper alike came back inside it. That is
    a true statement and an answer to nothing, and it is the reason a second
    measure with the whole canon behind it was needed rather than a tuned
    version of this one.

    Pinned rather than fixed: the band is still the right check against
    *over*-reading a small distance, and narrowing it to a quantile would make
    it a different statistic wearing the same name.
    """
    node = a_claim(graph)
    inside = [
        place(graph, study, node, work=w)["placement"]["inside_null"]
        for w in ("D0", "D1")
    ]
    assert all(inside), (
        "the fixture no longer reproduces the condition that motivated "
        "cohort.association — check whether the band is still this permissive"
    )
