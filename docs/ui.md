# The researcher UI

The same functionality as the Python API, in a browser. That parity is the
point: COHORT should be usable as a library by people who write Python, and as a
tool by researchers who don't.

    .venv/bin/pip install -e '.[ui]'
    cd cohort/ui/frontend && npm install && npm run build && cd -
    .venv/bin/python scripts/seed_demo_graph.py          # needs the corpus
    .venv/bin/python scripts/serve_ui.py --db demo_graph.sqlite

Open <http://127.0.0.1:8000>.

## Capabilities are opt-in separately

Because they carry different consequences: reading the corpus is free, accepting
a finding is a scholarly act, and starting an agent run spends money.

| Flag | Enables |
|---|---|
| *(none)* | read-only graph, provenance, refusal log |
| `--corpus` | corpus browse and search |
| `--allow-writes` | accept / reject / reopen |
| `--allow-runs` | the Inquiry launcher (`--max-budget` caps each run) |

Without a flag the routes are **not mounted at all** — a disabled capability
returns 404 rather than a 403, because the server simply doesn't have it.

It binds `127.0.0.1` by default and deliberately: the corpus behind the graph is
licence-restricted. Over SSH, forward the port rather than changing the bind.

    ssh -L 8000:127.0.0.1:8000 -L 5173:127.0.0.1:5173 you@server

## Reads never block writes

Every request opens the projection through `Graph.open_read_only()`, which takes
no writer lock — so the UI serves *while an agent run is writing*. Each write
takes the exclusive lock for **one request** and releases it; if a run holds the
lock, the endpoint answers 409 rather than waiting.

## What the graph view has to show

[design.md](design.md) §10 is a requirement, not a style guide: a naive
rendering "flattens exactly the epistemics that justify the system". If nodes
show without status and edges without the independence flag, a densely linked
node looks well supported regardless of whether its support is independent —
the visualization would silently argue *against* the thesis.

So, enforced (and covered by `tests/test_ui_theme.py`):

- **node status is a visual channel**, not a tooltip — the node's own
  outline, and not by hue alone: `proposed` is dashed because it is
  provisional, `accepted` is heavier because it is the only citable state, and
  `rejected` keeps a struck-through title. Selection and focus ride a separate
  outer ring, so selecting a node never repaints its status;
- **`parallel_of` and `descends_from` are visually distinct** from `attests` —
  dashed, heavier, differently coloured, and labelled "**discounts** support" in
  the legend. The API also flags them `discounts: true` so a frontend cannot
  drop the distinction by accident;
- **contradiction edges are as visible as agreement edges**;
- **`tests` is drawn as neither** — dotted and violet, because the
  falsifiability edge is the only relation in the picture that is still open: a
  prediction recorded before the evidence was in, which the corpus may not yet
  have been asked. Its solid grey neighbour `searched_for` is the opposite
  tense — the prior-art retrieval that *was* run before proposing — and the two
  must not read alike;
- **`addresses` gets its own channel**, not the structural one. `part_of` and
  `verifies` say where a record sits; `addresses` says what the work was *for*;
- **clicking any node reaches its provenance** — authorship, verifications with
  their `limitations`, edges both ways, and the `independent_support` block.

Layout is a deterministic evidence chain (witness → passage → claim), not a
force simulation, which would place the same graph differently on every load —
a poor property for something meant to be read and cited. **Research questions
are the terminal column**: the last column reads as where the chain arrives,
and what it arrives at is the thing the work was for. Audit sits before it,
because a query and a verification are how an assertion was reached, not where
it was heading.

Audit nodes (`verification`, `decision`) are hidden by default as bookkeeping
rather than evidence, behind a toggle in settings.

`tests/test_ui_vocabulary_coverage.py` asserts that **every** node type has a
column and every edge type has both a style and a legend entry. The vocabulary
is closed, so the frontend can enumerate it; nothing made it, and adding
`question`/`addresses` to the graph without adding them here dropped question
nodes from the view in silence while every other tab showed them.

### The legend describes the graph, not the vocabulary

It lists only the entries whose edges are actually drawn, and only the statuses
actually present — including shrinking when the audit toggle goes off, which is
the point: turning bookkeeping off should take its key with it. A fixed key
with six entries beside a picture using two teaches the reader to stop reading
the key.

Safe to shrink *because* it is derived from the drawn edges: an entry can only
disappear once there is nothing left on screen for it to label. The ordering is
fixed rather than following the graph — the three edge kinds that carry the
argument, then `tests` and `addresses`, then bookkeeping — so the key does not
reshuffle itself as a graph grows.

## Tabs

- **Graph** — the evidence graph, its legend, provenance on click. The refusal
  count and the node/edge stats live here, because both describe this graph.
