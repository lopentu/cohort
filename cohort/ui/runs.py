"""Running an agent from the web UI, with the same guarantees the scripts have.

The goal is parity: everything you can do with `scripts/run_*.py` should be
doable from a browser, and nothing the scripts refuse should become possible
because the caller is a web request instead of a shell.

Four things make that true, and each is a constraint rather than a feature:

**0. A run is one *or several* agents.** Several workers share one process,
one `Graph` and therefore one lock, so a swarm is not a harder concurrency
problem than a single agent — `AttestationWorker.run_async()` already argues
why (its `to_thread` is scoped to the one blocking HTTP call, and no graph
write is ever inside that window). What several agents buy is the thing the
design actually claims: **declared viewpoint diversity**. Each agent carries
its own `corpus_scope` and `method_label`, and those are real research
commitments that change what it looks at — not persona prompts layered over an
identical view (docs/roadmap.md, "viewpoint formation without persona theater").
Agents still cannot address each other; there is no channel and no shared
transcript (docs/design.md §5 principle 3).

**1. One run at a time, enforced by the same lock as everything else.** An
agent run holds the graph's exclusive `flock` for its whole duration —
minutes, not milliseconds — because it writes continuously. So while a run is
active, `POST /api/accept` answers 409, exactly as it would while
`scripts/run_cbeta_demo.py` was running in a terminal. That is not a
limitation introduced here; it is docs/design.md §5 principle 7 behaving normally,
and the UI's job is to *say so* rather than to work around it.

**2. Spend is capped in code, per run, with a ceiling the client cannot
raise.** `cohort/agents/budget.py` refuses the request that would cross the
cap. The browser chooses a budget, but `max_budget_usd` — set by whoever
started the server — bounds what it may choose. A client-supplied number that
nothing checks is not a budget, it is a suggestion.

**3. The run happens in a background thread, not in the request.** A model
loop takes minutes; an HTTP request that blocked for that long would time out
somewhere unhelpful. `POST /api/run` returns immediately with a run id and
`GET /api/run` reports progress. The thread owns its own `Graph` and its own
event loop, which also satisfies sqlite3's same-thread rule for free — the
same reason `AttestationWorker`'s docstring gives for its own threading model.

**4. The API key never reaches the browser.** It is read server-side from the
environment, the same way the scripts read it. The UI can start a run; it
cannot see the credential that pays for one.

**What is deliberately absent.** There is no queue and no retry. If a run is
already going, starting another is refused with a clear reason rather than
enqueued — a queue would let a researcher accumulate spend they cannot see,
and a retry would make the single-writer rule feel like flakiness.
"""
from __future__ import annotations

import asyncio
import threading
import time
import uuid
from pathlib import Path
from typing import Any

from ..agents.attestation_worker import AttestationWorker
from ..agents.budget import BudgetedTransport, BudgetExceeded
from ..agents.openrouter import (
    OpenRouterError,
    load_model_pool,
    load_openrouter_config,
)
from ..agents.swarm import run_swarm
from ..eventlog import read_refusals, read_runs
from ..graph import Graph
from ..agents.review_worker import ReviewWorker, pending_review_context
from ..agents.roster import RosterNotIndependent, check_distinct_model_families
from ..families import model_family
from ..schemas import AgentKind, AgentProfile, NodeType
from ..sources.base import Source

#: What a run may cost unless the operator raises it. Low on purpose: the
#: whole live conjecture run cost $0.004, so a dollar is already generous, and
#: a default that cannot surprise anyone is worth more than a convenient one.
DEFAULT_MAX_BUDGET_USD = 1.00

#: Turn ceiling, same reasoning. A worker that has not finished in this many
#: turns is usually looping, not thinking.
DEFAULT_MAX_TURNS = 8

#: How many agents one run may fan out to. Bounded because every agent
#: multiplies the spend against one shared cap, and because past a handful
#: the count starts being the claim rather than the mechanism — which
#: docs/design.md §9 lists as an anti-goal.
DEFAULT_MAX_AGENTS = 4


class RunRejected(RuntimeError):
    """A run could not be started. Carries a reason meant to be shown."""


