"""Shared lookup used by the stage-4 tools, which take a `witness_id` but need
the archive entry that witness came from.

Both `link_parallels` and `collate_editions` carried a byte-identical copy of
this, only one of which was documented. It lives here so the reasoning below is
stated once — the two tools read different markup out of the same document, so
if this lookup is ever wrong it is wrong for both.
"""
from __future__ import annotations

from cohort.graph import Graph
from cohort.schemas import EdgeType


def source_ref_for_witness(graph: Graph, witness_id: str) -> str | None:
    """The `source_ref` of any passage belonging to `witness_id`. Any will do:
    every passage of a witness came from the same archive entry, and the markup
    these tools parse (`<cb:docNumber>` cross-references, `<app>` apparatus) is
    a property of that document, not of the passage within it.

    `None` means the witness has no located passage carrying a `source_ref`,
    which is a refusal case for the caller rather than something to guess past.
    """
    for edge in graph.edges(edge_type=EdgeType.PART_OF, dst=witness_id):
        passage = graph.get_node(edge.src)
        source_ref = passage.payload.get("source_ref")
        if source_ref:
            return source_ref
    return None
