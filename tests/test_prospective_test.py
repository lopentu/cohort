"""Running the query the falsifiability gate demanded.

`propose_conjecture` has always required a query that would settle a conjecture
going forward, and `attest()` has always refused a conjecture without one.
Between them they checked that a test *existed*; nothing ran it. These tests
pin what running it means, and — more importantly — what it deliberately does
not mean.

Three properties matter:

* the prediction is recorded before the query is ever run, and cannot be
  supplied afterwards;
* a result is `pass`/`fail` against that prediction, never a judgement about
  the conjecture; and
* passing grants no assurance rung, because the ladder grades how well a
  node's citations stand up and this grades something else.
"""
from __future__ import annotations

from pathlib import Path

import pytest

from cohort.errors import WrongNodeType
from cohort.schemas import (
    RESEARCHER,
    AssuranceLevel,
    ClaimPayload,
    ConjecturePayload,
    EdgeType,
    HitExpectation,
    QueryPayload,
    VerificationMethod,
    VerificationResult,
)
from cohort.sources.local_reader import LocalReader
from cohort.tools.propose_conjecture import ProposeConjectureInput, propose_conjecture
from cohort.tools.run_prospective_test import run_prospective_test

AGENT = "agent:worker-1"
FIXTURE = Path(__file__).parent.parent / "examples" / "local_corpus"


@pytest.fixture
def source():
    r = LocalReader(FIXTURE)
    yield r
    r.close()


def conjecture(graph, source, *, query, expectation="at_most", hits=0):
    return propose_conjecture(
        graph, source,
        ProposeConjectureInput(
            text="An earlier recension underlies this passage",
            derivation="vocabulary patterns",
            corpus_boundary="only the local_corpus fixture was searched",
            selection_risks="none identified",
            alternative_explanations="a later redactor chose similar vocabulary",
            prior_art_query="recension",
            tests_query_text=query,
            tests_expectation=expectation,
            tests_expected_hits=hits,
        ),
        authored_by=AGENT,
    )


# --- the prediction is on the record first -----------------------------------

def test_the_prediction_is_written_when_the_conjecture_is(graph, source):
    """A prediction stated after the result is known is not a prediction. It
    goes on the query node's payload, which nothing can edit afterwards and
    which `verify_integrity()` hashes."""
    cid = conjecture(graph, source, query="不存在的詞", expectation="at_most", hits=0)
    query = graph.get_node(
        graph.edges(edge_type=EdgeType.TESTS, dst=cid)[0].src
    )
    assert query.payload["expectation"] == HitExpectation.AT_MOST
    assert query.payload["expected_hits"] == 0


def test_a_conjecture_cannot_be_proposed_without_one(graph, source):
    """Required at proposal time, by pydantic, before the tool runs — the same
    place the rest of the dossier is enforced."""
    with pytest.raises(Exception) as e:
        ProposeConjectureInput(
            text="t", derivation="d", corpus_boundary="c", selection_risks="s",
            alternative_explanations="a", prior_art_query="p",
            tests_query_text="q",
        )
    assert "tests_expectation" in str(e.value)


# --- running it --------------------------------------------------------------

def test_a_prediction_that_holds_passes(graph, source):
    cid = conjecture(graph, source, query="這個詞不在語料庫裡", expectation="at_most", hits=0)
    report = run_prospective_test(graph, source, cid, authored_by=RESEARCHER)

    assert report.observed_hits == 0
    assert report.result == VerificationResult.PASS
    assert "the prediction held" in report.note


def test_a_prediction_that_breaks_fails_and_says_by_how_much(graph, source):
    """The conjecture is not touched. A broken prediction is evidence for a
    reading, not a verdict on the conjecture — it may indict the query or the
    corpus boundary instead."""
    cid = conjecture(graph, source, query="明月", expectation="at_most", hits=0)
    report = run_prospective_test(graph, source, cid, authored_by=RESEARCHER)

    assert report.observed_hits > 0
    assert report.result == VerificationResult.FAIL
    assert f"observed {report.observed_hits}" in report.note
    assert graph.get_node(cid).status == "proposed"


def test_at_least_is_the_other_direction(graph, source):
    """Not every prospective query predicts silence. A conjecture that says
    'this pattern recurs' predicts hits, and reading `at_most 0` into it would
    invert the test."""
    cid = conjecture(graph, source, query="明月", expectation="at_least", hits=1)
    assert run_prospective_test(
        graph, source, cid, authored_by=RESEARCHER
    ).result == VerificationResult.PASS


# --- what it records ---------------------------------------------------------

def test_the_result_is_recorded_as_a_verification_on_the_conjecture(graph, source):
    cid = conjecture(graph, source, query="明月", expectation="at_most", hits=0)
    report = run_prospective_test(graph, source, cid, authored_by=RESEARCHER)

    v = graph.get_node(report.verification_id)
    assert v.payload["method"] == VerificationMethod.PROSPECTIVE_TEST
    assert v.payload["result"] == VerificationResult.FAIL
    assert report.query_id in v.payload["detail"]
    assert v.id in [n.id for n in graph.verifications(cid)]