ROLE_WORKER = "worker"
ROLE_REVIEWER = "reviewer"
ROLES = (ROLE_WORKER, ROLE_REVIEWER)


class AgentSpec:
    """One agent's assignment. `corpus_scope` and `method_label` are its
    declared research commitments, not flavour text — see this module's
    docstring."""

    def __init__(self, agent_id: str, instructions: str,
                 corpus_scope: str = "", method_label: str = "",
                 model: str = "", role: str = ROLE_WORKER) -> None:
        self.agent_id = agent_id.strip()
        self.instructions = instructions.strip()
        self.corpus_scope = corpus_scope.strip()
        self.method_label = method_label.strip()
        #: empty means "the server's configured default", filled in by
        #: `RunManager.start` so the roster check sees real ids.
        self.model = model.strip()
        #: `worker` proposes and attests; `reviewer` checks what workers
        #: proposed and cannot propose anything (`ReviewWorker`). The roster
        #: check does not care which is which — a reviewer sharing a model
        #: family with the worker it checks is refused like any other overlap,
        #: which is the point of putting it in the same roster.
        self.role = (role or ROLE_WORKER).strip().lower()

    @property
    def is_reviewer(self) -> bool:
        return self.role == ROLE_REVIEWER

    def as_json(self) -> dict[str, Any]:
        return {
            "agent_id": self.agent_id,
            "instructions": self.instructions,
            "corpus_scope": self.corpus_scope,
            "method_label": self.method_label,
            "model": self.model,
            "role": self.role,
        }



# --- auto-planned inquiries ---------------------------------------------------
#
# "Ask a question and let it decide" has to decide two different kinds of thing,
# and they are not equally safe to automate.
#
# The *machinery* — how many agents, which models, which roles — carries no
# epistemic weight beyond one hard constraint (a roster sharing a model family
# is refused at the write boundary), so deciding it here is a convenience.
#
# The *agenda* does carry weight. `ask_question` is researcher-only because
# setting the agenda is the supervision (tests/test_question.py), so this
# planner never asks a model what to investigate: it templates the researcher's
# own question into the instructions verbatim, along with the `answerable_by`
# they wrote. No model call happens before the run, and nothing paraphrases the
# question into a task on the researcher's behalf. An auto mode that asked a
# model "what should we look into here?" would be the bottom-up
# question-generation this project has not agreed to.

#: The one worker's stance. Auto mode plans exactly one worker and one
#: reviewer, so the two jobs that used to be split across two workers go to the
#: same agent: propose what the passages support, *and* go looking for what
#: would break it.
#:
#: Merged rather than dropped. The disconfirming half is the half worth having —
#: `record_contradiction` has still never been called in a live run, which is
#: some evidence that nothing had ever asked anyone to try — and quietly losing
#: it when the roster shrank would have made the smaller run cheaper in the one
#: way that matters least.
#:
#: Fixed, not generated per run: a stance chosen per run would be a model
#: deciding how to inquire, and would make two runs on one question
#: incomparable.
INQUIRY_STANCE = (
    "attestation and disconfirmation",
    "First, search the corpus for passages that would attest an answer to this "
    "question, and propose the claims or conjectures those passages support. "
    "Cite what you find; propose nothing you cannot cite.\n\n"
    "Then do the opposite, before you stop: search for passages that would make "
    "your own answer wrong, or that it would have to explain away. Where two "
    "passages genuinely conflict, record the contradiction rather than choosing "
    "between them. An answer that survives this is worth more than one nobody "
    "tried to break, and finding out yours does not survive is a result, not a "
    "failure.",
)

REVIEW_STANCE = (
    "review",
    "Check the claims the worker proposed against the passages it "
    "cite. Attest what holds. Where a citation does not resolve, say so and "
    "leave it unattested — withholding is a result.",
)


