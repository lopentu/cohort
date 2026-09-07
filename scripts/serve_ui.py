"""Serve the researcher UI against a graph projection (build order stage 5).

Reads never take the writer lock, so this is safe to run while an agent run
is writing to the same graph (see `cohort/ui/api.py`).

`--allow-writes` additionally mounts the researcher's accept/reject/reopen
endpoints. Off by default, for two reasons: the read-only deployment stays the
default, and those endpoints act as `RESEARCHER`, the one privileged identity
in the promotion ladder. Passing the flag is the operator asserting that
whoever can reach this port is the researcher. Each write holds the exclusive
lock for one request only; if an agent run holds it, the endpoint answers 409
rather than waiting.

Binds 127.0.0.1 by default and deliberately: this is a shared lab machine, and
the corpus behind the graph is licensed CC BY-NC-SA-equivalent, so the default
must not publish it to the network. Over SSH, forward the port instead
(VS Code does this automatically; otherwise `ssh -L 8000:localhost:8000 ...`).

`--corpus` mounts corpus browse/search, and `--allow-runs` mounts the agent
run launcher. Together with `--allow-writes` they make the web UI reach parity
with the Python API: search the corpus, start a run, watch its spend and its
refusals, accept or reject the result. Each is opt-in separately because they
carry different consequences — reading the corpus is free, accepting a finding
is a scholarly act, and starting a run spends money.

Usage:
    .venv/bin/python scripts/serve_ui.py --db demo_graph.sqlite
    .venv/bin/python scripts/serve_ui.py --db demo_graph.sqlite --port 8010

    # everything the Python API can do, from the browser:
    .venv/bin/python scripts/serve_ui.py --db demo_graph.sqlite \
        --corpus --allow-writes --allow-runs --max-budget 0.50
"""
from __future__ import annotations

import argparse
import sys
from pathlib import Path

from cohort.ui.runs import DEFAULT_MAX_BUDGET_USD

REPO_ROOT = Path(__file__).resolve().parent.parent

def _open_corpus():
    """The same reader the CLI and the scripts build, from the same
    environment — so a query in the browser and a query in Python hit one
    index, not two. Shared implementation in `cohort.sources.env`.

    A missing archive disables the feature rather than refusing to start: the
    UI is useful without the corpus, since the graph is already there."""
    from cohort.sources.env import open_corpus_from_env

    source, reason = open_corpus_from_env(repo_root=REPO_ROOT)
    if source is None:
        print(f"note: corpus endpoints disabled — {reason}", file=sys.stderr)
    return source


