"""Edge retraction: the researcher can withdraw a relation.

Why this exists (compare.md §8): nodes have a ladder and can be rejected, but
edges had neither, so a wrong edge was permanent. That mattered more than it
sounds, because the edges drawn most prominently here are the ones that change
conclusions — a mistaken `parallel_of` does not add noise, it *suppresses*
independent support that genuinely exists, silently, in the direction of this
system's own thesis.

Retraction is the edge-equivalent of rejecting a node, so it follows §8's rules:
researcher only, a reason required, and it persists.
"""
from __future__ import annotations

import pytest

from cohort.errors import (
    EdgeAlreadyRetracted,
    EdgeNotFound,
    MissingRejectionReason,
    NotResearcher,
    PersistentRetraction,
)
from cohort.eventlog import read_events, read_refusals
from cohort.schemas import (
    RESEARCHER,
    ClaimPayload,
    Dating,
    DatingRoute,
    EdgeType,
    PassagePayload,
    WitnessPayload,
)

AGENT = "agent:worker-1"


@pytest.fixture
def supported(graph):
    """One claim, two witnesses the corpus calls parallel — so independence is
    genuinely False and retracting the edge has something to restore."""
    claim = graph.propose_claim(ClaimPayload(text="the phrase recurs"), authored_by=AGENT)
    witnesses = []
    for ref in ("T08n0251", "T08n0252"):
        w = graph.propose_witness(
            WitnessPayload(
                canonical_ref=ref,
                dating=Dating(confidence=DatingRoute.UNKNOWN,
                              basis="no dating route was run for this test"),
            ),
            authored_by=AGENT,
        )
        p = graph.propose_passage(
            PassagePayload(canonical_ref=f"{ref}#x", locator="juan 1", excerpt="色即是空"),
            witness_id=w, authored_by=AGENT,
        )
        graph.attest(p, authored_by=AGENT)
        graph.add_edge(EdgeType.ATTESTS, p, claim, authored_by=AGENT)
        witnesses.append(w)
    edge = graph.add_edge(
        EdgeType.PARALLEL_OF, witnesses[0], witnesses[1], authored_by=AGENT,
    )
    return claim, witnesses, edge


# --- the thing that matters -------------------------------------------------

def test_retracting_a_parallel_edge_restores_the_support_it_suppressed(graph, supported):
    """The whole point. A wrong `parallel_of` discounts real evidence; undoing
    it must give the evidence back, without changing the count."""
    claim, _, edge = supported
    before = graph.independent_support(claim)
    assert before.independent is False and before.attesting_count == 2

    graph.retract_edge(
        edge, authored_by=RESEARCHER,
        reason="the docNumber bracket was a cf. reference, not an asserted parallel",
    )

    after = graph.independent_support(claim)
    assert after.independent is True
    assert after.non_independent_pairs == []
    # The evidence never went anywhere — only the claim about its independence.
    assert after.attesting_count == before.attesting_count
    assert after.distinct_witnesses == before.distinct_witnesses


def test_restoring_puts_the_discount_back(graph, supported):
    claim, _, edge = supported
    graph.retract_edge(edge, authored_by=RESEARCHER, reason="withdrawn pending a check")
    graph.restore_edge(edge, authored_by=RESEARCHER, reason="the bracket is a bare list after all")
    assert graph.independent_support(claim).independent is False


def test_retracting_an_attests_edge_drops_the_support_count(graph, supported):
    """Retraction is general, not a `parallel_of` special case."""
    claim, _, _ = supported
    attests = graph.edges(edge_type=EdgeType.ATTESTS, dst=claim)
    graph.retract_edge(attests[0].id, authored_by=RESEARCHER, reason="the excerpt was misquoted")
    assert graph.independent_support(claim).attesting_count == 1


# --- nothing is deleted -----------------------------------------------------

def test_a_retracted_edge_is_withdrawn_not_erased(graph, supported):
    """"The researcher withdrew this" and "this was never asserted" are
    different facts about the record."""
    _, _, edge = supported
    graph.retract_edge(edge, authored_by=RESEARCHER, reason="mistaken reading of the bracket")

    assert graph.edges(edge_type=EdgeType.PARALLEL_OF) == []
    kept = graph.edges(edge_type=EdgeType.PARALLEL_OF, include_retracted=True)
    assert kept, "the row must survive retraction"
    assert all(e.retracted_at for e in kept)
    assert all("mistaken reading" in e.retracted_reason for e in kept)


def test_both_directions_of_a_symmetric_edge_retract_together(graph, supported):
    """`parallel_of` is stored as two rows. A relation that held in one
    direction only is not a state this vocabulary has."""
    _, _, edge = supported
    graph.retract_edge(edge, authored_by=RESEARCHER, reason="withdrawn after re-reading")
    kept = graph.edges(edge_type=EdgeType.PARALLEL_OF, include_retracted=True)
    assert len(kept) == 2
    assert all(e.retracted_at is not None for e in kept)
    # and each row says who did it, not just that it happened
    assert all("retracted" in [a.action for a in e.authorship] for e in kept)


def test_retraction_survives_a_rebuild(graph, supported):
    """The log is ground truth, so a retraction has to replay."""
    _, _, edge = supported
    graph.retract_edge(edge, authored_by=RESEARCHER, reason="withdrawn after re-reading")
    assert graph.rebuild().ok is True
    assert any(e.event == "retract_edge" for e in read_events(graph.event_log.path))


