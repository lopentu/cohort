"""link_parallels: record `parallel_of` edges between witnesses the corpus
itself says are parallel texts (build order stage 4).

The evidence is CBETA's `<cb:docNumber>` cross-reference list, e.g.
`No. 251 [Nos. 250, 252-255, 257]` on the Heart Sutra — the other Taisho
numbers are its parallel translations. `cohort/sources/cbeta_markup.py` does
the reading; this tool decides what may be written from it.

**Two refusals are the point of this tool, not caveats on it.**

1. *Only `asserted` references become edges.* A `cf.` reference is a
   curatorial "compare", sometimes openly vague (`[cf. No. 220(4 or 5)
   etc.]`), and `Part of` is containment rather than symmetric parallelism.
   `parallel_of` has teeth here — `Graph.independent_support()` flips
   `independent` to False as soon as one links two witnesses backing the same
   claim — so minting an edge from a weak reference would *suppress*
   independent support, manufacturing the consensus illusion docs/design.md §4
   exists to expose. Weak references are reported, never written.

2. *Only witnesses already in the graph are linked.* A parallel target the
   graph has never fetched is reported as a candidate, not proposed as a
   `witness` node. Proposing one would assert a source record nobody has
   read — an unevidenced node standing in for evidence. Fetch it first; then
   re-run this tool and the edge appears.

Nothing is inferred from a witness's `canonical_ref` alone: the document is
re-fetched through the `Source`, from a `source_ref` recorded on one of the
witness's own passages, so the markup being parsed is the archive's, not a
guess about which file the witness came from.
"""
from __future__ import annotations

from pydantic import BaseModel, ConfigDict, Field

from cohort.errors import NodeNotFound, SourceRefMissing, WrongNodeType
from cohort.graph import Graph
from cohort.schemas import EdgeType, NodeType
from cohort.sources.base import Source
from cohort.sources.cbeta_markup import parse_parallel_refs

from ._witness_source import source_ref_for_witness

NAME = "link_parallels"
DESCRIPTION = (
    "Record parallel_of edges between a witness and the parallel texts its "
    "own CBETA cross-reference list asserts, skipping weaker 'cf.' and "
    "'Part of' references and any target not already in the graph."
)


class LinkParallelsInput(BaseModel):
    model_config = ConfigDict(extra="forbid")

    witness_id: str = Field(min_length=1)


class LinkParallelsReport(BaseModel):
    """What was written, and — at equal prominence — what was not. A caller
    that only reads `linked` learns nothing about the references this tool
    declined, which is why the other four fields exist."""

    model_config = ConfigDict(extra="forbid")

    witness_id: str
    #: witness ids newly linked by a `parallel_of` edge this call
    linked: list[str] = []
    #: already linked before this call; re-running is a no-op, not a duplicate
    already_linked: list[str] = []
    #: asserted parallels resolved to a witness ref the graph does not hold.
    #: Fetch these, then re-run.
    absent_from_graph: list[str] = []
    #: Taisho numbers this tool refused to resolve, with the reason —
    #: ambiguous (several volumes or lettered siblings) or unknown.
    unresolved: dict[str, str] = {}
    #: references deliberately not written: `cf.` and `Part of` lists, plus
    #: bracket contents the parser declined to read.
    not_asserted: dict[str, list[str]] = {}


def link_parallels(
    graph: Graph, source: Source, args: LinkParallelsInput, *, authored_by: str,
    model_call_id: int | None = None,
) -> LinkParallelsReport:
    witness = graph.get_node(args.witness_id)
    if witness.type != NodeType.WITNESS:
        raise WrongNodeType(f"{args.witness_id} is a {witness.type}, not a witness")

    source_ref = source_ref_for_witness(graph, args.witness_id)
    if source_ref is None:
        raise SourceRefMissing(
            f"{args.witness_id} has no passage carrying a source_ref, so its "
            "document cannot be re-fetched; nothing to parse"
        )

    document = source.fetch(source_ref).text
    refs = parse_parallel_refs(document)

    report = LinkParallelsReport(
        witness_id=args.witness_id,
        not_asserted={
            "compare_only": [r.number for r in refs.compare_only],
            "part_of": [r.number for r in refs.part_of],
            "unparsed": list(refs.unparsed),
        },
    )

    own_ref = witness.payload.get("canonical_ref")
    for ref in refs.asserted:
        candidates = _resolve(source, ref.number)
        if not candidates:
            report.unresolved[ref.number] = "no entry in the archive for this Taisho number"
            continue
        if len(candidates) > 1:
            report.unresolved[ref.number] = (
                f"ambiguous: resolves to {', '.join(candidates)} — not guessed"
            )
            continue

        target_ref = candidates[0]
        if target_ref == own_ref:
            continue  # a text listed against itself is not a parallel relation
        target_id = f"{NodeType.WITNESS}:{target_ref}"
        try:
            graph.get_node(target_id)
        except NodeNotFound:
            report.absent_from_graph.append(target_ref)
            continue
        # `parallel_of` is symmetric and written in both directions from one
        # event, so checking either direction is sufficient to stay idempotent.
        if graph.edges(edge_type=EdgeType.PARALLEL_OF, src=args.witness_id, dst=target_id):
            report.already_linked.append(target_ref)
            continue
        graph.add_edge(
            EdgeType.PARALLEL_OF, args.witness_id, target_id,
            authored_by=authored_by, model_call_id=model_call_id,
        )
        report.linked.append(target_ref)

    return report


def _resolve(source: Source, number: str) -> list[str]:
    """Ask the source to map a bare Taisho number onto witness refs. Readers
    without that capability (e.g. `LocalReader`) simply yield nothing, so
    this tool degrades to reporting rather than failing."""
    resolver = getattr(source, "resolve_taisho_number", None)
    if resolver is None:
        return []
    return resolver(number)