def main() -> None:
    parser = argparse.ArgumentParser(description=__doc__)
    parser.add_argument("--db", default=str(REPO_ROOT / "demo_graph.sqlite"))
    parser.add_argument(
        "--pcatalogue", metavar="DIR", default=None,
        help="directory holding an ascription study: `corpus/T-stripped/` and "
             "a catalogue. Opening one builds a Delta space over the whole "
             "corpus, which takes about half a minute and is done once at "
             "startup so no request pays for it",
    )
    parser.add_argument("--benchmark-label", default="P-23")
    parser.add_argument("--control-label", default="interloper")
    parser.add_argument("--host", default="127.0.0.1")
    parser.add_argument("--port", type=int, default=8000)
    parser.add_argument("--reload", action="store_true")
    parser.add_argument(
        "--allow-writes", action="store_true",
        help="mount the researcher's accept/reject/reopen endpoints (acts as RESEARCHER)",
    )
    parser.add_argument(
        "--log", default=None,
        help="event log path (default: the --db path with a .jsonl suffix)",
    )
    parser.add_argument(
        "--corpus", action="store_true",
        help="mount corpus browse/search (needs LOCAL_CORPUS_ROOT, or CBETA_ARCHIVE_PATH and CBETA_FTS_PATH)",
    )
    parser.add_argument(
        "--allow-runs", action="store_true",
        help="mount the agent run launcher — these endpoints spend money (implies --corpus)",
    )
    parser.add_argument(
        "--radich", default=None, metavar="PATH",
        help="mount the translator-evidence tab over Radich's pre-450 corpus at PATH "
             "(licence-restricted; never inside the repository)",
    )
    parser.add_argument(
        "--max-budget", type=float, default=DEFAULT_MAX_BUDGET_USD,
        help=(
            f"hard per-run USD ceiling the browser cannot raise "
            f"(default {DEFAULT_MAX_BUDGET_USD:.2f})"
        ),
    )
    args = parser.parse_args()

    try:
        import uvicorn
    except ModuleNotFoundError:
        print(
            "the `ui` extra is not installed: .venv/bin/pip install -e '.[ui]'",
            file=sys.stderr,
        )
        sys.exit(1)

    db_path = Path(args.db)
    if not db_path.is_file():
        print(f"no graph projection at {db_path}", file=sys.stderr)
        print("build one first: .venv/bin/python scripts/seed_demo_graph.py", file=sys.stderr)
        sys.exit(1)

    from cohort.ui.api import FRONTEND_DIR, create_app
    from cohort.ui.runs import RunManager

    source = None
    if args.corpus or args.allow_runs:
        source = _open_corpus()
        if source is None and args.allow_runs:
            print(
                "error: --allow-runs needs a corpus, but none could be opened "
                "(see the message above)",
                file=sys.stderr,
            )
            sys.exit(1)

    study = None
    if args.pcatalogue:
        from cohort.delta_study import open_study

        print(f"building the Delta space over {args.pcatalogue} — about 35s, once",
              file=sys.stderr)
        study = open_study(
            args.pcatalogue,
            benchmark_label=args.benchmark_label,
            control_label=args.control_label,
        )
        print(f"  {study.corpus_size} works read, {len(study.space.works())} "
              f"long enough to profile, {len(study.space.features)} features; "
              f"{len(study.catalogue.works())} catalogued works indexed for counting",
              file=sys.stderr)

    # After the study, because a run manager built without it would hand every
    # agent a toolset missing the four ascription tools — silently, and only
    # discoverable by paying for a run and reading the transcript.
    run_manager = None
    if args.allow_runs:
        log_path = Path(args.log) if args.log else db_path.with_suffix(".jsonl")
        run_manager = RunManager(
            db_path, log_path, source, max_budget_usd=args.max_budget,
            study=study,
        )

    attribution = None
    if args.radich:
        import time

        from cohort.attribution import AttributionIndex
        t0 = time.time()
        try:
            attribution = AttributionIndex.load(args.radich)
        except (FileNotFoundError, ValueError) as e:
            print(f"error: --radich {args.radich}: {e}", file=sys.stderr)
            sys.exit(1)
        led = attribution.units()["ledger"]
        print(f"evidence: {led['kept for profiling']} units in {led['classes profiled']} classes "
              f"profiled ({time.time() - t0:.0f}s; cached beside the data for next time)")
        if run_manager is not None:
            # Agents get the evidence tools only when the data behind them is here.
            from cohort.embeddings import EmbeddingIndex

            run_manager.attribution = attribution
            try:
                run_manager.embeddings = EmbeddingIndex.from_env()
            except (FileNotFoundError, ValueError, RuntimeError) as e:
                print(f"note: semantic_neighbors disabled — {e}", file=sys.stderr)
            tools = ["attribution_evidence", "align_passages"] + (
                ["semantic_neighbors"] if run_manager.embeddings is not None else []
            )
            print(f"  agent evidence tools: {', '.join(tools)}")

    if not FRONTEND_DIR.is_dir():
        print(
            f"note: no built frontend at {FRONTEND_DIR} — serving the JSON API only.\n"
            "      build it with: cd cohort/ui/frontend && npm install && npm run build",
            file=sys.stderr,
        )

    if args.host not in ("127.0.0.1", "localhost"):
        print(
            f"warning: binding {args.host} exposes a CC BY-NC-SA-licensed corpus "
            "view beyond this machine",
            file=sys.stderr,
        )

    modes = ["read-only"]
    if args.allow_writes:
        modes.append("researcher writes")
    if source is not None:
        modes.append("corpus")
    if study is not None:
        modes.append("ascription study")
    if run_manager is not None:
        modes.append(f"agent runs (max ${args.max_budget:.2f}/run)")
    if attribution is not None:
        modes.append("evidence")
    mode = " + ".join(modes)
    print(f"serving {db_path} at http://{args.host}:{args.port} ({mode})")
    if args.allow_writes:
        print(
            "  writes enabled: accept/reject/reopen act as RESEARCHER, and take the "
            "writer lock\n  for one request each (409 while an agent run holds it)"
        )
    if run_manager is not None:
        cfg = run_manager.config()
        if not cfg["model_configured"]:
            print(f"  warning: {cfg['config_error']} — runs will be refused", file=sys.stderr)
        else:
            print(f"  agent runs enabled: model {cfg['model']}, ceiling ${args.max_budget:.2f} per run")
            print("  every run is capped in code and stops before the call that would exceed it")

    uvicorn.run(
        create_app(
            db_path, args.log, allow_writes=args.allow_writes,
            source=source, run_manager=run_manager,
            attribution=attribution, study=study,
        ),
        host=args.host, port=args.port,
    )


if __name__ == "__main__":
    main()
