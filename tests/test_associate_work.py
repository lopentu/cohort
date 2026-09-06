"""Recording an association against a hypothesis.

The tool for Radich's actual question — does this work associate with the group
*against the rest of the canon* — as against `place_work`, which reads a
distance against the group's own internal spread.

What these mostly pin is that the three things which stop the measure being
over-read cannot be dropped from the record: the calibration, the count of
members the method cannot see, and the nearest work outside the group.
"""
from __future__ import annotations

import pytest

from cohort.attribution import CAVEAT, load_study
from cohort.catalogue import load_catalogue
from cohort.delta import DEFAULT_MIN_CHARS
from cohort.errors import WrongNodeType
from cohort.schemas import (
    RESEARCHER,
    ClaimPayload,
    QuestionPayload,
    VerificationMethod,
    VerificationResult,
)
from cohort.tools.associate_work import AssociateWorkInput, associate_work

AGENT = "agent:worker-1"
U = 700


def write(root, work, text):
    d = root / work
    d.mkdir(parents=True, exist_ok=True)
    (d / "大.txt").write_text(text, encoding="utf-8")


@pytest.fixture(scope="module")
def study(tmp_path_factory):
    """The same shape as `test_association.py`'s fixture — a group with a
    signature, a genre cluster sharing its subject matter, and a background
    canon — built through `load_study` so the catalogue and corpus wiring is
    exercised too."""
    tmp = tmp_path_factory.mktemp("assoc")
    root = tmp / "T-stripped"
    SIG, THEME = "阿黎耶", "波羅蜜"
    fill = lambda c: (chr(c) * 3) * U
    for i in range(6):
        write(root, f"G{i}", SIG * U + THEME * U + fill(0x4E00 + i))
    write(root, "MEMBERLIKE", SIG * U + THEME * U + fill(0x4E20))
    write(root, "DECOY", THEME * U + fill(0x4E21) + fill(0x4E22))
    for i in range(30):
        write(root, f"TH{i:02d}", THEME * U + fill(0x5100 + i) + fill(0x5200 + i))
    for i in range(120):
        write(root, f"X{i:03d}", "多阿含" * U + fill(0x6000 + i) + fill(0x6100 + i))
    write(root, "TINY", "阿黎耶")

    cat = tmp / "cat.txt"
    cat.write_text(
        "".join(f"G{i} bench\n" for i in range(6))
        + "MEMBERLIKE weird\nDECOY weird\nTINY weird\nTH00 control\nTH01 control\n",
        encoding="utf-8",
    )
    s = load_study(root, load_catalogue(cat, benchmark_label="bench",
                                        control_label="control"))
    yield s
    s.corpus.close()


def a_claim(graph, text="MEMBERLIKE belongs with the bench group"):
    return graph.propose_claim(ClaimPayload(text=text), authored_by=AGENT)


def run(graph, study, node, work="MEMBERLIKE"):
    return associate_work(
        graph, study, AssociateWorkInput(claim_or_conjecture_id=node, work=work),
        authored_by=AGENT,
    )


# --- what reaches the record ------------------------------------------------

def test_the_calibration_is_in_the_payload_not_only_in_the_prose(graph, study):
    """A share is uninterpretable without what a known member scores. If the
    calibration lived only in the sentence, a table could render the share
    alone and it would read as a result."""
    out = run(graph, study, a_claim(graph))
    a = graph.get_node(out["verification_id"]).payload["association"]
    for e in a["enrichment"]:
        assert e["calibration_n"] > 0
        assert "calibration_median" in e and "calibration_blind" in e


def test_the_nearest_work_outside_the_group_is_recorded(graph, study):
    """The genre control. Without it, "its nearest neighbour is a group member"
    is unfalsifiable — the reader cannot see how close the nearest non-member
    was."""
    out = run(graph, study, a_claim(graph))
    a = graph.get_node(out["verification_id"]).payload["association"]
    assert a["nearest_outside_group"] is not None
    assert a["nearest_in_group"] is not None


def test_the_caveat_travels_and_says_a_null_places_nothing(graph, study):
    out = run(graph, study, a_claim(graph))
    limits = graph.get_node(out["verification_id"]).payload["limitations"]
    assert CAVEAT in limits
    assert "not been placed anywhere" in limits


def test_it_grants_no_rung_on_the_ladder(graph, study):
    out = run(graph, study, a_claim(graph))
    v = graph.get_node(out["verification_id"]).payload
    assert v["method"] == VerificationMethod.CORPUS_MEASUREMENT
    assert v["assurance_level"] == "A0_UNCHECKED"


def test_ranks_are_recorded_so_a_neighbour_list_is_not_just_an_order(graph, study):
    out = run(graph, study, a_claim(graph))
    a = graph.get_node(out["verification_id"]).payload["association"]
    assert [n["rank"] for n in a["neighbours"]][:3] == [1, 2, 3]


# --- baseline, then check ---------------------------------------------------

def test_the_first_call_is_a_baseline_and_the_second_reproduces(graph, study):
    node = a_claim(graph)
    assert run(graph, study, node)["result"] == VerificationResult.INDETERMINATE
    assert run(graph, study, node)["result"] == VerificationResult.PASS


def test_two_works_on_one_hypothesis_are_two_baselines(graph, study):
    node = a_claim(graph)
    run(graph, study, node, work="MEMBERLIKE")
    assert run(graph, study, node, work="DECOY")["result"] == VerificationResult.INDETERMINATE
    assert run(graph, study, node, work="MEMBERLIKE")["result"] == VerificationResult.PASS


# --- what it refuses --------------------------------------------------------

def test_a_work_below_the_floor_is_refused_with_the_reason(graph, study):
    with pytest.raises(WrongNodeType, match="character floor"):
        run(graph, study, a_claim(graph), work="TINY")


def test_only_a_claim_or_conjecture_can_carry_one(graph, study):
    """An association recorded against a question would be a measurement with
    nothing staked on it — no assertion it could support, and none it could
    break."""
    question = graph.ask_question(
        QuestionPayload(
            text="Does MEMBERLIKE belong with bench?",
            answerable_by="an association measure over the fixture corpus",
        ),
        authored_by=RESEARCHER,
    )
    with pytest.raises(WrongNodeType, match="only a claim or"):
        run(graph, study, question)
