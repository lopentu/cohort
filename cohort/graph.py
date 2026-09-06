"""SQLite projection — the only writer (design doc §5 principles 4 and 7).

The graph is rebuildable from the event log; if the two disagree, the log is
right and the projection has a bug (principle 1). Every public write-boundary
method here follows the same shape: validate against current state, log the
event, then apply it — `_apply()` is the only place SQL runs, is reused
verbatim by `rebuild()`'s shadow graph, and never generates a random id or a
fresh timestamp, so replay is deterministic.
"""
from __future__ import annotations

import fcntl
import hashlib
import itertools
import json
import sqlite3
import uuid
from collections.abc import Iterable
from pathlib import Path
from typing import NoReturn

from .errors import (
    EdgeAlreadyRetracted,
    EdgeNotFound,
    PersistentRetraction,
    EdgeDomainViolation,
    EdgeEndpointMissing,
    EdgeSelfLoop,
    CohortError,
    MissingRejectionReason,
    NodeNotFound,
    NoEventLog,
    NotResearcher,
    PassageNotLocated,
    PersistentRejection,
    RebuildMismatch,
    ReviewerNotIndependent,
    RungSkipped,
    SelfAttestation,
    SingleWriterViolation,
    UnattestableClaim,
    UnattestableConjecture,
)
from .eventlog import EventLog, read_events
from .families import model_family
from .migrations import SCHEMA_VERSION, MigrationError, apply_migrations
from .schemas import (
    RESEARCHER,
    AgentProfile,
    AgentReport,
    AssuranceLevel,
    Authorship,
    ClaimPayload,
    ConjecturePayload,
    DecisionPayload,
    Edge,
    EdgeType,
    Event,
    IndependentSupport,
    IntegrityReport,
    Node,
    NodeStatus,
    NodeType,
    PassagePayload,
    QueryPayload,
    QuestionPayload,
    RebuildReport,
    VerificationMethod,
    VerificationPayload,
    VerificationResult,
    WitnessPayload,
)

#: design doc §6's edge table. "any" = any (type, type) pair is legal;
#: "same_type" = src.type == dst.type, any type.
EDGE_DOMAINS: dict[EdgeType, set[tuple[NodeType, NodeType]] | str] = {
    EdgeType.ATTESTS: {
        (NodeType.PASSAGE, NodeType.CLAIM),
        (NodeType.PASSAGE, NodeType.CONJECTURE),
    },
    EdgeType.CONTRADICTS: "any",
    EdgeType.PARALLEL_OF: {
        (NodeType.PASSAGE, NodeType.PASSAGE),
        (NodeType.WITNESS, NodeType.WITNESS),
    },
    EdgeType.DESCENDS_FROM: {
        (NodeType.PASSAGE, NodeType.PASSAGE),
        (NodeType.WITNESS, NodeType.WITNESS),
    },
    EdgeType.QUOTES: {(NodeType.PASSAGE, NodeType.PASSAGE)},
    EdgeType.TESTS: {(NodeType.QUERY, NodeType.CONJECTURE)},
    EdgeType.ADDRESSES: {
        (NodeType.CLAIM, NodeType.QUESTION),
        (NodeType.CONJECTURE, NodeType.QUESTION),
    },
    EdgeType.SUPERSEDES: "same_type",
    EdgeType.PART_OF: {(NodeType.PASSAGE, NodeType.WITNESS)},
    EdgeType.VERIFIES: {
        (NodeType.VERIFICATION, NodeType.CLAIM),
        (NodeType.VERIFICATION, NodeType.CONJECTURE),
        (NodeType.VERIFICATION, NodeType.PASSAGE),
        (NodeType.VERIFICATION, NodeType.WITNESS),
    },
    #: widened from conjecture-only when `propose_claim` arrived: a claim's
    #: grounding search is the same kind of fact about the same kind of node
    #: — a retrieval that was actually run before something was proposed —
    #: so it belongs on this edge rather than on a second, near-identical
    #: type. The vocabulary stays closed; only this type's domain grew.
    #: `tests` is deliberately *not* widened alongside it: a `tests` edge is
    #: what makes a conjecture attestable, and letting one point at a claim
    #: would offer a second route past the falsifiability gate.
    EdgeType.SEARCHED_FOR: {
        (NodeType.QUERY, NodeType.CONJECTURE),
        (NodeType.QUERY, NodeType.CLAIM),
    },
}

#: written as two rows (both directions) from one logged event, so a
#: contradiction or a shared-transmission relation is never missed just
#: because a query only checked one direction (design doc §11's "not
#: symmetric on read" weak point, fixed by construction here).
SYMMETRIC_EDGE_TYPES = {EdgeType.CONTRADICTS, EdgeType.PARALLEL_OF}

#: AssuranceLevel is defined low-to-high; StrEnum iteration order is
#: definition order, so this ranks each rung without hardcoding numbers
#: that could drift from the enum.
_ASSURANCE_RANK = {level: i for i, level in enumerate(AssuranceLevel)}

