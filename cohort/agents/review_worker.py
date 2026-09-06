"""A reviewer: an agent that checks claims other agents authored, and never
authors one itself.

Both sibling projects separate the checker from the checked, and COHORT did
not — verification was a tool any worker could call, and nothing stopped an
agent attesting its own claim (compare.md §10, which called this the most
substantive outstanding criticism). `Graph.attest()` now refuses that write.
This class is the other half: someone for the refused work to fall to.

**What a reviewer is not.** It is not a second model whose agreement counts
as evidence. `VerificationMethod` rules out `MODEL_ENTAILMENT` deliberately —
"a second model's opinion is still another agent's opinion" — and a reviewer
built as an entailment judge would reintroduce exactly the consensus-seeking
the whole design argues against. So this agent's evidence is mechanical: it
re-fetches every cited passage and re-locates the excerpt against the freshly
fetched source, and *that* is what promotes a claim. Its judgment is a veto
only: it can withhold promotion, never manufacture it. See
`cohort.tools.review_claim`.

**Why the tool set is this small.** A reviewer has exactly two tools:
`review_claim` and `record_contradiction`. It cannot propose, because a
checker that authors claims accumulates work it is then barred from checking,
and on a small roster "everyone reviews everyone" degrades to no review at
all. It cannot accept: citable is still the researcher's word alone. The
restriction is not enforced by the prompt — the tools simply are not on the
list, so there is no instruction for a model to talk itself out of.

**Model family.** A reviewer sharing a provider with the author it checks is
refused at the write boundary like any other agent (`cohort.families`), so
the run layer must give it a model from another provider. That is a floor on
independence, not a proof of one.
"""
from __future__ import annotations

from cohort.graph import Graph
from cohort.schemas import NodeStatus, NodeType
from cohort.tools.record_contradiction import DESCRIPTION as RECORD_CONTRADICTION_DESCRIPTION
from cohort.tools.record_contradiction import NAME as RECORD_CONTRADICTION_NAME
from cohort.tools.record_contradiction import RecordContradictionInput, record_contradiction
from cohort.tools.review_claim import DESCRIPTION as REVIEW_CLAIM_DESCRIPTION
from cohort.tools.review_claim import NAME as REVIEW_CLAIM_NAME
from cohort.tools.review_claim import ReviewClaimInput, review_claim

from .attestation_worker import AttestationWorker

#: bump whenever REVIEW_PROMPT or REVIEW_TOOLS changes shape, so logged
#: model_call rows stay comparable across prompt revisions.
REVIEW_PROMPT_VERSION = "review_worker/v1"

REVIEW_PROMPT = (
    "You are a reviewer in COHORT, an evidence graph for textual research. "
    "Other agents propose claims; you check them. You did not write any of "
    "them and you may not write any: you have no tool for proposing, and "
    "that is deliberate.\n\n"
    "review_claim re-fetches every passage cited by a claim and re-locates "
    "its excerpt in the freshly-fetched source, then records your verdict. "
    "Understand what your verdict can and cannot do. If every cited span "
    "re-verifies AND you answer 'sound', the claim advances to attested. If "
    "any span fails to re-verify, nothing you say can advance it. If you "
    "answer 'unsound' or 'indeterminate', the claim does not advance and your "
    "reason is recorded against it. You can stop a claim; you cannot promote "
    "one on your own say-so.\n\n"
    "So judge the citation, not the prose. The question is whether the "
    "passages cited actually say what the claim says they say — not whether "
    "the claim sounds plausible, matches what you know about the text, or is "
    "one you would have made. A claim you find implausible but that its "
    "citations support is 'sound'; a well-phrased claim whose passages are "
    "about something else is 'unsound'. Your own knowledge of the corpus is "
    "not evidence here; the fetched text is.\n\n"
    "Watch for a claim resting on several passages from witnesses that are "
    "copies of one another — review_claim reports distinct witnesses and "
    "whether the support is independent. Repetition is not corroboration. "
    "If two passages genuinely conflict, record_contradiction records that "
    "as structure rather than as an opinion.\n\n"
    "State what you checked, in a sentence. Call tools; do not narrate."
)