- **Findings** — every claim and conjecture as a **hypothesis**, then what the
  researcher has accepted (the only citable nodes) and what they rejected, with
  reasons, side by side; plus the two integrity checks. Rejections sit next to
  findings deliberately: showing conclusions without showing what was thrown out
  and why would misrepresent the record.

  Opening a hypothesis shows its dossier, all of which the graph already held
  and none of which was reachable without walking edges by hand: the
  **derivation**, the **corpus boundary** it was framed against, the
  **selection risks**, the **alternative explanations** that would account for
  the same evidence, the prior-art search that was actually run before
  proposing, the **prediction recorded at proposal time** and what happened when
  its query was run, the evidence with excerpts, and the verifications — with
  the machine's finding and a reviewer's reading in separate fields, because a
  confident sentence in the machine's field reads later as a mechanical result.

  The list is **not ranked**. Sorting hypotheses by how much attests them would
  be a confidence score under another name, which is the habit the whole design
  exists to break; where support does not survive the independence check the row
  says so, and the attesting count is left unchanged.
- **Corpus** — browse and search, with `--corpus`.
- **Inquiry** — asking a question and running agents against it, with
  `--allow-runs`. Named for the unit rather than the mechanism:
  [vocabulary.md](vocabulary.md) already defines a `question` as "what an
  inquiry is asking", and the tab opens on a question rather than on a roster.

  The **question lives here, not in Findings**. A question is where work
  starts, not something that was found — and asking it in one tab to run
  against it in another made the connection between them something the
  researcher had to remember rather than something the tool did.

Clicking an author in a node's provenance opens that agent's contribution
counts. Counts, never a score: a reputation number would reward volume, so an
agent proposing ten weak claims would outrank one proposing a single good one.

## HTTP API

JSON throughout. Node ids are passed as **query parameters, never path
segments**, because a passage id contains `#` (`{witness}#{excerpt}`) which a
URL path silently truncates at the fragment.

### Always available

| Route | Notes |
|---|---|
| `GET /api/health` | counts by node type, edge total, and which capabilities are on (`writes_enabled`, `corpus_enabled`, `runs_enabled`) |
| `GET /api/graph?node_type=&limit=` | nodes + edges, `limit` 1–5000 (default 500). Reports `truncated` explicitly and lists `discounting_edge_types` |
| `GET /api/node?id=` | one node with full provenance |
| `GET /api/citable` | accepted nodes only — the only ones citable by output |
| `GET /api/rejected?node_type=` | rejected nodes **with their reasons** |
| `GET /api/agent?id=` | contribution counts, not a score |
| `GET /api/questions?id=` | research questions; with `id`, one and what addresses it |
| `GET /api/findings?id=&limit=` | claims and conjectures as hypotheses; with `id`, the whole dossier |
| `GET /api/refusals?limit=&run_id=` | refused writes, read from the event log, plus a `census`; `run_id` narrows both to one run |
| `GET /api/integrity?id=` | re-hash stored payloads against their recorded hashes |
| `GET /api/rebuild` | replay the log and diff it against this projection |

`truncated` is reported rather than silently cutting: a truncated graph shows
fewer supporting witnesses than exist, which here changes what the picture
appears to say about support.

Both integrity routes are `GET` because neither changes anything — `rebuild`
names what it replays into a throwaway in-memory graph. Neither needs the
writer's lock, so a read-only deployment can still verify itself; refusing to
let you check a projection you are allowed to read would be a strange place to
draw the line. A rebuild mismatch comes back as `ok: false` with the diff rather
than a 500: the projection being wrong is a finding about the system, not a
fault in the request.

`/api/refusals` returns `available: false` when there's no log, rather than an
empty list — an in-memory or freshly copied projection legitimately has none,
and saying so beats implying zero refusals.

Its `census` covers the **whole** log even when `refusals` is a truncated tail:
a census of the tail would report a smaller total than the log holds while
looking authoritative. The panel renders categories, rule counts and streaks
from it rather than tallying the rows it was given, which is what it used to do
— and which quietly understated every rule once a log grew past the limit. See
[refusals.md](refusals.md).

### With `--allow-writes`

| Route | Body |
|---|---|
| `POST /api/questions` | `{text, answerable_by}` to ask, or `{id, address}` to record that a hypothesis answers one |
| `POST /api/accept?id=` | — |
| `POST /api/reject?id=` | `{"reason": "..."}` |
| `POST /api/reopen?id=` | `{"reason": "..."}` |

All act as `RESEARCHER`, the one privileged identity in the ladder. Passing the
flag is the operator asserting that whoever can reach this port is the
researcher.

The `reason` is required by the **graph**, not by this layer — it's passed
through so the write boundary refuses it, keeping one rule in one place and
getting the refusal logged like any other.

Status codes carry meaning:

- **404** — no such node.
- **409** — an agent run holds the writer lock.
- **422** — the graph's own rules declined a well-formed request, returning
  `{"rule": "...", "message": "..."}`. This is *a real answer from the system*,
  not a server fault.

### With `--corpus`

| Route | Notes |
|---|---|
| `GET /api/corpus/search?q=&limit=` | exactly `source.search()` — a query typed here returns the same hits in the same order as one typed in Python. Response states `ordering: "corpus order; no relevance ranking"` |
| `GET /api/corpus/fetch?ref=&max_chars=&strip_markup=` | one record; `strip_markup` is display-only and **breaks offsets**, so never store its output |

