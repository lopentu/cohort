"""The author is not the reviewer.

COHORT had no reviewer role: verification was a tool any worker could call,
and nothing stopped an agent attesting its own claim. Both sibling projects
separate the checker from the checked; compare.md §10 called this the most
substantive outstanding criticism of the project. These tests pin the two
halves of the answer — the rule at the write boundary, and the role that
gives the refused work somewhere to go.
"""
from __future__ import annotations

from pathlib import Path

import pytest

from cohort.errors import (
    ReviewerNotIndependent,
    SelfAttestation,
)
from cohort.eventlog import read_events
from cohort.schemas import (
    RESEARCHER,
    AgentKind,
    AgentProfile,
    ClaimPayload,
    ConjecturePayload,
    Dating,
    DatingRoute,
    EdgeType,
    NodeStatus,
    PassagePayload,
    QueryPayload,
    VerificationResult,
    WitnessPayload,
)
from cohort.sources.local_reader import LocalReader
from cohort.tools.find_attestations import FindAttestationsInput, find_attestations
from cohort.tools.review_claim import ReviewClaimInput, review_claim

AUTHOR = "agent:author"
REVIEWER = "agent:reviewer"
FIXTURE = Path(__file__).parent.parent / "examples" / "local_corpus"


@pytest.fixture
def source():
    r = LocalReader(FIXTURE)
    yield r
    r.close()


def _register(graph, agent_id: str, model: str, kind=AgentKind.WORKER) -> None:
    graph.register_agent(
        AgentProfile(id=agent_id, kind=kind, model=model), authored_by=agent_id,
    )


def _backed_claim(graph, source, *, author=AUTHOR, text="the phrase recurs") -> str:
    """A claim with real, re-verifiable citations, authored by `author`.

    The author gathers its own evidence — that is ordinary and allowed. What
    it cannot do is close the rung, which is what leaves the claim `proposed`
    and is exactly the state a reviewer exists to resolve."""
    claim_id = graph.propose_claim(ClaimPayload(text=text), authored_by=author)
    report = find_attestations(
        graph, source,
        FindAttestationsInput(claim_or_conjecture_id=claim_id, query="明月"),
        authored_by=author,
    )
    assert report.passages, "fixture must yield hits for this test to mean anything"
    return claim_id


# --- the rule ---------------------------------------------------------------

def test_an_agent_cannot_attest_the_claim_it_authored(graph, source):
    claim_id = _backed_claim(graph, source)
    with pytest.raises(SelfAttestation):
        graph.attest(claim_id, authored_by=AUTHOR)
    assert graph.get_node(claim_id).status == NodeStatus.PROPOSED


def test_the_refusal_is_recorded_with_the_reason(graph, source):
    """A refused write is part of the scholarly record, not an error swallowed
    in a tool loop — the researcher must be able to read *why* a claim stalled."""
    claim_id = _backed_claim(graph, source)
    with pytest.raises(SelfAttestation):
        graph.attest(claim_id, authored_by=AUTHOR)

    refusals = [e for e in read_events(graph.event_log.path) if e.event == "refused"]
    assert len(refusals) == 1
    assert refusals[0].detail["rule"] == "SelfAttestation"
    assert "may not attest it" in refusals[0].detail["message"]


def test_another_agent_can_attest_it(graph, source):
    claim_id = _backed_claim(graph, source)
    graph.attest(claim_id, authored_by=REVIEWER)
    assert graph.get_node(claim_id).status == NodeStatus.ATTESTED


def test_a_reviewer_sharing_a_model_family_is_refused(graph, source):
    """A different agent id on the same model is not a different reader. This
    is the roster rule applied at the write, which catches what a roster check
    cannot see: two agents registered by separate runs against one graph."""
    _register(graph, AUTHOR, "z-ai/glm-5.3")
    _register(graph, REVIEWER, "z-ai/glm-5.3-flash", kind=AgentKind.REVIEWER)
    claim_id = _backed_claim(graph, source)

    with pytest.raises(ReviewerNotIndependent) as e:
        graph.attest(claim_id, authored_by=REVIEWER)
    assert "z-ai" in str(e.value)
    assert graph.get_node(claim_id).status == NodeStatus.PROPOSED


def test_a_reviewer_from_another_family_may_attest(graph, source):
    _register(graph, AUTHOR, "z-ai/glm-5.3")
    _register(graph, REVIEWER, "deepseek/deepseek-v4-flash", kind=AgentKind.REVIEWER)
    claim_id = _backed_claim(graph, source)

    graph.attest(claim_id, authored_by=REVIEWER)
    assert graph.get_node(claim_id).status == NodeStatus.ATTESTED


