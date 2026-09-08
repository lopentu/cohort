# Agents, swarms and spend

The agent layer is `cohort/agents/`. It has **no client library**: OpenRouter
over stdlib `urllib.request`, so nothing here adds a dependency
([roadmap.md](roadmap.md) tech stack).

## The worker

`AttestationWorker` runs a tool-use loop over the six registered tools
([tools.md](tools.md)). Nothing heavier: the tool layer is already the
constraint surface, so a framework would add machinery the design doesn't need.

    worker = AttestationWorker(graph, source, agent_id="agent:me",
                               profile=AgentProfile(...))
    log = await worker.run_async(instructions, max_turns=8,
                                 on_tool_call=..., should_stop=...)

`on_tool_call` fires per call so a caller can stream progress; `should_stop` is
checked between turns so a run can be stopped without killing it mid-write.

> A worker's turns must run in **one** `run_async` call. Calling it repeatedly
> with `max_turns=1` restarts the conversation each time and discards every
> prior tool result — which is why the callbacks exist instead.

A worker's `profile` declares **corpus scope** and **method label**. These are
prepended to its instructions and recorded on the agent, so two agents that
disagree disagree from declared positions. That is what makes disagreement
meaningful rather than cosmetic.

`agent_report()` returns a pure contribution count — proposed, attested,
rejected. It is **deliberately not a reputation score**; see
[design.md](design.md) §9.

## The reviewer

`ReviewWorker` is the same tool loop with a different role: it checks claims
other agents wrote, and cannot write one itself. It exists because
`Graph.attest()` refuses a self-attestation
([vocabulary.md](vocabulary.md)) — the refused work has to fall to somebody.

    from cohort.agents.review_worker import ReviewWorker
    reviewer = ReviewWorker(graph, source, authored_by="agent:reviewer",
                            model="deepseek/deepseek-v4-flash")

**A reviewer is not a second model whose agreement counts as evidence.**
`VerificationMethod` excludes `MODEL_ENTAILMENT` deliberately — "a second
model's opinion is still another agent's opinion" — and an entailment judge
would reintroduce exactly the consensus-seeking the design argues against. So
the reviewer's evidence is mechanical: `review_claim` re-fetches every cited
passage and re-locates its excerpt against the freshly fetched source.

**Its judgment can only subtract.** Promotion needs the spans to re-verify
*and* the reviewer not to object. An objection withholds attestation; no
amount of model agreement supplies one.

| reviewer says | spans re-verify | result |
|---|---|---|
| sound | yes | attested |
| sound | **no** | **not attested** — a verdict cannot outvote the bytes |
| unsound / indeterminate | yes | not attested; the objection recorded in `limitations` |
| anything | no citations | nothing to re-check, nothing advanced |

Two tools only — `review_claim` and `record_contradiction`. No `propose_*`: a
checker that authors claims accumulates work it is then barred from checking,
and on a small roster "everyone reviews everyone" is peer review in name only.
The restriction is the tool list, not the prompt, so there is no instruction
for a model to talk itself out of.

**Reviewers run after the workers**, in a second phase — a reviewer launched
alongside them would start before any claim existed. What there is to review is
appended to its instructions at that point by `pending_review_context()`, since
the browser and the CLI cannot know it when the run is configured. A reviewer
with nothing to review is **skipped, not billed**, and reported as a note
rather than an error.

    cohort run --agent "find attestations for 色即是空" --model z-ai/glm-5.3 \
               --reviewer "check what the worker proposed" \
                 --reviewer-model deepseek/deepseek-v4-flash \
               --budget 0.05

In the UI: **+ Add reviewer** beside **+ Add agent**.

## Swarms

    from cohort.agents.swarm import run_swarm
    results = await run_swarm([(worker_a, task_a), (worker_b, task_b)],
                              max_turns=6, on_tool_call=..., should_stop=...)

Agents share one `Graph` and communicate **only through it** — no messaging, no
shared transcript ([design.md](design.md) §5 principle 3). This buys three
things: every contribution has an author, cost is linear rather than quadratic
in agent count, and the researcher can pause the whole system because the entire
shared state is one inspectable object.

`asyncio.to_thread` is scoped around only the blocking HTTP call, so model calls
overlap while graph writes cannot interleave. Failures are isolated with
`return_exceptions=True`: one agent's transport error is reported against that
agent rather than failing the run.

## Agents in one run may not share a model family

Enforced at the run boundary, before any request is made:

    cohort run --agent "…" --model z-ai/glm-5.3-flash \
               --agent "…" --model deepseek/deepseek-v4-flash

A roster whose agents share a provider prefix is **refused**, naming which
agents clashed. The reason is this project's own argument, applied to itself:
two agents on one model share training priors and prompt-shaped convergence, so
their agreement is one observation reported twice — exactly what
`independent_support()` exists to catch between witnesses, committed one layer
up between readers. Declared viewpoint diversity is only real if the readers
differ.

