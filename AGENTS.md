# Working in this repository

Guidance for coding agents (and people) making changes to Cohort. It states
what the code and docs already enforce, so an agent does not have to
rediscover it; when this file and `docs/design.md` disagree, design.md wins.

## What Cohort is

A system that helps a researcher go from a research question over a corpus to
hypotheses backed by citable evidence, in which **nothing is asserted true**.
Agents propose claims, which must cite passages, and conjectures, which must
come with a search that could refute them. A different agent checks; only the
human researcher accepts. Refusals are an output, not an error path. The
event log (`*.jsonl`) is the ground truth and SQLite is a rebuildable
projection of it. Read `docs/design.md` before changing anything under
`cohort/graph.py`, `cohort/schemas.py` or `cohort/eventlog.py`.

## Onboarding someone new

If you are an assistant helping a person get started, walk them through this
in order. Do not summarise the whole of `docs/`.

1. **What it is for:** `README.md`, then `docs/design.md` §1 (thesis), §7
   (claims and conjectures) and §8 (the promotion ladder).
2. **What works and what doesn't:** `docs/handoff.md`. Its "What does not
   exist" section is as important as what does.
3. **How good the output has been:** `docs/presentation/conjecture-review.md`
   and `docs/presentation/researcher-review.md`.
4. **Current work:** `docs/handoff-paper-2027.md`, a one-month plan toward an
   ACL 2027 or IJCAI-27 submission.
5. **Run something:** the test suite and `demo.py` (see below). Neither needs a
   corpus, an API key or network.

Most collaborators **do not have CBETA or Radich's corpus**. Before suggesting a
script, check its docstring: most of `scripts/` and all of
`cohort/attribution.py` need one of them. What runs without them:

- the tests;
- `demo.py`;
- `scripts/run_swarm_demo.py`, which needs an OpenRouter key;
- any corpus the person supplies through `LocalReader` (`docs/corpus.md`).

Never ask them to obtain or share `data/`.

## Setup and commands

    uv sync --extra dev --extra ui          # dependencies (or: pip install -e '.[dev,ui]')
    uv run pytest -q                        # the whole suite; it must stay green
    uvx ruff check .                        # lint; configuration lives in pyproject.toml
    uvx ty check cohort scripts             # types
    cd cohort/ui/frontend && npm run build  # rebuild the researcher UI into cohort/ui/static/
    uv run python scripts/serve_ui.py --db demo_graph.sqlite [--corpus] [--radich PATH]

Run ruff and ty before opening a PR. The ruff configuration is strict on
purpose; do not silence a rule inline without a comment saying why that line
is the exception.

## Rules the tests enforce

- **Single writer.** `Graph.open()` takes an `fcntl.flock`; `graph.py` holds
  the handle open deliberately (`SIM115` is ignored there for that reason).
  Reads go through `Graph.open_read_only()` and never take the lock.
- **CLI and web UI have the same capabilities.** `tests/test_parity.py` maps
  every HTTP route to a CLI command and back. Add both, or record the
  asymmetry in `EXEMPT` with a reason.
- **Every UI helper a panel calls must be imported by that panel**
  (`tests/test_ui_imports.py`); Vite will not catch a missing import.
- **Every node and edge type has a column, a style and a legend entry**
  (`tests/test_ui_vocabulary_coverage.py`).
- **Node status is a visual channel**, and edges that *discount* support
  (`parallel_of`, `descends_from`) are drawn differently from edges that add it
  (`tests/test_ui_theme.py`). Do not flatten this; `docs/design.md` §10.
- **Author is not reviewer**, and the reviewer must be a different model
  family (`cohort/families.py`).

## Style

- Docstrings and comments explain *why*, and name the mistake they prevent
  when there was one. Match the density of the surrounding file.
- Report arithmetic, not assertion: count outputs, print ledgers of what was
  discarded, and never quote a number the code did not compute.
- Prefer a check that can fail over a comment that promises. An assertion that
  recomputes the same arithmetic it is checking cannot fail; assert the
  invariant instead.
- Standard library first. The agent layer talks to OpenRouter over
  `urllib.request` on purpose; do not add a client SDK.
- Absolute imports (`from cohort.graph import Graph`), never relative.

## Data and licences

`data/` is git-ignored and must stay so. The CBETA archive is
CC BY-NC-SA-equivalent and Radich's corpus is his unpublished modification of
it; correspondence in `data/` carries personal addresses. Never commit, print,
or screenshot the contents of `data/`, and keep servers bound to
`127.0.0.1`. Tests use synthetic corpora under `tmp_path`, never the real one.

## Things that bit us

- `demo.py` used one agent id to author and attest: refused by design. Use a
  second agent id for review.
- Reading `sys.argv` at import time in a module that other scripts import.
- A module-level global used as a classifier's smoothing denominator, left
  at the wrong value by a previous loop iteration. Pass parameters.
- Leave-one-*unit*-out on a corpus whose units are chapters of the same book:
  82% that was really 52%. Hold out the whole work.
- `pkill -f` with a pattern that matches your own shell.
- The browser caching `index.html` and loading a stale bundle after a
  frontend rebuild; `/` now sends `Cache-Control: no-cache`.

## Hosted service preparation

`lope-service.json` declares the managed hosting boundary; it remains discovery
until catalog, responsibility, data-transfer, backup and acceptance gates pass.
Follow `docs/hosting.md`. Production code belongs under `/opt/lope/services/cohort`,
configuration under `/etc/lope/services/cohort`, root-controlled secrets under
`/etc/lope/secrets/cohort`, and mutable state under `/srv/lope/services/cohort`.
Do not proxy to a personal-home checkout. Validate the authoritative fleet catalog
and the service contract with `--repository-root` and `--catalog` before deployment.
Keep reviewed images, explicit start/stop/restore/rollback instructions and the
previous workspace available; a failing checker is a deployment blocker.
