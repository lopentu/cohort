"""propose_conjecture: propose something not yet stated by any source,
together with a dossier and the query that would test it.

The falsifiability gate's write side (design doc §7) is unchanged: a
conjecture proposed any other way has no `tests` edge and is permanently
unattestable via `attests` edges, however many it collects. This tool is
still the only sanctioned way to get a conjecture past that gate.

Layered on top (docs/roadmap.md "Scope revision", verification axis): the
dossier fields (`derivation`, `corpus_boundary`, `selection_risks`,
`alternative_explanations`) are enforced by `ConjecturePayload` itself, at
proposal time, not by a new write-boundary rule — pydantic already refuses
the payload before this tool ever calls `graph.propose_conjecture()`. And a
prior-art search is now required and actually run (not just claimed): this
tool searches the corpus first, records the search as a `query` node with a
`searched_for` edge to the conjecture, distinct from the `tests` edge
(which records what would settle the conjecture going forward, not what was
already searched before proposing it).

The `tests` query also carries a **prediction** — a direction and a hit count,
recorded before the query is ever run. The gate has always demanded a query
that would settle the conjecture and never asked it; `run_prospective_test`
is what asks it, and it can only be a real test if the expected answer was on
the record first. See `cohort/tools/run_prospective_test.py`.
"""
from __future__ import annotations

from pydantic import BaseModel, ConfigDict, Field

from cohort.graph import Graph
from cohort.schemas import ConjecturePayload, EdgeType, HitExpectation, QueryPayload
from cohort.sources.base import Source

NAME = "propose_conjecture"
DESCRIPTION = (
    "Propose a conjecture the sources don't yet state outright. Requires a "
    "full dossier (derivation, corpus boundary, selection risks, "
    "alternative explanations), a prior-art query that is actually run "
    "against the corpus before proposing, and a query that would confirm "
    "or refute the conjecture going forward together with what you predict "
    "that query will return. A conjecture proposed without the prospective "
    "query cannot be attested."
)


class ProposeConjectureInput(BaseModel):
    model_config = ConfigDict(extra="forbid")

    text: str = Field(min_length=1)
    derivation: str = Field(min_length=1)
    corpus_boundary: str = Field(min_length=1)
    selection_risks: str = Field(min_length=1)
    alternative_explanations: str = Field(min_length=1)
    prior_art_query: str = Field(min_length=1)
    tests_query_text: str = Field(min_length=1)
    #: The prediction, recorded before the query is ever run. Required, and
    #: required *here* rather than supplied later, because a prediction stated
    #: after the result is known is not a prediction. `at_most 0` is the usual
    #: shape — "if this query finds anything, the conjecture is in trouble".
    tests_expectation: HitExpectation
    tests_expected_hits: int = Field(ge=0)


def propose_conjecture(
    graph: Graph, source: Source, args: ProposeConjectureInput, *, authored_by: str,
    model_call_id: int | None = None,
) -> str:
    prior_art_hits = source.search(args.prior_art_query)
    prior_art_query_id = graph.propose_query(
        QueryPayload(text=f"prior art: {args.prior_art_query!r} ({len(prior_art_hits)} hits)"),
        authored_by=authored_by, model_call_id=model_call_id,
    )

    conjecture_id = graph.propose_conjecture(
        ConjecturePayload(
            text=args.text,
            derivation=args.derivation,
            corpus_boundary=args.corpus_boundary,
            selection_risks=args.selection_risks,
            alternative_explanations=args.alternative_explanations,
        ),
        authored_by=authored_by, model_call_id=model_call_id,
    )

    graph.add_edge(
        EdgeType.SEARCHED_FOR, prior_art_query_id, conjecture_id, authored_by=authored_by,
        model_call_id=model_call_id,
    )

    # The prediction rides on the query node, not on the conjecture: it is a
    # statement about what *this retrieval* will return, and it has to sit
    # somewhere nothing can edit afterwards. Payloads are immutable and
    # hashed, so recording it here is what makes the later comparison a
    # prospective test rather than a story told about a number.
    tests_query_id = graph.propose_query(
        QueryPayload(
            text=args.tests_query_text,
            expectation=args.tests_expectation,
            expected_hits=args.tests_expected_hits,
        ),
        authored_by=authored_by, model_call_id=model_call_id,
    )
    graph.add_edge(
        EdgeType.TESTS, tests_query_id, conjecture_id, authored_by=authored_by,
        model_call_id=model_call_id,
    )
    return conjecture_id
