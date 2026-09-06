"""Closed vocabulary: nodes, edges, events, dating (design doc §6).

Pydantic v2 models, not dataclasses, because these shapes are the contract an
*agent* has to satisfy — validation at this boundary is what makes a write
machine-checkable, not merely plausible (design doc §5 principle 4).

Closed on purpose: an unlisted vocabulary string is a `ValidationError`
before it ever reaches the write boundary, not a silently-accepted string.
"""
from __future__ import annotations

from datetime import datetime, timezone
from enum import StrEnum
from typing import Literal

from pydantic import BaseModel, ConfigDict, Field, field_validator


def now() -> str:
    return datetime.now(timezone.utc).isoformat()


class _Model(BaseModel):
    model_config = ConfigDict(extra="forbid")

    def to_dict(self) -> dict:
        return self.model_dump()


RESEARCHER = "researcher"


# --- closed vocabulary ------------------------------------------------------

class NodeType(StrEnum):
    WITNESS = "witness"
    PASSAGE = "passage"
    CLAIM = "claim"
    CONJECTURE = "conjecture"
    QUERY = "query"
    #: A research question: what an inquiry was actually asking.
    #:
    #: Added 2026-09-02 with the argument §6 requires, after a comparison
    #: against two sibling projects that both lead their output with a
    #: question and COHORT structurally could not.
    #:
    #: Every other node type answers "what is in the corpus" or "what does the
    #: record say". None of them answers "what were we asking", so a reader of
    #: a COHORT graph could not tell whether a claim was the point of an
    #: inquiry or a byproduct of one, and a findings page had no title it could
    #: honestly give itself. An agent's declared corpus scope also floated
    #: free, being a scope of nothing in particular.
    #:
    #: It is **not** a `query`, and the two must not be conflated: a query is a
    #: retrieval to run against the corpus, and a question is not runnable. It
    #: is also not evidence — a question asserts nothing, so principle 2 has
    #: nothing to object to.
    QUESTION = "question"
    DECISION = "decision"
    #: one verification attempt against a claim/conjecture/passage/witness.
    #: Parallel to `decision`: a record of a judgement, not evidential
    #: content itself (docs/roadmap.md "Scope revision", verification axis).
    VERIFICATION = "verification"


class EdgeType(StrEnum):
    ATTESTS = "attests"
    CONTRADICTS = "contradicts"
    PARALLEL_OF = "parallel_of"
    DESCENDS_FROM = "descends_from"
    QUOTES = "quotes"
    TESTS = "tests"
    SUPERSEDES = "supersedes"
    #: passage -> witness. Added to the vocabulary deliberately (design doc
    #: §11 flags the payload-field version as a weak point to fix in stage
    #: 2; there's no migration cost to building the edge form from day one).
    PART_OF = "part_of"
    #: verification -> {claim, conjecture, passage, witness}. The evidentiary
    #: node points at what it evidences, same direction as `attests`/`tests`.
    VERIFIES = "verifies"
    #: {claim, conjecture} -> question. What an assertion was put forward as
    #: an answer to. Direction follows `attests` and `tests`: the dependent
    #: points at what it depends on.
    #:
    #: Deliberately *not* the other way round. A question pointing at its
    #: answers would make it a container, and a container with nine claims in
    #: it reads as a question that has been answered — which is a conclusion
    #: no edge should draw.
    ADDRESSES = "addresses"
    #: query -> conjecture. Records that a prior-art search was actually run
    #: before a conjecture was proposed, distinct from `tests` (which records
    #: what would settle the conjecture going forward, not what was already
    #: searched for before proposing it).
    SEARCHED_FOR = "searched_for"


class NodeStatus(StrEnum):
    PROPOSED = "proposed"
    ATTESTED = "attested"
    ACCEPTED = "accepted"
    REJECTED = "rejected"


class DatingRoute(StrEnum):
    DATED = "dated"
    ATTRIBUTED = "attributed"
    SOURCE_LABEL = "source_label"
    UNKNOWN = "unknown"


