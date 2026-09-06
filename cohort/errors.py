"""One exception per rule the design claims (design doc §0).

Pydantic owns *shape* validity (a malformed payload, a `basis` that isn't a
sentence) — those raise `pydantic.ValidationError` at construction, before a
write ever reaches the graph. This module owns *state* validity — rules that
depend on what's already in the graph, raised by `graph.py`'s write
boundary and nowhere else.
"""
from __future__ import annotations

from enum import StrEnum


class CohortError(Exception):
    """Base for every COHORT rule violation."""

    #: Set by `Graph._refuse` / `Graph.log_refusal` once the refusal has been
    #: appended to the event log, so a caller further out can tell an
    #: already-recorded refusal from one that would otherwise go unrecorded.
    logged_to_event_log: bool = False


# --- event log ---------------------------------------------------------------

class UnknownEventType(CohortError):
    """An event string outside the closed vocabulary."""


class NoEventLog(CohortError):
    """A write was attempted on a Graph with no attached EventLog."""


# --- rebuild (design doc §5 principle 1) --------------------------------------

class RebuildMismatch(CohortError):
    """The event log, replayed, does not match the live projection."""


# --- edges (design doc §6) ----------------------------------------------------

class EdgeDomainViolation(CohortError):
    """This edge type is not valid between these two node types."""


class EdgeEndpointMissing(CohortError):
    """An edge's src or dst node id does not exist."""


class EdgeSelfLoop(CohortError):
    """An edge's src and dst are the same node."""


# --- the falsifiability gate (design doc §7) ----------------------------------

class UnattestableClaim(CohortError):
    """A claim has no attests edge from an attested-or-better passage."""


class UnattestableConjecture(CohortError):
    """A conjecture has no tests edge; attests edges never satisfy this."""


class PassageNotLocated(CohortError):
    """A passage has no part_of edge to a witness."""


# --- the promotion ladder (design doc §8) -------------------------------------

class RungSkipped(CohortError):
    """A status transition was attempted out of order."""


class NotResearcher(CohortError):
    """Only the researcher may accept, reject, or reopen a node."""


class MissingRejectionReason(CohortError):
    """reject()/reopen() requires a stated reason."""


class PersistentRejection(CohortError):
    """A rejected node cannot be re-proposed; only the researcher may reopen it."""


class SelfAttestation(CohortError):
    """An agent tried to attest a claim or conjecture it authored.

    `attest` means "the mechanical preconditions hold", and the party with an
    interest in that answer is the worst party to give it. Both sibling
    projects separate the checker from the checked; this is that separation,
    enforced at the write boundary rather than asked for in a prompt.

    The researcher is exempt, deliberately. `accept` is already the human
    gate, the researcher is the accountable party, and requiring a second
    human would make single-researcher use impossible — which is not the
    problem this rule exists to solve.
    """


class ReviewerNotIndependent(CohortError):
    """The attesting agent shares a model family with an author of the node.

    A different agent id on the same model is not a different reader: it
    shares training priors and failure modes, so its confirmation is the
    author's own confirmation reported twice. That is the error
    `independent_support()` catches between witnesses, committed one layer up
    between readers — see `cohort.agents.roster`, which refuses the same
    overlap when a roster is assembled. This catches it at the write itself,
    where a roster check cannot reach: agents registered by separate runs
    still write to one graph.

    The family test is the same provider-prefix heuristic `roster` uses and
    inherits its limits. An agent whose model was never registered cannot be
    tested at all, and is allowed through: an unknown model is unknown, and
    refusing on it would state more than is known.
    """


# --- lookup --------------------------------------------------------------------

class EdgeNotFound(CohortError):
    """No such edge id. Same discipline as `NodeNotFound`: an id that does not
    resolve is refused rather than silently ignored."""


class PersistentRetraction(CohortError):
    """A retracted edge may not be redrawn by the next worker along.

    The mirror of `PersistentRejection` for edges, and for the same reason
    (design doc §8): without it, retracting a wrong `parallel_of` would last
    only until the next `link_parallels` run put it back, and the researcher's
    judgement would be quietly overwritten by a tool. Restoring one is a
    researcher action.
    """


class EdgeAlreadyRetracted(CohortError):
    """Retracting a retracted edge, or restoring one that is not retracted."""


class NodeNotFound(CohortError):
    """No node with this id exists."""


# --- the tool layer's own rules -----------------------------------------------
#
# Every one of these was a bare `ValueError` until a live multi-model run was
# censused for the first time (2026-09-02) and its single refusal came back
# `unclassified`. The census reads a refusal's *rule name*, so a tool raising
# `ValueError` told a researcher nothing: a claim the corpus would not support,
# a reviewer barred from the claim it was handed, and a mistyped node id all
# arrived under one label and in one bucket. These are rules the design claims,
# so they are named here with the rest of them.


class WrongNodeType(CohortError):
    """A tool was handed a node of a type it cannot act on."""


class UngroundedClaim(CohortError):
    """A claim's grounding query returned no hits, so it could never be cited.

    Refused on the evidence, not on form — which is why it is the one tool
    rule in the `EVIDENCE` bucket. The refusal names the alternative: an
    absence is settled by a retrieval, so it belongs in a conjecture.
    """


class SourceRefMissing(CohortError):
    """No passage under this witness carries a source_ref to re-fetch."""


