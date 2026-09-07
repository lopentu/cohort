"""The write boundary: identity, edges, the falsifiability gate, the
promotion ladder, rebuild, and the single-writer lock (design doc §5-8, §11).
"""
from __future__ import annotations

import sqlite3

import pytest

from cohort.errors import (
    EdgeDomainViolation,
    EdgeEndpointMissing,
    EdgeSelfLoop,
    MissingRejectionReason,
    NodeNotFound,
    NoEventLog,
    NotResearcher,
    PersistentRejection,
    RebuildMismatch,
    RungSkipped,
    SingleWriterViolation,
    UnattestableClaim,
    UnattestableConjecture,
)
from cohort.eventlog import EventLog, read_events
from cohort.graph import Graph
from cohort.migrations import MigrationError
from cohort.schemas import (
    RESEARCHER,
    ClaimPayload,
    ConjecturePayload,
    Dating,
    DatingRoute,
    EdgeType,
    NodeStatus,
    PassagePayload,
    QueryPayload,
    WitnessPayload,
)

AGENT = "agent:worker-1"
#: A second agent, because an agent may not attest what it authored
#: (`Graph._reviewer_conflict`). Unregistered on purpose in most of
#: these fixtures: with no declared model there is no family to
#: compare, so what is being exercised is the author-is-not-reviewer
#: half of the rule on its own.
REVIEWER = "agent:reviewer-1"
AGENT_2 = "agent:worker-2"


def _witness(g, ref="T01n0001", *, authored_by=AGENT):
    payload = WitnessPayload(
        canonical_ref=ref,
        dating=Dating(
            confidence=DatingRoute.SOURCE_LABEL,
            basis="colophon states a Northern Song printing",
        ),
    )
    return g.propose_witness(payload, authored_by=authored_by)


def _passage(g, witness_id, ref, *, authored_by=AGENT):
    payload = PassagePayload(canonical_ref=ref, locator="juan 3, line 12")
    return g.propose_passage(payload, witness_id=witness_id, authored_by=authored_by)


def _claim(g, text="X translated Y in the Tang", *, authored_by=AGENT):
    return g.propose_claim(ClaimPayload(text=text), authored_by=authored_by)


def _conjecture(g, text="Y is a lost Kuchean original", *, authored_by=AGENT):
    return g.propose_conjecture(
        ConjecturePayload(
            text=text,
            derivation="the passage's vocabulary matches Kuchean loanword patterns",
            corpus_boundary="only the local_corpus fixture was searched",
            selection_risks="none identified",
            alternative_explanations="a later redactor independently chose similar vocabulary",
        ),
        authored_by=authored_by,
    )


def _query(g, text="search catalogue for a Kuchean fragment of Y", *, authored_by=AGENT):
    return g.propose_query(QueryPayload(text=text), authored_by=authored_by)


def _attested_claim_with_two_witness_backed_passages(g):
    w1 = _witness(g, "T01n0001")
    w2 = _witness(g, "T02n0002")
    p1 = _passage(g, w1, "T01n0001p0001a12")
    p2 = _passage(g, w2, "T02n0002p0003b04")
    g.attest(p1, authored_by=AGENT)
    g.attest(p2, authored_by=AGENT)
    c = _claim(g)
    g.add_edge(EdgeType.ATTESTS, p1, c, authored_by=AGENT)
    g.add_edge(EdgeType.ATTESTS, p2, c, authored_by=AGENT)
    return c, w1, w2


# --- identity and authorship (design doc §5 principle 5, §11) ---------------

def test_propose_witness_twice_converges_and_accumulates_authorship(graph):
    id1 = _witness(graph, authored_by=AGENT)
    id2 = _witness(graph, authored_by=AGENT_2)
    assert id1 == id2
    node = graph.get_node(id1)
    assert [a.author for a in node.authorship] == [AGENT, AGENT_2]
    assert node.authorship[1].action == "converged"


def test_claim_identity_is_never_content_derived(graph):
    id1 = _claim(graph, text="same text")
    id2 = _claim(graph, text="same text")
    assert id1 != id2


