# Architecture

How the system actually works, from the bottom. The design rationale is in
[design.md](design.md); this is the mechanism.

## The one-sentence version

An append-only JSONL event log is ground truth. SQLite is a rebuildable
projection of it. Everything that mutates the graph goes through one enforced
write boundary, held by one process at a time, and a refused write is recorded
rather than dropped.

    tool call ──▶ Graph method ──▶ [ enforce rule ] ──┬─▶ EventLog.append()  (ground truth)
                                                      └─▶ SQLite UPDATE      (projection)
                                          │
                                          └─ refused ─▶ log_refusal()  (also ground truth)

## The event log is ground truth

`cohort/eventlog.py`. One JSON object per line, appended and flushed as it
happens, with a monotonic `seq`. Nothing rewrites or deletes a line.

The projection is a cache of the log's meaning, and `Graph.rebuild()` proves it:
it replays every event into a fresh in-memory graph and diffs that against the
live projection. A mismatch raises `RebuildMismatch` — *a failing diff is a bug,
not a warning*. This is design principle 1, and it's the reason the schema can
change safely: migrations alter the projection, never the log.

    graph.rebuild()   # RebuildReport(ok=True, events_replayed=81, nodes=37, edges=43)

Read the log directly without a database at all:

    from cohort.eventlog import (read_events, read_refusals,
                                 summarize_model_calls, summarize_refusals)

`read_refusals()` is a pure log scan. It exists because refusals are output, not
diagnostics — see below. `summarize_refusals()` is the arithmetic over them:
counts by rule, by category and by author, plus **streaks** — one agent refused
repeatedly by one rule. See [refusals.md](refusals.md).

## The projection

`cohort/graph.py`, ~1,050 lines, the only writer. SQLite in WAL mode, no ORM.
Tables: `nodes`, `edges`, `agents`, plus schema bookkeeping.

Migrations are numbered and forward-only (`cohort/migrations.py`), currently at
`SCHEMA_VERSION = 5`:

| # | Name | What it does |
|---|---|---|
| 1 | `baseline` | the initial schema |
| 2 | `node_payload_hash` | adds the integrity hash, with a backfill |
| 3 | `edge_reason` | adds `edges.reason`, no backfill — older edges have none |
| 4 | `edge_retraction` | adds `edges.retracted_at` / `retracted_reason` |
| 5 | `agent_model` | adds `agents.model`, so a run's readers are on the record |

A read-only projection is opened with `Graph.open_read_only()`: SQLite `mode=ro`,
**no** writer lock, no `EventLog` attached, and migrations skipped rather than
applied — because applying one is itself a write, so an out-of-date projection
is refused rather than misread. Every mutating method then fails through the
existing `event_log_or_raise()` guard rather than a parallel check that could
drift from it.

## Single writer

Design principle 7. One process owns the write connection, held by an exclusive
non-blocking `fcntl.flock` on a `.lock` sidecar. A second writer gets
`SingleWriterViolation` immediately rather than blocking.

Readers never take the lock. WAL already makes concurrent readers safe, and a
reader has no business asking for a writer's lock — which is what lets the UI
serve a graph *while an agent run writes to it*. There is a test asserting
exactly that.

Concurrency inside one process is a different question. `run_swarm()` runs
several workers against one `Graph`, and `asyncio.to_thread` is scoped around
**only** the blocking HTTP call — so two workers' model calls overlap while
their graph writes cannot interleave.

## The write boundary

Design principle 4: *a rule enforced in a prompt is a request; a rule enforced
at the write boundary is a property.* Every rule the design claims has one
exception class in `cohort/errors.py` and one enforcement site in `graph.py`.

What is enforced, not merely documented:

- **Edge domains.** `EDGE_DOMAINS` maps each edge type to the
  `(src_type, dst_type)` pairs it permits, or the sentinel `"any"`
  (`contradicts`) or `"same_type"` (`supersedes`). See
  [vocabulary.md](vocabulary.md).
- **Edges never create endpoints.** A missing endpoint is
  `EdgeEndpointMissing`, not a silently-minted node — which is what makes an
  agent's invented node id a refusal instead of a fabrication.
- **The falsifiability gate.** A conjecture with no `tests` edge cannot be
  attested; a claim with no `attests` edge cannot be attested. See
  [design.md](design.md) §7 — this is the contribution.
- **The ladder.** No rung may be skipped; only `RESEARCHER` may accept or
  reject; rejection needs a stated reason and persists.
- **The author is not the reviewer.** An agent may not attest a claim or
  conjecture it authored, nor one whose author shares its model family. The
  roster check guards who is *in* a run; this guards the write itself, and
  catches what a roster cannot see — agents registered by separate runs
  writing to one graph. See [vocabulary.md](vocabulary.md).
- **Identity from the source.** A passage is named by its canonical reference,
  so two agents finding the same passage converge on one node carrying two
  authorship records. Payload hashing is for integrity checking, never for
  identity — hashing agent text into identity fragments the graph silently,
  which makes the system look more productive as it becomes less correct.