class InvalidVerdict(CohortError):
    """A review verdict outside the closed set."""


# --- single writer (design doc §5 principle 7) --------------------------------

class SingleWriterViolation(CohortError):
    """Another process already holds the write lock on this graph."""


# --- what a refusal indicts (docs/design.md §15) -------------------------------
#
# Refusals are scholarly output, not error telemetry — but a flat list of 40
# refusals answers no question a researcher actually has. The question is
# *which* refusals to read, and that depends on what each one indicts.
#
# This taxonomy is the answer, and it lives here rather than in the reporting
# module so that adding a rule forces the decision. `tests/test_refusal_census.py`
# fails if a `CohortError` subclass has no category, the same discipline
# `tests/test_parity.py` applies to the two front ends.

class RefusalCategory(StrEnum):
    """What a refused write tells you to go and look at."""

    #: The corpus did not support the move. Well-formed, permitted, and
    #: refused on the evidence — reading these tells you about the *texts*.
    #: The falsifiability gate lives here.
    EVIDENCE = "evidence"

    #: Who was writing, or what state the node was in, forbade it. Reading
    #: these tells you the discipline held: an agent tried to sign its own
    #: work, or to skip a rung, or to relitigate something already settled.
    STANDING = "standing"

    #: The writer could not say what it meant — a reference that does not
    #: resolve, a malformed input, a relation outside the vocabulary.
    #:
    #: **This is the bucket worth reading.** A single one is usually a model
    #: slip. A *run* of them from one agent against one rule is the signature
    #: of a gap in the tool layer: the agent adapted, tried again, and was
    #: refused again, because there was no sanctioned way to express a
    #: legitimate intention. Every such run in this project's history so far
    #: turned out to be exactly that — a missing `propose_claim`, witness ids
    #: the tools never returned, a claim its own author could not advance —
    #: and each one was a tool fix, not a model failure.
    EXPRESSION = "expression"

    #: The system's own preconditions, not a judgement about research. These
    #: rarely reach the refusal log at all (most are raised before a write is
    #: attempted); they are categorised so the taxonomy is total.
    OPERATIONAL = "operational"

    #: A rule name this taxonomy does not know. Reported rather than dropped:
    #: a census that silently ignored what it could not classify would
    #: understate the very thing it exists to count.
    UNCLASSIFIED = "unclassified"


REFUSAL_CATEGORIES: dict[str, RefusalCategory] = {
    # the corpus did not support it
    UnattestableClaim.__name__: RefusalCategory.EVIDENCE,
    UnattestableConjecture.__name__: RefusalCategory.EVIDENCE,
    PassageNotLocated.__name__: RefusalCategory.EVIDENCE,
    # who was writing, or what state it was in
    NotResearcher.__name__: RefusalCategory.STANDING,
    SelfAttestation.__name__: RefusalCategory.STANDING,
    ReviewerNotIndependent.__name__: RefusalCategory.STANDING,
    RungSkipped.__name__: RefusalCategory.STANDING,
    PersistentRejection.__name__: RefusalCategory.STANDING,
    PersistentRetraction.__name__: RefusalCategory.STANDING,
    EdgeAlreadyRetracted.__name__: RefusalCategory.STANDING,
    # the writer could not say what it meant
    NodeNotFound.__name__: RefusalCategory.EXPRESSION,
    EdgeNotFound.__name__: RefusalCategory.EXPRESSION,
    EdgeEndpointMissing.__name__: RefusalCategory.EXPRESSION,
    EdgeSelfLoop.__name__: RefusalCategory.EXPRESSION,
    EdgeDomainViolation.__name__: RefusalCategory.EXPRESSION,
    MissingRejectionReason.__name__: RefusalCategory.EXPRESSION,
    WrongNodeType.__name__: RefusalCategory.EXPRESSION,
    InvalidVerdict.__name__: RefusalCategory.EXPRESSION,
    # the corpus did not support it, from the tool layer
    UngroundedClaim.__name__: RefusalCategory.EVIDENCE,
    # the system's own preconditions
    NoEventLog.__name__: RefusalCategory.OPERATIONAL,
    RebuildMismatch.__name__: RefusalCategory.OPERATIONAL,
    SingleWriterViolation.__name__: RefusalCategory.OPERATIONAL,
    UnknownEventType.__name__: RefusalCategory.OPERATIONAL,
    SourceRefMissing.__name__: RefusalCategory.OPERATIONAL,
    # Not a CohortError, but it reaches the log by class name like the rest:
    # `AttestationWorker._dispatch` logs whatever a tool raised, and pydantic
    # rejects a malformed tool argument before any rule in this module is
    # consulted. A model that cannot fill in a tool's arguments is failing to
    # express itself, so it belongs with the rest of that bucket.
    "ValidationError": RefusalCategory.EXPRESSION,
}


def refusal_category(rule: str) -> RefusalCategory:
    """The category of a rule name as recorded in the log.

    Takes a string, not a class: the log stores the rule's *name*, and a
    census reads logs written by versions of this code that may have had
    rules this one does not. An unknown name is `UNCLASSIFIED`, never an
    error — a census that crashed on an old log would be useless for exactly
    the historical reading it exists to support."""
    return REFUSAL_CATEGORIES.get(rule, RefusalCategory.UNCLASSIFIED)