def plan_inquiry(
    question: str, *, answerable_by: str = "", models: list[str] | None = None,
    max_agents: int = 4,
) -> list[AgentSpec]:
    """A roster for one question, without asking anyone what to look into.

    Returns workers first and the reviewer last, which is also the order
    `_execute` runs them in — a reviewer alongside the workers would have
    nothing proposed yet to review.
    """
    question = (question or "").strip()
    if not question:
        raise RunRejected("an inquiry needs a question")

    pool = [m for m in (models or []) if m.strip()]
    families = list(dict.fromkeys(model_family(m) for m in pool))
    # One model per family, in pool order: `check_distinct_model_families`
    # refuses a roster that reuses one, so planning a roster the write boundary
    # would reject is not an option worth offering.
    by_family: dict[str, str] = {}
    for m in pool:
        by_family.setdefault(model_family(m), m)
    usable = [by_family[f] for f in families]

    # One worker, one reviewer — and the reviewer is not the optional half.
    # An agent may not attest what it authored, so a roster with only one model
    # family can propose but never promote: every claim stops at `proposed` and
    # the run's output is a pile of assertions nothing has checked. The count
    # that buys a *checked* answer is two, and the second seat is spent on
    # checking rather than on more proposing.
    #
    # The two models must come from different providers. Both the roster check
    # (`check_distinct_model_families`) and the write boundary
    # (`ReviewerNotIndependent`) refuse a reviewer sharing a family with the
    # author, because a different id on one model is not a different reader —
    # so a roster that reused one would be refused before it could run.
    usable = usable[:2]
    reviewing = max_agents >= 2 and len(usable) >= 2

    specs: list[AgentSpec] = []
    label, stance = INQUIRY_STANCE
    specs.append(
        AgentSpec(
            agent_id="agent:inquiry-1",
            instructions=_inquiry_task(question, answerable_by, stance),
            method_label=label,
            model=usable[0] if usable else "",
            role=ROLE_WORKER,
        )
    )
    if reviewing:
        label, stance = REVIEW_STANCE
        specs.append(
            AgentSpec(
                agent_id="agent:inquiry-reviewer",
                instructions=_inquiry_task(question, answerable_by, stance),
                method_label=label,
                model=usable[1],
                role=ROLE_REVIEWER,
            )
        )
    return specs


def _inquiry_task(question: str, answerable_by: str, stance: str) -> str:
    """The question reaches the agent as the researcher wrote it.

    `answerable_by` travels with it because it is the useful half: it is the
    researcher saying what retrieval over this corpus can and cannot settle,
    which is the fence an agent otherwise walks straight through — answering a
    dating question from a corpus that cannot date anything.
    """
    parts = [f"The researcher's question, verbatim: {question}"]
    if answerable_by.strip():
        parts.append(
            "What the researcher says would answer it: "
            f"{answerable_by.strip()}. Anything beyond that is outside what "
            "this corpus can settle — say so rather than answering anyway."
        )
    parts.append(stance)
    return "\n\n".join(parts)