## Refusals are output

The distinctive claim in [design.md](design.md) §15 is that the system's
refusals are part of its scholarly output. That is implemented, and it took two
passes to be true.

Write-boundary refusals were always logged: `_refuse()` records the attempt, the
rule, and the reason, then raises. But lookup failures were not — `_require_node`
raised `NodeNotFound` directly, so the most interesting refusal of all (an agent
inventing a node id) left no trace in the log. `Graph.log_refusal()` closes
that; `AttestationWorker._dispatch` calls it for any tool failure, and
idempotence comes from an `error.logged_to_event_log` flag so a refusal already
recorded by `_refuse()` isn't double-counted.

    from cohort.eventlog import read_refusals
    for r in read_refusals("graph.jsonl"):
        print(r.seq, r.attempted, r.rule, r.message)

The UI surfaces these as results, not errors: a run whose agent was refused five
times did not fail — that is the boundary working.

## Observability

Every model call is logged as a non-mutating audit marker via
`log_model_call()`, returning an id that threads through to the writes it
caused. So `model_call_id` on a node answers "which call produced this", and
`summarize_model_calls()` totals spend from the log itself rather than from a
running tally that could drift.

## Runs are events too

An agent run writes `run_started` and `run_finished` — non-mutating, like
`model_call`, because a run beginning is not a change to the graph — and every
event written while it is open carries its `run_id`.

The stamp happens in one place, `EventLog.append`, rather than being threaded
through every write signature. The difference from `model_call_id` is real: a
model call is a *cause* that a particular write has to name, while a run is the
session doing the writing, so the log knows it without being told once per call.

Two things follow. A run survives the process that ran it — `read_runs()` and
`cohort run --history` read it back from the log, where before a server restart
erased every run ever launched from the browser. And the log becomes sliceable:
`read_refusals(run_id=…)`, `summarize_refusals(run_id=…)` and
`summarize_model_calls(run_id=…)` answer "what did *that* run do", which is a
different question from what the graph has ever done, and the one a scaling
comparison needs.

A run with no closing event is reported open rather than repaired. It may still
be going or it may have been killed mid-write; both are facts about the
session, and inventing an end for it would be the tidying this log refuses.

## Two front ends, one capability set

COHORT is meant to be driven from a terminal or from a browser, and "the same
functionality either way" is the kind of promise that decays quietly: someone
adds a route and forgets the command, and nothing complains until a user finds
the hole.

So the promise is a test. `tests/test_parity.py` maps every HTTP route to a CLI
command and fails if either side gains a capability the other lacks. A
deliberate asymmetry is allowed but has to be written into its `EXEMPT` table
with a reason, which makes it a decision instead of an oversight.

Three shared modules keep the two honest, each extracted after the duplication
had already caused a divergence:

- **`cohort/views.py`** — the read-shapes. When the CLI and the API each had
  their own serializer they disagreed about the shape of a node immediately.
  A test now asserts `cohort node X --json` and `GET /api/node?id=X` are equal
  payloads, not merely similar ones.
- **`cohort/sources/env.py`** — builds the CBETA reader from the environment,
  so a query in the browser and a query in the terminal hit one index. The
  archive hash lives here too; it had been copy-pasted into eight scripts, and
  the provenance argument rests on it.
- **`cohort/ui/runs.py`** — the run launcher both front ends drive.

Neither front end enforces a rule. `cohort accept` and `POST /api/accept` both
call `Graph.accept()`, so the write boundary refuses identically whichever way
you arrive — which is the point of principle 4.

## Layer map

    cohort/
      schemas.py        closed vocabulary: nodes, edges, events, dating, verification
      views.py          shared read-shapes, so the CLI and the API describe a node identically
      cli.py            the terminal front end
      errors.py         one exception per rule the design claims
      eventlog.py       append-only JSONL; read_events / read_refusals
      graph.py          the projection and the only writer
      migrations.py     numbered, forward-only
      _locking.py       the cross-platform exclusive lock behind single-writer
      attribution.py    string-profile comparison over Radich's corpus (needs it)
      embeddings.py     reads the precomputed passage-embedding index
      related.py        one passage and its nearest neighbours; writes nothing
      sources/          search(query) / fetch(ref) — the whole corpus seam
                        (env.py builds the CBETA reader for every front end;
                        radich_manifest.py reads Radich's corpus)
      tools/            named, schema-validated, individually refusable writes,
                        plus three read-only evidence tools
      agents/           OpenRouter transport, worker, reviewer, read-only analyst,
                        action explanations, swarm, budget cap
      ui/               FastAPI JSON API + React frontend (optional `ui` extra);
                        local accounts (auth.py), reverse-proxy hosting (hosting.py)

The dependency direction is strictly downward: `tools/` may use `graph.py` and
`sources/`, `agents/` may use `tools/`, and `ui/` may use anything. Nothing
below reaches up. `sources/` knows nothing about the graph — which is what keeps
the corpus seam one function signature wide, per [design.md](design.md) §2.
