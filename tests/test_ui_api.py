"""The read-only JSON API (build order stage 5).

Two properties matter more than the routing: the API cannot write, and it
does not flatten the epistemics docs/design.md §10 warns about — status travels
with every node, and edges that *discount* support are marked as such rather
than looking like edges that add it.
"""
from __future__ import annotations

import pytest

fastapi = pytest.importorskip("fastapi", reason="the `ui` extra is not installed")
from fastapi.testclient import TestClient  # noqa: E402

from cohort.errors import CohortError  # noqa: E402
from cohort.graph import Graph  # noqa: E402
from cohort.schemas import (  # noqa: E402
    RESEARCHER,
    AgentKind,
    AgentProfile,
    ClaimPayload,
    Dating,
    DatingRoute,
    EdgeType,
    PassagePayload,
    WitnessPayload,
)
from cohort.ui.api import create_app  # noqa: E402

AGENT = "agent:worker-1"
#: A second agent, because an agent may not attest what it authored
#: (`Graph._reviewer_conflict`). Unregistered on purpose in most of
#: these fixtures: with no declared model there is no family to
#: compare, so what is being exercised is the author-is-not-reviewer
#: half of the rule on its own.
REVIEWER = "agent:reviewer-1"


@pytest.fixture
def populated(tmp_path):
    """A graph shaped like the real Heart Sutra case: one claim supported by
    two witnesses that the corpus says are parallel, so the discounting edge
    is present and independence is genuinely False."""
    db_path = tmp_path / "graph.sqlite"
    g = Graph.open(db_path, tmp_path / "events.jsonl")
    g.register_agent(
        AgentProfile(id=AGENT, kind=AgentKind.WORKER, corpus_scope="CBETA", method_label="textual"),
        authored_by=AGENT,
    )
    claim_id = g.propose_claim(ClaimPayload(text="form is emptiness"), authored_by=AGENT)
    passages = []
    for ref in ("T08n0251", "T08n0252"):
        w = g.propose_witness(
            WitnessPayload(
                canonical_ref=ref,
                dating=Dating(confidence=DatingRoute.UNKNOWN, basis="not dated for this test"),
            ),
            authored_by=AGENT,
        )
        p = g.propose_passage(
            PassagePayload(canonical_ref=f"{ref}#x", locator="juan 1", excerpt="色即是空"),
            witness_id=w, authored_by=AGENT,
        )
        g.attest(p, authored_by=AGENT)
        g.add_edge(EdgeType.ATTESTS, p, claim_id, authored_by=AGENT)
        passages.append((w, p))
    g.add_edge(EdgeType.PARALLEL_OF, passages[0][0], passages[1][0], authored_by=AGENT)
    g.attest(claim_id, authored_by=REVIEWER)
    g.accept(claim_id, authored_by=RESEARCHER)
    g.close()
    return db_path, claim_id


@pytest.fixture
def client(populated):
    db_path, _ = populated
    return TestClient(create_app(db_path))


def test_health_reports_counts(client):
    body = client.get("/api/health").json()
    assert body["ok"] is True
    assert body["nodes"]["claim"] == 1
    assert body["nodes"]["witness"] == 2


def test_graph_view_carries_status_on_every_node(client):
    """§10: 'node status is a visual channel, not a tooltip'. The frontend
    cannot render what the API does not send."""
    body = client.get("/api/graph").json()
    assert body["nodes"]
    assert all("status" in n for n in body["nodes"])
    assert all("assurance" in n for n in body["nodes"])


def test_discounting_edges_are_marked_as_such(client):
    """§4: parallel_of/descends_from reduce support rather than adding it.
    An edge list that did not say so would let a densely-linked node look
    well-supported regardless of independence."""
    body = client.get("/api/graph").json()
    by_type = {e["type"]: e for e in body["edges"]}
    assert by_type["parallel_of"]["discounts"] is True
    assert by_type["attests"]["discounts"] is False
    assert set(body["discounting_edge_types"]) == {"descends_from", "parallel_of"}


def test_graph_view_reports_truncation_explicitly(client):
    body = client.get("/api/graph", params={"limit": 2}).json()
    assert len(body["nodes"]) == 2
    assert body["truncated"] is True


def test_node_detail_carries_provenance_and_independence(client, populated):
    _, claim_id = populated
    body = client.get("/api/node", params={"id": claim_id}).json()
    assert body["payload"]["text"] == "form is emptiness"
    assert body["authorship"]
    assert body["edges_in"]
    support = body["independent_support"]
    assert support["attesting_count"] == 2
    assert support["independent"] is False  # the two witnesses are parallel
    assert support["non_independent_pairs"]