class AssuranceLevel(StrEnum):
    """A computed read over a node's `verifies`-linked verification nodes
    (`Graph.assurance_for()`), never a second mutable field on the subject
    node — the graph is a projection, and a stored assurance field could
    drift from the verification nodes it's supposed to summarize (design doc
    §5 principle 1). Orthogonal to `NodeStatus`: a claim can be `accepted`
    with no verification ever run, or `proposed` with several. StrEnum
    values are stable strings so a later rung can be inserted without
    renumbering or touching already-recorded verification nodes.

    **A3 was renamed on 2026-09-02, and the rename is the point.** It read
    `A3_INDEPENDENCE_CHECKED`, and the only check that reaches it —
    `collate_editions`, via `CROSS_EDITION_COLLATION` — had to carry a
    standing `limitations` paragraph explaining that it establishes nothing of
    the kind: apparatus describes variants *within one document*, so it cannot
    speak to the relation between two witnesses. A tool whose job includes
    disclaiming its own rung is a misnamed rung, not a careful tool.

    **Cross-witness independence is deliberately not on this ladder.** It is
    a pure function of current graph state, so `independent_support()` computes
    it live on every read and both front ends print it beside the support count.
    Freezing it into a verification record would store a derivable fact
    (against principle 1) and would be the one rung that could go stale with
    nobody having touched the node — adding one `parallel_of` edge elsewhere
    would falsify a recorded "independence checked" without re-running
    anything. There is also no state to grade: COHORT examines independence on
    every read, so "independence examined" is true of every node with
    attestations and distinguishes nothing.
    """

    A0_UNCHECKED = "A0_UNCHECKED"
    A1_LOCATOR_VALID = "A1_LOCATOR_VALID"
    A2_EXACT_SPAN_MATCHED = "A2_EXACT_SPAN_MATCHED"
    A3_EDITION_SUPPORT_CHECKED = "A3_EDITION_SUPPORT_CHECKED"
    A4_HUMAN_APPROVED = "A4_HUMAN_APPROVED"

    @classmethod
    def _missing_(cls, value):
        """Accept the pre-rename string so recorded nodes and replayed logs
        still parse.

        The event log is ground truth and is never rewritten, so a graph
        seeded before the rename holds `A3_INDEPENDENCE_CHECKED` in its
        payloads and in its log. Rewriting those would either break the
        payload hashes `verify_integrity()` checks or make `rebuild()`
        disagree with the log — so the old name is read, never written."""
        if value == "A3_INDEPENDENCE_CHECKED":
            return cls.A3_EDITION_SUPPORT_CHECKED
        return None


