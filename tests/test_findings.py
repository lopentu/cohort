"""Hypotheses, not node ids.

The Findings tab was two lists of bare ids while the graph already held the
whole dossier — derivation, corpus boundary, selection risks, alternative
explanations, the prior-art search that was actually run, the prediction
recorded at proposal time — reachable only by walking edges by hand. That is
the step at which the honest fields get skipped, so the walk lives in
`views.py` where both front ends get the same answer.

What these pin is mostly what the shape refuses to do: it does not rank, it
does not merge the machine's finding with a reviewer's reading, and it does not
let a stale verification outrank a later one.
"""
from __future__ import annotations

from pathlib import Path

import pytest

from cohort.errors import NodeNotFound
from cohort.schemas import (
    RESEARCHER,
    ClaimPayload,
    Dating,
    DatingRoute,
    EdgeType,
    PassagePayload,
    VerificationMethod,
    VerificationResult,
    WitnessPayload,
)
from cohort.sources.local_reader import LocalReader
from cohort.tools.propose_conjecture import ProposeConjectureInput, propose_conjecture
from cohort.views import dossier_json, findings_json

AGENT = "agent:worker-1"
REVIEWER = "agent:reviewer-1"
FIXTURE = Path(__file__).parent.parent / "examples" / "local_corpus"


@pytest.fixture
def source():
    r = LocalReader(FIXTURE)
    yield r
    r.close()


def cited_claim(graph, *, text="a claim", ref="poem-001", excerpt="明月"):
    w = graph.propose_witness(
        WitnessPayload(
            canonical_ref=ref,
            dating=Dating(confidence=DatingRoute.UNKNOWN, basis="not dated for this test"),
        ),
        authored_by=AGENT,
    )
    graph.attest(w, authored_by=AGENT)
    p = graph.propose_passage(
        PassagePayload(canonical_ref=f"{ref}#1", locator="line 1", excerpt=excerpt),
        witness_id=w, authored_by=AGENT,
    )
    graph.attest(p, authored_by=AGENT)
    claim_id = graph.propose_claim(ClaimPayload(text=text), authored_by=AGENT)
    graph.add_edge(EdgeType.ATTESTS, p, claim_id, authored_by=AGENT)
    return claim_id, w, p


# --- the list ----------------------------------------------------------------

def test_findings_lists_claims_and_conjectures_and_nothing_else(graph, source):
    """Witnesses, passages, queries and verifications are the *record*; a
    hypothesis is what someone is actually asserting."""
    claim_id, witness_id, passage_id = cited_claim(graph)
    listed = {f["id"] for f in findings_json(graph)["findings"]}
    assert claim_id in listed
    assert witness_id not in listed and passage_id not in listed


def test_findings_are_not_ranked_by_support(graph, source):
    """A list sorted by 'most attested' is a confidence ranking wearing a
    different hat, which is the habit this system exists to break. Newest
    first, and the order does not move when support does."""
    first, _w, _p = cited_claim(graph, text="one", ref="poem-001")
    second, _w2, _p2 = cited_claim(graph, text="two", ref="poem-002")
    for i in range(3):
        w = graph.propose_witness(
            WitnessPayload(
                canonical_ref=f"extra-{i}",
                dating=Dating(confidence=DatingRoute.UNKNOWN, basis="not dated for this test"),
            ),
            authored_by=AGENT,
        )
        graph.attest(w, authored_by=AGENT)
        p = graph.propose_passage(
            PassagePayload(canonical_ref=f"extra-{i}#1", locator="l", excerpt="明月"),
            witness_id=w, authored_by=AGENT,
        )
        graph.attest(p, authored_by=AGENT)
        graph.add_edge(EdgeType.ATTESTS, p, first, authored_by=AGENT)

    ids = [f["id"] for f in findings_json(graph)["findings"]]
    assert ids == [second, first], "heavily-attested `first` must not float up"


def test_the_row_says_whether_support_survives_the_independence_check(graph, source):
    claim_id, w1, _p = cited_claim(graph, text="c", ref="poem-001")
    _c2, w2, p2 = cited_claim(graph, text="other", ref="poem-002")
    graph.add_edge(EdgeType.ATTESTS, p2, claim_id, authored_by=AGENT)

    row = next(f for f in findings_json(graph)["findings"] if f["id"] == claim_id)
    assert row["support"]["independent"] is True

    graph.add_edge(EdgeType.PARALLEL_OF, w1, w2, authored_by=AGENT)
    row = next(f for f in findings_json(graph)["findings"] if f["id"] == claim_id)
    assert row["support"]["independent"] is False
    assert row["support"]["attesting_count"] == 2, "the count is unchanged; the meaning is not"