def test_an_unregistered_model_is_allowed_through(graph, source):
    """The documented limit of the heuristic, pinned so it cannot be mistaken
    for a guarantee: with no declared model there is no family to compare, and
    refusing on that would state more than is known. The author-is-not-reviewer
    half still applies, and is what actually holds here."""
    _register(graph, AUTHOR, "z-ai/glm-5.3")
    claim_id = _backed_claim(graph, source)

    graph.attest(claim_id, authored_by=REVIEWER)  # never registered a model
    assert graph.get_node(claim_id).status == NodeStatus.ATTESTED


def test_the_researcher_may_attest_their_own_proposal(graph, source):
    """The exemption, stated as a test so it is a decision and not an
    oversight. `accept` is already the human gate and the researcher is the
    accountable party; requiring a second human would make single-researcher
    use impossible, which is not what this rule is for."""
    claim_id = _backed_claim(graph, source, author=RESEARCHER)
    # `find_attestations` already closed the rung, because for the researcher
    # there is no conflict to decline over — that is the exemption in action.
    assert graph.get_node(claim_id).status == NodeStatus.ATTESTED
    graph.accept(claim_id, authored_by=RESEARCHER)
    assert graph.get_node(claim_id).status == NodeStatus.ACCEPTED


def test_a_passage_may_be_attested_by_the_agent_that_found_it(graph):
    """Source-derived nodes are exempt. Where a passage sits is settled by the
    corpus, not by its finder's judgement, and two agents recording the same
    passage converge onto one node — so "the author" is not a single party to
    hold at arm's length."""
    w = graph.propose_witness(
        WitnessPayload(
            canonical_ref="T01n0001",
            dating=Dating(confidence=DatingRoute.UNKNOWN, basis="not dated for this test"),
        ),
        authored_by=AUTHOR,
    )
    graph.attest(w, authored_by=AUTHOR)
    p = graph.propose_passage(
        PassagePayload(canonical_ref="T01n0001#a", locator="juan 1", excerpt="明月"),
        witness_id=w, authored_by=AUTHOR,
    )
    graph.attest(p, authored_by=AUTHOR)
    assert graph.get_node(p).status == NodeStatus.ATTESTED


def test_a_query_is_not_reviewable(graph):
    """A query is a retrieval to run, not an assertion, so there is nothing
    for a second reader to be right or wrong about — and `verify()` refuses a
    query as a subject, so a rule here would create a rung no reviewer could
    record having checked."""
    q = graph.propose_query(QueryPayload(text="明月"), authored_by=AUTHOR)
    graph.attest(q, authored_by=AUTHOR)
    assert graph.get_node(q).status == NodeStatus.ATTESTED


def test_attesting_does_not_make_you_an_author(graph, source):
    """`_proposing_authors` counts `proposed`/`converged` only. If an
    `attested` row counted, a reviewer would lock itself out of a node it had
    already legitimately checked — an easy off-by-one with a silent effect."""
    claim_id = _backed_claim(graph, source)
    graph.attest(claim_id, authored_by=REVIEWER)
    graph.reject(claim_id, authored_by=RESEARCHER, reason="on reflection, too broad")
    graph.reopen(claim_id, authored_by=RESEARCHER, reason="narrowed and worth re-testing")

    graph.attest(claim_id, authored_by=REVIEWER)  # same reviewer, second time
    assert graph.get_node(claim_id).status == NodeStatus.ATTESTED


def test_attest_conflict_reports_the_reason_without_writing(graph, source):
    """The public read that lets a caller decline instead of provoking a
    certain refusal."""
    claim_id = _backed_claim(graph, source)

    assert "may not attest it" in str(graph.attest_conflict(claim_id, AUTHOR))
    assert graph.attest_conflict(claim_id, REVIEWER) is None
    assert [e for e in read_events(graph.event_log.path) if e.event == "refused"] == []


# --- the tool ---------------------------------------------------------------

def test_review_promotes_a_claim_whose_spans_re_verify(graph, source):
    claim_id = _backed_claim(graph, source)
    report = review_claim(
        graph, source,
        ReviewClaimInput(claim_id=claim_id, verdict="sound",
                         detail="re-fetched both citations; the phrase is where it says"),
        authored_by=REVIEWER,
    )

    assert report.spans_checked == report.spans_matched > 0
    assert report.attested is True
    assert graph.get_node(claim_id).status == NodeStatus.ATTESTED
    verification = graph.get_node(report.verification_id)
    assert verification.payload["result"] == VerificationResult.PASS