Set the pool with `OPENROUTER_MODELS` (comma-separated); `OPENROUTER_MODEL`
stays the single-agent default, and a one-agent run is always allowed — with
nothing to agree with, shared priors cannot manufacture corroboration.

**What "family" means, and what it cannot mean.** The provider prefix of the
OpenRouter id: `z-ai/glm-5.3` and `z-ai/glm-5.3-flash` are one family. This is a
heuristic, stated as one. It catches the ordinary case — a roster filled from
one provider — and **cannot** catch the same weights served under two provider
names. It is a floor on independence, not a proof of it.

The model is recorded on each agent's profile, so the graph says what produced
what rather than leaving it to be assumed.

**Fan-out is not a headline.** Agent count is allowed to grow only when it
demonstrates declared viewpoint diversity — scale for its own sake is the thing
being critiqued, not the claim being made.

## Spend is capped in code, not estimated

`cohort/agents/budget.py`. This is the only part of the system that spends
money, and the design follows from that.

    transport = BudgetedTransport(budget_usd=0.50, unknown_call_cost=0.01,
                                  on_call=...)

Two properties that matter more than they look:

- **The cap is checked *before* a request**, not after. A cap enforced
  afterwards is a report, not a cap.
- **A response reporting no cost is charged the estimate**, not treated as free.
  Unpriced calls are counted and surfaced, so a displayed total is an honest
  lower bound rather than a silent undercount. This has fired in practice: a
  malformed provider response was charged $0.01 exactly as designed.

A third bound sits under both: **every request carries an output-token
ceiling** (`DEFAULT_MAX_OUTPUT_TOKENS = 2800`), because nothing bounded model
output until 2026-09-02. That is a cost bound rather than a correctness one —
the budget is still the hard stop; the ceiling keeps one call from consuming an
unreasonable share of it. Lifting it means passing `None` deliberately.

`BudgetExceeded` stops the run. `snapshot()` gives live spend, which is why the
UI can show a bar filling rather than a total at the end — a cap you cannot
watch approaching is one you only learn about by hitting it.

## Runs from the UI

`cohort/ui/runs.py` wraps all of the above for the browser, keeping the scripts'
guarantees rather than reimplementing them.

| Bound | Default | Why |
|---|---|---|
| `max_budget_usd` | 1.00 | the browser proposes; the server bounds |
| `max_turns` | 8 | per agent |
| `max_agents` | 4 | past a handful the count becomes the claim rather than the mechanism |

One run may hold several `AgentSpec`s, and they share **one** graph, **one**
lock and **one** budget. Three separate budgets would mean the number you typed
bounded none of them.

See [ui.md](ui.md) for the HTTP surface.

## Live scripts and their costs

Everything under `scripts/` that calls a model is **manual-only and never run by
the test suite**. Each names its own cost in its docstring. The full list, with
prerequisites, is in [cli.md](cli.md).

Observed costs, for calibration:

| Run | Cost |
|---|---|
| `smoke_openrouter.py` — one call | ~$0.0002 |
| browser-launched single agent, 4 calls | $0.00236 |
| `run_conjecture_demo.py` — live conjecture | ~$0.004 |
| browser-launched 2-agent swarm, 16 calls, 62.8s | $0.00336 |

Set `OPENROUTER_API_KEY` and `OPENROUTER_MODEL` in `.env`. **Never paste a real
key into a chat session.**

### Recorded action purposes

Worker tool calls require `action_reason`: a brief, researcher-facing explanation
of the chosen action and inputs. The runner refuses a missing or blank explanation
before dispatch. This records the worker's stated purpose; it does not validate
that purpose or expose private model reasoning. Direct Python tool calls retain
their existing signatures.

`tool_action` and `tool_result` are non-mutating audit events. The first records
the purpose before execution; the second records the outcome and a bounded metadata
summary without bulk excerpts. They replay without adding evidence nodes or edges.
A missing result means the outcome was not recorded, not that the action succeeded.
The shared run-history reader reconstructs these actions for both CLI and UI.
Older events are unchanged and have no retroactively generated explanations.

### Read-only view analysis

The `analyst` run role explains a Graph or Evidence view and can investigate with
`inspect_node`, `search_corpus`, `read_source`, and configured Evidence tools.
It has no proposal, attestation, review or researcher-decision tools. Its calls,
stated reasons and final interpretation are saved as audit events; `analysis`
events do not create evidence nodes or change their status. The interpretation
is model output, not a verified finding. It remains the researcher's job to assess
it. The role uses the existing single-run scheduler and can hit its turn limit.

The UI's **Analyze this view** opens controls; **Start analysis** launches the paid
model calls. Graph sends its visible record IDs and activity as starting context;
Evidence sends the current text, vocabulary, highlighting pair and exclusions.
The analyst may investigate beyond that starting view using read-only tools.
CLI equivalent: `cohort run --analyze --agent 'Explain claim:... using its citations'`
(with the usual corpus/model configuration). `--json` includes the interpretation,
and run history preserves it across restarts. No output-token ceiling is sent.