# --- edges (design doc §6) ---------------------------------------------------

def test_add_edge_refuses_missing_src(graph):
    w = _witness(graph)
    with pytest.raises(EdgeEndpointMissing):
        graph.add_edge(EdgeType.PARALLEL_OF, "witness:missing", w, authored_by=AGENT)


def test_add_edge_refuses_missing_dst(graph):
    w = _witness(graph)
    with pytest.raises(EdgeEndpointMissing):
        graph.add_edge(EdgeType.PARALLEL_OF, w, "witness:missing", authored_by=AGENT)


def test_add_edge_refuses_self_loop(graph):
    w = _witness(graph)
    with pytest.raises(EdgeSelfLoop):
        graph.add_edge(EdgeType.PARALLEL_OF, w, w, authored_by=AGENT)


def test_edge_domain_violation(graph):
    w = _witness(graph)
    c = _claim(graph)
    with pytest.raises(EdgeDomainViolation):
        graph.add_edge(EdgeType.ATTESTS, w, c, authored_by=AGENT)  # attests: passage -> claim only


def test_attests_edge_is_legal_passage_to_claim(graph):
    w = _witness(graph)
    p = _passage(graph, w, "T01n0001p0001a12")
    c = _claim(graph)
    assert graph.add_edge(EdgeType.ATTESTS, p, c, authored_by=AGENT)


def test_re_adding_the_same_edge_converges_instead_of_erroring(graph):
    w1 = _witness(graph, "T01n0001")
    w2 = _witness(graph, "T02n0002")
    id1 = graph.add_edge(EdgeType.PARALLEL_OF, w1, w2, authored_by=AGENT)
    id2 = graph.add_edge(EdgeType.PARALLEL_OF, w1, w2, authored_by=AGENT_2)
    assert id1 == id2
    edge = graph.edges(edge_type=EdgeType.PARALLEL_OF, src=w1, dst=w2)[0]
    assert [a.author for a in edge.authorship] == [AGENT, AGENT_2]


def test_contradicts_is_materialized_both_directions(graph):
    c1 = _claim(graph, text="A")
    c2 = _claim(graph, text="B")
    graph.add_edge(EdgeType.CONTRADICTS, c1, c2, authored_by=AGENT)
    assert graph.edges(edge_type=EdgeType.CONTRADICTS, src=c1, dst=c2)
    assert graph.edges(edge_type=EdgeType.CONTRADICTS, src=c2, dst=c1)


def test_parallel_of_is_materialized_both_directions(graph):
    w1 = _witness(graph, "T01n0001")
    w2 = _witness(graph, "T02n0002")
    graph.add_edge(EdgeType.PARALLEL_OF, w1, w2, authored_by=AGENT)
    assert graph.edges(edge_type=EdgeType.PARALLEL_OF, src=w1, dst=w2)
    assert graph.edges(edge_type=EdgeType.PARALLEL_OF, src=w2, dst=w1)


def test_descends_from_is_single_direction(graph):
    w1 = _witness(graph, "T01n0001")
    w2 = _witness(graph, "T02n0002")
    graph.add_edge(EdgeType.DESCENDS_FROM, w2, w1, authored_by=AGENT)  # w2 descends from w1
    assert graph.edges(edge_type=EdgeType.DESCENDS_FROM, src=w2, dst=w1)
    assert not graph.edges(edge_type=EdgeType.DESCENDS_FROM, src=w1, dst=w2)


def test_propose_passage_creates_part_of_edge_and_is_attestable(graph):
    w = _witness(graph)
    p = _passage(graph, w, "T01n0001p0001a12")
    assert graph.edges(edge_type=EdgeType.PART_OF, src=p, dst=w)
    graph.attest(p, authored_by=AGENT)  # PassageNotLocated never fires — part_of exists by construction
    assert graph.get_node(p).status == NodeStatus.ATTESTED


# --- the falsifiability gate (design doc §7) --------------------------------

def test_claim_unattestable_without_attests_edge(graph):
    c = _claim(graph)
    with pytest.raises(UnattestableClaim):
        graph.attest(c, authored_by=REVIEWER)