class VerificationMethod(StrEnum):
    """Domain-appropriate mechanical checks only — no numerical/statistical/
    code/database verifiers (no such claims exist in a philological corpus),
    and deliberately no MODEL_ENTAILMENT: a second model's opinion is still
    another agent's opinion, and admitting it as a formal verification
    method would smuggle consensus-among-models back in through the side
    door (design doc §4's whole thesis)."""

    LOCATOR_RESOLUTION = "locator_resolution"
    EXACT_SPAN = "exact_span"
    CROSS_EDITION_COLLATION = "cross_edition_collation"
    DATING_ROUTE_CONFIDENCE = "dating_route_confidence"
    HUMAN_REVIEW = "human_review"

    #: Re-run a conjecture's prospective query and compare the hit count to
    #: the prediction its author recorded *before* it was ever run
    #: (`cohort.tools.run_prospective_test`).
    #:
    #: Added 2026-09-02 with the argument §6 requires. The falsifiability gate
    #: has always demanded a query that would settle a conjecture going
    #: forward, and nothing ever asked it — the gate checked that a test
    #: *existed*, never that it was run. This is the method that runs it.
    #:
    #: It belongs here, and `MODEL_ENTAILMENT` still does not, because nothing
    #: in it is anyone's opinion: a stored query is re-run against the corpus
    #: and a stored integer is compared to the count that comes back. It is
    #: also the only method that can fail on **new evidence** rather than on a
    #: broken record — every other method here asks whether the record still
    #: holds up, and this one asks whether the world still agrees. That is what
    #: makes it a test rather than a check.
    PROSPECTIVE_TEST = "prospective_test"

    #: Re-count a stated feature across the corpus and compare the numbers to
    #: the ones a claim's author recorded (`cohort.measure`,
    #: `cohort.tools.measure_claim`).
    #:
    #: Added 2026-09-06 with the argument §6 requires, for the Paramārtha
    #: ascription question. Until now an agent could write "occurs eighteen
    #: times in P-23, twice in P-weird" into a `derivation` and the graph had
    #: no way to disagree. In an attribution study *every* claim is a count or
    #: a rate, so that gap is not a rough edge: it is the difference between a
    #: finding and a story with figures in it.
    #:
    #: It belongs here for the same reason `PROSPECTIVE_TEST` does and
    #: `MODEL_ENTAILMENT` still does not — nothing in it is anyone's opinion.
    #: A stated feature is counted again over the same works and the same base
    #: edition, and the integers are compared. `cohort.measure` is pure and
    #: deterministic precisely so this comparison means something.
    #:
    #: What it cannot do is say a feature *discriminates*. It re-derives the
    #: numbers a claim rests on; whether they support the claim is a judgement,
    #: and putting that judgement in a verification would turn a recount into a
    #: verdict.
    CORPUS_MEASUREMENT = "corpus_measurement"


class VerificationResult(StrEnum):
    PASS = "pass"
    FAIL = "fail"
    INDETERMINATE = "indeterminate"


AuthorshipAction = Literal[
    "proposed", "attested", "accepted", "rejected", "reopened", "converged",
    # edges have no ladder, but they can be withdrawn and restored by the
    # researcher — recorded here so an edge carries who withdrew it, not
    # only that it is withdrawn.
    "retracted", "restored",
]


class AgentKind(StrEnum):
    WORKER = "worker"
    #: An agent that checks other agents' claims and never authors one. Not a
    #: second opinion: a reviewer re-runs the *mechanical* checks a claim
    #: rests on against freshly-fetched source, and may withhold promotion but
    #: never supply it on its own say-so (`cohort.tools.review_claim`). The
    #: write boundary enforces the separation independently of this label —
    #: `Graph.attest()` refuses a self-attestation whatever kind the author
    #: declared.
    REVIEWER = "reviewer"
    RESEARCHER = "researcher"


# --- dating (design doc §6) -------------------------------------------------

class Dating(_Model):
    value: str | None = None
    confidence: DatingRoute
    basis: str = Field(min_length=1)

    @field_validator("basis")
    @classmethod
    def _real_sentence(cls, v: str) -> str:
        v = v.strip()
        if len(v.split()) < 3:
            raise ValueError("basis must be a stated sentence, not a label")
        return v


# --- authorship --------------------------------------------------------------
# A field on every node/edge (accumulating, never overwritten), not an edge —
# an `authored_by` edge would duplicate this with no way to keep the two
# consistent (design doc §6).

class Authorship(_Model):
    author: str = Field(min_length=1)
    at: str = Field(default_factory=now)
    action: AuthorshipAction


# --- agent identity (sidecar, not a graph node) -----------------------------
# An agent's declared corpus/method scope is operational metadata about a
# writer, not evidence about the corpus — principle 2 makes it a category
# error inside the closed node/edge vocabulary. Lives in a sidecar `agents`
# table, same footing as `node_authorship`/`edge_authorship` (docs/roadmap.md
# "Scope revision", agent-society axis).

class AgentProfile(_Model):
    id: str = Field(min_length=1)
    kind: AgentKind
    corpus_scope: str | None = None
    method_label: str | None = None
    #: the model this agent ran on. Recorded because declared viewpoint
    #: diversity is only real if the readers differ: two agents on one model
    #: share priors, so their agreement is one observation reported twice.
    #: `cohort.agents.roster` refuses a run whose agents share a model family.
    model: str | None = None


