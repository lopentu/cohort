"""A single agent that finds attestations for claims/conjectures via an
OpenRouter tool-use loop (design doc §5 principle 3: the agent's entire
world is read graph -> call a tool -> write back; no agent-to-agent
messaging, no shared transcript, no framework beyond the transport itself).

Replaces the Anthropic SDK entirely (docs/roadmap.md "Scope revision", OpenRouter
workstream) — see `cohort/agents/openrouter.py` for the transport and why it's
stdlib-only rather than a client library.

`run_async()` is the canonical loop (docs/roadmap.md "Scope revision",
agent-society axis step 4 — real concurrency); `run()` is a thin sync
wrapper. Safe to run several workers concurrently against one shared
`Graph`: `to_thread` is scoped only around the one blocking HTTP call in
`complete()`, and every `graph`/`source` call in `_dispatch()` runs
synchronously back on the event loop's own thread — a coroutine only yields
control at its own `to_thread` await, and no graph write is ever inside
that window, so concurrent workers' writes can never interleave with each
other. This also satisfies sqlite3's default same-thread restriction for
free, since `Graph`'s connection is only ever touched from the one thread
that created it.
"""
from __future__ import annotations

import asyncio
import json
import time
from typing import Any

from ..graph import Graph
from ..schemas import AgentProfile, EdgeType, NodeType
from ..sources.base import Source
from ..tools.find_attestations import DESCRIPTION as FIND_ATTESTATIONS_DESCRIPTION
from ..tools.find_attestations import NAME as FIND_ATTESTATIONS_NAME
from ..tools.find_attestations import FindAttestationsInput, find_attestations
from ..tools.collate_editions import DESCRIPTION as COLLATE_EDITIONS_DESCRIPTION
from ..tools.collate_editions import NAME as COLLATE_EDITIONS_NAME
from ..tools.collate_editions import CollateEditionsInput, collate_editions
from ..tools.link_parallels import DESCRIPTION as LINK_PARALLELS_DESCRIPTION
from ..tools.link_parallels import NAME as LINK_PARALLELS_NAME
from ..tools.link_parallels import LinkParallelsInput, link_parallels
from ..tools.record_contradiction import DESCRIPTION as RECORD_CONTRADICTION_DESCRIPTION
from ..tools.record_contradiction import NAME as RECORD_CONTRADICTION_NAME
from ..tools.record_contradiction import RecordContradictionInput, record_contradiction
from ..tools.propose_claim import DESCRIPTION as PROPOSE_CLAIM_DESCRIPTION
from ..tools.propose_claim import NAME as PROPOSE_CLAIM_NAME
from ..tools.propose_claim import ProposeClaimInput, propose_claim
from ..tools.propose_conjecture import DESCRIPTION as PROPOSE_CONJECTURE_DESCRIPTION
from ..tools.propose_conjecture import NAME as PROPOSE_CONJECTURE_NAME
from ..tools.propose_conjecture import ProposeConjectureInput, propose_conjecture
from ..tools.discriminator import (
    APPLY_DESCRIPTION,
    APPLY_NAME,
    CONTROL_DESCRIPTION,
    CONTROL_NAME,
    REGISTER_DESCRIPTION,
    REGISTER_NAME,
    ApplyToDisputedInput,
    RegisterDiscriminatorInput,
    RunControlTestInput,
    apply_to_disputed,
    register_discriminator,
    run_control_test,
)
from ..tools.place_work import DESCRIPTION as PLACE_WORK_DESCRIPTION
from ..tools.place_work import NAME as PLACE_WORK_NAME
from ..tools.place_work import PlaceWorkInput, place_work
from .openrouter import (
    DEFAULT_MAX_OUTPUT_TOKENS,
    complete,
    default_transport,
    load_openrouter_config,
)

#: bump whenever SYSTEM_PROMPT or TOOLS changes shape, so logged model_call
#: events can be grouped by which prompt/tool contract actually produced them.
PROMPT_VERSION = "attestation_worker/v6-ascription-tools"

