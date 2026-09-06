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

from cohort.graph import Graph
from cohort.schemas import AgentProfile, EdgeType, NodeType
from cohort.sources.base import Source
from cohort.tools.align_passages import DESCRIPTION as ALIGN_PASSAGES_DESCRIPTION
from cohort.tools.align_passages import NAME as ALIGN_PASSAGES_NAME
from cohort.tools.align_passages import AlignPassagesInput, align_passages
from cohort.tools.attribution_evidence import DESCRIPTION as ATTRIBUTION_EVIDENCE_DESCRIPTION
from cohort.tools.attribution_evidence import NAME as ATTRIBUTION_EVIDENCE_NAME
from cohort.tools.attribution_evidence import AttributionEvidenceInput, attribution_evidence
from cohort.tools.collate_editions import DESCRIPTION as COLLATE_EDITIONS_DESCRIPTION
from cohort.tools.collate_editions import NAME as COLLATE_EDITIONS_NAME
from cohort.tools.collate_editions import CollateEditionsInput, collate_editions
from cohort.tools.find_attestations import DESCRIPTION as FIND_ATTESTATIONS_DESCRIPTION
from cohort.tools.find_attestations import NAME as FIND_ATTESTATIONS_NAME
from cohort.tools.find_attestations import FindAttestationsInput, find_attestations
from cohort.tools.link_parallels import DESCRIPTION as LINK_PARALLELS_DESCRIPTION
from cohort.tools.link_parallels import NAME as LINK_PARALLELS_NAME
from cohort.tools.link_parallels import LinkParallelsInput, link_parallels
from cohort.tools.propose_claim import DESCRIPTION as PROPOSE_CLAIM_DESCRIPTION
from cohort.tools.propose_claim import NAME as PROPOSE_CLAIM_NAME
from cohort.tools.propose_claim import ProposeClaimInput, propose_claim
from cohort.tools.propose_conjecture import DESCRIPTION as PROPOSE_CONJECTURE_DESCRIPTION
from cohort.tools.propose_conjecture import NAME as PROPOSE_CONJECTURE_NAME
from cohort.tools.propose_conjecture import ProposeConjectureInput, propose_conjecture
from cohort.tools.record_contradiction import DESCRIPTION as RECORD_CONTRADICTION_DESCRIPTION
from cohort.tools.record_contradiction import NAME as RECORD_CONTRADICTION_NAME
from cohort.tools.record_contradiction import RecordContradictionInput, record_contradiction
from cohort.tools.semantic_neighbors import DESCRIPTION as SEMANTIC_NEIGHBORS_DESCRIPTION
from cohort.tools.semantic_neighbors import NAME as SEMANTIC_NEIGHBORS_NAME
from cohort.tools.semantic_neighbors import SemanticNeighborsInput, semantic_neighbors

from .openrouter import (
    DEFAULT_MAX_OUTPUT_TOKENS,
    complete,
    default_transport,
    load_openrouter_config,
    output_limits_from_env,
)

#: bump whenever SYSTEM_PROMPT or TOOLS changes shape, so logged model_call
#: events can be grouped by which prompt/tool contract actually produced them.
PROMPT_VERSION = "attestation_worker/v6-evidence-tools"