def test_a_model_verdict_cannot_promote_a_claim_whose_spans_fail(graph, source):
    """The property the whole design rests on: promotion comes from the
    mechanical re-check, never from what a model said. Here the reviewer says
    'sound' and the citation does not re-verify — and the claim does not move.

    Without this, a reviewer would be a second model whose agreement counts as
    evidence, which is precisely what `VerificationMethod` refuses to admit as
    a verification method."""
    w = graph.propose_witness(
        WitnessPayload(
            canonical_ref="poem-001",
            dating=Dating(confidence=DatingRoute.UNKNOWN, basis="not dated for this test"),
        ),
        authored_by=AUTHOR,
    )
    graph.attest(w, authored_by=AUTHOR)
    p = graph.propose_passage(
        PassagePayload(
            canonical_ref="poem-001#ghost", locator="line 1",
            excerpt="這句話不在原文裡",  # not in the fixture text
        ),
        witness_id=w, authored_by=AUTHOR,
    )
    graph.attest(p, authored_by=AUTHOR)
    claim_id = graph.propose_claim(ClaimPayload(text="a claim on a bad citation"), authored_by=AUTHOR)
    graph.add_edge(EdgeType.ATTESTS, p, claim_id, authored_by=AUTHOR)

    report = review_claim(
        graph, source,
        ReviewClaimInput(claim_id=claim_id, verdict="sound", detail="looks right to me"),
        authored_by=REVIEWER,
    )

    assert report.spans_matched == 0
    assert report.attested is False
    assert graph.get_node(claim_id).status == NodeStatus.PROPOSED
    assert graph.get_node(report.verification_id).payload["result"] == VerificationResult.FAIL
    assert "did not re-verify" in report.note


def test_a_sound_verdict_never_lands_in_the_machines_field(graph, source):
    """`detail` is what the re-fetch established; the reviewer's words are a
    limit on what that establishes. A positive verdict was the exception until
    the negative control showed what the exception cost: a model returned
    `sound` over a citation that did not re-verify, and its confident sentence
    was written into `detail` on a verification whose result was `fail`."""
    w = graph.propose_witness(
        WitnessPayload(
            canonical_ref="poem-001",
            dating=Dating(confidence=DatingRoute.UNKNOWN, basis="not dated for this test"),
        ),
        authored_by=AUTHOR,
    )
    graph.attest(w, authored_by=AUTHOR)
    p = graph.propose_passage(
        PassagePayload(canonical_ref="poem-001#ghost", locator="line 1",
                       excerpt="這句話不在原文裡"),
        witness_id=w, authored_by=AUTHOR,
    )
    graph.attest(p, authored_by=AUTHOR)
    claim_id = graph.propose_claim(ClaimPayload(text="a claim on a bad citation"), authored_by=AUTHOR)
    graph.add_edge(EdgeType.ATTESTS, p, claim_id, authored_by=AUTHOR)

    report = review_claim(
        graph, source,
        ReviewClaimInput(claim_id=claim_id, verdict="sound",
                         detail="Re-fetched and re-verified every cited passage."),
        authored_by=REVIEWER,
    )

    payload = graph.get_node(report.verification_id).payload
    assert payload["result"] == VerificationResult.FAIL
    assert "re-verified every cited passage" not in payload["detail"]
    assert "sound" in payload["limitations"]
    assert "re-verified every cited passage" in payload["limitations"]


def test_an_objection_withholds_promotion_and_is_recorded(graph, source):
    """The other side of the asymmetry: the reviewer's judgement can subtract.
    A silent non-attestation would be indistinguishable from a reviewer that
    never ran, so the objection is written down even though the ladder does
    not move."""
    claim_id = _backed_claim(graph, source)
    report = review_claim(
        graph, source,
        ReviewClaimInput(
            claim_id=claim_id, verdict="unsound",
            detail="the passage is about the moon, not about homesickness",
        ),
        authored_by=REVIEWER,
    )

    assert report.spans_matched == report.spans_checked  # the spans were fine
    assert report.attested is False
    assert graph.get_node(claim_id).status == NodeStatus.PROPOSED

    payload = graph.get_node(report.verification_id).payload
    assert payload["result"] == VerificationResult.PASS  # mechanically, yes
    assert "unsound" in payload["limitations"]
    assert "homesickness" in payload["limitations"]
    # the model's reading never becomes the mechanical finding
    assert "homesickness" not in payload["detail"]


def test_a_reviewer_is_refused_its_own_claim_before_spending_a_fetch(graph, source):
    """`attest()` would refuse at the end anyway, but a reviewer that has
    already re-fetched every citation has learnt the rule too late to act on
    it."""
    claim_id = _backed_claim(graph, source)
    with pytest.raises(SelfAttestation, match="may not attest it"):
        review_claim(
            graph, source,
            ReviewClaimInput(claim_id=claim_id, verdict="sound", detail="mine, surely"),
            authored_by=AUTHOR,
        )
    assert graph.verifications(claim_id) == []


