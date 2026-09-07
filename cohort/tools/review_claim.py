"""review_claim: a second agent re-runs the mechanical checks a claim rests
on, and may promote it only if they hold.

**Why this is not "a second model agrees".** `VerificationMethod`'s docstring
rules out `MODEL_ENTAILMENT` in as many words — "a second model's opinion is
still another agent's opinion, and admitting it as a formal verification
method would smuggle consensus-among-models back in through the side door".
A reviewer built as an entailment judge would be exactly that door. So the
reviewer's evidence is not its opinion: it re-fetches every cited passage's
source and re-locates the excerpt (`verify_exact_span`), which is a check
against bytes that a model cannot talk its way past.

**The asymmetry that makes the role safe.** The reviewer's judgment can only
subtract. Promotion requires the mechanical checks to pass *and* the reviewer
not to object; an objection withholds attestation, but no amount of model
agreement can supply one. A claim therefore never advances on the strength of
something a model said — only on a re-verified span — while a reviewer that
notices the citation does not support the claim can still stop it. That is
the honest division: machines are good at re-checking locations and bad at
adjudicating meaning, so only the first is given force.

**What the reviewer cannot do.** It has no `propose_*` tool: a checker that
authors claims accumulates work it is then barred from checking, and the
separation `Graph.attest()` enforces would decay into "everyone reviews
everyone" — which is peer review in name only when the roster is small. It
also cannot `accept`: promotion to citable stays the researcher's, unchanged.

**Why the objection is recorded even when nothing is written to the ladder.**
A silent non-attestation is indistinguishable from a reviewer that never ran.
The verification node is written either way, carrying the mechanical result
in `detail` and the reviewer's stated objection in `limitations` — the field
for what a passing check does *not* establish, which is precisely what an
objection over verified spans is.
"""
from __future__ import annotations

from pydantic import BaseModel, ConfigDict, Field

from cohort.errors import CohortError, InvalidVerdict, WrongNodeType
from cohort.graph import Graph
from cohort.schemas import (
    AssuranceLevel,
    EdgeType,
    NodeStatus,
    NodeType,
    VerificationMethod,
    VerificationResult,
)
from cohort.sources.base import Source

from .verify_exact_span import verify_exact_span

NAME = "review_claim"
DESCRIPTION = (
    "Review a claim or conjecture you did not author: every passage citing "
    "it is re-fetched from the corpus and its excerpt re-located, then you "
    "give a verdict. Verdict 'sound' promotes it to attested only if every "
    "span re-verified; 'unsound' or 'indeterminate' withholds promotion and "
    "records your stated reason. You cannot promote a claim whose spans fail "
    "to re-verify, and you cannot accept anything — that stays the "
    "researcher's. State what you checked, not whether you find the claim "
    "plausible."
)


class ReviewClaimInput(BaseModel):
    model_config = ConfigDict(extra="forbid")

    claim_id: str = Field(min_length=1)
    verdict: str = Field(
        description=(
            "'sound' if the cited passages support the claim as written, "
            "'unsound' if they do not, 'indeterminate' if you cannot tell "
            "from the citations alone"
        ),
    )
    detail: str = Field(
        min_length=1,
        description=(
            "what you checked and what you found, in a sentence — recorded "
            "verbatim on the verification node"
        ),
    )


VERDICTS = ("sound", "unsound", "indeterminate")


class ReviewClaimReport(BaseModel):
    #: the verification node recording this review
    verification_id: str
    #: passages cited by the claim, and how many re-verified against a fresh
    #: fetch of their source
    spans_checked: int
    spans_matched: int
    #: distinct witnesses behind those passages, and whether any descent or
    #: parallel relation links two of them — surfaced to the reviewer because
    #: an author has no incentive to look and a researcher reading the
    #: verification should not have to go and ask separately
    distinct_witnesses: int
    independent: bool
    #: whether this review advanced the claim to `attested`
    attested: bool
    note: str