def test_passing_grants_no_assurance_rung(graph, source):
    """The ladder grades how well a node's *citations* stand up. A surviving
    prediction says something else entirely, and giving it a rung would repeat
    the A3 mistake of grading one thing with a name that reads as another."""
    cid = conjecture(graph, source, query="這個詞不在語料庫裡", expectation="at_most", hits=0)
    report = run_prospective_test(graph, source, cid, authored_by=RESEARCHER)

    assert report.result == VerificationResult.PASS
    assert graph.assurance_for(cid) == AssuranceLevel.A0_UNCHECKED


def test_the_record_says_what_a_result_does_not_settle(graph, source):
    cid = conjecture(graph, source, query="明月", expectation="at_most", hits=0)
    report = run_prospective_test(graph, source, cid, authored_by=RESEARCHER)

    limits = graph.get_node(report.verification_id).payload["limitations"]
    assert "the corpus boundary" in limits
    assert "as indexed today" in limits


# --- a capped search is a floor, not a count ---------------------------------

def test_a_capped_search_cannot_settle_a_prediction_it_does_not_already_break(
    graph, source, monkeypatch
):
    """Here the count *is* the finding, so a search that returns the cap has
    been floored rather than counted. Reporting `at least 200` as if it were
    200 is how a measurement layer starts publishing numbers it did not
    measure."""
    import cohort.tools.run_prospective_test as mod

    monkeypatch.setattr(mod, "MAX_RESULTS", 1)
    cid = conjecture(graph, source, query="明月", expectation="at_least", hits=5)
    report = mod.run_prospective_test(graph, source, cid, authored_by=RESEARCHER)

    assert report.count_saturated is True
    assert report.result == VerificationResult.INDETERMINATE
    assert "cannot settle" in report.note


def test_a_floor_that_already_breaks_the_prediction_still_fails_it(
    graph, source, monkeypatch
):
    """The floor settles it in one direction: if `at most 0` was predicted and
    the search already found one, the true count can only be higher."""
    import cohort.tools.run_prospective_test as mod

    monkeypatch.setattr(mod, "MAX_RESULTS", 1)
    cid = conjecture(graph, source, query="明月", expectation="at_most", hits=0)
    report = mod.run_prospective_test(graph, source, cid, authored_by=RESEARCHER)

    assert report.count_saturated is True
    assert report.result == VerificationResult.FAIL
    assert "at least 1" in report.note


# --- what it refuses ---------------------------------------------------------

def test_a_claim_has_nothing_to_predict(graph, source):
    """A claim asserts what the sources already say. There is no prospective
    query on it and there should not be one."""
    cid = graph.propose_claim(ClaimPayload(text="a claim"), authored_by=AGENT)
    with pytest.raises(WrongNodeType, match="only a conjecture"):
        run_prospective_test(graph, source, cid, authored_by=RESEARCHER)


def test_a_conjecture_with_no_tests_query_is_refused(graph, source):
    """Reachable only by going round `propose_conjecture` — which is the same
    conjecture the falsifiability gate already refuses to attest."""
    cid = graph.propose_conjecture(
        ConjecturePayload(
            text="smuggled in", derivation="d", corpus_boundary="c",
            selection_risks="s", alternative_explanations="a",
        ),
        authored_by=AGENT,
    )
    with pytest.raises(WrongNodeType, match="no tests query"):
        run_prospective_test(graph, source, cid, authored_by=RESEARCHER)


def test_a_conjecture_predating_predictions_is_indeterminate_not_assumed(graph, source):
    """Older conjectures carry a tests query with no prediction on it. Reading
    that as 'no hits were expected' would invent the prediction after seeing
    the answer, so it is reported as indeterminate instead."""
    cid = graph.propose_conjecture(
        ConjecturePayload(
            text="from before predictions existed", derivation="d",
            corpus_boundary="c", selection_risks="s", alternative_explanations="a",
        ),
        authored_by=AGENT,
    )
    qid = graph.propose_query(QueryPayload(text="明月"), authored_by=AGENT)
    graph.add_edge(EdgeType.TESTS, qid, cid, authored_by=AGENT)

    report = run_prospective_test(graph, source, cid, authored_by=RESEARCHER)
    assert report.expectation is None
    assert report.result == VerificationResult.INDETERMINATE
    assert "no prediction was recorded" in report.note


# --- it is not an agent tool -------------------------------------------------

def test_no_agent_can_call_it(graph, source):
    """Same footing as `verify_exact_span`: a check, not a contribution. Its
    value is in being run *later*, and an agent running it in the turn that
    proposed the conjecture would be testing a prediction against the state
    that produced it."""
    from cohort.agents.attestation_worker import TOOLS
    from cohort.tools.run_prospective_test import NAME

    assert NAME not in {t["function"]["name"] for t in TOOLS}