class Graph:
    def __init__(
        self, db_path: str | Path, event_log: EventLog | None = None, *,
        read_only: bool = False,
    ) -> None:
        self.db_path = db_path
        self.event_log = None if read_only else event_log
        self.read_only = read_only
        self._lock_file = None
        self._in_memory = str(db_path) == ":memory:"
        if read_only:
            self._open_read_only(Path(db_path))
            return
        if not self._in_memory:
            self._acquire_lock(Path(db_path))
        self.conn = sqlite3.connect(str(db_path))
        self.conn.row_factory = sqlite3.Row
        self.conn.execute("PRAGMA journal_mode=WAL")
        apply_migrations(self.conn)

    def _open_read_only(self, db_path: Path) -> None:
        """Attach to an existing projection without taking the writer lock.

        Single-writer discipline is enforced by an exclusive `flock` in
        `_acquire_lock`, so a second process — a UI, a report, an inspector —
        cannot open the graph at all while an agent run holds it. That is
        correct for writers and useless for readers, and the answer is not to
        relax the lock: WAL already lets any number of readers run
        concurrently with the one writer, safely, so a reader simply should
        not be asking for the lock in the first place.

        Three things make this genuinely read-only rather than nominally so:
        SQLite is opened `mode=ro`, so the kernel refuses a write; migrations
        are skipped, since applying one would itself be a write; and
        `event_log` is forced to None, which makes every mutating method fail
        through the existing `event_log_or_raise()` guard rather than through
        a new parallel check that could drift from it.

        Because migrations are skipped, a projection older than this code is
        refused outright — reading it would silently misinterpret columns a
        migration was supposed to add."""
        if self._in_memory:
            raise ValueError("an in-memory Graph cannot be opened read-only: it has no file to read")
        if not db_path.is_file():
            raise FileNotFoundError(f"no graph projection at {db_path}")
        self.conn = sqlite3.connect(f"file:{db_path}?mode=ro", uri=True)
        self.conn.row_factory = sqlite3.Row
        actual = self.conn.execute("PRAGMA user_version").fetchone()[0]
        if actual != SCHEMA_VERSION:
            raise MigrationError(
                f"projection at {db_path} is at schema version {actual}, but this "
                f"code expects {SCHEMA_VERSION}; open it for writing once to migrate"
            )

    @classmethod
    def open(cls, db_path: str | Path, log_path: str | Path) -> "Graph":
        db_path = Path(db_path)
        log_path = Path(log_path)
        fresh_db = not db_path.exists()
        event_log = EventLog(log_path)
        graph = cls(db_path, event_log=event_log)
        if fresh_db and len(event_log) > 0:
            for ev in read_events(log_path):
                graph._apply(ev)
        return graph

    @classmethod
    def open_read_only(cls, db_path: str | Path) -> "Graph":
        """A reader's handle on an existing projection: no writer lock, no
        event log, no migrations. Safe to open while an agent run holds the
        write lock — see `_open_read_only`."""
        return cls(db_path, read_only=True)

    # --- lifecycle -------------------------------------------------------

    def _acquire_lock(self, db_path: Path) -> None:
        db_path.parent.mkdir(parents=True, exist_ok=True)
        lock_path = db_path.with_suffix(db_path.suffix + ".lock")
        f = open(lock_path, "w")
        try:
            fcntl.flock(f.fileno(), fcntl.LOCK_EX | fcntl.LOCK_NB)
        except BlockingIOError:
            f.close()
            raise SingleWriterViolation(
                f"another process already holds the write lock on {db_path}"
            )
        self._lock_file = f

    def close(self) -> None:
        if self.conn is not None:
            self.conn.close()
        if self._lock_file is not None:
            fcntl.flock(self._lock_file.fileno(), fcntl.LOCK_UN)
            self._lock_file.close()
            self._lock_file = None

    def __enter__(self) -> "Graph":
        return self

    def __exit__(self, *exc) -> None:
        self.close()

    def event_log_or_raise(self) -> EventLog:
        if self.event_log is None:
            raise NoEventLog("this Graph has no attached EventLog; writes are disabled")
        return self.event_log

    def log_model_call(
        self, *, authored_by: str, model: str, provider: str = "openrouter",
        prompt_version: str | None = None, latency_ms: int | None = None,
        input_tokens: int | None = None, output_tokens: int | None = None,
        cost_usd: float | None = None,
    ) -> Event:
        """A non-mutating audit marker (design doc §5 principle 1: every
        mutation is logged — this logs an API call, which is not one, hence
        `_apply()` treats it as a no-op, same as "refused"). Returns the
        Event so its `seq` can be threaded through as `model_call_id` on the
        write(s) it caused."""
        ev = self.event_log_or_raise().append(
            "model_call", authored_by=authored_by, model=model, provider=provider,
            prompt_version=prompt_version, latency_ms=latency_ms,
            input_tokens=input_tokens, output_tokens=output_tokens, cost_usd=cost_usd,
        )
        self._apply(ev)
        return ev

    def during_run(self, run_id: str):
        """Stamp `run_id` on every event written inside this block.

        Delegates to the log because that is where events are made. A caller
        holding a `Graph` should not have to reach past it to say which run is
        writing."""
        return self.event_log_or_raise().during_run(run_id)

    def log_run_started(
        self, run_id: str, *, authored_by: str, agents: list[dict],
        budget_usd: float | None = None, question_id: str | None = None,
    ) -> Event:
        """A non-mutating marker opening a run, like `log_model_call`.

        `run_id` alone can say which events belong together but not what the
        run was *for*. The roster — each agent's id, role, model and declared
        scope — is the thing a reader needs to interpret the writes that
        follow, and declared scope per agent is the condition under which this
        design permits more than one agent at all.

        `question_id` is what the run was *asked*, as opposed to what its
        agents were told. The two differ — the instructions are templated from
        the question and carry a stance — and only the question is stable
        enough to group runs by, which is what makes a second run on the same
        question legible as another pass at it rather than an unrelated run."""
        detail: dict = {"run_id": run_id, "agents": agents, "budget_usd": budget_usd}
        if question_id:
            detail["question_id"] = question_id
        ev = self.event_log_or_raise().append(
            "run_started", authored_by=authored_by, detail=detail,
        )
        self._apply(ev)
        return ev

    def log_run_finished(
        self, run_id: str, *, authored_by: str, state: str,
        spent_usd: float | None = None, calls: int = 0, error: str | None = None,
    ) -> Event:
        """The closing marker. Absent for a run that was killed mid-write,
        which `read_runs` reports as still open rather than repairing."""
        ev = self.event_log_or_raise().append(
            "run_finished", authored_by=authored_by,
            detail={"run_id": run_id, "state": state, "spent_usd": spent_usd,
                    "calls": calls, "error": error},
        )
        self._apply(ev)
        return ev

    # --- proposal ----------------------------------------------------------

    def propose_witness(
        self, payload: WitnessPayload, *, authored_by: str, model_call_id: int | None = None
    ) -> str:
        return self._propose_source_derived(
            NodeType.WITNESS, payload, authored_by=authored_by, model_call_id=model_call_id
        )

    def propose_passage(
        self, payload: PassagePayload, *, witness_id: str, authored_by: str,
        model_call_id: int | None = None,
    ) -> str:
        if self._get_row(witness_id) is None:
            self._refuse(
                "propose", authored_by,
                EdgeEndpointMissing(f"witness {witness_id} does not exist"),
                node_type=NodeType.PASSAGE,
            )
        node_id = f"{NodeType.PASSAGE}:{payload.canonical_ref}"
        existing = self._get_row(node_id)
        if existing is not None and existing["status"] == NodeStatus.REJECTED:
            self._refuse(
                "propose", authored_by, PersistentRejection(
                    f"{node_id} was rejected by the researcher and proposing "
                    "it again would quietly undo that. Reopen it with a reason "
                    "if it deserves another look — the rejection stays on the "
                    "record either way."
                ),
                node_id=node_id, node_type=NodeType.PASSAGE,
            )
        edge_id = None if existing is not None else f"edge:{uuid.uuid4().hex}"
        ev = self.event_log_or_raise().append(
            "propose", authored_by=authored_by, node_id=node_id, node_type=NodeType.PASSAGE,
            edge_id=edge_id, edge_type=(EdgeType.PART_OF if edge_id else None),
            model_call_id=model_call_id,
            detail={
                "payload": payload.model_dump(mode="json"),
                "witness_id": witness_id,
                "converge": existing is not None,
            },
        )
        self._apply(ev)
        return node_id

    def propose_claim(
        self, payload: ClaimPayload, *, authored_by: str, model_call_id: int | None = None
    ) -> str:
        return self._propose_agent_authored(
            NodeType.CLAIM, payload, authored_by=authored_by, model_call_id=model_call_id
        )

    def propose_conjecture(
        self, payload: ConjecturePayload, *, authored_by: str, model_call_id: int | None = None
    ) -> str:
        return self._propose_agent_authored(
            NodeType.CONJECTURE, payload, authored_by=authored_by, model_call_id=model_call_id
        )

    def propose_query(
        self, payload: QueryPayload, *, authored_by: str, model_call_id: int | None = None
    ) -> str:
        return self._propose_agent_authored(
            NodeType.QUERY, payload, authored_by=authored_by, model_call_id=model_call_id
        )

    def _propose_source_derived(
        self, node_type: NodeType, payload, *, authored_by: str, model_call_id: int | None = None
    ) -> str:
        node_id = f"{node_type}:{payload.canonical_ref}"
        existing = self._get_row(node_id)
        if existing is not None and existing["status"] == NodeStatus.REJECTED:
            self._refuse(
                "propose", authored_by, PersistentRejection(
                    f"{node_id} was rejected by the researcher and proposing "
                    "it again would quietly undo that. Reopen it with a reason "
                    "if it deserves another look — the rejection stays on the "
                    "record either way."
                ),
                node_id=node_id, node_type=node_type,
            )
        ev = self.event_log_or_raise().append(
            "propose", authored_by=authored_by, node_id=node_id, node_type=node_type,
            model_call_id=model_call_id,
            detail={
                "payload": payload.model_dump(mode="json"),
                "converge": existing is not None,
            },
        )
        self._apply(ev)
        return node_id

    def _propose_agent_authored(
        self, node_type: NodeType, payload, *, authored_by: str, model_call_id: int | None = None
    ) -> str:
        node_id = f"{node_type}:{uuid.uuid4().hex}"
        ev = self.event_log_or_raise().append(
            "propose", authored_by=authored_by, node_id=node_id, node_type=node_type,
            model_call_id=model_call_id,
            detail={"payload": payload.model_dump(mode="json"), "converge": False},
        )
        self._apply(ev)
        return node_id

    # --- the ladder (design doc §8) -----------------------------------------

    def attest(
        self, node_id: str, *, authored_by: str, model_call_id: int | None = None
    ) -> None:
        node = self._require_node(node_id)
        if node.status != NodeStatus.PROPOSED:
            self._refuse(
                "attest", authored_by,
                RungSkipped(f"{node_id} is {node.status}, not proposed"),
                node_id=node_id, node_type=node.type,
            )
        conflict = self._reviewer_conflict(node, authored_by)
        if conflict is not None:
            self._refuse(
                "attest", authored_by, conflict, node_id=node_id, node_type=node.type,
            )
        if node.type == NodeType.CLAIM:
            if not self._has_qualifying_attestation(node_id):
                self._refuse(
                    "attest", authored_by, UnattestableClaim(
                        f"{node_id} has no attesting passage that is itself "
                        "attested or better, so the mechanical check has "
                        "nothing to run against. Gather evidence for it first "
                        "— a claim is attestable once a located passage cites it."
                    ),
                    node_id=node_id, node_type=node.type,
                )
        elif node.type == NodeType.CONJECTURE:
            if not self._has_inbound_edge(node_id, EdgeType.TESTS):
                self._refuse(
                    "attest", authored_by, UnattestableConjecture(
                        f"{node_id} has no `tests` query, so nothing could "
                        "refute it. Attesting passages do not satisfy this: a "
                        "conjecture exceeds its evidence by design, and what "
                        "makes it attestable is naming the retrieval that "
                        "would settle it."
                    ),
                    node_id=node_id, node_type=node.type,
                )
        elif node.type == NodeType.PASSAGE:
            if not self._has_outbound_edge(node_id, EdgeType.PART_OF):
                self._refuse(
                    "attest", authored_by, PassageNotLocated(
                        f"{node_id} has no `part_of` edge to a witness, so "
                        "where it sits in the corpus is unrecorded and its "
                        "reference cannot be resolved."
                    ),
                    node_id=node_id, node_type=node.type,
                )
        ev = self.event_log_or_raise().append(
            "attest", authored_by=authored_by, node_id=node_id, node_type=node.type,
            model_call_id=model_call_id, detail={},
        )
        self._apply(ev)

    def accept(
        self, node_id: str, *, authored_by: str, reason: str | None = None,
        model_call_id: int | None = None,
    ) -> str:
        self._require_researcher(authored_by, action="accept", node_id=node_id)
        node = self._require_node(node_id)
        if node.status != NodeStatus.ATTESTED:
            self._refuse(
                "accept", authored_by,
                RungSkipped(f"{node_id} is {node.status}, not attested"),
                node_id=node_id, node_type=node.type,
            )
        return self._apply_verdict_write(node, "accept", authored_by, reason, model_call_id)

    def reject(
        self, node_id: str, *, authored_by: str, reason: str, model_call_id: int | None = None
    ) -> str:
        self._require_researcher(authored_by, action="reject", node_id=node_id)
        if not reason or not reason.strip():
            self._refuse(
                "reject", authored_by, MissingRejectionReason(
                    f"rejecting {node_id} needs a stated reason. What was "
                    "thrown out and why is part of the record; a rejection "
                    "with no reason reads later as an unexplained gap."
                ), node_id=node_id,
            )
        node = self._require_node(node_id)
        if node.status not in (NodeStatus.PROPOSED, NodeStatus.ATTESTED):
            self._refuse(
                "reject", authored_by,
                RungSkipped(f"{node_id} is {node.status}, cannot reject"),
                node_id=node_id, node_type=node.type,
            )
        return self._apply_verdict_write(node, "reject", authored_by, reason, model_call_id)

    def reopen(
        self, node_id: str, *, authored_by: str, reason: str, model_call_id: int | None = None
    ) -> str:
        self._require_researcher(authored_by, action="reopen", node_id=node_id)
        if not reason or not reason.strip():
            self._refuse(
                "reopen", authored_by, MissingRejectionReason(
                    f"reopening {node_id} needs a stated reason, for the same "
                    "reason rejecting it did: the record has to say what "
                    "changed."
                ), node_id=node_id,
            )
        node = self._require_node(node_id)
        if node.status != NodeStatus.REJECTED:
            self._refuse(
                "reopen", authored_by,
                RungSkipped(f"{node_id} is {node.status}, not rejected"),
                node_id=node_id, node_type=node.type,
            )
        return self._apply_verdict_write(node, "reopen", authored_by, reason, model_call_id)

    def _apply_verdict_write(
        self, node: Node, event: str, authored_by: str, reason: str | None,
        model_call_id: int | None = None,
    ) -> str:
        decision_id = f"{NodeType.DECISION}:{uuid.uuid4().hex}"
        clean_reason = reason.strip() if reason and reason.strip() else None
        ev = self.event_log_or_raise().append(
            event, authored_by=authored_by, node_id=node.id, node_type=node.type,
            model_call_id=model_call_id,
            detail={"decision_node_id": decision_id, "reason": clean_reason},
        )
        self._apply(ev)
        return decision_id

    # --- edges (design doc §6) ----------------------------------------------

    def add_edge(
        self, edge_type: EdgeType, src: str, dst: str, *, authored_by: str,
        model_call_id: int | None = None, reason: str | None = None,
    ) -> str:
        if src == dst:
            self._refuse(
                "add_edge", authored_by, EdgeSelfLoop(f"{src} -> {dst}"), edge_type=edge_type,
            )
        src_row = self._get_row(src)
        dst_row = self._get_row(dst)
        if src_row is None:
            self._refuse(
                "add_edge", authored_by,
                EdgeEndpointMissing(f"src {src} does not exist"), edge_type=edge_type,
            )
        if dst_row is None:
            self._refuse(
                "add_edge", authored_by,
                EdgeEndpointMissing(f"dst {dst} does not exist"), edge_type=edge_type,
            )
        domain = EDGE_DOMAINS[edge_type]
        if domain != "any":
            if domain == "same_type":
                ok = src_row["type"] == dst_row["type"]
            else:
                ok = (src_row["type"], dst_row["type"]) in domain
            if not ok:
                self._refuse(
                    "add_edge", authored_by,
                    EdgeDomainViolation(
                        f"{edge_type} not valid from {src_row['type']} to {dst_row['type']}"
                    ),
                    edge_type=edge_type,
                )
        existing = self.conn.execute(
            "SELECT id, retracted_at FROM edges WHERE type=? AND src=? AND dst=?",
            (edge_type, src, dst),
        ).fetchone()
        if existing is not None and existing["retracted_at"] is not None:
            # The mirror of PersistentRejection. Without this, retracting a
            # wrong `parallel_of` would last only until the next link_parallels
            # run redrew it, and a researcher judgement would be quietly
            # overwritten by a tool.
            self._refuse(
                "add_edge", authored_by,
                PersistentRetraction(
                    f"{edge_type} {src} -> {dst} was retracted by the researcher and "
                    f"may not be redrawn; restoring it is a researcher action"
                ),
                edge_id=existing["id"], edge_type=edge_type,
            )
        edge_id = existing["id"] if existing else f"edge:{uuid.uuid4().hex}"
        ev = self.event_log_or_raise().append(
            "add_edge", authored_by=authored_by, edge_id=edge_id, edge_type=edge_type,
            model_call_id=model_call_id,
            detail={
                "src": src, "dst": dst, "converge": existing is not None,
                **({"reason": reason} if reason else {}),
            },
        )
        self._apply(ev)
        return edge_id

    def retract_edge(self, edge_id: str, *, authored_by: str, reason: str) -> None:
        """Withdraw an edge, with a stated reason. A researcher action.

        Edges have no promotion ladder, which used to mean a wrong one was
        permanent — and the edges that carry an argument (`parallel_of`,
        `descends_from`, `contradicts`) are exactly the ones that change
        conclusions. A mistaken `parallel_of` between two witnesses does not
        merely add noise: it *suppresses* independent support that genuinely
        exists, silently, in the direction of the system's own thesis.

        Retraction is the edge-equivalent of rejecting a node, so it follows
        the same rules (design doc §8): only the researcher may do it, a reason
        is required, and it persists — `add_edge` refuses to redraw a retracted
        edge. Nothing is deleted; the row and the log both keep it, and
        `edges(include_retracted=True)` still returns it.
        """
        self._require_researcher(authored_by, action="retract_edge", edge_id=edge_id)
        if not reason or not reason.strip():
            self._refuse(
                "retract_edge", authored_by,
                MissingRejectionReason(f"retracting {edge_id} requires a stated reason"),
                edge_id=edge_id,
            )
        edge = self._require_edge(edge_id)
        if edge["retracted_at"] is not None:
            self._refuse(
                "retract_edge", authored_by,
                EdgeAlreadyRetracted(f"{edge_id} is already retracted"),
                edge_id=edge_id, edge_type=edge["type"],
            )
        ev = self.event_log_or_raise().append(
            "retract_edge", authored_by=authored_by, edge_id=edge_id,
            edge_type=edge["type"], detail={"reason": reason},
        )
        self._apply(ev)

    def restore_edge(self, edge_id: str, *, authored_by: str, reason: str) -> None:
        """Undo a retraction. A researcher action, like `reopen` for nodes.

        Without this, retraction would create a second permanent state and
        replace one irreversible mistake with another."""
        self._require_researcher(authored_by, action="restore_edge", edge_id=edge_id)
        if not reason or not reason.strip():
            self._refuse(
                "restore_edge", authored_by,
                MissingRejectionReason(f"restoring {edge_id} requires a stated reason"),
                edge_id=edge_id,
            )
        edge = self._require_edge(edge_id)
        if edge["retracted_at"] is None:
            self._refuse(
                "restore_edge", authored_by,
                EdgeAlreadyRetracted(f"{edge_id} is not retracted"),
                edge_id=edge_id, edge_type=edge["type"],
            )
        ev = self.event_log_or_raise().append(
            "restore_edge", authored_by=authored_by, edge_id=edge_id,
            edge_type=edge["type"], detail={"reason": reason},
        )
        self._apply(ev)

    def verify(
        self, subject_node_id: str, *, method: VerificationMethod, result: VerificationResult,
        assurance_level: AssuranceLevel, detail: str, limitations: str | None = None,
        source_hash: str | None = None, excerpt_hash: str | None = None,
        span_start: int | None = None, span_end: int | None = None,
        groups: tuple = (), authored_by: str, model_call_id: int | None = None,
    ) -> str:
        """One verification attempt against a claim/conjecture/passage/
        witness — a record of a judgement, not evidential content, same
        footing as `decision` (design doc §5 principle 2). Born directly at
        status=accepted, like `decision`: subjecting a verification record
        to its own promotion ladder would be a regress. `HUMAN_REVIEW`
        requires the researcher, same pattern as `accept()`. The four
        hash-chain fields are optional and only meaningful for EXACT_SPAN
        checks (`cohort/tools/verify_exact_span.py`)."""
        subject = self._require_node(subject_node_id)
        if subject.type not in (NodeType.CLAIM, NodeType.CONJECTURE, NodeType.PASSAGE, NodeType.WITNESS):
            self._refuse(
                "verify", authored_by,
                EdgeDomainViolation(f"cannot verify a {subject.type}"),
                node_id=subject_node_id, node_type=subject.type,
            )
        if method == VerificationMethod.HUMAN_REVIEW:
            self._require_researcher(authored_by, action="verify", node_id=subject_node_id)
        payload = VerificationPayload(
            method=method, result=result, assurance_level=assurance_level,
            detail=detail, limitations=limitations, source_hash=source_hash,
            excerpt_hash=excerpt_hash, span_start=span_start, span_end=span_end,
            groups=groups,
        )
        verification_id = f"{NodeType.VERIFICATION}:{uuid.uuid4().hex}"
        edge_id = f"edge:{uuid.uuid4().hex}"
        ev = self.event_log_or_raise().append(
            "verify", authored_by=authored_by, node_id=verification_id,
            node_type=NodeType.VERIFICATION, edge_id=edge_id, edge_type=EdgeType.VERIFIES,
            model_call_id=model_call_id,
            detail={"payload": payload.model_dump(mode="json"), "subject_node_id": subject_node_id},
        )
        self._apply(ev)
        return verification_id

    def ask_question(
        self, payload: QuestionPayload, *, authored_by: str,
        model_call_id: int | None = None,
    ) -> str:
        """Record what an inquiry is asking.

        **The researcher asks.** Agents propose claims and conjectures; setting
        the agenda is the supervision, and an agent that could ask its own
        question and then answer it would be doing unsupervised research with a
        paper trail. Same reasoning as `accept`/`reject`/`reopen` (principle 6),
        and easy to relax later if a reviewer's "someone should ask X" turns out
        to be worth recording as a question rather than as prose.

        Born `accepted`, bypassing the ladder like `decision` and
        `verification`: there is no mechanical check that could promote a
        question and no rung for it to climb. **`accepted` here means asked,
        not answered** — nothing about this status says the question has been
        settled, and `citable()` excludes questions so nothing can cite one as
        a premise.
        """
        if authored_by != RESEARCHER:
            self._refuse(
                "ask", authored_by,
                NotResearcher(
                    f"{authored_by} may not ask a research question; only the "
                    "researcher sets the agenda. Propose a claim or a "
                    "conjecture instead"
                ),
                node_type=NodeType.QUESTION,
            )
        question_id = f"{NodeType.QUESTION}:{uuid.uuid4().hex}"
        ev = self.event_log_or_raise().append(
            "ask", authored_by=authored_by, node_id=question_id,
            node_type=NodeType.QUESTION, model_call_id=model_call_id,
            detail={"payload": payload.model_dump(mode="json")},
        )
        self._apply(ev)
        return question_id

    def register_agent(
        self, profile: AgentProfile, *, authored_by: str, model_call_id: int | None = None
    ) -> str:
        """Declare an agent's identity and (optionally) its corpus/method
        scope — a sidecar record, not a graph node (see `AgentProfile`'s
        docstring). Idempotent: re-registering the same id updates the row
        rather than erroring, so a worker can re-declare its scope without
        first checking whether it already has."""
        ev = self.event_log_or_raise().append(
            "register_agent", authored_by=authored_by, model_call_id=model_call_id,
            detail={"payload": profile.model_dump(mode="json")},
        )
        self._apply(ev)
        return profile.id

    def edges(
        self, *, edge_type: EdgeType | None = None, src: str | None = None,
        dst: str | None = None, include_retracted: bool = False,
    ) -> list[Edge]:
        """Relations that currently hold.

        Retracted edges are excluded by default because most callers are asking
        what the graph asserts, and a withdrawn relation asserts nothing. Pass
        `include_retracted=True` to see the record instead of the state — the
        UI does, so a retraction is visible as a withdrawal rather than as an
        absence."""
        query = "SELECT * FROM edges WHERE 1=1"
        params: list = []
        if not include_retracted:
            query += " AND retracted_at IS NULL"
        if edge_type is not None:
            query += " AND type=?"
            params.append(edge_type)
        if src is not None:
            query += " AND src=?"
            params.append(src)
        if dst is not None:
            query += " AND dst=?"
            params.append(dst)
        rows = self.conn.execute(query, params).fetchall()
        return [self._row_to_edge(r) for r in rows]

    # --- read-only surface ---------------------------------------------------

    def get_node(self, node_id: str) -> Node:
        return self._require_node(node_id)

    def citable(self) -> list[Node]:
        """Only accepted, non-decision, non-verification, non-question nodes —
        the only things usable as a premise or citable in output (design doc
        §5 principle 6). Decision and verification nodes are always
        status=accepted (they bypass the ladder) but are audit bookkeeping,
        not evidence. A question is accepted the moment it is asked and is
        never evidence either: output cites what answers a question, never the
        question."""
        rows = self.conn.execute(
            "SELECT * FROM nodes WHERE status=? AND type NOT IN (?, ?, ?)",
            (NodeStatus.ACCEPTED, NodeType.DECISION, NodeType.VERIFICATION,
             NodeType.QUESTION),
        ).fetchall()
        return [self._row_to_node(r) for r in rows]

    def nodes(
        self, *, node_type: NodeType | None = None, limit: int | None = None,
        offset: int = 0,
    ) -> list[Node]:
        """Nodes in creation order, optionally of one type.

        The general listing `citable()`/`rejected()` are the opinionated views
        of: those answer "what may be cited" and "what was refused", while
        this answers "what is in the graph", which a viewer needs and neither
        of those provides. Ordering is `created_seq` rather than insertion
        order in the table, so a paged read is stable against the projection
        being rewritten by a rebuild."""
        sql = "SELECT * FROM nodes"
        params: list = []
        if node_type is not None:
            sql += " WHERE type = ?"
            params.append(node_type)
        sql += " ORDER BY created_seq"
        if limit is not None:
            sql += " LIMIT ? OFFSET ?"
            params.extend([int(limit), int(offset)])
        return [self._row_to_node(r) for r in self.conn.execute(sql, params).fetchall()]

    def verifications(self, node_id: str) -> list[Node]:
        """Every verification attempt recorded against a node, oldest first."""
        rows = self.conn.execute(
            "SELECT n.* FROM edges e JOIN nodes n ON n.id = e.src "
            "WHERE e.type=? AND e.dst=? ORDER BY n.created_seq",
            (EdgeType.VERIFIES, node_id),
        ).fetchall()
        return [self._row_to_node(r) for r in rows]

    def assurance_for(self, node_id: str) -> AssuranceLevel:
        """The best assurance a node currently holds: the **latest** result
        from each verification method, then the highest passing level among
        those. A0_UNCHECKED if nothing has passed. A computed read, never a
        second mutable field on the subject node — see `AssuranceLevel`'s
        docstring.

        **Latest-per-method, not the historical maximum.** This took the
        maximum over every passing verification until 2026-09-02, which meant
        a later failure could never lower a node's standing: a passage
        verified at A2, whose excerpt then *moved in the source*, still read
        `A2_EXACT_SPAN_MATCHED` — `verify_exact_span` detected the move,
        recorded the FAIL, and the stale PASS outranked it forever. That is
        the drift `AssuranceLevel`'s own docstring says computing this rather
        than storing it was supposed to prevent; it just arrived through stale
        history instead of a stale field. The same shape as the failure
        `verify_exact_span` guards against internally — "passing review while
        proving nothing".

        Per *method* rather than simply the latest overall, because different
        methods establish different things and a node legitimately holds
        several at once: a later `CROSS_EDITION_COLLATION` must not erase a
        standing `EXACT_SPAN` result. Only the same check, re-run with a
        different answer, supersedes itself.

        Nothing is deleted or rewritten by this: every verification stays in
        the log and on the node, and `verifications()` still returns the whole
        history. Only the *summary* stops treating a superseded pass as
        current."""
        self._require_node(node_id)
        latest: dict[str, Node] = {}
        for node in self.verifications(node_id):
            latest[node.payload["method"]] = node  # verifications() is seq-ordered
        best = AssuranceLevel.A0_UNCHECKED
        for node in latest.values():
            if node.payload["result"] != VerificationResult.PASS:
                continue
            level = AssuranceLevel(node.payload["assurance_level"])
            if _ASSURANCE_RANK[level] > _ASSURANCE_RANK[best]:
                best = level
        return best

    def agent_profile(self, agent_id: str) -> AgentProfile | None:
        row = self.conn.execute("SELECT * FROM agents WHERE id=?", (agent_id,)).fetchone()
        if row is None:
            return None
        return AgentProfile(
            id=row["id"], kind=row["kind"],
            corpus_scope=row["corpus_scope"], method_label=row["method_label"],
            model=row["model"],
        )

    def agent_report(self, agent_id: str) -> AgentReport:
        """A pure contribution-history count for `agent_id` — proposed,
        attested, accepted, rejected, and discount edges contributed
        (`descends_from`/`parallel_of`, which surface non-independence
        rather than hide it). Never a score; see `AgentReport`'s docstring.
        Works for any agent_id string, registered or not, since registration
        is informational, not enforced."""
        def _count(table: str, col: str, action: str) -> int:
            return self.conn.execute(
                f"SELECT COUNT(*) AS c FROM {table} WHERE {col}=? AND action=?",
                (agent_id, action),
            ).fetchone()["c"]

        discount_edges = self.conn.execute(
            "SELECT COUNT(*) AS c FROM edge_authorship ea JOIN edges e ON e.id = ea.edge_id "
            "WHERE ea.author=? AND ea.action='proposed' AND e.type IN (?, ?)",
            (agent_id, EdgeType.DESCENDS_FROM, EdgeType.PARALLEL_OF),
        ).fetchone()["c"]

        return AgentReport(
            agent_id=agent_id,
            proposed=_count("node_authorship", "author", "proposed"),
            attested=_count("node_authorship", "author", "attested"),
            accepted=_count("node_authorship", "author", "accepted"),
            rejected=_count("node_authorship", "author", "rejected"),
            discount_edges_contributed=discount_edges,
        )

    def rejected(self, *, node_type: NodeType | None = None) -> list[Node]:
        """Rejected nodes, with their reasons (design doc §8: "the graph
        records the judgement calls, not only the findings"). For
        `witness`/`passage`, persistent rejection is already enforced
        mechanically at the write boundary via `canonical_ref` identity. For
        `claim`/`conjecture`, there is no content-derived identity to block
        on — principle 5 forbids hashing agent-produced text into identity —
        so a rejected conjecture cannot be caught by id if reworded. This
        method is how that gap gets closed instead: by making rejections
        visible to an agent's own reasoning, not by faking an identity key
        for content the design deliberately declines to hash."""
        query = "SELECT * FROM nodes WHERE status=?"
        params: list = [NodeStatus.REJECTED]
        if node_type is not None:
            query += " AND type=?"
            params.append(node_type)
        rows = self.conn.execute(query, params).fetchall()
        return [self._row_to_node(r) for r in rows]

    def independent_support(self, node_id: str) -> IndependentSupport:
        """design doc §4, §11 — the counter-argument to consensus-seeking:
        attesting count stays put while `independent` flips to False the
        instant a descent/parallel relation links two supporting witnesses."""
        self._require_node(node_id)
        attesting = self.conn.execute(
            "SELECT src FROM edges WHERE type=? AND dst=? AND retracted_at IS NULL",
            (EdgeType.ATTESTS, node_id),
        ).fetchall()
        passages = [r["src"] for r in attesting]
        witnesses: dict[str, str | None] = {}
        for p in passages:
            row = self.conn.execute(
                "SELECT dst FROM edges WHERE type=? AND src=? AND retracted_at IS NULL",
                (EdgeType.PART_OF, p),
            ).fetchone()
            witnesses[p] = row["dst"] if row else None
        distinct_witnesses = {w for w in witnesses.values() if w is not None}
        subjects = list(dict.fromkeys([*passages, *distinct_witnesses]))
        flips = [
            (a, b) for a, b in itertools.combinations(subjects, 2)
            if self._related(a, b, (EdgeType.DESCENDS_FROM, EdgeType.PARALLEL_OF))
        ]
        return IndependentSupport(
            node_id=node_id,
            attesting_count=len(passages),
            distinct_witnesses=len(distinct_witnesses),
            independent=not flips,
            # `independent` is vacuously true with nothing to discount. Said
            # out loud rather than left for each reader to notice, because
            # "independent" over an empty support set reads as a result.
            vacuous=not passages,
            non_independent_pairs=flips,
        )

    def rebuild(self, *, log_path: str | Path | None = None) -> RebuildReport:
        """Replay the event log into a shadow graph and diff it against the
        live projection. A failing diff is a bug, not a warning (design doc
        §5 principle 1).

        `log_path` defaults to the attached event log. Passing it explicitly is
        what lets a read-only handle run this check: replaying and diffing are
        pure reads, and the attached log was the only thing here that required
        the writer's lock. Refusing to verify a projection you are allowed to
        read would be a strange place to draw the line — this is the check that
        proves the projection is honest."""
        if log_path is None:
            log_path = self.event_log_or_raise().path
        shadow = Graph(":memory:", event_log=None)
        events = list(read_events(log_path))
        for ev in events:
            shadow._apply(ev)
        diff = self._diff(shadow)
        shadow.close()
        if diff:
            raise RebuildMismatch(diff)
        return RebuildReport(
            ok=True, events_replayed=len(events),
            nodes=self._count("nodes"), edges=self._count("edges"),
        )

    def verify_integrity(self, node_id: str | None = None) -> IntegrityReport:
        """An explicit, on-demand check — never an ambient hazard on every
        read. A tampered row must not turn every future `get_node()`/
        `citable()` call touching it into a crash; that would make one bad
        row take down read access to the whole graph, a worse failure mode
        than the thing being guarded against. Independently re-hashes each
        row's stored `payload` and compares against its recorded
        `payload_hash` — the same "re-verify, don't trust a stored claim"
        discipline `rebuild()` applies to the whole projection, applied here
        per row."""
        query = "SELECT id, payload, payload_hash FROM nodes"
        params: tuple = ()
        if node_id is not None:
            query += " WHERE id=?"
            params = (node_id,)
        checked = 0
        mismatched: list[str] = []
        unhashed: list[str] = []
        for row in self.conn.execute(query, params).fetchall():
            checked += 1
            if row["payload_hash"] is None:
                unhashed.append(row["id"])
                continue
            actual = hashlib.sha256(row["payload"].encode("utf-8")).hexdigest()
            if actual != row["payload_hash"]:
                mismatched.append(row["id"])
        return IntegrityReport(checked=checked, mismatched=mismatched, unhashed=unhashed)

    # --- apply: the only place SQL runs (used live and by rebuild) -----------

    def _apply(self, ev: Event) -> None:
        if ev.event == "propose":
            self._apply_propose(ev)
        elif ev.event == "attest":
            self._apply_attest(ev)
        elif ev.event == "accept":
            self._apply_verdict(ev, NodeStatus.ACCEPTED, "accepted")
        elif ev.event == "reject":
            self._apply_verdict(ev, NodeStatus.REJECTED, "rejected")
        elif ev.event == "reopen":
            self._apply_verdict(ev, NodeStatus.PROPOSED, "reopened")
        elif ev.event == "add_edge":
            self._apply_add_edge(ev)
        elif ev.event == "retract_edge":
            self._apply_edge_retraction(ev, retracted=True)
        elif ev.event == "restore_edge":
            self._apply_edge_retraction(ev, retracted=False)
        elif ev.event == "verify":
            self._apply_verify(ev)
        elif ev.event == "ask":
            self._apply_ask(ev)
        elif ev.event == "register_agent":
            self._apply_register_agent(ev)
        elif ev.event == "refused":
            pass  # an audit marker only; never mutates state
        elif ev.event == "model_call":
            pass  # an audit marker only; never mutates state
        elif ev.event in ("run_started", "run_finished"):
            pass  # a run beginning is not a change to the graph
        else:  # pragma: no cover — Event already validates against EVENT_TYPES
            raise CohortError(f"no _apply handler for event {ev.event!r}")

    def _apply_propose(self, ev: Event) -> None:
        detail = ev.detail
        existing = self._get_row(ev.node_id)
        if existing is not None:
            self._add_authorship("node", ev.node_id, ev.authored_by, "converged", ev.at, ev.seq)
            self.conn.execute("UPDATE nodes SET updated_seq=? WHERE id=?", (ev.seq, ev.node_id))
        else:
            self._insert_node_row(
                ev.node_id, ev.node_type, NodeStatus.PROPOSED,
                json.dumps(detail["payload"]), None, ev.seq,
            )
            self._add_authorship("node", ev.node_id, ev.authored_by, "proposed", ev.at, ev.seq)
        if ev.edge_id is not None and ev.edge_type is not None:
            self._insert_edge_row(ev.edge_id, ev.edge_type, ev.node_id, detail["witness_id"], ev.seq)
            self._add_authorship("edge", ev.edge_id, ev.authored_by, "proposed", ev.at, ev.seq)
        self.conn.commit()

    def _apply_attest(self, ev: Event) -> None:
        self.conn.execute(
            "UPDATE nodes SET status=?, updated_seq=? WHERE id=?",
            (NodeStatus.ATTESTED, ev.seq, ev.node_id),
        )
        self._add_authorship("node", ev.node_id, ev.authored_by, "attested", ev.at, ev.seq)
        self.conn.commit()

    def _apply_verdict(self, ev: Event, new_status: NodeStatus, verdict: str) -> None:
        detail = ev.detail
        decision_id = detail["decision_node_id"]
        reason = detail.get("reason")
        rejected_reason = reason if new_status == NodeStatus.REJECTED else None
        self.conn.execute(
            "UPDATE nodes SET status=?, rejected_reason=?, updated_seq=? WHERE id=?",
            (new_status, rejected_reason, ev.seq, ev.node_id),
        )
        self._add_authorship("node", ev.node_id, ev.authored_by, verdict, ev.at, ev.seq)
        decision_payload = DecisionPayload(
            subject_node_id=ev.node_id, verdict=verdict, reason=reason
        ).model_dump(mode="json")
        self._insert_node_row(
            decision_id, NodeType.DECISION, NodeStatus.ACCEPTED,
            json.dumps(decision_payload), None, ev.seq,
        )
        self._add_authorship("node", decision_id, ev.authored_by, "proposed", ev.at, ev.seq)
        self.conn.commit()

    def _apply_add_edge(self, ev: Event) -> None:
        src, dst = ev.detail["src"], ev.detail["dst"]
        if ev.detail.get("converge"):
            self._add_authorship("edge", ev.edge_id, ev.authored_by, "converged", ev.at, ev.seq)
            self.conn.commit()
            return
        reason = ev.detail.get("reason")
        self._insert_edge_row(ev.edge_id, ev.edge_type, src, dst, ev.seq, reason)
        self._add_authorship("edge", ev.edge_id, ev.authored_by, "proposed", ev.at, ev.seq)
        if ev.edge_type in SYMMETRIC_EDGE_TYPES:
            rev_id = f"{ev.edge_id}:rev"
            self._insert_edge_row(rev_id, ev.edge_type, dst, src, ev.seq, reason)
            self._add_authorship("edge", rev_id, ev.authored_by, "proposed", ev.at, ev.seq)
        self.conn.commit()

    def _apply_edge_retraction(self, ev: Event, *, retracted: bool) -> None:
        """Both directions of a symmetric edge move together. `parallel_of` and
        `contradicts` are stored as two rows; retracting one and leaving its
        twin would make the relation hold in one direction only, which is not a
        state this vocabulary has."""
        at = ev.at if retracted else None
        reason = ev.detail.get("reason") if retracted else None
        action = "retracted" if retracted else "restored"
        for row_id in self._edge_row_ids(ev.edge_id):
            self.conn.execute(
                "UPDATE edges SET retracted_at=?, retracted_reason=? WHERE id=?",
                (at, reason, row_id),
            )
            # Authorship goes on both rows, the way `_apply_add_edge` writes it
            # on both: a twin that is retracted but does not say who retracted
            # it would be a row whose state no author owns.
            self._add_authorship("edge", row_id, ev.authored_by, action, ev.at, ev.seq)
        self.conn.commit()

    def _edge_row_ids(self, edge_id: str) -> list[str]:
        """An edge id and its reverse twin, if one exists."""
        base = edge_id[: -len(":rev")] if edge_id.endswith(":rev") else edge_id
        return [
            r["id"] for r in self.conn.execute(
                "SELECT id FROM edges WHERE id=? OR id=?", (base, f"{base}:rev")
            ).fetchall()
        ]

    def _require_edge(self, edge_id: str):
        row = self.conn.execute("SELECT * FROM edges WHERE id=?", (edge_id,)).fetchone()
        if row is None:
            raise EdgeNotFound(
                f"no edge {edge_id}. Edge ids come from `edges()` or from the "
                "call that created one; they are not derivable from the nodes "
                "they join."
            )
        return row

    def _apply_verify(self, ev: Event) -> None:
        detail = ev.detail
        self._insert_node_row(
            ev.node_id, NodeType.VERIFICATION, NodeStatus.ACCEPTED,
            json.dumps(detail["payload"]), None, ev.seq,
        )
        self._add_authorship("node", ev.node_id, ev.authored_by, "proposed", ev.at, ev.seq)
        self._insert_edge_row(ev.edge_id, ev.edge_type, ev.node_id, detail["subject_node_id"], ev.seq)
        self._add_authorship("edge", ev.edge_id, ev.authored_by, "proposed", ev.at, ev.seq)
        self.conn.commit()

    def _apply_ask(self, ev: Event) -> None:
        self._insert_node_row(
            ev.node_id, NodeType.QUESTION, NodeStatus.ACCEPTED,
            json.dumps(ev.detail["payload"]), None, ev.seq,
        )
        self._add_authorship("node", ev.node_id, ev.authored_by, "proposed", ev.at, ev.seq)
        self.conn.commit()

    def _apply_register_agent(self, ev: Event) -> None:
        payload = ev.detail["payload"]
        self.conn.execute(
            "INSERT INTO agents (id, kind, corpus_scope, method_label, model, created_seq) "
            "VALUES (?, ?, ?, ?, ?, ?) "
            "ON CONFLICT(id) DO UPDATE SET kind=excluded.kind, "
            "corpus_scope=excluded.corpus_scope, method_label=excluded.method_label, "
            "model=excluded.model",
            (payload["id"], payload["kind"], payload.get("corpus_scope"),
             payload.get("method_label"), payload.get("model"), ev.seq),
        )
        self.conn.commit()

    # --- small helpers ---------------------------------------------------------

    def _refuse(
        self, attempted: str, authored_by: str, error: CohortError, *,
        node_id: str | None = None, edge_id: str | None = None,
        node_type: NodeType | None = None, edge_type: EdgeType | None = None,
    ) -> NoReturn:
        if self.event_log is not None:
            self.event_log.append(
                "refused", authored_by=authored_by, node_id=node_id, edge_id=edge_id,
                node_type=node_type, edge_type=edge_type,
                detail={"attempted": attempted, "rule": type(error).__name__, "message": str(error)},
            )
            #: so a caller further out (the tool boundary, `log_refusal`) can
            #: tell an already-recorded refusal from one that would otherwise
            #: go unrecorded, instead of logging the same refusal twice.
            error.logged_to_event_log = True
        raise error

    def log_refusal(
        self, attempted: str, authored_by: str, error: Exception, *,
        node_id: str | None = None, model_call_id: int | None = None,
    ) -> None:
        """Record a refused *agent action* that the write boundary itself
        never saw.

        `_refuse` only fires for rules `graph.py` enforces on a write it was
        actually asked to perform. A tool call can be refused earlier than
        that and for equally real reasons — a node id that does not exist
        (`NodeNotFound`, raised by lookup, not by a write), a payload pydantic
        rejects, a tool's own precondition — and those never reached the log.
        The live conjecture run made the cost concrete: five refused
        `find_attestations` calls against invented node ids were reported to
        the model and then lost, so the log recorded a clean run and
        docs/design.md §15's "refusals are part of its scholarly output" held only
        for the subset of refusals that happened to be write-boundary rules.

        Idempotent with `_refuse`: an error already logged there carries
        `logged_to_event_log` and is skipped, so one refusal is one event.
        No-op on a read-only graph, which has no log to append to."""
        if self.event_log is None or getattr(error, "logged_to_event_log", False):
            return
        self.event_log.append(
            "refused", authored_by=authored_by, node_id=node_id,
            model_call_id=model_call_id,
            detail={
                "attempted": attempted,
                "rule": type(error).__name__,
                "message": str(error),
            },
        )
        error.logged_to_event_log = True

    def _require_researcher(
        self, authored_by: str, *, action: str,
        node_id: str | None = None, edge_id: str | None = None,
    ) -> None:
        if authored_by != RESEARCHER:
            self._refuse(
                action, authored_by,
                NotResearcher(f"{action} requires authored_by='researcher', got {authored_by!r}"),
                node_id=node_id, edge_id=edge_id,
            )

    def _require_node(self, node_id: str) -> Node:
        row = self._get_row(node_id)
        if row is None:
            raise NodeNotFound(self._unfound_detail(node_id))
        return self._row_to_node(row)

    def _unfound_detail(self, node_id: str) -> str:
        """`NodeNotFound`'s message, naming the near miss when there is one.

        A refusal is output, not telemetry (design.md §15), so it should say
        what to do differently. The first live multi-model run to be censused
        (2026-09-02) produced eight of these and every one was the same near
        miss: three agents on three different model families each dropped the
        `claim:` prefix, reading it as a label on the id rather than as part
        of it. Agreement across families is not three coincidences.

        Naming the node it nearly matched turns a dead end into a correction
        **without accepting the malformed id**. The prefix is what makes an id
        say what kind of thing it names (principle 5), and a boundary that
        quietly repaired it would be teaching that the type is decoration.

        The suffix search is unindexed, so it scans; it runs only on the
        failure path, where a scan is cheaper than a wasted turn.
        """
        if ":" in node_id:
            return node_id
        near = [
            r["id"] for r in self.conn.execute(
                "SELECT id FROM nodes WHERE id LIKE ? ORDER BY id LIMIT 3",
                (f"%:{node_id}",),
            )
        ]
        if len(near) == 1:
            return (
                f"{node_id} — did you mean {near[0]}? An id carries its type "
                "prefix, which is part of the id and not a label on it"
            )
        if near:
            return (
                f"{node_id} — more than one node ends with it "
                f"({', '.join(near)}); pass the whole id, prefix included"
            )
        return node_id

    def _get_row(self, node_id: str):
        return self.conn.execute("SELECT * FROM nodes WHERE id=?", (node_id,)).fetchone()

    #: Node types where `attest` asserts something the author could be wrong
    #: about in an interested way, so the author may not be the attester.
    #:
    #: Witnesses and passages are deliberately absent. Their identity is
    #: source-derived and their attest precondition is settled by the source
    #: rather than by judgment — a passage is attested when it is located in a
    #: witness, which `verify_exact_span` re-checks against bytes. Requiring a
    #: second agent to confirm a fact the corpus already decides would add a
    #: round trip and no independence, and would break convergence: two agents
    #: recording the same passage converge onto one node, so "the author" of a
    #: source-derived node is not a meaningful single party.
    #:
    #: Queries are absent for a different reason: a query is a retrieval to
    #: run, not an assertion, so there is nothing for a second reader to be
    #: right or wrong about. `verify()` refuses a query as a subject for the
    #: same reason, which means a rule here would create a rung no reviewer
    #: could ever record having checked.
    REVIEWABLE_TYPES = (NodeType.CLAIM, NodeType.CONJECTURE)

    def attest_conflict(self, node_id: str, authored_by: str) -> CohortError | None:
        """The error `attest(node_id, authored_by=...)` would refuse with as a
        self-review, or None if it would not.

        A public read so a caller can decline to try rather than generate a
        predictable refusal: `find_attestations` uses it to avoid logging a
        refusal on every single call for the claim it just authored, and the
        UI uses it to explain why an attest button is unavailable. Asking is
        not a substitute for the boundary check — `attest()` re-checks
        regardless of whether anyone asked.

        It hands back the error rather than its message so a caller that does
        decide to refuse can raise *this* rule by name. A tool that wrapped it
        in a generic error would cost the refusal census the two rule names it
        most wants to count."""
        node = self._require_node(node_id)
        return self._reviewer_conflict(node, authored_by)

    def _reviewer_conflict(self, node: Node, authored_by: str) -> CohortError | None:
        """The author≠reviewer rule (compare.md §10; design doc §5 principle 3).

        Returns the error to refuse with, or None to allow. Two distinct
        failures, kept distinct because they are refused for different
        reasons and a researcher reading the refusal log should see which:
        the same agent checking itself, and a different agent that is not
        actually a different reader."""
        if authored_by == RESEARCHER or node.type not in self.REVIEWABLE_TYPES:
            return None
        authors = self._proposing_authors(node.id)
        if not authors:
            return None
        if authored_by in authors:
            return SelfAttestation(
                f"{authored_by} authored {node.id} and may not attest it. "
                "An attestation is a check that the mechanical preconditions "
                "hold, and the author is the one party with an interest in "
                "the answer. Let another agent on a different model family "
                "attest it, or accept it yourself as the researcher."
            )
        mine = self._agent_model(authored_by)
        if not mine:
            return None
        my_family = model_family(mine)
        for author in sorted(authors):
            theirs = self._agent_model(author)
            if theirs and model_family(theirs) == my_family:
                return ReviewerNotIndependent(
                    f"{authored_by} ({mine}) and the author {author} ({theirs}) "
                    f"share the model family {my_family!r}, so attesting "
                    f"{node.id} would be the author confirming itself under a "
                    "second name. Give the reviewer a model from another "
                    "provider (OPENROUTER_MODELS lists the pool)."
                )
        return None

    def _proposing_authors(self, node_id: str) -> set[str]:
        """Everyone who put this node into the graph — `proposed` for an
        agent-authored node, plus `converged` for a source-derived one, where
        several agents may have arrived at the same id. Later actions
        (`attested`, `accepted`) are not authorship of the assertion and are
        excluded, or a reviewer would lock itself out of a node it had
        already legitimately attested once."""
        rows = self.conn.execute(
            "SELECT DISTINCT author FROM node_authorship WHERE node_id=? "
            "AND action IN ('proposed', 'converged')",
            (node_id,),
        ).fetchall()
        return {r["author"] for r in rows}

    def _agent_model(self, agent_id: str) -> str | None:
        """The model a registered agent declared, or None if it never
        registered one. `authored_by` is not a foreign key into `agents` (see
        the schema comment), so an unregistered author is ordinary, not an
        error."""
        row = self.conn.execute(
            "SELECT model FROM agents WHERE id=?", (agent_id,)
        ).fetchone()
        return row["model"] if row is not None else None

    def _has_qualifying_attestation(self, node_id: str) -> bool:
        rows = self.conn.execute(
            "SELECT n.status FROM edges e JOIN nodes n ON n.id = e.src "
            "WHERE e.type=? AND e.dst=?",
            (EdgeType.ATTESTS, node_id),
        ).fetchall()
        return any(r["status"] in (NodeStatus.ATTESTED, NodeStatus.ACCEPTED) for r in rows)

    def _has_inbound_edge(self, node_id: str, edge_type: EdgeType) -> bool:
        row = self.conn.execute(
            "SELECT 1 FROM edges WHERE type=? AND dst=? LIMIT 1", (edge_type, node_id)
        ).fetchone()
        return row is not None

    def _has_outbound_edge(self, node_id: str, edge_type: EdgeType) -> bool:
        row = self.conn.execute(
            "SELECT 1 FROM edges WHERE type=? AND src=? LIMIT 1", (edge_type, node_id)
        ).fetchone()
        return row is not None

    def _related(self, a: str, b: str, edge_types: Iterable[EdgeType]) -> bool:
        types = tuple(edge_types)
        placeholders = ",".join("?" for _ in types)
        row = self.conn.execute(
            f"SELECT 1 FROM edges WHERE type IN ({placeholders}) AND "
            f"retracted_at IS NULL AND "
            f"((src=? AND dst=?) OR (src=? AND dst=?)) LIMIT 1",
            (*types, a, b, b, a),
        ).fetchone()
        return row is not None

    def _insert_edge_row(
        self, edge_id: str, edge_type: EdgeType, src: str, dst: str, seq: int,
        reason: str | None = None,
    ) -> None:
        self.conn.execute(
            "INSERT INTO edges (id, type, src, dst, created_seq, reason) "
            "VALUES (?, ?, ?, ?, ?, ?)",
            (edge_id, edge_type, src, dst, seq, reason),
        )

    def _insert_node_row(
        self, node_id: str, node_type: NodeType, status: NodeStatus, payload_json: str,
        rejected_reason: str | None, seq: int,
    ) -> None:
        """The only place a node row is ever inserted — hashes the literal
        bytes being stored, not a re-serialized dict, so "hash matches
        bytes" holds by construction (design doc §5 principle 1: the graph
        is a projection, and a hash computed from anything other than what
        was actually written could drift from it)."""
        payload_hash = hashlib.sha256(payload_json.encode("utf-8")).hexdigest()
        self.conn.execute(
            "INSERT INTO nodes (id, type, status, payload, payload_hash, rejected_reason, "
            "created_seq, updated_seq) VALUES (?, ?, ?, ?, ?, ?, ?, ?)",
            (node_id, node_type, status, payload_json, payload_hash, rejected_reason, seq, seq),
        )

    def _add_authorship(self, kind: str, id_: str, author: str, action: str, at: str, seq: int) -> None:
        table = "node_authorship" if kind == "node" else "edge_authorship"
        col = "node_id" if kind == "node" else "edge_id"
        self.conn.execute(
            f"INSERT INTO {table} ({col}, author, action, at, seq) VALUES (?, ?, ?, ?, ?)",
            (id_, author, action, at, seq),
        )

    def _row_to_node(self, row) -> Node:
        authorship = [
            Authorship(author=r["author"], at=r["at"], action=r["action"])
            for r in self.conn.execute(
                "SELECT author, action, at FROM node_authorship WHERE node_id=? ORDER BY seq",
                (row["id"],),
            ).fetchall()
        ]
        return Node(
            id=row["id"], type=row["type"], status=row["status"],
            payload=json.loads(row["payload"]), authorship=authorship,
            rejected_reason=row["rejected_reason"],
            created_seq=row["created_seq"], updated_seq=row["updated_seq"],
        )

    def _row_to_edge(self, row) -> Edge:
        authorship = [
            Authorship(author=r["author"], at=r["at"], action=r["action"])
            for r in self.conn.execute(
                "SELECT author, action, at FROM edge_authorship WHERE edge_id=? ORDER BY seq",
                (row["id"],),
            ).fetchall()
        ]
        return Edge(
            id=row["id"], type=row["type"], src=row["src"], dst=row["dst"],
            authorship=authorship, created_seq=row["created_seq"],
            reason=row["reason"],
            retracted_at=row["retracted_at"],
            retracted_reason=row["retracted_reason"],
        )

    def _count(self, table: str) -> int:
        return self.conn.execute(f"SELECT COUNT(*) AS c FROM {table}").fetchone()["c"]

    def _diff(self, other: "Graph") -> dict:
        mine, theirs = self._snapshot(), other._snapshot()
        return {} if mine == theirs else {"self": mine, "other": theirs}

    def _snapshot(self) -> dict:
        nodes = {
            r["id"]: (r["type"], r["status"], r["payload"], r["rejected_reason"])
            for r in self.conn.execute("SELECT * FROM nodes").fetchall()
        }
        edges = {
            r["id"]: (r["type"], r["src"], r["dst"], r["retracted_at"], r["retracted_reason"])
            for r in self.conn.execute("SELECT * FROM edges").fetchall()
        }
        node_auth = sorted(
            (r["node_id"], r["author"], r["action"], r["seq"])
            for r in self.conn.execute("SELECT * FROM node_authorship").fetchall()
        )
        edge_auth = sorted(
            (r["edge_id"], r["author"], r["action"], r["seq"])
            for r in self.conn.execute("SELECT * FROM edge_authorship").fetchall()
        )
        agents = {
            r["id"]: (r["kind"], r["corpus_scope"], r["method_label"])
            for r in self.conn.execute("SELECT * FROM agents").fetchall()
        }
        return {
            "nodes": nodes, "edges": edges, "node_auth": node_auth, "edge_auth": edge_auth,
            "agents": agents,
        }