class AgentReport(_Model):
    """A pure contribution-history count, never a score. Deliberately not a
    reputation number: outcome-based signals that could feed one (ladder
    survival rate, independence quality, discount-edge contribution,
    responsiveness after rejection) are follow-on work, not built here — see
    docs/roadmap.md. This report must never be consulted by a write-boundary
    method; a number here feeding back into `attest()`/`accept()` would
    violate principle 6 by the back door."""

    agent_id: str
    proposed: int
    attested: int
    accepted: int
    rejected: int
    discount_edges_contributed: int


# --- node payloads -----------------------------------------------------------

class WitnessPayload(_Model):
    canonical_ref: str = Field(min_length=1)
    label: str | None = None
    dating: Dating
    #: license/rights terms for a restrictively-licensed but locally-held
    #: source (e.g. CBETA — CC BY-NC-SA-equivalent, not public domain).
    #: Additive; a single descriptive string is deliberate, not a
    #: structured rights model — docs/design.md §2 forbids COHORT from building a
    #: governance layer, even a small one (docs/roadmap.md "Scope revision").
    source_terms: str | None = None


class PassagePayload(_Model):
    canonical_ref: str = Field(min_length=1)
    locator: str = Field(min_length=1)
    excerpt: str | None = None
    #: how to re-fetch this passage's source for re-verification (e.g. a
    #: CbetaReader ref string). Additive; existing passages have none.
    source_ref: str | None = None


class ClaimPayload(_Model):
    text: str = Field(min_length=1)


class ConjecturePayload(_Model):
    """The falsifiability gate's own check (design doc §7, `attest()`'s
    conjecture branch) is untouched by the dossier below — it still asks
    only for a `tests` edge. These four fields are the *richer* dossier
    (docs/roadmap.md "Scope revision"), enforced by pydantic at proposal time,
    not by a new write-boundary rule. "none identified" is a legitimate
    value for the risk/alternatives fields, same pattern as `Dating.basis`:
    declining is legitimate, silence isn't."""

    text: str = Field(min_length=1)
    derivation: str = Field(min_length=1)
    corpus_boundary: str = Field(min_length=1)
    selection_risks: str = Field(min_length=1)
    alternative_explanations: str = Field(min_length=1)


class HitExpectation(StrEnum):
    """The direction of a prediction about a prospective query's hit count.

    Two values, not a free-text prediction, because the comparison has to be
    mechanical: a sentence about what the author expects is a sentence someone
    has to interpret afterwards, and an interpretation recorded after the
    result is known is not a prediction."""

    AT_MOST = "at_most"
    AT_LEAST = "at_least"


class DiscriminationPrediction(_Model):
    """What a candidate discriminator promises, registered before it is run.

    Added 2026-09-06 with the argument §6 requires, for the Paramārtha
    ascription question.

    **Two-sided, and that is the whole point.** A one-sided prediction — "this
    feature appears in the benchmark" — is satisfied by any sufficiently common
    word, which is how a description gets mistaken for a discriminator. The
    control ceiling is what makes it a test: the feature must be present in the
    benchmark group *and* absent from a set of works believed not to belong.
    `HitExpectation` cannot say this, because one threshold on one count cannot
    express a contrast between two groups.

    Shares of *works*, not of characters or occurrences. The groups contain
    works differing in length by more than two hundred fold, and a share of
    characters would let one long text carry a prediction on its own. An
    ascription claim is about works, so the threshold is too.

    The control group is named here rather than inferred, so a discriminator
    records which negative control it was actually tested against — a later
    reader should not have to assume it was the strict one.
    """

    feature: str = Field(min_length=1)
    benchmark_label: str = Field(min_length=1)
    control_label: str = Field(min_length=1)
    #: fraction of *measurable* benchmark works that must attest the feature
    min_benchmark_share: float = Field(ge=0.0, le=1.0)
    #: fraction of *measurable* control works that may attest it and no more
    max_control_share: float = Field(ge=0.0, le=1.0)


