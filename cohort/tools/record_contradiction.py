"""record_contradiction: write a `contradicts` edge between two nodes that
disagree, with a stated reason.

Why this exists: `contradicts` has been in the closed vocabulary since stage
1, is materialised in both directions (`SYMMETRIC_EDGE_TYPES`), and the UI
deliberately draws it as heavily as `attests` — but until now **nothing in
the system ever created one**. docs/design.md §6 lists it as "disagreement made
visible" and §10 warns that a view hiding disagreement "flattens exactly the
epistemics that justify the system"; a vocabulary entry with no producer
makes that claim true only in principle. This is the producer.

**Why a stated reason is required.** `contradicts` is the one edge whose
domain is `"any"` (`EDGE_DOMAINS`), so the write boundary can check almost
nothing about it: any node may contradict any node. Every other edge type is
constrained by its domain, and `attests`/`tests` additionally carry
consequences the ladder enforces. An unexplained `contradicts` would
therefore be the least checkable and most consequential edge an agent could
mint — it is rendered as prominently as evidence and it is exactly the kind
of assertion a reader will act on. So the reason is not decoration: it is the
only thing standing between "disagreement made visible" and "disagreement
asserted without grounds", and it is recorded as a `decision`-shaped fact
that travels with the edge.

**What this tool does not claim.** It records that *this agent asserts* these
two nodes disagree, in these words. It does not verify the disagreement, and
it deliberately does not compute one: automatic cross-witness contradiction
detection needs locus alignment between witnesses (knowing that passage A in
one recension and passage B in another are *the same place* in the text),
which COHORT does not have and does not pretend to. The corpus's own
`<app>`/`<lem>`/`<rdg>` apparatus records disagreement *within* one document
and cannot supply that alignment either — see `collate_editions.py`'s
limitations note. So this is an agent-or-researcher judgement, logged as one,
and `scripts/scan_contradiction_candidates.py` surfaces *places to look*
without writing anything.

**Direction does not matter and is not implied.** `contradicts` is symmetric
and `graph.add_edge()` materialises both rows from one event, so callers need
not decide which node is "wrong" — which is correct for textual
disagreement, where usually neither is.
"""
from __future__ import annotations

from pydantic import BaseModel, ConfigDict, Field

from cohort.errors import WrongNodeType
from cohort.graph import Graph
from cohort.schemas import EdgeType, NodeType

NAME = "record_contradiction"
DESCRIPTION = (
    "Record that two nodes in the graph disagree, as a contradicts edge with "
    "a stated reason. Use it when two claims assert incompatible things, or "
    "two passages give irreconcilable readings. Both node ids must already "
    "exist — never invent one. The reason is required and should say what the "
    "disagreement actually is. This records your judgement that they "
    "disagree; it does not verify it."
)

#: node types it makes sense to call contradictory. `contradicts` itself is
#: domain-`"any"` at the write boundary, deliberately — but a *tool* offering
#: it to an agent should still refuse the cases that are certainly mistakes:
#: an agent marking a `decision` or `verification` node as contradictory is
#: confusing audit bookkeeping with evidence (docs/design.md §5 principle 6), and
#: a `query` cannot disagree with anything, it is a retrieval.
CONTRADICTABLE_TYPES = frozenset({
    NodeType.CLAIM, NodeType.CONJECTURE, NodeType.PASSAGE, NodeType.WITNESS,
})


class RecordContradictionInput(BaseModel):
    model_config = ConfigDict(extra="forbid")

    node_a_id: str = Field(min_length=1)
    node_b_id: str = Field(min_length=1)
    reason: str = Field(
        min_length=1,
        description=(
            "what the disagreement is: which readings or assertions conflict, "
            "and on what basis"
        ),
    )


def record_contradiction(
    graph: Graph, args: RecordContradictionInput, *, authored_by: str,
    model_call_id: int | None = None,
) -> str:
    """Returns the edge id. Raises `NodeNotFound` if either node is unknown,
    and `ValueError` for a node type that cannot meaningfully contradict."""
    for node_id in (args.node_a_id, args.node_b_id):
        node = graph.get_node(node_id)  # raises NodeNotFound, reported to the caller
        if node.type not in CONTRADICTABLE_TYPES:
            raise WrongNodeType(
                f"{node_id} is a {node.type}; a contradicts edge is for evidence and "
                f"assertions ({', '.join(sorted(CONTRADICTABLE_TYPES))}), not for "
                "audit records or retrievals"
            )

    return graph.add_edge(
        EdgeType.CONTRADICTS, args.node_a_id, args.node_b_id,
        authored_by=authored_by, model_call_id=model_call_id,
        reason=args.reason,
    )