Every hit carries a `cbeta_url` deep link to the published edition, and so does
every witness and passage node (`GET /api/node`). The mapping is not guessable
— CBETA Online addresses a work by a canon-scoped id with the volume digits
removed (`A097n1267` → `A1267`) — so it lives in
[`cohort/sources/cbeta_refs.py`](../cohort/sources/cbeta_refs.py), checked
against CBETA's own metadata API rather than reasoned out, and returns `None`
for a ref it does not recognise rather than a guess.

These links are **display-only provenance**. `verify_exact_span` re-fetches
from the local archive whose bytes were hashed, because a verification that
depended on a remote page would fail on a network error and pass or fail
differently depending on when it ran. A link is a courtesy to the reader; a
citation is what the graph checks.

Search returns 503 if the reader has no index, naming the reason.

### With `--allow-runs`

| Route | Notes |
|---|---|
| `GET /api/run/config` | model, ceilings, whether a corpus is present |
| `GET /api/run` | current run + history |
| `GET /api/run/{run_id}` | one run |
| `POST /api/run` | start; `{question_id, auto: true}` plans the roster, or pass a single agent or `agents: [...]`, each with an optional `role`. `question_id` alone records what an explicit roster was asked |
| `POST /api/run/stop` | stop after the current turn |

### Auto is the default, and what it may decide

`{question_id, auto: true}` plans the roster instead of taking one. The split
is deliberate and narrow:

- it decides the **machinery** — how many agents, which models, which roles —
  which carries no epistemic weight beyond one hard constraint, that a roster
  sharing a model family is refused at the write boundary;
- it never decides the **agenda**. No model call happens before the run.
  The researcher's question reaches each agent *verbatim*, along with the
  `answerable_by` they wrote, which is the fence an agent otherwise walks
  straight through. `ask_question` is researcher-only because setting the
  agenda is the supervision, and a planner that paraphrased the question into
  a task would be relocating that decision, not automating it.

The roster is **one worker and one reviewer**, and does not scale with the
pool. Two things about that are deliberate:

- **the second seat is a reviewer, not a second worker.** No agent may attest
  what it authored, so a one-family roster can propose but never promote:
  every claim stops at `proposed` and the output is a pile of assertions
  nothing has checked. The count that buys a *checked* answer is two.
- **the worker is asked to break its own answer** — propose what the passages
  support, then search for what would make that answer wrong, recording a
  contradiction rather than choosing between conflicting passages. That job
  used to belong to a second worker; it moved rather than disappearing when
  the roster shrank, because it is the half worth keeping.

The two models must come from **different providers**. Both the roster check
(`check_distinct_model_families`) and the write boundary
(`ReviewerNotIndependent`) refuse a reviewer that shares a model family with
the author — a different id on one model is not a different reader — so a
same-family reviewer would be refused before the run started, and could never
promote anything even if it were not. The worker takes `OPENROUTER_MODEL`, the
configured default; the reviewer takes the next distinct family in
`OPENROUTER_MODELS`.

The stance is fixed rather than generated per run, so two runs on one question
are comparable. `GET /api/run/config` reports the roster auto would
build (`plan`), so the launcher can name what it is about to spend money on;
the shape depends on how many model *families* the pool has, which a browser
computing it itself would have to reimplement and would drift from.

Every claim or conjecture a run proposes gets an `addresses` edge to the
question, added by the worker rather than by the researcher afterwards. A
question whose answers are only sometimes attached to it reads as a tally.

The equivalent in the terminal is `cohort run --question ID`, which calls the
same planner — the parity promise is not that both front ends can start a run,
it is that a run started either way is the same run.

**Customize** opens the explicit roster: per-agent task, model, corpus scope,
method and role, exactly as before. It changes nothing about what a run may do
— the ceilings are the server's either way.

Each agent takes `role: "worker"` (the default) or `"reviewer"`. **+ Add
reviewer** sits beside **+ Add agent** in the panel. A reviewer checks claims
the workers proposed, cannot propose any of its own, and runs in a second phase
after them — see [agents.md](agents.md). Its card says so, because "why can I
not give this one a task about the corpus" is the first question it raises.

A reviewer with nothing to review is skipped and reported as a `note` on its
row, not an `error`: the run did not fail, there was simply no work.

The browser proposes a budget; the server bounds it. A field that accepted any
number and rejected it only after the button was pressed would be worse than no
field.

Spend is shown **while the run goes**, not summarised at the end, and refusals
are shown as **results, not errors** — a run whose agent was refused five times
did not fail.

## Development

    cd cohort/ui/frontend && npm run dev     # :5173, proxies /api to :8000

The dev server and the built bundle behave identically. `npm run build` outputs
to `cohort/ui/static/`, which the API mounts when present; that directory is
gitignored and regenerated from `src/`.

Theming has **three** states, not two: an explicit choice stamps
`data-theme="light|dark"`, and "system" stamps nothing and follows
`prefers-color-scheme`. Contrast is measured against WCAG AA (4.5:1 for small
text), not eyeballed.