class QueryPayload(_Model):
    text: str = Field(min_length=1)

    #: Set only on the `tests` query of a conjecture: what its author said the
    #: query would return, recorded at proposal time, before it was run.
    #: Optional because most query nodes are retrievals rather than
    #: predictions — a prior-art search predicts nothing — and because every
    #: query node written before this field existed must still validate.
    #:
    #: A prediction is only a prediction if it is on the record first. These
    #: are written by `propose_conjecture` in the same call that creates the
    #: conjecture, and nothing can edit a payload afterwards.
    expectation: HitExpectation | None = None
    expected_hits: int | None = Field(default=None, ge=0)

    #: Set only on the `tests` query of a candidate discriminator, by
    #: `register_discriminator`, in the same call that creates the conjecture.
    #: Same contract as `expectation` above: on the record first, or it is not
    #: a prediction.
    discrimination: DiscriminationPrediction | None = None


class QuestionPayload(_Model):
    """What is being asked, and what would count as an answer.

    `answerable_by` is required for the same reason `propose_conjecture`
    requires a query that would settle a conjecture: a question nobody can say
    how to answer is not a research question, it is a mood. Stating it before
    looking is what stops the question from being quietly reshaped afterwards
    to fit whatever turned up.

    Deliberately thin otherwise. A question is a framing, not a finding, and
    every field it accumulates is a field that invites it to start asserting
    things.
    """

    text: str = Field(min_length=1)
    answerable_by: str = Field(min_length=1)


class DecisionPayload(_Model):
    subject_node_id: str = Field(min_length=1)
    verdict: Literal["accepted", "rejected", "reopened"]
    reason: str | None = None


class GroupOutcome(_Model):
    """What one labelled group of works showed, as a tally.

    Added 2026-09-06 alongside `DiscriminationPrediction`. A control test's
    result is four numbers, and until this existed they lived only inside the
    `detail` sentence — which meant every reader of the record, the ledger
    included, had to parse English to tabulate them. Prose is the right place
    for what a result *means* and the wrong place for what it *was*.

    Tallies of works, matching the shares a prediction is written in. No rates
    and no totals: a group whose members differ in length by two hundred fold
    has no meaningful pooled rate, and offering a field for one would invite
    somebody to fill it.
    """

    label: str = Field(min_length=1)
    works_measured: int = Field(ge=0)
    works_attesting: int = Field(ge=0)
    works_skipped_short: int = Field(ge=0)


class WorkOutcome(_Model):
    """What one work showed, as the row a table can print.

    Added 2026-09-06, for the same reason `GroupOutcome` was: a check that
    reached individual works — a feature applied to disputed texts, a Delta
    placement — reported them only inside its `detail` sentence, so a reader
    wanting the numbers had to parse English, and the Findings dossier could
    only ever render prose.

    Per work and never pooled, and `per_10k` is None rather than 0.0 below the
    character floor — the same disciplines `cohort.measure` enforces, carried
    into the record so a payload cannot state a rate the measurement itself
    refused to give.
    """

    work: str = Field(min_length=1)
    label: str | None = None
    chars: int = Field(ge=0)
    count: int = Field(ge=0)
    per_10k: float | None = None
    editions_attesting: int = Field(ge=0)
    editions_total: int = Field(ge=0)
    sufficient: bool = True
    note: str | None = None


class VerificationPayload(_Model):
    method: VerificationMethod
    result: VerificationResult
    assurance_level: AssuranceLevel
    detail: str = Field(min_length=1)
    limitations: str | None = None
    #: the hash chain for an EXACT_SPAN check: hash of the whole fetched
    #: source text, hash of the located excerpt, and the span it was found
    #: at. Additive; only EXACT_SPAN verifications populate these. The unit
    #: is reader-dependent, not always bytes: a `Source` that returns
    #: decoded `str` (the general case) yields character offsets from
    #: `str.find()`; a reader operating on raw bytes (e.g. CBETA's archive
    #: reader) yields true byte offsets. Named span_*, not byte_*, so the
    #: field name doesn't overclaim a precision the generic case can't give.
    source_hash: str | None = None
    excerpt_hash: str | None = None
    span_start: int | None = None
    span_end: int | None = None
    #: Populated only by checks that compared labelled groups of works — a
    #: discriminator's control test. Empty for everything else, and additive,
    #: so every verification written before this existed still validates.
    groups: tuple[GroupOutcome, ...] = ()
    #: Populated only by checks that reached individual works — a feature
    #: applied to disputed texts, a Delta placement. Additive alongside
    #: `groups`, which tallies; this is what was tallied.
    works: tuple[WorkOutcome, ...] = ()