def test_restoration_survives_a_rebuild(graph, supported):
    _, _, edge = supported
    graph.retract_edge(edge, authored_by=RESEARCHER, reason="withdrawn after re-reading")
    graph.restore_edge(edge, authored_by=RESEARCHER, reason="restored after a second look")
    assert graph.rebuild().ok is True


# --- it persists, like rejection -------------------------------------------

def test_a_retracted_edge_cannot_be_redrawn_by_a_tool(graph, supported):
    """The mirror of PersistentRejection. Without this, retracting a wrong
    `parallel_of` would last only until the next link_parallels run put it
    back, and the researcher's judgement would be silently overwritten."""
    _, witnesses, edge = supported
    graph.retract_edge(edge, authored_by=RESEARCHER, reason="the reference was a cf.")
    with pytest.raises(PersistentRetraction):
        graph.add_edge(EdgeType.PARALLEL_OF, witnesses[0], witnesses[1], authored_by=AGENT)


def test_a_refused_redraw_is_recorded_as_a_refusal(graph, supported):
    _, witnesses, edge = supported
    graph.retract_edge(edge, authored_by=RESEARCHER, reason="the reference was a cf.")
    with pytest.raises(PersistentRetraction):
        graph.add_edge(EdgeType.PARALLEL_OF, witnesses[0], witnesses[1], authored_by=AGENT)
    rules = [r.rule for r in read_refusals(graph.event_log.path)]
    assert "PersistentRetraction" in rules


def test_restoring_lets_it_be_redrawn_again(graph, supported):
    _, witnesses, edge = supported
    graph.retract_edge(edge, authored_by=RESEARCHER, reason="withdrawn pending a check")
    graph.restore_edge(edge, authored_by=RESEARCHER, reason="the check confirmed the parallel")
    # converges onto the same edge rather than creating a second one
    again = graph.add_edge(
        EdgeType.PARALLEL_OF, witnesses[0], witnesses[1], authored_by=AGENT,
    )
    assert again == edge


# --- authority and reasons --------------------------------------------------

def test_only_the_researcher_may_retract(graph, supported):
    _, _, edge = supported
    with pytest.raises(NotResearcher):
        graph.retract_edge(edge, authored_by=AGENT, reason="I think this is wrong")


def test_only_the_researcher_may_restore(graph, supported):
    _, _, edge = supported
    graph.retract_edge(edge, authored_by=RESEARCHER, reason="withdrawn pending a check")
    with pytest.raises(NotResearcher):
        graph.restore_edge(edge, authored_by=AGENT, reason="I want it back")


def test_retraction_requires_a_stated_reason(graph, supported):
    _, _, edge = supported
    with pytest.raises(MissingRejectionReason):
        graph.retract_edge(edge, authored_by=RESEARCHER, reason="   ")


def test_double_retraction_is_refused(graph, supported):
    _, _, edge = supported
    graph.retract_edge(edge, authored_by=RESEARCHER, reason="withdrawn after re-reading")
    with pytest.raises(EdgeAlreadyRetracted):
        graph.retract_edge(edge, authored_by=RESEARCHER, reason="withdrawn again somehow")


def test_restoring_an_edge_that_is_not_retracted_is_refused(graph, supported):
    _, _, edge = supported
    with pytest.raises(EdgeAlreadyRetracted):
        graph.restore_edge(edge, authored_by=RESEARCHER, reason="nothing to restore")


def test_an_invented_edge_id_is_refused(graph):
    with pytest.raises(EdgeNotFound):
        graph.retract_edge("edge:nope", authored_by=RESEARCHER, reason="does not exist")


def test_a_quotation_discounts_independence_like_a_parallel(graph):
    """A commentary that quotes its base text is not a second witness to the
    words it quotes. Two passages attesting one claim, one quoting the other:
    two attestations, two distinct witnesses, and `independent` False -- and
    retracting the quotes edge restores it, the way it does for parallel_of."""
    claim = graph.propose_claim(ClaimPayload(text="the phrase recurs"), authored_by=AGENT)
    passages = []
    for ref in ("T15n0603", "T33n1694"):
        w = graph.propose_witness(
            WitnessPayload(
                canonical_ref=ref,
                dating=Dating(confidence=DatingRoute.UNKNOWN, basis="not dated for this test"),
            ),
            authored_by=AGENT,
        )
        p = graph.propose_passage(
            PassagePayload(canonical_ref=f"{ref}#x", locator="juan 1", excerpt="譬是人為多熱"),
            witness_id=w, authored_by=AGENT,
        )
        graph.attest(p, authored_by=AGENT)
        graph.add_edge(EdgeType.ATTESTS, p, claim, authored_by=AGENT)
        passages.append(p)
    before = graph.independent_support(claim)
    assert before.attesting_count == 2
    assert before.distinct_witnesses == 2
    assert before.independent is True
    edge = graph.add_edge(EdgeType.QUOTES, passages[1], passages[0], authored_by=AGENT)
    after = graph.independent_support(claim)
    assert after.attesting_count == 2  # the count of citations never moves
    assert after.distinct_witnesses == 2
    assert after.independent is False
    graph.retract_edge(edge, authored_by=RESEARCHER, reason="the quotation was misidentified")
    assert graph.independent_support(claim).independent is True
    assert graph.agent_report(AGENT).discount_edges_contributed == 1
