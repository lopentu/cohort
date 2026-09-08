# Command-line reference

## `cohort` — the terminal front end

Installed by `pip install -e .`. **It has the same capabilities as the web UI**,
and that is enforced rather than intended: `tests/test_parity.py` fails if
either front end gains something the other lacks. Both call the same library
functions, so a rule refuses identically whichever way you reach it.

    cohort health                             # node and edge counts
    cohort graph --type claim --limit 50      # list nodes and their edges
    cohort node claim:abc123                  # full provenance, with independence
    cohort citable                            # accepted nodes — the only citable ones
    cohort rejected                           # thrown out, with reasons
    cohort agent agent:worker-1               # contribution counts, not a score
    cohort refusals                           # writes the graph declined
    cohort refusals --census                  # the summary only: rules, categories, streaks
    cohort integrity                          # re-hash payloads against their hashes
    cohort rebuild                            # replay the log, diff this projection

    cohort attest claim:abc123                # the mechanical check (as the researcher)
    cohort accept claim:abc123
    cohort reject claim:abc123 --reason "conflates two recensions"
    cohort reopen claim:abc123 --reason "the objection was mine, not the text's"
    cohort retract-edge edge:abc --reason "the bracket was a cf., not an assertion"
    cohort restore-edge edge:abc --reason "checked again; it is a bare list"

    cohort question                           # what this inquiry is asking
    cohort question --ask "…" --answerable-by "…"
    cohort question --id question:abc --address conjecture:def

    cohort findings                           # claims and conjectures as hypotheses
    cohort findings --id conjecture:abc123    # the whole dossier for one

    cohort test-conjecture conjecture:abc123  # run its prospective query against
                                              #   the prediction recorded with it

    cohort run --history                      # past runs, from the log; spends nothing
    cohort refusals --run 1c0a47ba0b67 --census

    cohort search 色即是空                     # same hits as the browser, same order
    cohort fetch "T08n0251::色即是空"
    cohort run --agent "find attestations for 色即是空" --budget 0.05
    # several agents need one model each — they may not share a family:
    cohort run --agent "…" --model z-ai/glm-5.3-flash \
               --agent "…" --model deepseek/deepseek-v4-flash --budget 0.05
    # a reviewer checks what the workers proposed and cannot propose anything:
    cohort run --agent "…"    --model z-ai/glm-5.3-flash \
               --reviewer "…" --reviewer-model deepseek/deepseek-v4-flash \
               --budget 0.05

Global options: `--db` (default `demo_graph.sqlite`), `--log` (default: `--db`
with `.jsonl`), and `--json`.

**`--json` prints exactly what the corresponding HTTP route returns.** That is
what makes the parity claim checkable instead of asserted — there is a test
comparing the two payloads for equality, not for a few matching keys.

Exit codes: `0` success, `1` usage or missing graph, **`2` a refused write** —
distinguished because a refusal is a real answer from this system, already
recorded to the event log, not a failure to run.

`cohort run` blocks and Ctrl-C stops it after the current turn. The web
launcher is asynchronous only because a browser cannot block.

Reviewers run in a **second phase**, after the workers, because there is
nothing to review before ([agents.md](agents.md)). A run of workers alone
leaves its claims at `proposed` — no agent may attest what it authored — so
either add a `--reviewer` on another provider, or check them yourself with
`cohort node` and `cohort accept`.

`cohort run --history` lists past runs out of the **event log**, not out of a
running process: a run writes `run_started`/`run_finished` and stamps its id on
everything it writes, so it outlives the server that launched it. That is also
what makes `cohort refusals --run <id>` possible — the census of one run rather
than of a graph's whole life. See [architecture.md](architecture.md).

`--scope` and `--method` are each **one per agent**, in roster order (every
`--agent`, then every `--reviewer`), or one for the whole roster:

    cohort run --agent "…" --model z-ai/glm-5.3-flash \
                 --scope "Prajñāpāramitā sūtras" --method "phrase distribution" \
               --agent "…" --model deepseek/deepseek-v4-flash \
                 --scope "Heart Sutra apparatus" --method "cross-edition collation" \
               --budget 0.05

Distinct declared scope per agent is the design's own condition for allowing
more than one agent at all ([roadmap.md](roadmap.md), "Scope revision"), and
`POST /api/run` has always taken these per agent — a terminal that could only
set them for the whole roster could not say what the browser could. A count
that is neither 1 nor the number of agents is refused rather than padded.

## Scripts

Everything below is a demo, a corpus builder or the server — not part of the
CLI/UI parity surface.


**The rule that governs this whole directory: anything that calls a model is
manual-only and is never run by the test suite.** Each such script names its own
cost in its docstring, and spend is capped in code
([agents.md](agents.md)), not estimated.

## No corpus, no key, no network