PAYLOAD_BY_TYPE: dict[NodeType, type[_Model]] = {
    NodeType.WITNESS: WitnessPayload,
    NodeType.PASSAGE: PassagePayload,
    NodeType.CLAIM: ClaimPayload,
    NodeType.CONJECTURE: ConjecturePayload,
    NodeType.QUERY: QueryPayload,
    NodeType.QUESTION: QuestionPayload,
    NodeType.DECISION: DecisionPayload,
    NodeType.VERIFICATION: VerificationPayload,
}


# --- read-return shapes --------------------------------------------------

class Node(_Model):
    id: str
    type: NodeType
    status: NodeStatus = NodeStatus.PROPOSED
    payload: dict
    authorship: list[Authorship] = Field(default_factory=list)
    rejected_reason: str | None = None
    created_seq: int
    updated_seq: int

    def typed_payload(self) -> _Model:
        return PAYLOAD_BY_TYPE[self.type].model_validate(self.payload)


class Edge(_Model):
    id: str
    type: EdgeType
    src: str
    dst: str
    authorship: list[Authorship] = Field(default_factory=list)
    created_seq: int
    #: why this edge was drawn. Optional because most edge types carry their
    #: meaning in the type plus their endpoints; required in practice for
    #: `contradicts`, which `record_contradiction` will not write without one
    #: (see that tool for the argument).
    reason: str | None = None
    #: when the researcher withdrew this edge, and why. A retracted edge is
    #: never deleted — the log keeps it and so does this row, because a
    #: withdrawn relation and a relation that was never drawn are different
    #: facts about the record. It simply stops counting: `independent_support`
    #: ignores it, so retracting a wrong `parallel_of` restores the support it
    #: was suppressing.
    retracted_at: str | None = None
    retracted_reason: str | None = None


class IndependentSupport(_Model):
    """design doc §4, §11 — the counter-argument to consensus-seeking."""

    node_id: str
    attesting_count: int
    distinct_witnesses: int

    #: False the instant a descent/parallel relation links two supporting
    #: witnesses. **True is not a finding on its own** — see `vacuous`.
    independent: bool

    #: Nothing attests this node, so `independent` is True only because there
    #: is nothing that could make it False.
    #:
    #: Added 2026-09-02 after a seeded conjecture with no evidence at all
    #: displayed as "0 attesting, 0 distinct witnesses — independent", which
    #: reads as a clean bill of health for a node that has never been tested.
    #: `independent` is deliberately left alone: it is a flip flag, computed
    #: as "no discounting pair was found", and every caller since stage 1
    #: depends on that meaning. The vacuous case is reported beside it instead,
    #: so a front end says "not yet supported" rather than "independent".
    vacuous: bool = False

    non_independent_pairs: list[tuple[str, str]] = Field(default_factory=list)


class RebuildReport(_Model):
    ok: bool
    events_replayed: int
    nodes: int
    edges: int


class IntegrityReport(_Model):
    """An explicit, on-demand check (`Graph.verify_integrity()`), never an
    ambient hazard on every read — one tampered row must not turn every
    future `get_node()`/`citable()` call touching it into a crash. Symmetrical
    with `RebuildReport`: something you call to check, not something that
    silently gates reads."""

    checked: int
    mismatched: list[str] = Field(default_factory=list)
    unhashed: list[str] = Field(default_factory=list)