def review_claim(
    graph: Graph, source: Source, args: ReviewClaimInput, *, authored_by: str,
    model_call_id: int | None = None,
) -> ReviewClaimReport:
    if args.verdict not in VERDICTS:
        raise InvalidVerdict(f"verdict must be one of {VERDICTS}, got {args.verdict!r}")

    node = graph.get_node(args.claim_id)
    if node.type not in (NodeType.CLAIM, NodeType.CONJECTURE):
        raise WrongNodeType(
            f"{args.claim_id} is a {node.type}; only a claim or conjecture is reviewable")

    # Refuse the review itself rather than doing the work and discarding it.
    # `attest()` would refuse at the end anyway, but a reviewer that spends
    # fetches re-verifying a claim it is barred from promoting has learnt the
    # rule too late to act on it.
    conflict = graph.attest_conflict(args.claim_id, authored_by)
    if conflict is not None:
        # Re-raised as itself, not wrapped: the census reads the rule name, and
        # `SelfAttestation` and `ReviewerNotIndependent` are the two rules a
        # researcher most needs to see holding.
        raise conflict

    passages = [e.src for e in graph.edges(edge_type=EdgeType.ATTESTS, dst=args.claim_id)]
    matched = 0
    for passage_id in passages:
        verification_id = verify_exact_span(
            graph, source, passage_id, authored_by=authored_by, model_call_id=model_call_id,
        )
        if graph.get_node(verification_id).payload["result"] == VerificationResult.PASS:
            matched += 1

    support = graph.independent_support(args.claim_id)
    spans_ok = bool(passages) and matched == len(passages)
    result = (
        VerificationResult.PASS if spans_ok
        else VerificationResult.FAIL if passages
        else VerificationResult.INDETERMINATE
    )

    mechanical = (
        f"reviewer {authored_by} re-fetched {len(passages)} cited passage(s); "
        f"{matched} re-verified at the recorded span. "
        f"{support.distinct_witnesses} distinct witness(es); "
        f"independent={support.independent}."
    )
    # The reviewer's own words go in `limitations`, never in `detail`, and
    # never into `result`. `detail` is what the machine established; a model's
    # reading is a limit on what that establishes, which is what this field is
    # for. Keeping them in separate fields is what stops a confident sentence
    # from reading later as a mechanical finding.
    #
    # `sound` used to be the exception: its prose was appended to `detail` on
    # the reasoning that a positive verdict is not a limitation. The negative
    # control (2026-09-02, scripts/run_negative_control.py) showed what that
    # cost. A reviewer handed a claim with one altered excerpt returned `sound`
    # with "Re-fetched and re-verified the cited passages... confirming that
    # the title indeed appears in the corpus" — and that sentence landed in
    # `detail`, the machine's field, on a verification whose result was `fail`.
    # A sound verdict over a failing check is not corroboration; it is the most
    # important thing on the record to mark as *not* established.
    limitations = f"reviewer verdict {args.verdict}: {args.detail}"

    # A2, and independence is deliberately not graded at all.
    #
    # The review re-fetches spans, which is what A2 records. It also computes
    # independence — but that is not a rung and must not become one: it is a
    # pure function of current graph state, so `independent_support()` gives
    # it live on every read, and freezing it here would store a derivable fact
    # that one later `parallel_of` edge elsewhere could falsify with nobody
    # having touched this node. See `AssuranceLevel`, which records the
    # argument and the 2026-09-02 rename that removed the misleading rung.
    #
    # The independence finding still goes in `detail`, where it is readable
    # without being graded.
    verification_id = graph.verify(
        args.claim_id,
        method=VerificationMethod.EXACT_SPAN,
        result=result,
        assurance_level=(
            AssuranceLevel.A2_EXACT_SPAN_MATCHED if spans_ok else AssuranceLevel.A0_UNCHECKED
        ),
        detail=mechanical,
        limitations=limitations,
        authored_by=authored_by,
        model_call_id=model_call_id,
    )

    attested = False
    note = ""
    if not passages:
        note = "nothing cites this claim, so there was nothing to re-check; not advanced."
    elif not spans_ok:
        note = (
            f"{len(passages) - matched} of {len(passages)} cited spans did not re-verify; "
            "not advanced. The citations, not the wording, are what failed."
        )
    elif args.verdict != "sound":
        note = (
            f"every span re-verified, but the verdict was {args.verdict}, so the claim was "
            "not advanced. A reviewer may withhold promotion; only the mechanical check can "
            "grant it."
        )
    elif node.status != NodeStatus.PROPOSED:
        note = f"already {node.status}; a review records evidence but does not repeat a rung."
    else:
        try:
            graph.attest(args.claim_id, authored_by=authored_by, model_call_id=model_call_id)
            attested = True
            note = "every cited span re-verified and the reviewer found it sound; now attested."
        except CohortError as e:
            # The write boundary owns the ladder's preconditions and may still
            # refuse — a conjecture with no `tests` edge is the ordinary case.
            # Already recorded to the refusal log by `_refuse`.
            #
            # The rule's name is carried, not just its message: several of
            # these errors stringify to a bare node id, and "not advanced:
            # conjecture:8da037…" tells a reviewer nothing it can act on.
            note = f"not advanced ({type(e).__name__}): {e}"

    return ReviewClaimReport(
        verification_id=verification_id,
        spans_checked=len(passages),
        spans_matched=matched,
        distinct_witnesses=support.distinct_witnesses,
        independent=support.independent,
        attested=attested,
        note=note,
    )
