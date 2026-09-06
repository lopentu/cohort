"""Shared read-shapes for the front ends.

The CLI and the web API must describe the same node the same way. When each had
its own serializer they drifted immediately — one returned the node flat, the
other nested it under a `node` key — so `cohort node X --json` and
`GET /api/node?id=X` disagreed about a graph they both read correctly.

These functions are the single answer. Nothing here imports FastAPI, so the
terminal front end does not drag in the optional `ui` extra to describe a node.
"""
from __future__ import annotations

from typing import Any

from .graph import Graph
from .ledger import ledger_json
from .sources.cbeta_refs import reader_url
from .schemas import EdgeType, NodeType, VerificationMethod, VerificationResult

#: The two edge types that *discount* support rather than adding it: witnesses
#: linked by either are evidence of shared descent, not independent
#: confirmation. Named once so no front end has to re-derive it, and so none
#: can quietly omit the distinction docs/design.md §10 requires.
DISCOUNTING_EDGE_TYPES = frozenset({EdgeType.DESCENDS_FROM, EdgeType.PARALLEL_OF})


def node_json(graph: Graph, node) -> dict[str, Any]:
    return {
        "id": node.id,
        "type": node.type,
        "status": node.status,
        "payload": node.payload,
        "rejected_reason": node.rejected_reason,
        "authorship": [a.model_dump(mode="json") for a in node.authorship],
        "created_seq": node.created_seq,
        "updated_seq": node.updated_seq,
        "assurance": graph.assurance_for(node.id),
        # Present on witnesses and passages, absent everywhere else, and
        # absent for a corpus CBETA does not publish. Computed here rather
        # than in each front end so the graph view, the dossier and the
        # corpus browser cannot disagree about where a passage lives.
        "cbeta_url": reader_url(node.payload.get("canonical_ref") or ""),
    }


def test_outcome(graph: Graph, conjecture_id: str) -> str:
    """`held`, `broke`, `undecided` or `unrun` for a conjecture's prospective
    test — the latest one, for the reason `assurance_for` takes the latest per
    method.

    Reported on the `tests` edge rather than on the conjecture, because the
    edge *is* the test: it points from the query that would settle something to
    the thing it would settle, and whether it did is a fact about that
    relation. Putting it on the node would also collide with status, which is
    the promotion ladder and must not start meaning "a prediction held".
    """
    latest = None
    for v in graph.verifications(conjecture_id):
        if v.payload.get("method") == VerificationMethod.PROSPECTIVE_TEST:
            latest = v.payload["result"]
    return {
        VerificationResult.PASS: "held",
        VerificationResult.FAIL: "broke",
        VerificationResult.INDETERMINATE: "undecided",
    }.get(latest, "unrun")


def edge_json(edge) -> dict[str, Any]:
    return {
        "id": edge.id,
        "type": edge.type,
        "src": edge.src,
        "dst": edge.dst,
        "discounts": edge.type in DISCOUNTING_EDGE_TYPES,
        "reason": edge.reason,
        # A retracted edge is reported, not omitted: "the researcher withdrew
        # this" and "this was never asserted" are different facts, and only one
        # of them is worth showing.
        "retracted": edge.retracted_at is not None,
        "retracted_at": edge.retracted_at,
        "retracted_reason": edge.retracted_reason,
        "authorship": [a.model_dump(mode="json") for a in edge.authorship],
        "created_seq": edge.created_seq,
    }


def node_detail_json(graph: Graph, node_id: str) -> dict[str, Any]:
    """Everything provenance-on-click needs: the node, its verifications, its
    edges both ways, and — for a claim or conjecture — whether its support is
    independent.

    `independent_support` is present only where it means something. Reporting
    it for a witness would invite reading a bare `attesting_count` as a
    confidence number, which is the habit this system exists to break.
    """
    node = graph.get_node(node_id)
    detail = node_json(graph, node)
    detail["verifications"] = [node_json(graph, v) for v in graph.verifications(node_id)]
    # Include retracted edges here — the inspector is where the record is read,
    # and a withdrawal with its reason is part of the provenance.
    detail["edges_out"] = [edge_json(e) for e in graph.edges(src=node_id, include_retracted=True)]
    detail["edges_in"] = [edge_json(e) for e in graph.edges(dst=node_id, include_retracted=True)]
    if node.type in (NodeType.CLAIM, NodeType.CONJECTURE):
        detail["independent_support"] = graph.independent_support(node_id).model_dump(
            mode="json"
        )
    return detail


#: The dossier fields `ConjecturePayload` requires, in the order a reader needs
#: them: what is claimed, how it was reached, what was searched, and then the
#: two that make it a hypothesis rather than an assertion — what could have
#: gone wrong in the selection, and what else could explain the same evidence.
DOSSIER_FIELDS = (
    "derivation", "corpus_boundary", "selection_risks", "alternative_explanations",
)