SYSTEM_PROMPT = (
    "You are an attestation worker in COHORT, an evidence graph for textual "
    "research. Every tool you have writes to the graph through its own "
    "enforced rules — you cannot write structure any other "
    "way, and a call that violates a rule is refused and reported back to "
    "you, not silently dropped. Never invent a node id: every id you pass to "
    "a tool must be one a tool returned to you, or one already in the graph. "
    "propose_claim creates a claim — an assertion the sources state, which "
    "must cite passages — and requires a grounding query that is run against "
    "the corpus first; a query with no hits refuses the claim, because a "
    "claim with nothing to cite can never be attested. find_attestations "
    "searches the corpus for a claim or conjecture and records matching "
    "passages as evidence; use it on the id propose_claim returns. "
    "propose_conjecture proposes something the sources don't state outright, "
    "but requires a full dossier (derivation, corpus boundary, selection "
    "risks, alternative explanations), a prior-art query that is actually "
    "run against the corpus first, and a query that would confirm or "
    "refute the conjecture going forward — a conjecture proposed without "
    "the prospective query is refused. An absence — that something does not "
    "occur in the corpus — is a conjecture, not a claim, because only a "
    "retrieval can settle it. Call tools; do not narrate progress "
    "in text. Stop once you've made reasonable progress or run out of "
    "queries worth trying."
)


def _rejected_context(graph: Graph) -> str:
    """A summary of already-rejected claims/conjectures and why, so the
    worker doesn't repropose them.

    `witness`/`passage` don't need this: their rejection is already blocked
    mechanically at the write boundary via `canonical_ref` identity
    (`PersistentRejection`). `claim`/`conjecture` have no content-derived
    identity to block on — principle 5 forbids hashing agent-produced text
    into identity — so a rejected conjecture, reworded, would sail through
    a fresh `propose_conjecture` call unblocked. This is the mitigation:
    make the rejection visible to the model's own reasoning instead of
    faking an identity key for content the design deliberately declines to
    hash.
    """
    rejected = [
        n for t in (NodeType.CLAIM, NodeType.CONJECTURE) for n in graph.rejected(node_type=t)
    ]
    if not rejected:
        return ""
    lines = ["Already rejected by the researcher — do not repropose these or close variants of them:"]
    for n in rejected:
        text = n.payload.get("text", n.id)
        lines.append(f"- [{n.type}] {text!r} — reason: {n.rejected_reason or '(no reason recorded)'}")
    return "\n".join(lines)


def _profile_context(profile: AgentProfile | None) -> str:
    """Declared research commitments, not a cosmetic role prompt — distinct
    corpus/method scope per agent is what "viewpoint formation without
    persona theater" means (docs/roadmap.md "Scope revision", agent-society
    axis): the diversity has to come from what the agent is actually scoped
    to look at, not from a personality prompt layered on an identical view
    of the whole corpus."""
    if profile is None:
        return ""
    parts = []
    if profile.corpus_scope:
        parts.append(f"corpus scope: {profile.corpus_scope}")
    if profile.method_label:
        parts.append(f"method: {profile.method_label}")
    if not parts:
        return ""
    return "Your declared research commitments — " + "; ".join(parts) + "."