def test_claim_attestable_once_an_attested_passage_backs_it(graph):
    w = _witness(graph)
    p = _passage(graph, w, "T01n0001p0001a12")
    graph.attest(p, authored_by=AGENT)
    c = _claim(graph)
    graph.add_edge(EdgeType.ATTESTS, p, c, authored_by=AGENT)
    graph.attest(c, authored_by=REVIEWER)
    assert graph.get_node(c).status == NodeStatus.ATTESTED


def test_claim_not_attestable_from_a_merely_proposed_passage(graph):
    w = _witness(graph)
    p = _passage(graph, w, "T01n0001p0001a12")  # not yet attested
    c = _claim(graph)
    graph.add_edge(EdgeType.ATTESTS, p, c, authored_by=AGENT)
    with pytest.raises(UnattestableClaim):
        graph.attest(c, authored_by=REVIEWER)


def test_conjecture_unattestable_without_tests_edge(graph):
    conj = _conjecture(graph)
    with pytest.raises(UnattestableConjecture):
        graph.attest(conj, authored_by=REVIEWER)


def test_conjecture_attests_edges_never_satisfy_the_gate(graph):
    """A conjecture smuggled attestations in through the wrong edge stays
    unattestable via that route, however many attests edges it collects
    (design doc §11) — a tests edge is what unblocks it."""
    w = _witness(graph)
    p = _passage(graph, w, "T01n0001p0001a12")
    graph.attest(p, authored_by=AGENT)
    conj = _conjecture(graph)
    graph.add_edge(EdgeType.ATTESTS, p, conj, authored_by=AGENT)  # legal domain, wrong gate
    with pytest.raises(UnattestableConjecture):
        graph.attest(conj, authored_by=REVIEWER)

    q = _query(graph)
    graph.add_edge(EdgeType.TESTS, q, conj, authored_by=AGENT)
    graph.attest(conj, authored_by=REVIEWER)
    assert graph.get_node(conj).status == NodeStatus.ATTESTED


# --- the promotion ladder (design doc §8) -----------------------------------

def test_full_ladder_proposed_attested_accepted(graph):
    c, _, _ = _attested_claim_with_two_witness_backed_passages(graph)
    graph.attest(c, authored_by=REVIEWER)
    assert graph.get_node(c).status == NodeStatus.ATTESTED
    decision_id = graph.accept(c, authored_by=RESEARCHER)
    assert graph.get_node(c).status == NodeStatus.ACCEPTED
    decision = graph.get_node(decision_id)
    assert decision.status == NodeStatus.ACCEPTED
    assert decision.payload["subject_node_id"] == c
    assert decision.payload["verdict"] == "accepted"


def test_accept_skipping_attested_raises(graph):
    c, _, _ = _attested_claim_with_two_witness_backed_passages(graph)
    with pytest.raises(RungSkipped):
        graph.accept(c, authored_by=RESEARCHER)  # still only proposed


def test_accept_by_non_researcher_raises(graph):
    c, _, _ = _attested_claim_with_two_witness_backed_passages(graph)
    graph.attest(c, authored_by=REVIEWER)
    with pytest.raises(NotResearcher):
        graph.accept(c, authored_by=AGENT)


def test_reject_requires_a_reason(graph):
    c = _claim(graph)
    with pytest.raises(MissingRejectionReason):
        graph.reject(c, authored_by=RESEARCHER, reason="   ")


def test_reject_from_proposed_and_from_attested(graph):
    c1 = _claim(graph)
    graph.reject(c1, authored_by=RESEARCHER, reason="text is unintelligible")
    assert graph.get_node(c1).status == NodeStatus.REJECTED
    assert graph.get_node(c1).rejected_reason == "text is unintelligible"

    c2, _, _ = _attested_claim_with_two_witness_backed_passages(graph)
    graph.attest(c2, authored_by=REVIEWER)
    graph.reject(c2, authored_by=RESEARCHER, reason="cited passage does not actually say this")
    assert graph.get_node(c2).status == NodeStatus.REJECTED