def test_witness_detail_has_no_independence_block(client):
    body = client.get("/api/node", params={"id": "witness:T08n0251"}).json()
    assert "independent_support" not in body


def test_node_id_containing_a_hash_is_reachable(client):
    """Passage ids are `{witness}#{excerpt}`. In a path segment the `#` would
    start a URL fragment and never reach the server, so the id travels as a
    query parameter."""
    body = client.get("/api/node", params={"id": "passage:T08n0251#x"}).json()
    assert body["id"] == "passage:T08n0251#x"
    assert body["payload"]["excerpt"] == "色即是空"


def test_missing_node_is_404(client):
    assert client.get("/api/node", params={"id": "claim:nope"}).status_code == 404


def test_citable_lists_only_accepted_evidence(client, populated):
    _, claim_id = populated
    ids = [n["id"] for n in client.get("/api/citable").json()]
    assert claim_id in ids


def test_agent_report_includes_declared_scope(client):
    body = client.get("/api/agent", params={"id": AGENT}).json()
    assert body["proposed"] > 0
    assert body["profile"]["corpus_scope"] == "CBETA"


# --- the API must not be able to write --------------------------------------

def test_api_exposes_no_mutating_routes(client):
    """Accept/reject are writes and are deliberately absent: a writing UI
    would need the exclusive lock for as long as a tab is open."""
    methods = {m for r in client.app.routes for m in getattr(r, "methods", set())}
    assert methods <= {"GET", "HEAD", "OPTIONS"}


def test_api_serves_while_a_writer_holds_the_lock(populated):
    """The whole point of the read-only path: a researcher can watch the
    graph while an agent run is writing to it."""
    db_path, claim_id = populated
    writer = Graph.open(db_path, db_path.parent / "events.jsonl")
    try:
        client = TestClient(create_app(db_path))
        assert client.get("/api/node", params={"id": claim_id}).status_code == 200
    finally:
        writer.close()


def test_missing_projection_is_503_not_a_crash(tmp_path):
    client = TestClient(create_app(tmp_path / "absent.sqlite"))
    assert client.get("/api/health").status_code == 503


# --- refusals as an output surface -------------------------------------------

@pytest.fixture
def with_refusals(tmp_path):
    """A graph whose log contains a real refused write."""
    db_path = tmp_path / "graph.sqlite"
    g = Graph.open(db_path, tmp_path / "events.jsonl")
    claim_id = g.propose_claim(ClaimPayload(text="unsupported"), authored_by=AGENT)
    with pytest.raises(CohortError):
        g.attest(claim_id, authored_by=REVIEWER)  # nothing attests it -> refused
    with pytest.raises(CohortError):
        g.accept(claim_id, authored_by=AGENT)  # not the researcher -> refused
    g.close()
    return db_path, tmp_path / "events.jsonl"


def test_refusals_endpoint_exposes_the_honest_log(with_refusals):
    """docs/design.md §15 claims refusals are part of the scholarly output. Before
    this endpoint they were reachable only by a list comprehension in
    demo.py, which made the claim true of the log but not of the system."""
    db_path, log_path = with_refusals
    client = TestClient(create_app(db_path, log_path))
    body = client.get("/api/refusals").json()
    assert body["available"] is True
    assert body["total"] == 2
    rules = {r["rule"] for r in body["refusals"]}
    assert rules == {"UnattestableClaim", "NotResearcher"}
    assert all(r["attempted"] for r in body["refusals"])
    assert all(r["message"] for r in body["refusals"])


def test_refusals_reports_a_missing_log_honestly(populated, tmp_path):
    """A projection with no log beside it must not read as 'zero refusals'."""
    db_path, _ = populated
    client = TestClient(create_app(db_path, tmp_path / "nonexistent.jsonl"))
    body = client.get("/api/refusals").json()
    assert body["available"] is False
    assert body["refusals"] == []


# --- researcher writes (opt-in) ----------------------------------------------

def test_writes_are_absent_unless_enabled(client):
    """The read-only deployment stays the default: the route should not even
    exist, rather than existing and refusing."""
    assert client.post("/api/accept?id=whatever").status_code == 404
    assert client.get("/api/health").json()["writes_enabled"] is False