TOOLS = [
    {
        "type": "function",
        "function": {
            "name": PROPOSE_CLAIM_NAME,
            "description": PROPOSE_CLAIM_DESCRIPTION,
            "parameters": ProposeClaimInput.model_json_schema(),
        },
    },
    {
        "type": "function",
        "function": {
            "name": FIND_ATTESTATIONS_NAME,
            "description": FIND_ATTESTATIONS_DESCRIPTION,
            "parameters": FindAttestationsInput.model_json_schema(),
        },
    },
    {
        "type": "function",
        "function": {
            "name": PROPOSE_CONJECTURE_NAME,
            "description": PROPOSE_CONJECTURE_DESCRIPTION,
            "parameters": ProposeConjectureInput.model_json_schema(),
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
    # The stage-4 pair. Registered late and deliberately: both write structure
    # with real epistemic consequences, so the question was whether a model
    # should be able to mint a `parallel_of` edge at all — a wrong one
    # *suppresses* independent support, and edges have no retraction.
    #
    # What settles it is that neither tool takes a judgement as input. Both
    # accept only a `witness_id`; the content comes from the corpus's own
    # `<cb:docNumber>` and `<app>` markup, and `link_parallels` already refuses
    # `cf.`/`Part of` references, ambiguous Taisho resolutions, and witnesses
    # absent from the graph. The model chooses *what to read*, not *what is
    # true*, which is the same discretion `find_attestations` already has.
    {
        "type": "function",
        "function": {
            "name": LINK_PARALLELS_NAME,
            "description": LINK_PARALLELS_DESCRIPTION,
            "parameters": LinkParallelsInput.model_json_schema(),
        },
    },
    {
        "type": "function",
        "function": {
            "name": COLLATE_EDITIONS_NAME,
            "description": COLLATE_EDITIONS_DESCRIPTION,
            "parameters": CollateEditionsInput.model_json_schema(),
        },
    },
]

#: Offered only when the server was started against an ascription study, and
#: the conditional is the point. These four are the *method* for an attribution
#: question — register a prediction, survive a negative control, only then
#: speak about a work in doubt — and `apply_to_disputed` refuses until the
#: control has passed. A worker on a graph with no catalogue would meet a tool
#: that can do nothing but refuse, and spend a turn learning that.
#:
#: The ordering here is the ordering they must be called in, and it is stated
#: again in `STUDY_PROMPT` because a model reads the prompt and skims the
#: schema list.
STUDY_TOOLS = [
    {
        "type": "function",
        "function": {
            "name": REGISTER_NAME,
            "description": REGISTER_DESCRIPTION,
            "parameters": RegisterDiscriminatorInput.model_json_schema(),
        },
    },
    {
        "type": "function",
        "function": {
            "name": CONTROL_NAME,
            "description": CONTROL_DESCRIPTION,
            "parameters": RunControlTestInput.model_json_schema(),
        },
    },
    {
        "type": "function",
        "function": {
            "name": APPLY_NAME,
            "description": APPLY_DESCRIPTION,
            "parameters": ApplyToDisputedInput.model_json_schema(),
        },
    },
    {
        "type": "function",
        "function": {
            "name": PLACE_WORK_NAME,
            "description": PLACE_WORK_DESCRIPTION,
            "parameters": PlaceWorkInput.model_json_schema(),
        },
    },
]


def _study_context(study) -> str:
    """What this study actually contains, so the model does not have to guess
    a label or a work id and get refused for it.

    Named groups and their sizes rather than the full membership: the
    catalogue can run to hundreds of works, and a worker that needs one by
    name can ask the corpus. What it cannot guess is the *labels*, which are a
    researcher's choice — `apply_to_disputed` takes one as an argument, and a
    wrong one is a refusal that teaches nothing.
    """
    if study is None:
        return ""
    cat = study.catalogue
    groups = ", ".join(
        f"{label} ({len(cat.works(label))} works)" for label in cat.labels()
    )
    return (
        "An ascription study is open on this graph. Its catalogue names: "
        f"{groups}. The benchmark group is {cat.benchmark_label!r} — the works "
        f"believed to belong — and {cat.control_label!r} is the negative "
        "control: works believed NOT to belong, which earlier methods could "
        "not separate from the benchmark.\n\n"
        "The order of the ascription tools is the method, and it is enforced. "
        "register_discriminator records a prediction about a feature before "
        "anything is counted. run_control_test counts and compares against "
        "that prediction; most candidates fail here, and a failure is a result "
        "to record, not a call to retry with a lower threshold — moving the "
        "prediction after seeing the numbers is the error this whole ordering "
        "exists to prevent. apply_to_disputed is refused outright until the "
        "control has passed. place_work measures a work's distance from the "
        "benchmark and is independent of that chain, but needs a claim or "
        "conjecture to record against, so propose one first.\n\n"
        "Prefer features that could track a translator's register — discourse "
        "particles, connectives, formulaic openings — over doctrinal "
        "vocabulary, which tracks what a text is about rather than who "
        "rendered it."
    )


class AttestationWorker:
    #: The three pieces that make this worker *this* role, as class attributes
    #: so a differently-roled agent can be a subclass rather than a copy of the
    #: tool loop. `ReviewWorker` overrides all three plus `_dispatch`; the
    #: loop itself — budget, refusal logging, model-call accounting, the
    #: concurrency argument in this module's docstring — is identical for
    #: every role and must not be forked.
    SYSTEM_PROMPT = SYSTEM_PROMPT
    TOOLS = TOOLS
    PROMPT_VERSION = PROMPT_VERSION

    def __init__(
        self,
        graph: Graph,
        source: Source,
        *,
        authored_by: str,
        model: str | None = None,
        api_key: str | None = None,
        transport=None,
        profile: AgentProfile | None = None,
        max_output_tokens: int | None = DEFAULT_MAX_OUTPUT_TOKENS,
        question_id: str | None = None,
        study=None,
    ) -> None:
        if model is None or api_key is None:
            config_key, config_model = load_openrouter_config()
            api_key = api_key if api_key is not None else config_key
            model = model if model is not None else config_model
        self.max_output_tokens = max_output_tokens
        self.graph = graph
        self.source = source
        self.authored_by = authored_by
        self.model = model
        self.api_key = api_key
        self.transport = transport or default_transport
        self.profile = profile

        #: An open ascription study, or None. Its presence is what decides
        #: whether this worker is offered the four ascription tools —
        #: `self.tools`, not `self.TOOLS`, is what the loop sends. The class
        #: attribute stays the role's fixed set so a subclass can still declare
        #: its own; this is the per-instance extension, which is the right
        #: shape because whether a study is open is a property of the server
        #: this run happens on, not of the role the agent plays.
        self.study = study
        self.tools = [*self.TOOLS, *STUDY_TOOLS] if study is not None else list(self.TOOLS)

        #: the question this worker was asked, if any. Every claim or
        #: conjecture it proposes gets an `addresses` edge to it — recording
        #: that the assertion was put forward *as an answer to this*, which is
        #: a fact about how the work happened and not an inference about
        #: whether it succeeded. Without it an auto-planned run answers a
        #: question and leaves nothing in the graph connecting the two, so the
        #: question reads as unaddressed and the claims read as unprompted.
        self.question_id = question_id

    def run(self, instructions: str, *, max_turns: int = 6) -> list[dict[str, Any]]:
        """Sync convenience wrapper around `run_async()`, for single-worker
        callers (tests, `demo.py`, `scripts/smoke_openrouter.py`) that don't
        want to deal with asyncio themselves. Refuses to run if called from
        inside an already-running event loop (e.g. by mistake, from inside
        a swarm's own loop) with a clear message, rather than letting
        `asyncio.run()`'s generic error surface from an unrelated line."""
        try:
            asyncio.get_running_loop()
        except RuntimeError:
            return asyncio.run(self.run_async(instructions, max_turns=max_turns))
        raise RuntimeError(
            f"{type(self).__name__}.run() cannot be called from inside a running "
            "event loop — use run_async() directly (e.g. from run_swarm())"
        )

    async def run_async(
        self, instructions: str, *, max_turns: int = 6,
        on_tool_call=None, should_stop=None,
    ) -> list[dict[str, Any]]:
        """Runs a tool-use loop against `instructions`. Returns the list of
        tool calls made (name, args, and either the result or the refusal),
        in order — this is the worker's own audit trail of its turn.

        Prepends, in order: the worker's own declared corpus/method scope
        if it has a `profile` (see `_profile_context`), then a summary of
        already-rejected claims/conjectures, if any (see
        `_rejected_context`) — this is what makes persistent rejection hold
        across a live loop for content that has no identity to block on
        mechanically.

        Safe to await concurrently alongside other workers against the same
        `Graph` — see this module's docstring for why.

        `on_tool_call(entry)` fires after each tool call with that call's log
        entry, and `should_stop()` is consulted between turns; both default to
        absent, so a script's behaviour is unchanged. They exist because a
        caller watching a run in progress (the web UI) needs partial results
        *and* a way out, and the alternative — calling this repeatedly with
        `max_turns=1` — would silently restart the conversation each time,
        throwing away every prior tool result and paying the model to
        rediscover it. Progress reporting must not change what the agent
        knows."""
        parts = [
            p for p in (
                _profile_context(self.profile),
                _study_context(self.study),
                _rejected_context(self.graph),
            ) if p
        ]
        full_instructions = "\n\n".join([*parts, instructions]) if parts else instructions
        messages: list[dict] = [
            {"role": "system", "content": self.SYSTEM_PROMPT},
            {"role": "user", "content": full_instructions},
        ]
        log: list[dict[str, Any]] = []

        for _ in range(max_turns):
            if should_stop is not None and should_stop():
                break
            started = time.monotonic()
            response = await asyncio.to_thread(
                complete, self.model, messages, self.tools, api_key=self.api_key,
                transport=self.transport, max_output_tokens=self.max_output_tokens,
            )
            latency_ms = int((time.monotonic() - started) * 1000)
            call_event = self.graph.log_model_call(
                authored_by=self.authored_by, model=response.model, provider="openrouter",
                prompt_version=self.PROMPT_VERSION, latency_ms=latency_ms,
                input_tokens=response.usage.prompt_tokens,
                output_tokens=response.usage.completion_tokens,
                cost_usd=response.usage.cost,
            )
            choice = response.choices[0]
            messages.append({
                "role": "assistant",
                "content": choice.message.content,
                "tool_calls": [tc.model_dump() for tc in (choice.message.tool_calls or [])],
            })

            if choice.finish_reason != "tool_calls":
                break

            for tc in choice.message.tool_calls or []:
                args = json.loads(tc.function.arguments)
                is_error, result = self._dispatch(tc.function.name, args, call_event.seq)
                entry = {
                    "tool": tc.function.name, "args": args,
                    "result": result, "is_error": is_error,
                }
                log.append(entry)
                if on_tool_call is not None:
                    on_tool_call(entry)
                messages.append({
                    "role": "tool",
                    "tool_call_id": tc.id,
                    "content": json.dumps({"is_error": is_error, "result": result}, default=str),
                })

        return log

    def _address(self, node_id: str, model_call_id: int | None) -> str:
        """Links a fresh assertion to the question this worker was asked.

        Done here rather than as a tool argument, because an agent that had to
        remember to pass the question id would sometimes not, and a question
        whose answers are only *sometimes* attached to it is worse than one
        with none — it reads as a tally.

        A failure here is swallowed on purpose. The assertion is already
        written and its id is already going back to the model; raising would
        turn a successful proposal into a tool error and invite the model to
        propose it again. The refusal is logged, so a missing edge is
        answerable from the log rather than being silently absent.
        """
        if not self.question_id:
            return node_id
        try:
            self.graph.add_edge(
                EdgeType.ADDRESSES, node_id, self.question_id,
                authored_by=self.authored_by, model_call_id=model_call_id,
            )
        except Exception as e:  # noqa: BLE001 — see docstring
            self.graph.log_refusal(
                "address_question", self.authored_by, e,
                node_id=node_id, model_call_id=model_call_id,
            )
        return node_id

    def _dispatch(self, name: str, args: dict, model_call_id: int | None = None) -> tuple[bool, Any]:
        """Returns (is_error, result). A CohortError (a refused write) is
        reported back to the model as a tool error, not raised — the worker
        should see refusals and adjust, the same way the audit log does.

        Every refused tool call is also recorded to the event log here, not
        just returned. `graph._refuse()` covers rules the write boundary
        enforces on a write it was asked to make, but a tool call can be
        refused before reaching it — most commonly a node id that does not
        exist, which `get_node` raises from a *lookup*. The live conjecture
        run lost five such refusals that way: the model saw them, adapted,
        and the log recorded a clean run, which understates what the system
        actually did. `log_refusal()` is idempotent with `_refuse()`, so a
        write-boundary refusal is still one event, not two."""
        try:
            if name == PROPOSE_CLAIM_NAME:
                parsed = ProposeClaimInput.model_validate(args)
                return False, self._address(propose_claim(
                    self.graph, self.source, parsed, authored_by=self.authored_by,
                    model_call_id=model_call_id,
                ), model_call_id)
            if name == FIND_ATTESTATIONS_NAME:
                parsed = FindAttestationsInput.model_validate(args)
                return False, find_attestations(
                    self.graph, self.source, parsed, authored_by=self.authored_by,
                    model_call_id=model_call_id,
                ).model_dump(mode="json")
            if name == PROPOSE_CONJECTURE_NAME:
                parsed = ProposeConjectureInput.model_validate(args)
                return False, self._address(propose_conjecture(
                    self.graph, self.source, parsed, authored_by=self.authored_by,
                    model_call_id=model_call_id,
                ), model_call_id)
            if name == LINK_PARALLELS_NAME:
                parsed = LinkParallelsInput.model_validate(args)
                return False, link_parallels(
                    self.graph, self.source, parsed, authored_by=self.authored_by,
                    model_call_id=model_call_id,
                ).model_dump(mode="json")
            if name == COLLATE_EDITIONS_NAME:
                parsed = CollateEditionsInput.model_validate(args)
                return False, collate_editions(
                    self.graph, self.source, parsed, authored_by=self.authored_by,
                    model_call_id=model_call_id,
                )
            if name == RECORD_CONTRADICTION_NAME:
                parsed = RecordContradictionInput.model_validate(args)
                return False, record_contradiction(
                    self.graph, parsed, authored_by=self.authored_by,
                    model_call_id=model_call_id,
                )
            # The four ascription tools, when a study is open. Routed by name
            # rather than by `self.study is not None`, so calling one against a
            # server that has no study answers with what is missing instead of
            # "unknown tool" — which would read as the model having invented a
            # name it was in fact handed on some other server.
            if name in _STUDY_TOOL_NAMES:
                return self._dispatch_study(name, args, model_call_id)
            return True, f"unknown tool: {name}"
        except Exception as e:  # noqa: BLE001 — deliberately broad: report to the model, don't crash the loop
            self.graph.log_refusal(
                name, self.authored_by, e,
                node_id=(
                    args.get("claim_or_conjecture_id")
                    or args.get("conjecture_id")
                    or args.get("witness_id")
                    or args.get("node_a_id")
                ),
                model_call_id=model_call_id,
            )
            return True, f"{type(e).__name__}: {e}"

    def _dispatch_study(self, name: str, args: dict, model_call_id: int | None) -> tuple[bool, Any]:
        """The four ascription tools. Split out of `_dispatch` rather than
        inlined because they share one precondition — an open study — and
        because a reader of `_dispatch` should be able to see the six tools
        every worker always has without four conditionally-registered ones
        interleaved among them.

        Raises rather than returning an error tuple: the caller's `except`
        already turns an exception into a tool error *and* logs the refusal,
        and returning early here would skip the logging.
        """
        if self.study is None:
            raise RuntimeError(
                f"{name} needs an ascription study, and this graph has none "
                "open. The server was started without one; a catalogue naming "
                "a benchmark group and a negative control is what these tools "
                "test against"
            )
        study, catalogue = self.study, self.study.catalogue
        if name == REGISTER_NAME:
            return False, register_discriminator(
                self.graph, RegisterDiscriminatorInput.model_validate(args),
                catalogue=catalogue, authored_by=self.authored_by,
                model_call_id=model_call_id,
            )
        if name == CONTROL_NAME:
            parsed = RunControlTestInput.model_validate(args)
            out = run_control_test(
                self.graph, study.corpus, parsed.conjecture_id, catalogue=catalogue,
                base_edition=parsed.base_edition, min_chars=parsed.min_chars,
                authored_by=self.authored_by, model_call_id=model_call_id,
            )
            # The measurement objects are dataclasses over every catalogued
            # work; sending them back would spend hundreds of tokens per call
            # on rows the model has no use for. What it needs is whether the
            # prediction held and by how much, which is in the two summaries
            # and the sentence the verification already recorded.
            return False, {
                "verification_id": out["verification_id"],
                "result": out["result"],
                "benchmark": _tally(out["benchmark"]),
                "control": _tally(out["control"]),
            }
        if name == APPLY_NAME:
            parsed = ApplyToDisputedInput.model_validate(args)
            out = apply_to_disputed(
                self.graph, study.corpus, parsed.conjecture_id, catalogue=catalogue,
                disputed_label=parsed.disputed_label, base_edition=parsed.base_edition,
                min_chars=parsed.min_chars, authored_by=self.authored_by,
                model_call_id=model_call_id,
            )
            return False, {
                "verification_id": out["verification_id"],
                "feature": out["feature"],
                "disputed_label": out["disputed_label"],
                "works": out["works"],
            }
        if name == PLACE_WORK_NAME:
            return False, place_work(
                self.graph, study, PlaceWorkInput.model_validate(args),
                authored_by=self.authored_by, model_call_id=model_call_id,
            )
        return True, f"unknown study tool: {name}"


def _tally(summary) -> dict | None:
    """A `LabelSummary` as the four numbers a model needs, without its `rates`
    tuple — one float per work, which for a benchmark of 23 is 23 numbers the
    model cannot do anything with that the share does not already say."""
    if summary is None:
        return None
    return {
        "label": summary.label,
        "works_measured": summary.works_measured,
        "works_attesting": summary.works_attesting,
        "works_skipped_short": summary.works_skipped_short,
        "share_attesting": summary.share_attesting,
    }


#: Which tool names `_dispatch_study` answers for. Derived from `STUDY_TOOLS`
#: rather than written out again, so a tool added to the schema list without a
#: dispatch case reaches `_dispatch_study` and gets a named error, instead of
#: falling through to "unknown tool" and looking like the model hallucinated it.
_STUDY_TOOL_NAMES = frozenset(t["function"]["name"] for t in STUDY_TOOLS)
