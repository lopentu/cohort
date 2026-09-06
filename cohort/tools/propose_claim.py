"""propose_claim: assert something the sources *do* state, grounded in a
search that is actually run.

Why this tool exists at all: an agent could already propose conjectures but
had no way to create a `claim`, so when a live run wanted attestations for a
proposition not yet in the graph it invented node ids and was refused five
times over (docs/handoff.md, conjecture run). The refusals were the write boundary
working correctly, but the gap they exposed is real — claims that cite
passages are the ordinary case the design is built around (design doc §7,
"Claims must cite nodes"), and there was no sanctioned way to make one.

Why it is not a bare one-field write. `ClaimPayload` asks only for `text`,
so an unguarded tool would be markedly *cheaper* than `propose_conjecture`,
which demands a four-field dossier, a prior-art search and a prospective
query. That asymmetry is a bypass: anything an agent could not get past the
falsifiability gate it could relabel as a claim, bolt on whatever passages a
search happens to return, and ride the ladder to `attested` with no dossier
at all. That is precisely the "vacuous grounded claim" design doc §7 says
citation checking "passes happily, because a claim can be perfectly cited
and say nothing".

The guard, mirroring `propose_conjecture`'s prior-art step: the grounding
query is run against the corpus *before* the claim node is written, and a
query with no hits refuses the claim instead of proposing it. Nothing is
written on that path — no orphan claim, no orphan query node. This is a
tool-level check, not a new write-boundary rule: `errors.py` owns state
validity raised by `graph.py` and nowhere else, so this raises a plain
`ValueError`, the same way `find_attestations` does for a wrong node type,
and `AttestationWorker._dispatch` reports it back to the model.

The guard costs nothing legitimate. A claim whose grounding query returns
nothing has no passages to cite, so `attest()` would refuse to advance it
anyway (`UnattestableClaim`) — the refusal just arrives at proposal time
instead of one rung later. The one case it genuinely turns away is the
*negative* claim ("X does not occur in this corpus"), and that case belongs
in `propose_conjecture` on its merits: an absence is settled by a retrieval,
not by citation, which is exactly what a `tests` edge records. The refusal
message says so rather than leaving the agent to guess.

This tool deliberately does *not* attach the attestations itself. Grounding
and citing are two jobs: `find_attestations` already takes a claim id and
records `attests` edges through the same boundary, and duplicating its body
here would give two tools two subtly different ways to write evidence.
"""
from __future__ import annotations

from pydantic import BaseModel, ConfigDict, Field

from cohort.errors import UngroundedClaim
from cohort.graph import Graph
from cohort.schemas import ClaimPayload, EdgeType, QueryPayload
from cohort.sources.base import Source

NAME = "propose_claim"
DESCRIPTION = (
    "Propose a claim: an assertion the sources state, which must cite "
    "passages. Requires a grounding query that is actually run against the "
    "corpus before the claim is created; if it returns no hits the claim is "
    "refused, because a claim with no passages to cite can never be "
    "attested. Follow this with find_attestations on the returned claim id "
    "to record the evidence. For something the sources do not state "
    "outright, or for the absence of something, use propose_conjecture "
    "instead."
)

#: how many hits the grounding search asks for. Small on purpose: this step
#: only has to establish that the claim has *something* to cite, and
#: `find_attestations` is what actually gathers the evidence.
GROUNDING_MAX_RESULTS = 5


class ProposeClaimInput(BaseModel):
    model_config = ConfigDict(extra="forbid")

    text: str = Field(min_length=1)
    grounding_query: str = Field(
        min_length=1,
        description=(
            "a corpus query whose hits this claim rests on; run before the "
            "claim is created, and the claim is refused if it returns nothing"
        ),
    )


def propose_claim(
    graph: Graph, source: Source, args: ProposeClaimInput, *, authored_by: str,
    model_call_id: int | None = None,
) -> str:
    hits = source.search(args.grounding_query, max_results=GROUNDING_MAX_RESULTS)
    if not hits:
        raise UngroundedClaim(
            f"grounding query {args.grounding_query!r} returned no hits in this "
            "corpus, so this claim has no passages to cite and could never be "
            "attested. Either ground it with a query that does hit, or — if the "
            "point is that this does not occur in the corpus — propose it as a "
            "conjecture, since an absence is settled by a retrieval rather than "
            "by citation."
        )

    grounding_query_id = graph.propose_query(
        QueryPayload(text=f"grounding: {args.grounding_query!r} ({len(hits)} hits)"),
        authored_by=authored_by, model_call_id=model_call_id,
    )
    claim_id = graph.propose_claim(
        ClaimPayload(text=args.text), authored_by=authored_by, model_call_id=model_call_id,
    )
    graph.add_edge(
        EdgeType.SEARCHED_FOR, grounding_query_id, claim_id, authored_by=authored_by,
        model_call_id=model_call_id,
    )
    return claim_id
