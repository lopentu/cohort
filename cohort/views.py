"""Shared read-shapes for the front ends.

The CLI and the web API must describe the same node the same way. When each had
its own serializer they drifted immediately — one returned the node flat, the
other nested it under a `node` key — so `cohort node X --json` and
`GET /api/node?id=X` disagreed about a graph they both read correctly.

These functions are the single answer. Nothing here imports FastAPI, so the
terminal front end does not drag in the optional `ui` extra to describe a node.
"""
from __future__ import annotations

from pathlib import Path
from typing import Any

from cohort.eventlog import read_events
from cohort.graph import Graph
from cohort.schemas import EdgeType, NodeType, VerificationMethod
from cohort.sources.cbeta_refs import reader_url

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


def node_detail_json(
    graph: Graph, node_id: str, *, log_path: Path | None = None,
) -> dict[str, Any]:
    """Everything provenance-on-click needs: the node, its verifications, its
    edges both ways, and — for a claim or conjecture — whether its support is
    independent.

    `independent_support` is present only where it means something. Reporting
    it for a witness would invite reading a bare `attesting_count` as a
    confidence number, which is the habit this system exists to break.
    """
    node = graph.get_node(node_id)
    detail = node_json(graph, node)
    detail["created_by"] = creation_provenance(node.created_seq, log_path)
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


def creation_provenance(created_seq: int, log_path: Path | None) -> dict[str, Any] | None:
    """Read the causal model call, not an agent's mutable current profile."""
    if log_path is None or not log_path.is_file():
        return None
    calls = {}
    rosters = {}
    actions = {}
    for event in read_events(log_path):
        if event.event == "tool_action":
            actions[event.model_call_id] = event.detail
        if event.event == "model_call":
            calls[event.seq] = event
        elif event.event == "run_started":
            rosters[event.run_id] = event.detail.get("agents", [])
        if event.seq == created_seq:
            call = calls.get(event.model_call_id)
            spec = next((a for a in rosters.get(event.run_id, [])
                         if a.get("agent_id") == event.authored_by), {})
            return {
                "author": event.authored_by,
                "role": spec.get("role"),
                "model": call.model if call is not None else None,
                "reason": actions.get(event.model_call_id, {}).get("reason"),
                "tool": actions.get(event.model_call_id, {}).get("tool"),
            }
        if event.seq > created_seq:
            break
    return None


def verified_span_for(graph: Graph, passage_id: str) -> tuple[int, int] | None:
    """The span recorded by `passage_id`'s last `EXACT_SPAN` verification, if
    it has one — the same "last recorded baseline" `verify_exact_span` itself
    trusts over a fresh search, and the reason `passage_context` (CLI and web
    alike) prefers it too: a short excerpt can occur more than once in a
    witness, and an unverified first match is a guess about which one was
    meant."""
    span = None
    for v in graph.verifications(passage_id):
        p = v.payload
        if p.get("method") == VerificationMethod.EXACT_SPAN and p.get("span_start") is not None:
            span = (p["span_start"], p["span_end"])
    return span


def locate_passage_span(
    source_text: str, excerpt: str, verified_span: tuple[int, int] | None,
) -> tuple[int, int, str]:
    """Where `excerpt` sits in `source_text`, and how it was found — `"verified_span"`
    (the recorded baseline still matches), `"stale_verified_span"` (it no
    longer does, and this fell back to a fresh search), or `"first_match"`
    (there was no recorded baseline to try).

    One function rather than one per front end, so the CLI's `context`
    command and the web API's `/api/passage/context` cannot quietly locate the
    same passage two different ways.

    Raises `ValueError` if the excerpt is not in the text at all — the caller
    decides how to report that (an HTTP 409, a CLI `SystemExit`)."""
    stale = False
    if verified_span is not None:
        start, end = verified_span
        if source_text[start:end] == excerpt:
            return start, end, "verified_span"
        stale = True
    idx = source_text.find(excerpt)
    if idx == -1:
        raise ValueError("excerpt not found in the freshly-fetched source; it may have moved")
    return idx, idx + len(excerpt), "stale_verified_span" if stale else "first_match"


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

    return detail


def findings_json(graph: Graph, *, limit: int | None = None) -> dict[str, Any]:
    """Every claim and conjecture, as a scannable list of hypotheses.

    Ordered newest first and reported with the numbers a reader needs to decide
    what to open: where it sits on the ladder, whether its support survives the
    independence check, and whether its prospective query has been run.

    Deliberately not scored or ranked by support count. A list sorted by
    "most attested" would be a confidence ranking wearing a different hat, and
    the whole argument is that counting agreement is the wrong move.
    """
    rows: list[dict[str, Any]] = []
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
    hypotheses: list[dict[str, Any]] = []
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
    rows: list[dict[str, Any]] = []
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