def _query_json(graph: Graph, node) -> dict[str, Any]:
    p = node.payload
    return {
        "id": node.id,
        "text": p.get("text"),
        "expectation": p.get("expectation"),
        "expected_hits": p.get("expected_hits"),
    }


def dossier_json(graph: Graph, node_id: str) -> dict[str, Any]:
    """A claim or conjecture as a hypothesis record, not as a node.

    Everything here is already in the graph and was, until this existed,
    reachable only by walking edges by hand: the dossier fields, the prior-art
    search that was actually run, the prospective query with the prediction
    recorded when it was proposed, the evidence with its excerpts, the
    independence discount, and the verifications with the machine's finding
    and a reviewer's reading kept in separate fields.

    Assembled here rather than in a panel because both front ends need the
    same answer, and because a reader deciding what a hypothesis is worth
    should not have to reconstruct it from a graph traversal — that is the
    step at which the honest fields get skipped.
    """
    detail = node_detail_json(graph, node_id)
    node = graph.get_node(node_id)
    payload = node.payload

    detail["assertion"] = payload.get("text")
    detail["dossier"] = {f: payload.get(f) for f in DOSSIER_FIELDS if payload.get(f)}

    # The two query nodes, resolved. `searched_for` records a prior-art search
    # that was run before proposing; `tests` records what would settle it
    # going forward. Kept apart because they answer opposite questions.
    detail["prior_art"] = [
        _query_json(graph, graph.get_node(e.src))
        for e in graph.edges(edge_type=EdgeType.SEARCHED_FOR, dst=node_id)
    ]
    detail["prospective_queries"] = [
        _query_json(graph, graph.get_node(e.src))
        for e in graph.edges(edge_type=EdgeType.TESTS, dst=node_id)
    ]

    # The evidence, with enough of each passage to read. A list of passage ids
    # is not evidence a person can weigh.
    evidence = []
    for e in graph.edges(edge_type=EdgeType.ATTESTS, dst=node_id):
        passage = graph.get_node(e.src)
        witness = next(
            (w.dst for w in graph.edges(edge_type=EdgeType.PART_OF, src=passage.id)), None
        )
        evidence.append({
            "passage_id": passage.id,
            "status": passage.status,
            "excerpt": passage.payload.get("excerpt"),
            "locator": passage.payload.get("locator"),
            "canonical_ref": passage.payload.get("canonical_ref"),
            "witness_id": witness,
            "assurance": graph.assurance_for(passage.id),
        })
    detail["evidence"] = evidence

    # The latest verification per method, which is what `assurance_for` reads
    # too — a stale pass must not outrank a later failure here either.
    latest: dict[str, dict[str, Any]] = {}
    for v in detail["verifications"]:
        latest[v["payload"]["method"]] = v
    detail["latest_verifications"] = list(latest.values())
    detail["prospective_test"] = latest.get("prospective_test")
    # All of them, not the latest — see `_measurements`. A hypothesis can carry
    # a placement of four works, and "the latest measurement" is not a thing a
    # reader of that wants.
    detail["measurements"] = _measurements(graph, node_id)

    return detail


#: A `CORPUS_MEASUREMENT` verification is written by three different tools, and
#: a reader needs to know which — a feature count, a feature applied to works in
#: doubt, and a Delta placement say different things and are read differently.
#: The distinction is recoverable from `detail`'s opening verb, which each tool
#: fixes deliberately, rather than from a field nothing validates.
MEASUREMENT_KINDS = (
    ("placed ", "placement"),
    ("applied ", "application"),
    ("counted ", "count"),
)


def _measurements(graph: Graph, node_id: str) -> list[dict[str, Any]]:
    """Every measurement recorded against a hypothesis, newest last.

    Not latest-per-method, unlike `latest_verifications`. A node can carry a
    placement of four different works and a count of two different features,
    and collapsing them to one would show whichever happened to be written
    last — which is the bug that made a stale pass outrank a later failure,
    committed on an axis where "latest" is not even the right idea.
    """
    out = []
    for v in graph.verifications(node_id):
        p = v.payload
        if p.get("method") != VerificationMethod.CORPUS_MEASUREMENT:
            continue
        detail = p.get("detail") or ""
        kind = next((k for prefix, k in MEASUREMENT_KINDS if detail.startswith(prefix)), "other")
        out.append({
            "id": v.id,
            "kind": kind,
            "result": p["result"],
            "detail": detail,
            "limitations": p.get("limitations"),
            "fingerprint": p.get("excerpt_hash"),
            "works": list(p.get("works") or ()),
        })
    return out