def test_researcher_can_reject_through_the_api(populated):
    db_path, _ = populated
    client = TestClient(create_app(db_path, allow_writes=True))
    assert client.get("/api/health").json()["writes_enabled"] is True

    # an attested passage: rejectable, unlike the fixture's already-accepted claim
    passage_id = next(
        n["id"] for n in client.get("/api/graph").json()["nodes"]
        if n["type"] == "passage"
    )
    r = client.post(
        "/api/reject", params={"id": passage_id},
        json={"reason": "the catalogue reference does not resolve"},
    )
    assert r.status_code == 200, r.text
    assert r.json()["node"]["status"] == "rejected"
    assert "does not resolve" in r.json()["node"]["rejected_reason"]
    assert r.json()["decision_node_id"]

    # durable: a fresh read-only app sees the same verdict
    assert TestClient(create_app(db_path)).get(
        "/api/node", params={"id": passage_id}
    ).json()["status"] == "rejected"


def test_rejecting_without_a_reason_is_refused_by_the_graph_not_the_api(populated):
    """One rule, one place: `MissingRejectionReason` lives at the write
    boundary, so the API passes the missing reason through and reports what
    the graph decided — 422, with the rule named."""
    db_path, _ = populated
    client = TestClient(create_app(db_path, allow_writes=True))
    passage_id = next(
        n["id"] for n in client.get("/api/graph").json()["nodes"]
        if n["type"] == "passage"
    )
    r = client.post("/api/reject", params={"id": passage_id}, json={})
    assert r.status_code == 422
    assert r.json()["detail"]["rule"] == "MissingRejectionReason"


def test_accepting_an_unattested_node_is_refused_with_the_rule_named(tmp_path):
    db_path = tmp_path / "g.sqlite"
    g = Graph.open(db_path, tmp_path / "e.jsonl")
    claim_id = g.propose_claim(ClaimPayload(text="only proposed"), authored_by=AGENT)
    g.close()

    client = TestClient(create_app(db_path, allow_writes=True))
    r = client.post("/api/accept", params={"id": claim_id})
    assert r.status_code == 422
    assert r.json()["detail"]["rule"] == "RungSkipped"


def test_a_write_conflicts_rather_than_waiting_while_an_agent_run_holds_the_lock(populated):
    """Single-writer discipline is unchanged, not relaxed. A held lock must
    surface as a 409 the researcher can act on, not a hang and not a 500."""
    db_path, claim_id = populated
    holder = Graph.open(db_path, db_path.with_suffix(".jsonl"))  # stands in for an agent run
    try:
        client = TestClient(create_app(db_path, allow_writes=True))
        r = client.post("/api/reject", params={"id": claim_id}, json={"reason": "x"})
        assert r.status_code == 409
        assert "agent run is writing" in r.json()["detail"]
        assert "Nothing was changed" in r.json()["detail"]
    finally:
        holder.close()


def test_reads_keep_working_while_a_writer_holds_the_lock(populated):
    db_path, _ = populated
    holder = Graph.open(db_path, db_path.with_suffix(".jsonl"))
    try:
        assert TestClient(create_app(db_path)).get("/api/health").json()["ok"] is True
    finally:
        holder.close()


def test_edge_reason_reaches_the_frontend(tmp_path):
    """A contradicts edge is rendered as prominently as evidence, so its
    grounds have to travel with it."""
    db_path = tmp_path / "g.sqlite"
    g = Graph.open(db_path, tmp_path / "e.jsonl")
    a = g.propose_claim(ClaimPayload(text="A"), authored_by=AGENT)
    b = g.propose_claim(ClaimPayload(text="B"), authored_by=AGENT)
    g.add_edge(EdgeType.CONTRADICTS, a, b, authored_by=AGENT, reason="incompatible datings")
    g.close()

    body = TestClient(create_app(db_path)).get("/api/graph").json()
    contradicts = [e for e in body["edges"] if e["type"] == "contradicts"]
    assert contradicts
    assert all(e["reason"] == "incompatible datings" for e in contradicts)
    assert all(e["discounts"] is False for e in contradicts)


# --- the integrity checks, reachable without the writer's lock --------------

def test_rebuild_endpoint_confirms_the_projection_matches_the_log(populated):
    """The check that the log, not the database, is ground truth. It has to be
    reachable from a read-only deployment: refusing to verify a projection you
    are allowed to read would be a strange place to draw the line."""
    db_path, _ = populated
    log_path = db_path.parent / "events.jsonl"
    body = TestClient(create_app(db_path, log_path)).get("/api/rebuild").json()
    assert body["available"] is True
    assert body["ok"] is True
    assert body["events_replayed"] > 0