def test_persistent_rejection_blocks_re_proposal(graph):
    w = _witness(graph)
    graph.reject(w, authored_by=RESEARCHER, reason="not a genuine witness, catalogue error")
    with pytest.raises(PersistentRejection):
        _witness(graph)  # same canonical_ref


def test_reopen_by_researcher_allows_progress_again(graph):
    w = _witness(graph)
    graph.reject(w, authored_by=RESEARCHER, reason="catalogue error, later corrected")
    graph.reopen(w, authored_by=RESEARCHER, reason="catalogue entry was itself amended")
    assert graph.get_node(w).status == NodeStatus.PROPOSED
    graph.attest(w, authored_by=AGENT)
    assert graph.get_node(w).status == NodeStatus.ATTESTED


def test_citable_returns_only_accepted_nodes_and_excludes_decisions(graph):
    c, w1, _ = _attested_claim_with_two_witness_backed_passages(graph)
    graph.attest(c, authored_by=REVIEWER)
    graph.accept(c, authored_by=RESEARCHER)  # also creates a decision node
    ids = {n.id for n in graph.citable()}
    assert c in ids
    assert w1 not in ids  # only attested, never accepted
    assert all(n.type != "decision" for n in graph.citable())


def test_rejected_returns_rejected_nodes_with_reasons(graph):
    c1 = _claim(graph, text="rejected claim")
    graph.reject(c1, authored_by=RESEARCHER, reason="unsupported by any passage")
    c2 = _claim(graph, text="untouched claim")

    rejected = graph.rejected()
    ids = {n.id for n in rejected}
    assert c1 in ids
    assert c2 not in ids
    r = next(n for n in rejected if n.id == c1)
    assert r.rejected_reason == "unsupported by any passage"


def test_rejected_filters_by_node_type(graph):
    w = _witness(graph)
    graph.reject(w, authored_by=RESEARCHER, reason="catalogue error")
    c = _claim(graph)
    graph.reject(c, authored_by=RESEARCHER, reason="unsupported")

    only_claims = graph.rejected(node_type="claim")
    assert {n.id for n in only_claims} == {c}


# --- independent_support: the headline demo output (design doc §4, §11) -----

def test_independent_support_starts_independent(graph):
    c, _, _ = _attested_claim_with_two_witness_backed_passages(graph)
    support = graph.independent_support(c)
    assert support.attesting_count == 2
    assert support.distinct_witnesses == 2
    assert support.independent is True


def test_independent_support_flips_on_parallel_of(graph):
    c, w1, w2 = _attested_claim_with_two_witness_backed_passages(graph)
    graph.add_edge(EdgeType.PARALLEL_OF, w1, w2, authored_by=AGENT)
    support = graph.independent_support(c)
    assert support.attesting_count == 2  # unchanged
    assert support.independent is False


def test_independent_support_flips_on_descends_from(graph):
    c, w1, w2 = _attested_claim_with_two_witness_backed_passages(graph)
    graph.add_edge(EdgeType.DESCENDS_FROM, w2, w1, authored_by=AGENT)
    support = graph.independent_support(c)
    assert support.attesting_count == 2
    assert support.independent is False


# --- rebuild (design doc §5 principle 1, §11) -------------------------------

def test_rebuild_matches_live_after_a_full_workflow(tmp_path):
    log = EventLog(tmp_path / "events.jsonl")
    g = Graph(tmp_path / "graph.sqlite", event_log=log)
    c, w1, w2 = _attested_claim_with_two_witness_backed_passages(g)
    g.attest(c, authored_by=REVIEWER)
    g.accept(c, authored_by=RESEARCHER)
    g.add_edge(EdgeType.PARALLEL_OF, w1, w2, authored_by=AGENT)
    report = g.rebuild()
    assert report.ok is True
    assert report.nodes == g._count("nodes")
    g.close()


def test_rebuild_does_not_write_a_stray_replay_log(tmp_path):
    log = EventLog(tmp_path / "events.jsonl")
    g = Graph(tmp_path / "graph.sqlite", event_log=log)
    _witness(g)
    before = {p.name for p in tmp_path.iterdir()}
    g.rebuild()
    after = {p.name for p in tmp_path.iterdir()}
    assert after == before
    g.close()