class Run:
    """One run's observable state — one agent or several. Written by the worker
    thread, read by request threads, so every mutation happens under `_lock`."""

    def __init__(self, run_id: str, specs: list[AgentSpec], budget_usd: float,
                 max_turns: int, model: str, question_id: str | None = None) -> None:
        self.id = run_id
        self.specs = specs
        self.question_id = question_id
        #: per-agent tool calls, keyed by agent id, so a live view can say
        #: *which* agent made a call rather than only that one happened
        self.per_agent: dict[str, list[dict[str, Any]]] = {s.agent_id: [] for s in specs}
        self.agent_errors: dict[str, str] = {}
        #: why an agent did nothing, when that is not an error — currently
        #: only a reviewer with nothing in the graph to review. Kept apart
        #: from `agent_errors` so "there was no work" never reads as "it
        #: broke", and so a run of one skipped reviewer still finishes.
        self.agent_notes: dict[str, str] = {}
        self.instructions = specs[0].instructions if len(specs) == 1 else ""
        self.agent_id = specs[0].agent_id if len(specs) == 1 else f"{len(specs)} agents"
        self.budget_usd = budget_usd
        self.max_turns = max_turns
        self.model = model
        self.state = "starting"   # starting | running | finished | failed | stopped
        self.started_at = time.time()
        self.ended_at: float | None = None
        self.tool_calls: list[dict[str, Any]] = []
        self.spend: dict[str, Any] = {
            "budget_usd": budget_usd, "spent_usd": 0.0,
            "remaining_usd": budget_usd, "calls": 0, "unpriced_calls": 0,
        }
        self.error: str | None = None
        self.stopped_early: str | None = None
        self.refusals: list[dict[str, Any]] = []
        self._lock = threading.Lock()
        self._cancel = threading.Event()

    def snapshot(self) -> dict[str, Any]:
        with self._lock:
            return {
                "id": self.id,
                "state": self.state,
                "question_id": self.question_id,
                "agent_id": self.agent_id,
                "model": self.model,
                "instructions": self.instructions,
                "agents": [
                    {
                        **spec.as_json(),
                        "tool_calls": list(self.per_agent.get(spec.agent_id, [])),
                        "error": self.agent_errors.get(spec.agent_id),
                        "note": self.agent_notes.get(spec.agent_id),
                    }
                    for spec in self.specs
                ],
                "max_turns": self.max_turns,
                "started_at": self.started_at,
                "ended_at": self.ended_at,
                "elapsed_s": round((self.ended_at or time.time()) - self.started_at, 1),
                "tool_calls": list(self.tool_calls),
                "spend": dict(self.spend),
                "error": self.error,
                "stopped_early": self.stopped_early,
                "refusals": list(self.refusals),
                "cancel_requested": self._cancel.is_set(),
            }

    def request_stop(self) -> None:
        """Ask the run to stop after the turn in progress.

        Deliberately cooperative rather than a kill: the in-flight HTTP call
        has already been paid for, and abandoning the thread mid-write could
        leave the projection and the log disagreeing — the one invariant this
        system is built on. So the flag is checked between turns.
        """
        self._cancel.set()