SYSTEM_PROMPT = (
    "You are an attestation worker in COHORT, an evidence graph for textual "
    "research. You have exactly three tools, all of which write to the graph "
    "through its own enforced rules — you cannot write structure any other "
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


#: The evidence tools are read-only views over Radich's corpus and its
#: embeddings. They are registered per worker, only when the server was given
#: that data (`attribution`, `embeddings`), because a tool that always answers
#: "not configured" teaches a model to stop calling tools.
EVIDENCE_TOOLS = {
    ATTRIBUTION_EVIDENCE_NAME: {
        "type": "function",
        "function": {
            "name": ATTRIBUTION_EVIDENCE_NAME,
            "description": ATTRIBUTION_EVIDENCE_DESCRIPTION,
            "parameters": AttributionEvidenceInput.model_json_schema(),
        },
    },
    ALIGN_PASSAGES_NAME: {
        "type": "function",
        "function": {
            "name": ALIGN_PASSAGES_NAME,
            "description": ALIGN_PASSAGES_DESCRIPTION,
            "parameters": AlignPassagesInput.model_json_schema(),
        },
    },
    SEMANTIC_NEIGHBORS_NAME: {
        "type": "function",
        "function": {
            "name": SEMANTIC_NEIGHBORS_NAME,
            "description": SEMANTIC_NEIGHBORS_DESCRIPTION,
            "parameters": SemanticNeighborsInput.model_json_schema(),
        },
    },
}

#: Appended to the system prompt when the evidence tools are present: the
#: contract that keeps a model from turning a frequency table into a verdict.
EVIDENCE_CONTRACT = (
    "\n\nYou also have read-only evidence tools over Radich's corpus. "
    "attribution_evidence reports where one unit's short strings lean between "
    "translator profiles, with raw counts; semantic_neighbors finds passages in "
    "other works with the same content; align_passages measures verbatim overlap "
    "between two units, with offsets you can cite. Chain them: a leaning, then the "
    "texts it might depend on, then the overlap that would explain it, then "
    "attribution_evidence again with the dependent unit withheld. Never propose a "
    "translator as a claim: the tools give a leaning, not an attribution. Propose "
    "what the corpus can settle -- that one text reproduces another's wording, "
    "cited by the shared run -- as a claim, and anything about who translated a "
    "text only as a conjecture whose refutation test is the recomputation with the "
    "dependent unit withheld. State two explanations where two exist: a shared hand, "
    "and a shared source or quotation."
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
    EVIDENCE_TOOLS_ALLOWED = True

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
        reasoning_effort: str | None = None,
        question_id: str | None = None,
        attribution=None,
        embeddings=None,
    ) -> None:
        self.attribution = attribution
        self.embeddings = embeddings
        # The tool list is per instance: the role's tools, plus the evidence
        # tools when their data is present. A reviewer keeps its own list.
        self.tools = list(self.TOOLS)
        self.system_prompt = self.SYSTEM_PROMPT
        if self.EVIDENCE_TOOLS_ALLOWED and attribution is not None:
            self.tools.append(EVIDENCE_TOOLS[ATTRIBUTION_EVIDENCE_NAME])
            self.tools.append(EVIDENCE_TOOLS[ALIGN_PASSAGES_NAME])
            if embeddings is not None:
                self.tools.append(EVIDENCE_TOOLS[SEMANTIC_NEIGHBORS_NAME])
            self.system_prompt = self.SYSTEM_PROMPT + EVIDENCE_CONTRACT
        if model is None or api_key is None:
            config_key, config_model = load_openrouter_config()
            api_key = api_key if api_key is not None else config_key
            model = model if model is not None else config_model
        # The module default means "whatever the environment says"; an explicit
        # number is a caller's decision and is kept.
        env_ceiling, env_effort = output_limits_from_env()
        if max_output_tokens == DEFAULT_MAX_OUTPUT_TOKENS:
            max_output_tokens = env_ceiling
        self.max_output_tokens = max_output_tokens
        self.reasoning_effort = reasoning_effort if reasoning_effort is not None else env_effort
        self.graph = graph
        self.source = source
        self.authored_by = authored_by
        self.model = model
        self.api_key = api_key
        self.transport = transport or default_transport
        self.profile = profile

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
            p for p in (_profile_context(self.profile), _rejected_context(self.graph)) if p
        ]
        full_instructions = "\n\n".join([*parts, instructions]) if parts else instructions
        messages: list[dict] = [
            {"role": "system", "content": self.system_prompt},
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
                reasoning_effort=self.reasoning_effort,
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
            assistant: dict[str, Any] = {
                "role": "assistant",
                "content": choice.message.content,
                "tool_calls": [tc.model_dump() for tc in (choice.message.tool_calls or [])],
            }
            if choice.message.reasoning_details:
                # Echoed back verbatim: a reasoning model's tool call is only
                # valid to the provider together with the thinking that made it.
                assistant["reasoning_details"] = choice.message.reasoning_details
            messages.append(assistant)

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
        except Exception as e:
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
            # The evidence tools read and never write, so a failure is reported
            # to the model and logged like any other refused call, but it is
            # not a write-boundary refusal.
            if name == ATTRIBUTION_EVIDENCE_NAME and self.attribution is not None:
                return False, attribution_evidence(
                    self.attribution, AttributionEvidenceInput.model_validate(args),
                )
            if name == ALIGN_PASSAGES_NAME and self.attribution is not None:
                return False, align_passages(
                    self.attribution, AlignPassagesInput.model_validate(args),
                )
            if name == SEMANTIC_NEIGHBORS_NAME and self.embeddings is not None and self.attribution is not None:
                return False, semantic_neighbors(
                    self.embeddings, self.attribution, SemanticNeighborsInput.model_validate(args),
                )
            return True, f"unknown tool: {name}"
        except Exception as e:
            self.graph.log_refusal(
                name, self.authored_by, e,
                node_id=(
                    args.get("claim_or_conjecture_id")
                    or args.get("witness_id")
                    or args.get("node_a_id")
                ),
                model_call_id=model_call_id,
            )
            return True, f"{type(e).__name__}: {e}"