def test_reviewing_an_uncited_claim_advances_nothing(graph):
    claim_id = graph.propose_claim(ClaimPayload(text="nothing cites this"), authored_by=AUTHOR)
    report = review_claim(
        graph, LocalReader(FIXTURE),
        ReviewClaimInput(claim_id=claim_id, verdict="sound", detail="nothing to check"),
        authored_by=REVIEWER,
    )
    assert report.spans_checked == 0
    assert report.attested is False
    assert "nothing to re-check" in report.note


def test_review_surfaces_independence_the_author_had_no_reason_to_check(graph, source):
    """Support count and independence travel together or the count misleads —
    the reviewer is the natural place to look, since the author has no
    incentive to."""
    claim_id = _backed_claim(graph, source)
    report = review_claim(
        graph, source,
        ReviewClaimInput(claim_id=claim_id, verdict="sound", detail="checked"),
        authored_by=REVIEWER,
    )
    assert report.distinct_witnesses >= 1
    assert isinstance(report.independent, bool)
    assert "independent=" in graph.get_node(report.verification_id).payload["detail"]


def test_a_conjecture_still_needs_its_tests_edge(graph, source):
    """The falsifiability gate outranks review: a sound-looking conjecture with
    no prospective test does not advance, and the reviewer is told why rather
    than left with a silent no-op."""
    conjecture_id = graph.propose_conjecture(
        ConjecturePayload(
            text="the phrase marks a later recension",
            derivation="vocabulary pattern in the fixture corpus",
            corpus_boundary="only the local_corpus fixture was searched",
            selection_risks="the fixture is small enough that one poem dominates",
            alternative_explanations="a shared formula rather than a recension boundary",
        ),
        authored_by=AUTHOR,
    )
    find_attestations(
        graph, source,
        FindAttestationsInput(claim_or_conjecture_id=conjecture_id, query="明月"),
        authored_by=AUTHOR,
    )
    report = review_claim(
        graph, source,
        ReviewClaimInput(claim_id=conjecture_id, verdict="sound", detail="citations check out"),
        authored_by=REVIEWER,
    )
    assert report.attested is False
    assert "UnattestableConjecture" in report.note or "tests edge" in report.note
    assert graph.get_node(conjecture_id).status == NodeStatus.PROPOSED


# --- the role, as an agent --------------------------------------------------

def test_a_reviewer_asking_for_a_proposing_tool_is_told_why_not(graph, source):
    """The role restriction is the tool list, but a model that asks for a tool
    it does not have should learn the reason rather than get a bare 'unknown
    tool' — a reviewer told only that would keep trying."""
    from cohort.agents.review_worker import ReviewWorker

    worker = ReviewWorker(
        graph, source=source, authored_by=REVIEWER, model="vendor/fake",
        api_key="test-key", transport=lambda *a: (200, b"{}"),
    )
    is_error, result = worker._dispatch("propose_claim", {"text": "x"})

    assert is_error
    assert "review_claim" in result
    assert "not a reviewer" in result


def test_the_reviewers_tool_list_holds_no_way_to_write_a_claim(graph, source):
    from cohort.agents.review_worker import ReviewWorker

    names = {t["function"]["name"] for t in ReviewWorker.TOOLS}
    assert names == {"review_claim", "record_contradiction"}


def test_pending_review_context_skips_what_this_reviewer_authored(graph, source):
    """A reviewer offered its own claim would spend a fetch, a turn and a
    refusal discovering a rule the graph could have told it for free."""
    from cohort.agents.review_worker import pending_review_context

    mine = _backed_claim(graph, source, author=REVIEWER, text="mine")
    theirs = _backed_claim(graph, source, author=AUTHOR, text="theirs")

    context = pending_review_context(graph, REVIEWER)
    assert theirs in context
    assert mine not in context


def test_pending_review_context_quotes_the_id_it_wants_copied(graph, source):
    """`- claim:abc… [claim] '…'` reads as a field label followed by a value,
    and in the first censused multi-model run all three models read it that
    way: every review was refused `NodeNotFound` on a prefix-stripped id.
    Quoting the id and saying the prefix is inside it is the fix on the
    prompt side; `Graph._unfound_detail` is the fix on the boundary side."""
    from cohort.agents.review_worker import pending_review_context

    theirs = _backed_claim(graph, source, author=AUTHOR, text="theirs")
    context = pending_review_context(graph, REVIEWER)

    assert f'"{theirs}"' in context
    assert "not a label on it" in context


def test_pending_review_context_is_none_when_there_is_nothing(graph, source):
    """None, not an empty string: 'nothing to review' is a reason to skip the
    agent entirely rather than bill a turn for it."""
    from cohort.agents.review_worker import pending_review_context

    _backed_claim(graph, source, author=REVIEWER)
    assert pending_review_context(graph, REVIEWER) is None