REVIEW_TOOLS = [
    {
        "type": "function",
        "function": {
            "name": REVIEW_CLAIM_NAME,
            "description": REVIEW_CLAIM_DESCRIPTION,
            "parameters": ReviewClaimInput.model_json_schema(),
        },
    },
    {
        "type": "function",
        "function": {
            "name": RECORD_CONTRADICTION_NAME,
            "description": RECORD_CONTRADICTION_DESCRIPTION,
            "parameters": RecordContradictionInput.model_json_schema(),
        },
    },
]


class ReviewWorker(AttestationWorker):
    """Same tool loop, different role — see the module docstring.

    Subclassing rather than copying is the point: budget accounting, refusal
    logging, model-call records and the concurrency argument that makes
    several workers safe against one `Graph` are role-independent, and a
    second hand-maintained copy of that loop would drift."""

    SYSTEM_PROMPT = REVIEW_PROMPT
    TOOLS = REVIEW_TOOLS
    PROMPT_VERSION = REVIEW_PROMPT_VERSION

    def _dispatch(self, name: str, args: dict, model_call_id: int | None = None) -> tuple[bool, object]:
        try:
            if name == REVIEW_CLAIM_NAME:
                parsed = ReviewClaimInput.model_validate(args)
                return False, review_claim(
                    self.graph, self.source, parsed, authored_by=self.authored_by,
                    model_call_id=model_call_id,
                ).model_dump(mode="json")
            if name == RECORD_CONTRADICTION_NAME:
                parsed = RecordContradictionInput.model_validate(args)
                return False, record_contradiction(
                    self.graph, parsed, authored_by=self.authored_by,
                    model_call_id=model_call_id,
                )
            # A reviewer asking for propose_claim lands here rather than in a
            # silent no-op, so the model is told the role is the reason.
            return True, (
                f"unknown tool: {name}. A reviewer has only "
                f"{REVIEW_CLAIM_NAME} and {RECORD_CONTRADICTION_NAME}; "
                "proposing and accepting are not a reviewer's to do."
            )
        except Exception as e:
            self.graph.log_refusal(
                name, self.authored_by, e,
                node_id=args.get("claim_id") or args.get("node_a_id"),
                model_call_id=model_call_id,
            )
            return True, f"{type(e).__name__}: {e}"


#: how many pending items to name in a reviewer's instructions. A reviewer
#: works through them one tool call at a time inside a bounded number of
#: turns, so listing hundreds would spend input tokens on claims it will
#: never reach and bury the ones it will.
MAX_PENDING_LISTED = 25


def pending_review_context(graph: Graph, authored_by: str) -> str | None:
    """The claims and conjectures this reviewer may actually promote, or None
    if there are none.

    Filtered through `Graph.attest_conflict`, so a claim the reviewer authored
    or one whose author shares its model family is never offered — the
    reviewer does not spend a fetch, a turn and a refusal discovering a rule
    the graph could have told it for free. None rather than an empty string
    because "nothing to review" is a reason to skip the agent entirely, and
    the run layer needs to tell that apart from "here is your list".

    This is computed after the workers finish, not when the run is
    configured: what there is to review does not exist yet at configuration
    time. That is also why a reviewer's instructions are the only ones the
    run layer appends to.
    """
    pending = [
        n
        for node_type in (NodeType.CLAIM, NodeType.CONJECTURE)
        for n in graph.nodes(node_type=node_type)
        if n.status == NodeStatus.PROPOSED
        and graph.attest_conflict(n.id, authored_by) is None
    ]
    if not pending:
        return None
    lines = [
        "Proposed claims and conjectures awaiting review. You may review any "
        "of these; each was authored by another agent. Pass the quoted id "
        "below as claim_id exactly as written, prefix included — the "
        '"claim:" / "conjecture:" part is inside the id, not a label on it. '
        "The first multi-model run to be censused lost every one of its "
        "reviews to that mistake."
    ]
    for n in pending[:MAX_PENDING_LISTED]:
        text = n.payload.get("text") or n.payload.get("statement") or n.id
        lines.append(f'- "{n.id}" [{n.type}] {text!r}')
    if len(pending) > MAX_PENDING_LISTED:
        lines.append(
            f"...and {len(pending) - MAX_PENDING_LISTED} more not listed. Review the "
            "ones above; the rest keep until a later run."
        )
    return "\n".join(lines)