def test_rebuild_detects_a_genuine_mismatch(tmp_path):
    log = EventLog(tmp_path / "events.jsonl")
    g = Graph(tmp_path / "graph.sqlite", event_log=log)
    _witness(g)
    g.conn.execute("UPDATE nodes SET status = 'accepted'")  # corrupt the projection directly
    g.conn.commit()
    with pytest.raises(RebuildMismatch):
        g.rebuild()
    g.close()


def test_graph_open_recovers_from_log_when_db_is_missing(tmp_path):
    db_path, log_path = tmp_path / "graph.sqlite", tmp_path / "events.jsonl"
    g1 = Graph.open(db_path, log_path)
    w = _witness(g1)
    g1.close()

    db_path.unlink()  # lose the projection, keep the log
    g2 = Graph.open(db_path, log_path)
    assert g2.get_node(w).id == w
    g2.close()


# --- refused writes leave an honest log (design doc §11) --------------------

def test_refused_write_is_logged_and_state_unchanged(graph):
    c = _claim(graph)
    with pytest.raises(UnattestableClaim):
        graph.attest(c, authored_by=REVIEWER)
    assert graph.get_node(c).status == NodeStatus.PROPOSED  # unchanged

    refused = [e for e in read_events(graph.event_log.path) if e.event == "refused"]
    assert len(refused) == 1
    assert refused[0].detail["rule"] == "UnattestableClaim"


# --- single-writer discipline (design doc §5 principle 7) -------------------

def test_second_open_on_the_same_db_raises(tmp_path):
    db_path, log_path = tmp_path / "graph.sqlite", tmp_path / "events.jsonl"
    g1 = Graph.open(db_path, log_path)
    with pytest.raises(SingleWriterViolation):
        Graph.open(db_path, log_path)
    g1.close()


def test_read_only_open_succeeds_while_a_writer_holds_the_lock(tmp_path):
    """A reader must not need the writer lock: WAL already makes concurrent
    reads safe, so a UI or report can attach during an agent run."""
    db_path, log_path = tmp_path / "graph.sqlite", tmp_path / "events.jsonl"
    writer = Graph.open(db_path, log_path)
    claim_id = writer.propose_claim(ClaimPayload(text="a claim to read"), authored_by=AGENT)

    reader = Graph.open_read_only(db_path)
    assert reader.get_node(claim_id).payload["text"] == "a claim to read"
    reader.close()
    writer.close()


def test_read_only_graph_refuses_writes_through_the_existing_guard(tmp_path):
    db_path, log_path = tmp_path / "graph.sqlite", tmp_path / "events.jsonl"
    writer = Graph.open(db_path, log_path)
    writer.close()

    reader = Graph.open_read_only(db_path)
    with pytest.raises(NoEventLog):
        reader.propose_claim(ClaimPayload(text="nope"), authored_by=AGENT)
    reader.close()


def test_read_only_graph_is_read_only_to_sqlite_itself(tmp_path):
    """Not merely read-only by convention: the connection is opened mode=ro,
    so a write refused by the kernel, not only by COHORT's own guard."""
    db_path, log_path = tmp_path / "graph.sqlite", tmp_path / "events.jsonl"
    Graph.open(db_path, log_path).close()

    reader = Graph.open_read_only(db_path)
    with pytest.raises(sqlite3.OperationalError, match="readonly"):
        reader.conn.execute("INSERT INTO nodes (id, type, status) VALUES ('x','claim','proposed')")
    reader.close()


def test_read_only_refuses_a_projection_it_cannot_migrate(tmp_path):
    """Migrations are writes, so a reader skips them — which means an older
    projection must be refused rather than read with the wrong columns."""
    db_path = tmp_path / "stale.sqlite"
    conn = sqlite3.connect(db_path)
    conn.execute("PRAGMA user_version = 1")
    conn.commit()
    conn.close()

    with pytest.raises(MigrationError, match="schema version"):
        Graph.open_read_only(db_path)


