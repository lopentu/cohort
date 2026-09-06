"""The feature ledger: every candidate discriminator and what became of it.

This is the presentation the method exists for, and the discarded rows are the
reason. In ordinary stylometry the features that did not work are invisible —
they were tried, they disappointed, nobody wrote them down — so a reader cannot
tell a discovery from a fishing expedition, and neither can the author. Here
every registered feature stays on the ledger with the prediction it made and
the control that finished it.

So the number to read first is not what survived. It is **how many were tried**.
Three features surviving out of four is a different claim from three surviving
out of ninety, and the second one is not evidence of much: enough candidates
tested against one small control will eventually produce a passing feature by
chance alone. The ledger reports both, and reports nothing that corrects for
it, because the correction depends on how the candidates were chosen — which is
a thing the researcher knows and the graph does not.

Deliberately no ranking and no score. `usable` here means "has survived one
negative control", which is a fact about a test that was run; it is not a
measure of how good a discriminator is, and the ledger offers no way to sort by
one.
"""
from __future__ import annotations

from typing import Any

from .graph import Graph
from .schemas import DiscriminationPrediction, EdgeType, NodeType, VerificationMethod
from .tools.discriminator import control_status

#: what a discriminator may be, and what each state licenses
FATES = {
    "untested": "registered; its control has not been run, so it may not be applied",
    "usable": "survived its negative control; may be applied to disputed works",
    "discarded": "failed its negative control; it tracks something other than the group",
}


def _registered(graph: Graph) -> list[tuple[str, str, DiscriminationPrediction]]:
    out = []
    for node in graph.nodes(node_type=NodeType.CONJECTURE):
        for edge in graph.edges(edge_type=EdgeType.TESTS, dst=node.id):
            payload = graph.get_node(edge.src).payload
            if payload.get("discrimination"):
                out.append((
                    node.id, edge.src,
                    DiscriminationPrediction.model_validate(payload["discrimination"]),
                ))
                break
    return out


def _control_result(graph: Graph, conjecture_id: str) -> dict[str, Any] | None:
    """The latest control test's own words, so the ledger quotes the record
    rather than recomputing a summary that could drift from it."""
    latest = None
    for v in graph.verifications(conjecture_id):
        p = v.payload
        if p.get("method") != VerificationMethod.PROSPECTIVE_TEST:
            continue
        if "control test of query" not in (p.get("detail") or ""):
            continue
        latest = {
            "result": p["result"], "detail": p["detail"],
            "limitations": p.get("limitations"),
            # The numbers as numbers. The sentence says what the result meant;
            # these say what it was, so a table does not have to parse English.
            "groups": list(p.get("groups") or ()),
        }
    return latest


def ledger_json(graph: Graph) -> dict[str, Any]:
    rows = []
    for conjecture_id, query_id, pred in _registered(graph):
        status = control_status(graph, conjecture_id)
        fate = {"passed": "usable", "failed": "discarded"}.get(status, "untested")
        node = graph.get_node(conjecture_id)
        rows.append({
            "conjecture_id": conjecture_id,
            "query_id": query_id,
            "feature": pred.feature,
            "status": node.status,
            "prediction": {
                "benchmark_label": pred.benchmark_label,
                "control_label": pred.control_label,
                "min_benchmark_share": pred.min_benchmark_share,
                "max_control_share": pred.max_control_share,
            },
            "fate": fate,
            "licenses": FATES[fate],
            "control": _control_result(graph, conjecture_id),
        })

    tried = len(rows)
    counts = {fate: sum(1 for r in rows if r["fate"] == fate) for fate in FATES}
    return {
        "features": rows,
        "tried": tried,
        "by_fate": counts,
        # Stated, not computed into a correction. How much a survival rate is
        # worth depends on how the candidates were chosen, and the graph does
        # not know that.
        "reading": (
            f"{counts['usable']} of {tried} registered feature(s) survived a "
            "negative control. Read that as a ratio: enough candidates tested "
            "against one small control will eventually produce a passing "
            "feature by chance, and nothing here corrects for how many were "
            "tried."
        ) if tried else "no candidate discriminators have been registered.",
    }