| Command | What it does |
|---|---|
| `.venv/bin/pytest -q` | 260 tests |
| `.venv/bin/python demo.py` | the `independent_support()` flip — **show this first** |

`demo.py` prints the thing worth seeing before anything else: a claim whose
support count stays at two while its independence flag goes false the moment a
`parallel_of` edge is recorded. That is the counter-argument to
consensus-seeking, in three lines of output. It also prints its own refusal log,
because refusals are output.

## Corpus, no model call

These need `CBETA_ARCHIVE_PATH`. None of them spends money.

| Command | Cost | Notes |
|---|---|---|
| `scripts/build_cbeta_index.py` | ~432s, 1.14 GB | one-off full-corpus FTS index. `--db`, `--prefix`, `--limit`, `--sha256` |
| `scripts/search_cbeta.py 色即是空` | ~65ms | needs the index. `--limit`, `--collection`, `--fetch`, `--db` |
| `scripts/scan_parallels.py` | ~8s, read-only | validates the `<cb:docNumber>` parser over all 20,190 entries. `--out`, `--limit` |
| `scripts/run_stage4_demo.py` | free | stage 4 on real text: shared descent recognised, consensus refused |
| `scripts/seed_demo_graph.py` | free | builds the demo graph for the UI from the **real** archive. `--db`, `--force` |

`scripts/search_cbeta.py` is a thin front end on the same `CbetaReader.search()`
the tools use, so what a researcher sees here is exactly what an agent gets.
`--fetch` proves every hit is fetchable, at the cost of a full archive
re-verification per hit.

`scripts/run_stage4_demo.py` is the sharpest demonstration in the repo and needs
no API key: T08n0250, T08n0251 and T08n0252 are three *different* Chinese
translations that all contain 色即是空，空即是色. A fact-checking model counts
that as three independent confirmations. It isn't — CBETA's own
`<cb:docNumber>` lists them as parallel texts. The script shows COHORT reaching
that conclusion **from the corpus's own markup**, not from a hand-added edge as
`demo.py` necessarily does.

`scripts/scan_parallels.py` writes three artifacts to `~/cbeta_scan/`:
`parallel_map.jsonl`, `unparsed.txt` (every bracket the parser declined, deduped
with an example each — i.e. its own failure report), and `summary.txt`.

## Live model calls — manual only

Need `OPENROUTER_API_KEY` and `OPENROUTER_MODEL`. **Never paste a real key into
a chat session.**

| Command | Cost | Notes |
|---|---|---|
| `scripts/smoke_openrouter.py` | ~$0.0002 | one real call; run once against a new key before trusting it |
| `scripts/run_cbeta_demo.py` | ~$0.002 | one agent against the real archive |
| `scripts/run_swarm_demo.py` | ~$0.003 | two *concurrent* real agents, distinct declared scope |
| `scripts/run_conjecture_demo.py` | ~$0.004 | the falsifiability gate live. `--budget` (default $0.25), `--max-turns` (4), `--db` |
| `scripts/run_negative_control.py` | ~$0.0005 | **the one that shows it catching something.** A real claim, five real citations, one excerpt altered by a character with its hash recomputed so integrity stays clean — then a live reviewer on another family. The claim must not advance. `--db`, `--budget`, `--force`, `--reviewer-model` |

## The UI

    .venv/bin/python scripts/serve_ui.py --db demo_graph.sqlite

| Flag | Default | Effect |
|---|---|---|
| `--db` | `demo_graph.sqlite` | the projection to serve |
| `--log` | `--db` with `.jsonl` | event log, for the refusal panel |
| `--host` / `--port` | `127.0.0.1` / `8000` | binds locally **deliberately** — the corpus is licence-restricted |
| `--corpus` | off | corpus browse/search |
| `--allow-writes` | off | accept/reject/reopen, acting as `RESEARCHER` |
| `--allow-runs` | off | the agent-run launcher (implies `--corpus`) — **spends money** |
| `--max-budget` | 1.00 | hard per-run ceiling the browser cannot raise |
| `--reload` | off | dev autoreload |

See [ui.md](ui.md) for the HTTP surface and for port forwarding over SSH.

## Environment variables

    OPENROUTER_API_KEY=      # live scripts and UI runs
    OPENROUTER_MODEL=
    CBETA_ARCHIVE_PATH=      # anything touching the real corpus
    CBETA_FTS_PATH=          # optional; defaults to cbeta_fts.sqlite

Copy `.env.example` to `.env` and fill it in by hand. `.env` is gitignored.


### Related indexed passages

`cohort related T0263-rest --start 4000 --radich PATH --json` uses
`EVIDENCE_EMBEDDINGS_PATH` to retrieve passages in other works, with cosine
scores, source positions and exact shared runs within the displayed windows.
Omit the unit ID to inspect coverage. It does not accept arbitrary query text,
run a language model or write graph records.