# --- events (design doc §5 principle 1) -------------------------------------
#
# "model_call" is a non-mutating audit marker, exactly like "refused" —
# _apply() treats it as a no-op. It's a dedicated event rather than metadata
# bolted onto every write it causes because the relationship is many-to-one:
# one API response can drive several tool calls, each producing several
# graph writes, and duplicating latency/cost across all of them would
# double-count it. Each write event instead carries model_call_id, pointing
# back at the model_call event's own seq.

EVENT_TYPES = {
    "retract_edge",
    "restore_edge",
    "propose", "attest", "accept", "reject", "reopen", "add_edge", "refused",
    "model_call", "verify", "register_agent",
    # A question is asked, never proposed: it does not climb the ladder, so it
    # cannot share the "propose" event, which is what puts a node at the
    # bottom rung. Its own event, the same way `verify` has one.
    "ask",
    # Run boundaries. Non-mutating like "model_call" and "refused": a run
    # starting is not a change to the graph. They exist because `run_id` alone
    # can say which events belong together but not what the run was *for* —
    # the roster, the declared scopes, the budget and what it actually spent
    # are the run's own record, and a projection cannot hold them because a
    # run is not graph content.
    "run_started", "run_finished",
}


class Event(_Model):
    seq: int
    event: str
    authored_by: str = Field(min_length=1)
    at: str = Field(default_factory=now)
    node_id: str | None = None
    edge_id: str | None = None
    node_type: NodeType | None = None
    edge_type: EdgeType | None = None
    detail: dict = Field(default_factory=dict)

    #: Which run wrote this, or None for a write made outside one — a
    #: researcher's `cohort accept`, a script, a test. Optional for the same
    #: reason as the observability envelope below: every event logged before
    #: this field existed replays identically.
    #:
    #: Stamped in one place, `EventLog.append`, rather than threaded through
    #: every write signature the way `model_call_id` is. The difference is
    #: real: a model call is a *cause* a particular write has to name, while a
    #: run is the session doing the writing, so the log knows it without being
    #: told once per call.
    run_id: str | None = None

    #: observability envelope — all optional so every event logged before
    #: this addition, and every event with nothing to report, replays
    #: identically. Set on "model_call" events; write events that a model
    #: call caused carry only model_call_id, pointing back at that event's seq.
    model_call_id: int | None = None
    model: str | None = None
    provider: str | None = None
    prompt_version: str | None = None
    latency_ms: int | None = None
    input_tokens: int | None = None
    output_tokens: int | None = None
    cost_usd: float | None = None

    @field_validator("event")
    @classmethod
    def _known_event(cls, v: str) -> str:
        if v not in EVENT_TYPES:
            raise ValueError(f"unknown event type: {v!r}")
        return v


class Refusal(_Model):
    """One refused write, read back out of the log.

    Refusals are part of the scholarly output (docs/design.md §15: "whose
    refusals are part of its scholarly output"), not error telemetry, so
    they get a real read model rather than being reassembled from raw
    `detail` dicts at every call site. `rule` is the exception class name —
    the rule the design claims, named in `errors.py` — which is what makes a
    refusal legible as "the system declined, and here is which commitment
    made it decline".

    Deliberately a projection of the log rather than a row in SQLite: a
    refusal never changed graph state, so storing it in the projection would
    put something in there that `nodes`/`edges` cannot account for.
    """

    seq: int
    at: str
    authored_by: str
    #: the write that was attempted: "propose", "attest", "accept", "add_edge", ...
    attempted: str
    #: the `errors.py` class name of the rule that refused it
    rule: str
    message: str
    node_id: str | None = None
    edge_id: str | None = None
    node_type: NodeType | None = None
    edge_type: EdgeType | None = None
    #: set when a model call caused the refused write, pointing at its event seq
    model_call_id: int | None = None