def test_nothing_attesting_reads_as_unsupported_not_independent(graph, source):
    """`independent` is `not flips`, so with no evidence at all it is vacuously
    true — and "0 attesting, 0 witnesses, independent" reads as a clean bill of
    health for a node that has never been tested. The flip flag keeps its
    meaning; the vacuous case is reported beside it."""
    bare = graph.propose_claim(ClaimPayload(text="nothing cites this"), authored_by=AGENT)
    support = findings_json(graph)["findings"][0]["support"]

    assert support["attesting_count"] == 0
    assert support["independent"] is True, "the flip flag's meaning is unchanged"
    assert support["vacuous"] is True

    cited, _w, _p = cited_claim(graph, ref="poem-002")
    row = next(f for f in findings_json(graph)["findings"] if f["id"] == cited)
    assert row["support"]["vacuous"] is False
    assert graph.get_node(bare).status == "proposed"


# --- the dossier -------------------------------------------------------------

def conjecture(graph, source, **over):
    args = {
        "text": "An earlier recension underlies this passage",
        "derivation": "vocabulary patterns",
        "corpus_boundary": "only the local_corpus fixture was searched",
        "selection_risks": "the index is unranked",
        "alternative_explanations": "a later redactor chose similar vocabulary",
        "prior_art_query": "recension",
        "tests_query_text": "這個詞不在語料庫裡",
        "tests_expectation": "at_most",
        "tests_expected_hits": 0,
    }
    args.update(over)
    return propose_conjecture(graph, source, ProposeConjectureInput(**args), authored_by=AGENT)


def test_the_dossier_carries_the_fields_that_make_it_a_hypothesis(graph, source):
    """Selection risks and alternative explanations are the two that turn an
    assertion into a hypothesis, and they are the two a card without a dossier
    view silently drops."""
    cid = conjecture(graph, source)
    d = dossier_json(graph, cid)
    assert set(d["dossier"]) == {
        "derivation", "corpus_boundary", "selection_risks", "alternative_explanations",
    }
    assert d["assertion"].startswith("An earlier recension")


def test_the_prediction_travels_with_the_prospective_query(graph, source):
    cid = conjecture(graph, source, tests_expectation="at_least", tests_expected_hits=3)
    d = dossier_json(graph, cid)
    q = d["prospective_queries"][0]
    assert q["expectation"] == "at_least" and q["expected_hits"] == 3
    # the prior-art search is a different question and stays separate
    assert d["prior_art"] and d["prior_art"][0]["expectation"] is None


def test_evidence_comes_back_readable_not_as_a_list_of_ids(graph, source):
    """A list of passage ids is not evidence a person can weigh."""
    claim_id, witness_id, passage_id = cited_claim(graph, excerpt="明月")
    e = dossier_json(graph, claim_id)["evidence"][0]
    assert e["passage_id"] == passage_id
    assert e["excerpt"] == "明月"
    assert e["witness_id"] == witness_id


def test_only_the_latest_verification_per_method_is_shown(graph, source):
    """The same rule `assurance_for` follows. A stale pass beside a later
    failure would read as two findings when it is one, superseded."""
    claim_id, _w, _p = cited_claim(graph)
    graph.verify(claim_id, method=VerificationMethod.EXACT_SPAN,
                 result=VerificationResult.PASS, assurance_level="A2_EXACT_SPAN_MATCHED",
                 detail="first look", authored_by=RESEARCHER)
    graph.verify(claim_id, method=VerificationMethod.EXACT_SPAN,
                 result=VerificationResult.FAIL, assurance_level="A0_UNCHECKED",
                 detail="the source moved", authored_by=RESEARCHER)

    d = dossier_json(graph, claim_id)
    assert len(d["verifications"]) == 2
    assert len(d["latest_verifications"]) == 1
    assert d["latest_verifications"][0]["payload"]["result"] == VerificationResult.FAIL


def test_the_machines_finding_and_a_readers_words_stay_in_separate_fields(graph, source):
    """Not a formatting preference. A confident sentence sitting in `detail`
    reads later as a mechanical result — which is exactly what the negative
    control caught on 2026-09-02."""
    claim_id, _w, _p = cited_claim(graph)
    graph.verify(claim_id, method=VerificationMethod.EXACT_SPAN,
                 result=VerificationResult.FAIL, assurance_level="A0_UNCHECKED",
                 detail="re-fetched 1 passage; 0 re-verified",
                 limitations="reviewer verdict sound: looks right to me",
                 authored_by=REVIEWER)

    v = dossier_json(graph, claim_id)["latest_verifications"][0]["payload"]
    assert "looks right to me" not in v["detail"]
    assert "looks right to me" in v["limitations"]


def test_an_unknown_id_is_an_error_not_an_empty_dossier(graph, source):
    with pytest.raises(NodeNotFound):
        dossier_json(graph, "claim:nope")