def findings_json(graph: Graph, *, limit: int | None = None) -> dict[str, Any]:
    """Every claim and conjecture, as a scannable list of hypotheses.

    Ordered newest first and reported with the numbers a reader needs to decide
    what to open: where it sits on the ladder, whether its support survives the
    independence check, whether its prospective query has been run, and — for a
    registered discriminator — what became of it.

    That last field is why the ledger's contents are here rather than only on
    their own page. A candidate feature was showing up in two places under two
    framings: once as an unranked hypothesis, and once as a ledger row with the
    fate that is the single most informative thing about it. The same node
    described twice in two places is how a reader ends up unable to assemble
    one picture, so `fate` travels with the hypothesis.

    Deliberately not scored or ranked by support count. A list sorted by
    "most attested" would be a confidence ranking wearing a different hat, and
    the whole argument is that counting agreement is the wrong move. Grouping
    by `fate` is a different thing and is allowed: a fate is a fact about a
    test that was run, not an estimate of how good a feature is.
    """
    fates = {
        row["conjecture_id"]: row
        for row in ledger_json(graph)["features"]
    }
    rows = []
    for node_type in (NodeType.CONJECTURE, NodeType.CLAIM):
        for node in graph.nodes(node_type=node_type):
            support = graph.independent_support(node.id)
            tests = [
                graph.get_node(e.src)
                for e in graph.edges(edge_type=EdgeType.TESTS, dst=node.id)
            ]
            prospective = next(
                (v for v in reversed(graph.verifications(node.id))
                 if v.payload["method"] == "prospective_test"),
                None,
            )
            rows.append({
                "id": node.id,
                "type": node.type,
                "status": node.status,
                "assurance": graph.assurance_for(node.id),
                "assertion": node.payload.get("text"),
                "rejected_reason": node.rejected_reason,
                "authors": sorted({a.author for a in node.authorship if a.action == "proposed"}),
                "attesters": sorted({a.author for a in node.authorship if a.action == "attested"}),
                "support": support.model_dump(mode="json"),
                "has_dossier": any(node.payload.get(f) for f in DOSSIER_FIELDS),
                "has_prospective_query": bool(tests),
                "prospective_result": prospective.payload["result"] if prospective else None,
                "created_seq": node.created_seq,
                # Present only on a registered discriminator: its fate, the
                # prediction it made, and the tallies the control observed.
                "ledger": fates.get(node.id),
                "measurements": _measurements(graph, node.id),
            })
    rows.sort(key=lambda r: -r["created_seq"])
    return {"count": len(rows), "findings": rows[:limit] if limit else rows}


def question_json(graph: Graph, question_id: str) -> dict[str, Any]:
    """A question with what has been put forward as an answer to it.

    Reported as a **tally, not a verdict**. It says how many hypotheses address
    the question and where each one stands; it does not say whether the
    question has been answered, because nothing mechanical could know that. A
    question with nine claims under it is not a settled question — the same
    reason `addresses` points from the answer to the question rather than the
    other way round.
    """
    node = graph.get_node(question_id)
    addressed = [
        graph.get_node(e.src)
        for e in graph.edges(edge_type=EdgeType.ADDRESSES, dst=question_id)
    ]
    hypotheses = []
    for n in sorted(addressed, key=lambda n: -n.created_seq):
        support = graph.independent_support(n.id)
        hypotheses.append({
            "id": n.id,
            "type": n.type,
            "status": n.status,
            "assurance": graph.assurance_for(n.id),
            "assertion": n.payload.get("text"),
            "support": support.model_dump(mode="json"),
        })

    by_status: dict[str, int] = {}
    for h in hypotheses:
        by_status[h["status"]] = by_status.get(h["status"], 0) + 1

    return {
        **node_json(graph, node),
        "question": node.payload.get("text"),
        "answerable_by": node.payload.get("answerable_by"),
        "hypotheses": hypotheses,
        "by_status": by_status,
        # Counted separately because it is the number that would be misread as
        # a score if it sat beside the others without a name.
        "unsupported": sum(1 for h in hypotheses if h["support"]["vacuous"]),
        "discounted": sum(
            1 for h in hypotheses
            if not h["support"]["vacuous"] and not h["support"]["independent"]
        ),
    }


def questions_json(graph: Graph) -> dict[str, Any]:
    """Every research question, newest first, with how much addresses each."""
    rows = []
    for node in graph.nodes(node_type=NodeType.QUESTION):
        addressing = graph.edges(edge_type=EdgeType.ADDRESSES, dst=node.id)
        rows.append({
            "id": node.id,
            "question": node.payload.get("text"),
            "answerable_by": node.payload.get("answerable_by"),
            "asked_by": [a.author for a in node.authorship],
            "addressed_by": len(addressing),
            "created_seq": node.created_seq,
        })
    rows.sort(key=lambda r: -r["created_seq"])
    return {"count": len(rows), "questions": rows}