def test_rebuild_endpoint_works_while_a_writer_holds_the_lock(populated):
    db_path, _ = populated
    log_path = db_path.parent / "events.jsonl"
    holder = Graph.open(db_path, log_path)
    try:
        client = TestClient(create_app(db_path, log_path))
        assert client.get("/api/rebuild").json()["ok"] is True
    finally:
        holder.close()


def test_rebuild_reports_a_missing_log_rather_than_claiming_ok(tmp_path):
    """A missing log must never read as a passing check."""
    db_path = tmp_path / "g.sqlite"
    Graph.open(db_path, tmp_path / "gone.jsonl").close()
    (tmp_path / "gone.jsonl").unlink()
    body = TestClient(create_app(db_path, tmp_path / "gone.jsonl")).get("/api/rebuild").json()
    assert body["available"] is False
    assert "ok" not in body


def test_rebuild_reports_a_mismatch_as_a_finding_not_a_500(populated):
    """A projection disagreeing with the log is this endpoint's most important
    answer, so it must arrive as data rather than as a server error."""
    db_path, _ = populated
    log_path = db_path.parent / "events.jsonl"
    # Tamper with the projection only — the log still says what really happened.
    g = Graph.open_read_only(db_path)
    g.close()
    import sqlite3
    conn = sqlite3.connect(db_path)
    # The fixture already accepts this claim, so demote it: the log says
    # accepted, the projection now says proposed, and they must disagree.
    conn.execute("UPDATE nodes SET status='proposed' WHERE type='claim'")
    conn.commit()
    conn.close()

    body = TestClient(create_app(db_path, log_path)).get("/api/rebuild").json()
    assert body["available"] is True
    assert body["ok"] is False
    assert body["mismatch"]


def test_integrity_endpoint_finds_no_tampering_in_a_clean_graph(populated):
    db_path, _ = populated
    body = TestClient(create_app(db_path)).get("/api/integrity").json()
    assert body["checked"] > 0
    assert body["mismatched"] == []


def test_integrity_endpoint_catches_an_edited_payload(populated):
    """The payload hash is independent of the payload, so editing the row
    behind the graph's back is detectable rather than invisible."""
    db_path, _ = populated
    import sqlite3
    conn = sqlite3.connect(db_path)
    conn.execute("UPDATE nodes SET payload='{\"text\":\"tampered\"}' WHERE type='claim'")
    conn.commit()
    conn.close()

    body = TestClient(create_app(db_path)).get("/api/integrity").json()
    assert body["mismatched"], "an edited payload must not pass the hash check"


def test_integrity_can_check_one_node(populated):
    db_path, _ = populated
    client = TestClient(create_app(db_path))
    claim = next(n for n in client.get("/api/graph").json()["nodes"] if n["type"] == "claim")
    body = client.get("/api/integrity", params={"id": claim["id"]}).json()
    assert body["checked"] == 1


# --- attest: the rung between proposed and accepted -------------------------

def test_attest_advances_a_proposed_claim_that_has_backing(tmp_path):
    """The dead end this closes: a claim with real attesting passages sat at
    `proposed`, accept refused it for skipping a rung, and the UI offered no
    way forward."""
    db_path = tmp_path / "g.sqlite"
    g = Graph.open(db_path, tmp_path / "e.jsonl")
    claim = g.propose_claim(ClaimPayload(text="c"), authored_by=AGENT)
    w = g.propose_witness(
        WitnessPayload(canonical_ref="T01n0001",
                       dating=Dating(confidence=DatingRoute.UNKNOWN,
                                     basis="no dating route was run for this test")),
        authored_by=AGENT,
    )
    p = g.propose_passage(
        PassagePayload(canonical_ref="T01n0001#x", locator="1", excerpt="空"),
        witness_id=w, authored_by=AGENT,
    )
    g.attest(p, authored_by=AGENT)
    g.add_edge(EdgeType.ATTESTS, p, claim, authored_by=AGENT)
    g.close()

    client = TestClient(create_app(db_path, tmp_path / "e.jsonl", allow_writes=True))
    assert client.post("/api/attest", params={"id": claim}).json()["node"]["status"] == "attested"
    assert client.post("/api/accept", params={"id": claim}).json()["node"]["status"] == "accepted"


