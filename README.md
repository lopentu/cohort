# Cohort

Evidential pluralism made auditable — a supervised evidence graph for
multi-agent textual research.

Agentic research systems usually import their verification model from
fact-checking: many sources agreeing raises confidence. Transmitted textual
corpora violate the independence assumption that model needs, because agreement
between witnesses is usually evidence of shared descent rather than independent
confirmation. COHORT is an evidence graph in which nothing is asserted as true,
relations of descent and parallelism are first-class, claims must cite their
sources, conjectures must arrive with what would refute them, and only the
researcher can promote a finding to citable status.

**📖 Documentation: [docs/index.md](docs/index.md)** — start there. It maps which
document answers which question. If you're picking this project up fresh, read
[docs/design.md](docs/design.md) then [docs/handoff.md](docs/handoff.md).

## Quickstart

No corpus, no API key, no network needed:

    python -m venv .venv && .venv/bin/pip install -e '.[dev]'
    .venv/bin/pytest -q
    .venv/bin/python demo.py

`demo.py` prints the thing worth seeing first: a claim whose support count stays
at two while its independence flag flips to false the moment a `parallel_of`
edge is recorded. That is the counter-argument to consensus-seeking, in three
lines of output.

## Two front ends, same capabilities

    cohort node claim:abc123      # provenance, with independence stated
    cohort accept claim:abc123
    cohort search 色即是空

Installed with the package. The CLI and the web UI cover the same capability
set, and that is enforced by a test rather than intended — see
[docs/cli.md](docs/cli.md).

## The researcher UI

The same functionality as the Python API, in a browser — because COHORT should
be usable as a library by people who write Python and as a tool by researchers
who don't.

    .venv/bin/pip install -e '.[ui]'
    cd cohort/ui/frontend && npm install && npm run build && cd -
    .venv/bin/python scripts/seed_demo_graph.py     # needs the corpus
    .venv/bin/python scripts/serve_ui.py --db demo_graph.sqlite

Reads never take the writer lock, so the UI can serve while an agent run is
writing. Three capabilities are opt-in separately, because they carry different
consequences — reading the corpus is free, accepting a finding is a scholarly
act, and starting an agent run spends money:

    --corpus        corpus browse/search
    --allow-writes  the researcher's accept / reject / reopen
    --allow-runs    the agent-run launcher   (--max-budget caps each run)
    --radich PATH   the Evidence tab and the evidence tools, over Radich's data folder

It binds `127.0.0.1` by default and deliberately: the corpus behind the graph is
licence-restricted. Over SSH, forward the port rather than changing the bind.
Details in [docs/ui.md](docs/ui.md).

## Access governance is a separate system, and it is not connected

COHORT has **no** access-governance layer. There is no policy file, no
allowlist, no request caps, no retention rules and no deletion verification, and
nothing here should be read as providing any of them. That work belongs to
ATELIER, which is a separate working system, currently **not** integrated —
COHORT's `search`/`fetch` source interface is deliberately shaped like
ATELIER's adapter so that integration later means writing one adapter class,
but that integration has not happened.

What COHORT does do about rights is narrow and worth stating exactly: the
development corpus (CBETA v061) is locally held and licensed
CC BY-NC-SA-equivalent, not public domain, so its terms are carried through
every derived artifact — `source_terms` on every witness node and in every
corpus API response — rather than dropped. Corpus bytes are never committed to
this repository; only a local path is configured. That is provenance hygiene,
not governance, and it is not a substitute for it.

See [docs/corpus.md](docs/corpus.md) for setup.

## Live scripts

Everything under `scripts/` that calls a model is **manual-only and never run by
the test suite**. Each one names its own cost in its docstring. Spend is capped
in code (`cohort/agents/budget.py`) rather than estimated: the cap is checked
*before* a request, and a response that reports no cost is charged an estimate
rather than treated as free. Full reference in [docs/cli.md](docs/cli.md).

## Conventions

`uvx ruff check .` and `uvx ty check cohort scripts` must pass before a PR;
the configuration in `pyproject.toml` is strict on purpose, and `AGENTS.md`
lists the rules the tests enforce. The house habit that matters most: **a document about this system should report
arithmetic, not assertion** — count the outputs rather than claiming things
about them. If a rule in [docs/design.md](docs/design.md) cannot be honoured,
say so and stop rather than quietly working around it.

## Comparisons

For comparisons with other implementations of this system by labmates, see [compare.md](compare.md).