def test_read_only_refuses_a_missing_projection(tmp_path):
    with pytest.raises(FileNotFoundError):
        Graph.open_read_only(tmp_path / "absent.sqlite")


def test_lock_is_released_on_close(tmp_path):
    db_path, log_path = tmp_path / "graph.sqlite", tmp_path / "events.jsonl"
    g1 = Graph.open(db_path, log_path)
    g1.close()
    g2 = Graph.open(db_path, log_path)  # should not raise — lock was released
    g2.close()


# --- observability envelope (design doc §5 principle 1, non-mutating) ------

def test_log_model_call_is_non_mutating(graph):
    before = graph._snapshot()
    ev = graph.log_model_call(
        authored_by=AGENT, model="claude-test", latency_ms=123,
        input_tokens=10, output_tokens=5, cost_usd=0.001,
    )
    assert ev.event == "model_call"
    assert graph._snapshot() == before  # no nodes/edges/authorship changed


def test_model_call_id_threads_through_to_the_write_it_caused(graph):
    call = graph.log_model_call(authored_by=AGENT, model="claude-test")
    graph.propose_claim(ClaimPayload(text="a claim"), authored_by=AGENT, model_call_id=call.seq)
    propose_events = [e for e in read_events(graph.event_log.path) if e.event == "propose"]
    assert propose_events[-1].model_call_id == call.seq


def test_rebuild_matches_live_with_model_call_events_present(tmp_path):
    log = EventLog(tmp_path / "events.jsonl")
    g = Graph(tmp_path / "graph.sqlite", event_log=log)
    call = g.log_model_call(authored_by=AGENT, model="claude-test", input_tokens=1, output_tokens=1)
    g.propose_claim(ClaimPayload(text="a claim"), authored_by=AGENT, model_call_id=call.seq)
    report = g.rebuild()
    assert report.ok is True
    g.close()


# --- what a missing node's refusal says --------------------------------------

def test_an_id_without_its_prefix_is_refused_but_names_the_near_miss(graph):
    """Every refusal in the first censused multi-model run was this: three
    agents on three model families each dropped the `claim:` prefix, reading it
    as a label rather than as part of the id. The write is still refused — the
    prefix is what makes an id say what it names — but the refusal is output,
    so it says what to do differently."""
    claim_id = graph.propose_claim(ClaimPayload(text="a claim"), authored_by=AGENT)
    bare = claim_id.split(":", 1)[1]

    with pytest.raises(NodeNotFound) as e:
        graph.get_node(bare)
    assert claim_id in str(e.value)
    assert "part of the id" in str(e.value)


def test_a_genuinely_unknown_id_gets_no_invented_suggestion(graph):
    """The hint is only ever a real node. An invented id must stay a dead end,
    or the refusal starts guessing on the agent's behalf."""
    graph.propose_claim(ClaimPayload(text="a claim"), authored_by=AGENT)
    with pytest.raises(NodeNotFound) as e:
        graph.get_node("nothing-like-this")
    assert "did you mean" not in str(e.value)


def test_an_ambiguous_suffix_lists_the_candidates_rather_than_choosing(graph):
    """Two node types can share a suffix. Picking one would be the endpoint
    minting this system refuses everywhere else, in a smaller costume."""
    claim_id = graph.propose_claim(ClaimPayload(text="a claim"), authored_by=AGENT)
    suffix = claim_id.split(":", 1)[1]
    # Written straight into the projection: ids are uuid-derived, so a
    # collision cannot be produced through the write boundary on purpose.
    graph.conn.execute(
        "INSERT INTO nodes (id, type, status, payload, created_seq, updated_seq, payload_hash) "
        "SELECT ?, 'query', status, payload, created_seq, updated_seq, payload_hash "
        "FROM nodes WHERE id=?",
        (f"query:{suffix}", claim_id),
    )

    with pytest.raises(NodeNotFound) as e:
        graph.get_node(suffix)
    assert "more than one node" in str(e.value)
    assert claim_id in str(e.value) and f"query:{suffix}" in str(e.value)
