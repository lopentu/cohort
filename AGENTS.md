# Working in this repository

Guidance for coding agents (and people) making changes to Cohort. It states
what the code and docs already enforce, so an agent does not have to
rediscover it; when this file and `docs/design.md` disagree, design.md wins.

## What Cohort is

An evidence graph for textual scholarship in which **nothing is asserted
true**. Agents propose; a different agent checks that citations resolve; only
the human researcher accepts. Refusals are an output, not an error path. The
event log (`*.jsonl`) is the ground truth and SQLite is a rebuildable
projection of it. Read `docs/design.md` before changing anything under
`cohort/graph.py`, `cohort/schemas.py` or `cohort/eventlog.py`.

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