class RunManager:
    """Holds at most one active run for one graph."""

    def __init__(
        self, db_path: Path, log_path: Path, source: Source | None,
        *, max_budget_usd: float = DEFAULT_MAX_BUDGET_USD,
        max_turns: int = DEFAULT_MAX_TURNS,
        max_agents: int = DEFAULT_MAX_AGENTS,
        transport_factory=None,
    ) -> None:
        self.db_path = db_path
        self.log_path = log_path
        self.source = source
        self.max_budget_usd = max_budget_usd
        self.max_turns = max_turns
        self.max_agents = max_agents
        #: test seam, mirroring `complete()`'s own `transport` parameter
        self._transport_factory = transport_factory or (
            lambda budget, on_call: BudgetedTransport(budget, on_call=on_call)
        )
        self._current: Run | None = None
        self._history: list[Run] = []
        self._lock = threading.Lock()

    # --- introspection --------------------------------------------------

    def config(self) -> dict[str, Any]:
        try:
            _, model = load_openrouter_config()
            configured, detail = True, model
        except OpenRouterError as e:
            configured, detail = False, str(e)
        return {
            "runs_enabled": True,
            "corpus_available": self.source is not None,
            "model_configured": configured,
            "model": detail if configured else None,
            # The pool a multi-agent roster draws on. Agents in one run may not
            # share a model family, so a browser offering "add agent" has to be
            # able to offer a different model with it.
            "models": load_model_pool(),
            "config_error": None if configured else detail,
            "max_budget_usd": self.max_budget_usd,
            "default_budget_usd": min(0.25, self.max_budget_usd),
            "max_turns": self.max_turns,
            "max_agents": self.max_agents,
            # The roster auto mode would build, minus the instructions, which
            # are the only part that depends on the question. Reported rather
            # than left for the browser to work out: the shape depends on how
            # many *families* the pool has, not how many models, so a client
            # computing it would have to reimplement `model_family` and would
            # drift from what the server actually does. A launcher that
            # promises three agents and starts two is worse than one that
            # promises nothing.
            "plan": [
                {
                    "agent_id": spec.agent_id, "role": spec.role,
                    "method_label": spec.method_label, "model": spec.model,
                }
                for spec in plan_inquiry(
                    "preview", models=load_model_pool(), max_agents=self.max_agents,
                )
            ],
        }

    def current(self) -> dict[str, Any] | None:
        with self._lock:
            run = self._current
        return run.snapshot() if run else None

    def history(self, limit: int = 10) -> list[dict[str, Any]]:
        with self._lock:
            runs = list(self._history[-limit:])
        return [r.snapshot() for r in reversed(runs)]

    def recorded(self, limit: int = 20) -> list[dict[str, Any]]:
        """Every run the *log* knows about, most recent first.

        `history()` is this process's memory and dies with it — before runs
        were events, a server restart erased every run ever launched from the
        browser. This survives, and needs no run manager state at all."""
        return [r.model_dump(mode="json") for r in read_runs(self.log_path, limit=limit)]

    def get(self, run_id: str) -> dict[str, Any] | None:
        with self._lock:
            for run in [self._current, *self._history]:
                if run is not None and run.id == run_id:
                    return run.snapshot()
        return None

    def stop(self) -> dict[str, Any]:
        with self._lock:
            run = self._current
        if run is None:
            raise RunRejected("no run is in progress")
        run.request_stop()
        return run.snapshot()

    # --- starting -------------------------------------------------------

    def start(
        self, agents: list[AgentSpec], *, budget_usd: float,
        max_turns: int | None = None, question_id: str | None = None,
    ) -> dict[str, Any]:
        """Start one run of one or more agents. Every refusal raises
        `RunRejected` with a reason meant to be read, not a status code."""
        if self.source is None:
            raise RunRejected(
                "no corpus is configured on this server, so an agent would have "
                "nothing to search. Start it with --corpus/--allow-runs, or set "
                "CBETA_ARCHIVE_PATH and CBETA_FTS_PATH."
            )
        if not agents:
            raise RunRejected("at least one agent is required")
        if len(agents) > self.max_agents:
            raise RunRejected(
                f"{len(agents)} agents exceeds this server's limit of "
                f"{self.max_agents}. The limit is set when the server starts, "
                "not by the browser."
            )
        for spec in agents:
            if not spec.agent_id:
                raise RunRejected("every agent needs an id")
            if not spec.instructions:
                raise RunRejected(f"{spec.agent_id} has no task: an agent needs one")
            if spec.role not in ROLES:
                raise RunRejected(
                    f"{spec.agent_id} has role {spec.role!r}; expected one of "
                    f"{', '.join(ROLES)}."
                )
        ids = [a.agent_id for a in agents]
        if len(set(ids)) != len(ids):
            raise RunRejected(
                "two agents share an id. Ids are how contributions are "
                "attributed, so distinct agents need distinct ids."
            )
        if budget_usd <= 0:
            raise RunRejected("budget must be positive")
        if budget_usd > self.max_budget_usd:
            raise RunRejected(
                f"budget ${budget_usd:.2f} exceeds this server's ceiling of "
                f"${self.max_budget_usd:.2f}. The ceiling is set when the server "
                "starts, not by the browser."
            )
        if question_id:
            # Checked before the run starts, not when the first claim tries to
            # link itself. A wrong id here would otherwise surface as a run
            # whose every proposal logged an edge refusal — a confusing way to
            # report a typo, and one that costs money to find out about.
            with Graph.open_read_only(self.db_path) as g:
                node = g.get_node(question_id)
                if node.type != NodeType.QUESTION:
                    raise RunRejected(
                        f"{question_id} is a {node.type}, not a question. An "
                        "inquiry runs against a question node; ask one first."
                    )
        turns = min(max_turns or self.max_turns, self.max_turns)

        try:
            _, model = load_openrouter_config()
        except OpenRouterError as e:
            raise RunRejected(f"OpenRouter is not configured: {e}") from e

        # Fill in the default before checking, so an unstated model is checked
        # as what it will actually be rather than skipped.
        for spec in agents:
            if not spec.model:
                spec.model = model
        try:
            check_distinct_model_families({a.agent_id: a.model for a in agents})
        except RosterNotIndependent as e:
            raise RunRejected(str(e)) from e

        with self._lock:
            if self._current is not None and self._current.state in ("starting", "running"):
                raise RunRejected(
                    f"run {self._current.id} is already in progress. Only one run at "
                    "a time: a run holds this graph's writer lock for its whole "
                    "duration (docs/design.md §5 principle 7). Several agents inside one "
                    "run are fine — they share the process and the lock."
                )
            run = Run(uuid.uuid4().hex[:12], agents, budget_usd, turns, model,
                      question_id=question_id)
            self._current = run
            self._history.append(run)

        thread = threading.Thread(
            target=self._execute, args=(run,),
            name=f"cohort-run-{run.id}", daemon=True,
        )
        thread.start()
        return run.snapshot()

    # --- the worker thread ----------------------------------------------

    def _execute(self, run: Run) -> None:
        """Owns its own Graph and event loop. Every exception is captured onto
        the run rather than raised: this thread has no caller to catch it, and a
        run that died silently would be worse than one that reports why.

        One `Graph`, one lock and one shared budget for the whole swarm. Sharing
        the budget is the point of a per-run cap — three agents with a cap each
        would be three caps, and the number the researcher typed would bound
        none of them. `BudgetedTransport` is thread-safe and its check and
        accumulate happen under one lock, so concurrent workers cannot both pass
        the check before either records its spend."""
        graph: Graph | None = None
        try:
            graph = Graph.open(self.db_path, self.log_path)
            # Everything this run writes carries its id from here on, so the
            # log can answer "what did that run do?" after the process that
            # ran it is gone. Set directly rather than with `during_run`
            # because the run's scope is this whole method including its
            # `finally`, not a block inside it.
            graph.event_log.run_id = run.id
            graph.log_run_started(
                run.id, authored_by=f"run:{run.id}",
                agents=[spec.as_json() for spec in run.specs],
                budget_usd=run.budget_usd, question_id=run.question_id,
            )

            def on_call(call: dict) -> None:
                with run._lock:
                    run.spend = {
                        "budget_usd": call["budget"], "spent_usd": call["spent"],
                        "remaining_usd": max(0.0, call["budget"] - call["spent"]),
                        "calls": call["call"],
                        "unpriced_calls": run.spend["unpriced_calls"]
                        + (0 if call["cost_reported"] else 1),
                    }

            transport = self._transport_factory(run.budget_usd, on_call)

            def build(spec) -> tuple:
                profile = graph.agent_profile(spec.agent_id)
                if profile is None:
                    profile = AgentProfile(
                        id=spec.agent_id,
                        kind=AgentKind.REVIEWER if spec.is_reviewer else AgentKind.WORKER,
                        corpus_scope=spec.corpus_scope or "not declared for this run",
                        method_label=spec.method_label or "not declared for this run",
                        model=spec.model,
                    )
                    graph.register_agent(profile, authored_by=spec.agent_id)
                cls = ReviewWorker if spec.is_reviewer else AttestationWorker
                return cls(
                    graph, source=self.source, authored_by=spec.agent_id,
                    profile=profile, transport=transport, model=spec.model,
                    question_id=run.question_id,
                ), spec.instructions

            workers = [s for s in run.specs if not s.is_reviewer]
            reviewers = [s for s in run.specs if s.is_reviewer]

            with run._lock:
                run.state = "running"

            # Two phases, not one gather. A reviewer launched alongside the
            # workers would start before any claim existed and have nothing to
            # review — the ordering is not an optimisation, it is what makes
            # the role possible at all. Both phases share the one graph, the
            # one writer lock and the one budget, so a reviewer's calls are
            # capped by the same number the researcher typed.
            results: dict[str, Any] = {}
            if workers:
                for spec, result in zip(
                    workers, self._run_turns(run, [build(s) for s in workers])
                ):
                    results[spec.agent_id] = result

            for spec in reviewers:
                if run._cancel.is_set():
                    break
                # What to review is only knowable now, so it is appended to the
                # reviewer's own instructions rather than asked for up front.
                # `attest_conflict` does the filtering: a claim this reviewer
                # could not promote anyway is not offered to it, so it never
                # spends a fetch discovering the rule.
                pending = pending_review_context(graph, spec.agent_id)
                if pending is None:
                    with run._lock:
                        run.agent_notes[spec.agent_id] = (
                            "nothing to review: no proposed claim or conjecture in the "
                            "graph was authored by anyone else. Skipped rather than "
                            "billed for a turn with no work in it."
                        )
                    continue
                reviewed = self._run_turns(
                    run, [(build(spec)[0], f"{pending}\n\n{spec.instructions}")]
                )
                results[spec.agent_id] = reviewed[0]

            # `run_swarm` returns exceptions in place, so a transport failure in
            # one agent is reported against that agent instead of failing the run
            with run._lock:
                for spec in run.specs:
                    if spec.agent_id not in results:
                        continue
                    result = results[spec.agent_id]
                    if isinstance(result, BaseException):
                        run.agent_errors[spec.agent_id] = f"{type(result).__name__}: {result}"
                    else:
                        run.per_agent[spec.agent_id] = list(result)
                run.tool_calls = [
                    {**entry, "agent_id": spec.agent_id}
                    for spec in run.specs
                    for entry in run.per_agent.get(spec.agent_id, [])
                ]
                if run._cancel.is_set():
                    run.state = "stopped"
                elif run.agent_errors and len(run.agent_errors) == len(run.specs):
                    run.state = "failed"
                    run.error = "every agent failed; see per-agent errors"
                else:
                    run.state = "finished"
        except BudgetExceeded as e:
            with run._lock:
                run.stopped_early = str(e)
                run.state = "finished"
        except Exception as e:  # noqa: BLE001 — nothing upstream can catch this
            with run._lock:
                run.error = f"{type(e).__name__}: {e}"
                run.state = "failed"
        finally:
            if graph is not None:
                # The closing marker goes in before the lock is dropped, and
                # its own failure is swallowed: a run that reached its end and
                # then could not say so is still better recorded as open than
                # replaced by an exception from the reporting path.
                try:
                    with run._lock:
                        state, error, spend = run.state, run.error, dict(run.spend)
                    graph.log_run_finished(
                        run.id, authored_by=f"run:{run.id}", state=state,
                        spent_usd=spend.get("spent_usd"),
                        calls=spend.get("calls", 0), error=error,
                    )
                except Exception:  # noqa: BLE001, S110 — reporting, never fatal
                    pass
                try:
                    graph.close()
                except Exception:  # noqa: BLE001, S110 — closing must not mask the real error
                    pass
            # Refusals this run produced. Read after the lock is released so
            # the log is complete, and selected by `run_id` rather than by
            # diffing a count taken beforehand — the count was right only
            # because nothing else may write while a run holds the lock, which
            # is a guarantee this reporting path should not have to depend on.
            try:
                if self.log_path.is_file():
                    new = read_refusals(self.log_path, run_id=run.id)
                    with run._lock:
                        run.refusals = [r.model_dump(mode="json") for r in new]
            except Exception:  # noqa: BLE001, S110 — reporting extra, never fatal
                pass
            with run._lock:
                run.ended_at = time.time()
            with self._lock:
                if self._current is run:
                    self._current = None

    def _run_turns(self, run: Run, assignments) -> list:
        """Drive `run_swarm` once, reporting progress per agent as it goes.

        The tempting shape — call `run_async(max_turns=1)` in a loop so each
        turn can be observed — is wrong: `run_async` builds its message list
        from scratch on entry, so every call would restart the conversation,
        discard all prior tool results, and pay the model to rediscover them.
        Progress reporting must not change what the agent knows. So the workers
        keep their single continuous loops and report outward through
        `on_tool_call`, and cancellation is checked by the same loops between
        turns via `should_stop`."""
        def on_tool_call(worker, entry: dict[str, Any]) -> None:
            with run._lock:
                calls = run.per_agent.setdefault(worker.authored_by, [])
                calls.append(entry)
                run.tool_calls = [*run.tool_calls, {**entry, "agent_id": worker.authored_by}]

        loop = asyncio.new_event_loop()
        try:
            asyncio.set_event_loop(loop)
            return loop.run_until_complete(
                run_swarm(
                    assignments, max_turns=run.max_turns,
                    on_tool_call=on_tool_call,
                    should_stop=run._cancel.is_set,
                )
            )
        finally:
            asyncio.set_event_loop(None)
            loop.close()