class RunRecord(_Model):
    """One agent run, read back out of the event log.

    The log is ground truth for runs as it is for everything else. `RunManager`
    holds the live one in memory, which is fine while it is running and useless
    afterwards: before this record existed, every run ever launched from the
    browser was gone when the server restarted.

    `finished_at` is None for a run that never wrote its closing event —
    killed, crashed, or still going. That is reported rather than repaired: a
    run that vanished mid-write is a fact about the session, and inventing an
    end for it would be the kind of tidying this project's log deliberately
    refuses.
    """

    run_id: str
    started_at: str
    #: the question this run was asked, when it was asked one. Optional
    #: because a run started from free-text instructions answers to nothing in
    #: the graph, and older logs have none.
    question_id: str | None = None
    finished_at: str | None = None
    #: as reported by the run itself when it closed: "finished", "stopped",
    #: "error". None while it is still open.
    state: str | None = None
    #: one entry per agent: id, role, model, declared scope and method
    agents: list[dict] = Field(default_factory=list)
    budget_usd: float | None = None
    spent_usd: float | None = None
    calls: int = 0
    #: every event this run wrote, refusals included
    events: int = 0
    refusals: int = 0
    error: str | None = None


class ModelCallSummary(_Model):
    calls: int
    total_input_tokens: int
    total_output_tokens: int
    total_latency_ms: int
    total_cost_usd: float


class RefusalStreak(_Model):
    """One agent refused repeatedly by one rule, with nothing else of its own
    in between.

    The signal the census exists to surface. A single `expression` refusal is
    usually a model slip; a *run* of them is the signature of a gap in the
    tool layer — the agent adapted, tried again, and was refused again,
    because there was no sanctioned way to say what it meant. Every such run
    in this project's history turned out to be exactly that.

    Consecutive **within one author's own sequence**, not within the whole
    log: two agents working concurrently interleave their refusals, and a
    definition that broke a streak whenever another agent was refused would
    make the signal vanish precisely when several agents are running.

    This is evidence for a human reading, not a verdict. `RefusalCategory`
    says which bucket to look in; a streak says where to look first. Neither
    concludes that a tool is missing — that is a judgement, and the point of
    counting is to put it in front of someone who can make it.
    """

    authored_by: str
    rule: str
    category: str
    #: how many consecutive refusals this run contains (always >= 2)
    count: int
    first_seq: int
    last_seq: int
    #: the writes attempted across the run, in order, deduplicated — an agent
    #: hitting one wall from several angles looks different from one repeating
    #: itself verbatim, and the distinction matters when reading it
    attempted: list[str] = Field(default_factory=list)
    #: the node ids it tried, deduplicated. Several distinct ids under one
    #: rule is the strongest tool-gap tell: the agent was *guessing*.
    node_ids: list[str] = Field(default_factory=list)


class RefusalCensus(_Model):
    """Arithmetic over a log's refused writes — counted, not asserted
    (design doc §13), the same habit as `ModelCallSummary`.

    A refusal is scholarly output (design doc §15), but a flat list of forty
    answers no question a researcher has. The question is *which* to read,
    and `by_category` is the answer: `evidence` refusals tell you about the
    texts, `standing` refusals tell you the discipline held, and `expression`
    refusals are the ones that may indict the tool layer rather than the
    model.

    Deliberately reports zero as a fact. A log with no refusals is a real
    result about a run, not an absence of news.
    """

    total: int
    #: every rule that fired, most frequent first
    by_rule: dict[str, int] = Field(default_factory=dict)
    #: every category, including any that fired zero times — a reader should
    #: see that `evidence` was empty, not have to notice its absence
    by_category: dict[str, int] = Field(default_factory=dict)
    by_author: dict[str, int] = Field(default_factory=dict)
    #: the write that was attempted: "attest", "add_edge", ...
    by_attempted: dict[str, int] = Field(default_factory=dict)
    streaks: list[RefusalStreak] = Field(default_factory=list)
    #: how many refusals fall in the bucket that may indict the tools, and how
    #: many of those sit inside a streak. Lifted out of `by_category` because
    #: it is the number the census is for.
    expression_count: int = 0
    streaked_count: int = 0
    first_at: str | None = None
    last_at: str | None = None