def test_attest_refuses_a_claim_with_nothing_attesting_it(tmp_path):
    """The button cannot promote something unsupported: the graph re-checks."""
    db_path = tmp_path / "g.sqlite"
    g = Graph.open(db_path, tmp_path / "e.jsonl")
    claim = g.propose_claim(ClaimPayload(text="ungrounded"), authored_by=AGENT)
    g.close()

    client = TestClient(create_app(db_path, tmp_path / "e.jsonl", allow_writes=True))
    res = client.post("/api/attest", params={"id": claim})
    assert res.status_code == 422
    assert res.json()["detail"]["rule"] == "UnattestableClaim"


def test_attest_is_not_mounted_without_allow_writes(populated):
    db_path, claim_id = populated
    assert TestClient(create_app(db_path)).post(
        "/api/attest", params={"id": claim_id}
    ).status_code == 404


# --- edge retraction over HTTP ---------------------------------------------

def test_retracting_a_parallel_edge_restores_independence_over_http(populated):
    """The fixture's claim is supported by two witnesses the corpus calls
    parallel, so `independent` is False. Withdrawing that edge must give the
    support back — through the API, not only in Python."""
    db_path, claim_id = populated
    log_path = db_path.parent / "events.jsonl"
    client = TestClient(create_app(db_path, log_path, allow_writes=True))

    before = client.get("/api/node", params={"id": claim_id}).json()
    assert before["independent_support"]["independent"] is False
    edge = next(
        e for e in client.get("/api/graph").json()["edges"] if e["type"] == "parallel_of"
    )

    res = client.post(
        "/api/edge/retract", params={"id": edge["id"]},
        json={"reason": "the docNumber bracket was a cf. reference"},
    )
    assert res.status_code == 200, res.text
    assert res.json()["edge"]["retracted"] is True

    after = client.get("/api/node", params={"id": claim_id}).json()
    assert after["independent_support"]["independent"] is True
    assert (
        after["independent_support"]["attesting_count"]
        == before["independent_support"]["attesting_count"]
    ), "retracting a discounting edge must not change how much evidence there is"


def test_a_retracted_edge_is_still_reported_on_the_node(populated):
    """Withdrawn, not erased — the inspector is where the record is read."""
    db_path, _claim_id = populated
    log_path = db_path.parent / "events.jsonl"
    client = TestClient(create_app(db_path, log_path, allow_writes=True))
    edge = next(
        e for e in client.get("/api/graph").json()["edges"] if e["type"] == "parallel_of"
    )
    client.post("/api/edge/retract", params={"id": edge["id"]},
                json={"reason": "withdrawn after re-reading the bracket"})

    witness = client.get("/api/node", params={"id": edge["src"]}).json()
    shown = [e for e in witness["edges_out"] + witness["edges_in"] if e["retracted"]]
    assert shown, "a withdrawn edge must still appear in provenance"
    assert "re-reading" in shown[0]["retracted_reason"]

    # ...but the graph view shows what currently holds
    assert not any(
        e["type"] == "parallel_of" for e in client.get("/api/graph").json()["edges"]
    )


def test_retract_without_a_reason_is_422_with_a_rule(populated):
    db_path, _ = populated
    log_path = db_path.parent / "events.jsonl"
    client = TestClient(create_app(db_path, log_path, allow_writes=True))
    edge = next(
        e for e in client.get("/api/graph").json()["edges"] if e["type"] == "parallel_of"
    )
    res = client.post("/api/edge/retract", params={"id": edge["id"]}, json={})
    assert res.status_code == 422
    assert res.json()["detail"]["rule"] == "MissingRejectionReason"


def test_retract_is_not_mounted_without_allow_writes(populated):
    db_path, _ = populated
    assert TestClient(create_app(db_path)).post(
        "/api/edge/retract", params={"id": "edge:whatever"}, json={"reason": "x"}
    ).status_code == 404


def test_restore_over_http_puts_the_discount_back(populated):
    db_path, claim_id = populated
    log_path = db_path.parent / "events.jsonl"
    client = TestClient(create_app(db_path, log_path, allow_writes=True))
    edge = next(
        e for e in client.get("/api/graph").json()["edges"] if e["type"] == "parallel_of"
    )
    client.post("/api/edge/retract", params={"id": edge["id"]},
                json={"reason": "withdrawn pending a check"})
    res = client.post("/api/edge/restore", params={"id": edge["id"]},
                      json={"reason": "the check confirmed the parallel"})
    assert res.status_code == 200, res.text
    node = client.get("/api/node", params={"id": claim_id}).json()
    assert node["independent_support"]["independent"] is False
