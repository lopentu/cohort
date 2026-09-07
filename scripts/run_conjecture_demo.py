"""Manual live run of `propose_conjecture` against the real CBETA archive —
the last stage-2/3 capability never exercised on real text (docs/handoff.md).

Never imported by pytest, never run automatically, same discipline as the
other live scripts.

**Spend is capped in code, not estimated** — see `cohort/agents/budget.py`,
which this script originally contained and now shares with the UI's run
launcher, so there is one cap implementation rather than two.

What makes the run worth doing now rather than earlier: `propose_conjecture`
must run a prior-art search *before* proposing, and that search now reaches
the whole corpus through the FTS index (20,190 entries) instead of a
four-entry hand list. The prior-art step is therefore a real check against
1.4 million citable spans rather than a formality.

Usage:
    .venv/bin/python scripts/run_conjecture_demo.py
    .venv/bin/python scripts/run_conjecture_demo.py --budget 0.10 --max-turns 3
"""
from __future__ import annotations

import argparse
import os
import sys
from pathlib import Path

from cohort.agents.attestation_worker import AttestationWorker
from cohort.agents.budget import BudgetedTransport, BudgetExceeded
from cohort.agents.openrouter import OpenRouterError, _load_dotenv
from cohort.eventlog import summarize_model_calls
from cohort.graph import Graph
from cohort.schemas import AgentKind, AgentProfile, NodeType
from cohort.sources.cbeta_fts import CbetaFtsIndex
from cohort.sources.cbeta_reader import CbetaArchiveError, CbetaReader
from cohort.sources.env import CBETA_V061_SHA256  # one definition; see docs/corpus.md

REPO_ROOT = Path(__file__).resolve().parent.parent
AGENT = "agent:worker-conjecture"


def main() -> None:
    parser = argparse.ArgumentParser(description=__doc__)
    parser.add_argument("--budget", type=float, default=0.25,
                        help="hard USD cap on this run (default 0.25)")
    parser.add_argument("--max-turns", type=int, default=4)
    parser.add_argument("--db", default=None, help="persist to this graph instead of a temp one")
    args = parser.parse_args()

    _load_dotenv(REPO_ROOT / ".env")
    archive_path = os.environ.get("CBETA_ARCHIVE_PATH")
    if not archive_path:
        print("config error: CBETA_ARCHIVE_PATH is not set", file=sys.stderr)
        sys.exit(1)

    fts_path = Path(os.environ.get("CBETA_FTS_PATH") or (REPO_ROOT / "cbeta_fts.sqlite"))
    try:
        index = CbetaFtsIndex(fts_path, CBETA_V061_SHA256)
        source = CbetaReader(archive_path, CBETA_V061_SHA256, fts=index)
    except CbetaArchiveError as e:
        print(f"error: {e}\n(build the index: scripts/build_cbeta_index.py)", file=sys.stderr)
        sys.exit(1)

    db_path = Path(args.db) if args.db else REPO_ROOT / "conjecture_run.sqlite"
    log_path = db_path.with_suffix(".jsonl")
    for p in (db_path, log_path, db_path.with_suffix(db_path.suffix + ".lock")):
        p.unlink(missing_ok=True)

    graph = Graph.open(db_path, log_path)
    graph.register_agent(
        AgentProfile(
            id=AGENT, kind=AgentKind.WORKER,
            corpus_scope="CBETA v061, full corpus via the FTS index",
            method_label="phrase distribution across witnesses",
        ),
        authored_by=AGENT,
    )

    def report(call: dict) -> None:
        marker = "" if call["cost_reported"] else "  (cost not reported; charged as estimate)"
        print(
            f'    call {call["call"]}: ${call["charged"]:.5f}  '
            f'running total ${call["spent"]:.5f}{marker}',
            flush=True,
        )

    transport = BudgetedTransport(args.budget, on_call=report)
    try:
        worker = AttestationWorker(
            graph, source=source, authored_by=AGENT,
            profile=graph.agent_profile(AGENT), transport=transport,
        )
    except OpenRouterError as e:
        print(f"config error: {e}", file=sys.stderr)
        graph.close()
        sys.exit(1)

    instructions = (
        "The phrase 色即是空 ('form is emptiness') appears in many different texts "
        "across the CBETA corpus, including several distinct Chinese translations "
        "of the Heart Sutra. Using propose_conjecture, propose ONE conjecture about "
        "the transmission of this phrase that the sources do not state outright. "
        "Use 色即是空 as the prior_art_query. Make exactly one propose_conjecture "
        "call, then stop."
    )

    print(f"budget cap: ${args.budget:.2f}   max turns: {args.max_turns}")
    print(f"model: {worker.model}\n")
    print("running one agent against OpenRouter...")

    stopped_early = None
    try:
        log = worker.run(instructions, max_turns=args.max_turns)
    except BudgetExceeded as e:
        stopped_early = str(e)
        log = []

    print()
    for entry in log:
        status = "error" if entry["is_error"] else "ok"
        result = entry["result"]
        print(f"  {entry['tool']} -> {status}: {str(result)[:160]}")

    conjectures = graph.nodes(node_type=NodeType.CONJECTURE)
    print(f"\nconjectures proposed: {len(conjectures)}")
    for node in conjectures:
        p = node.payload
        print(f"\n  [{node.status}] {p['text']}")
        for field in ("derivation", "corpus_boundary", "selection_risks",
                      "alternative_explanations"):
            print(f"    {field}: {p[field]}")
        tests = graph.edges(dst=node.id)
        kinds = {e.type for e in tests}
        print(f"    edges in: {sorted(kinds)}")
        print(f"    attestable by the falsifiability gate: {'tests' in kinds}")

    queries = graph.nodes(node_type=NodeType.QUERY)
    if queries:
        print(f"\nquery nodes recorded: {len(queries)}")
        for q in queries:
            print(f"  - {q.payload['text']}")

    graph.close()

    summary = summarize_model_calls(log_path)
    print(
        f"\n--- spend ---\n"
        f"  calls          : {summary.calls}\n"
        f"  input tokens   : {summary.total_input_tokens}\n"
        f"  output tokens  : {summary.total_output_tokens}\n"
        f"  cost (logged)  : ${summary.total_cost_usd:.5f}\n"
        f"  cost (charged) : ${transport.spent:.5f} of ${args.budget:.2f} cap"
    )
    if stopped_early:
        print(f"\nstopped early: {stopped_early}")


if __name__ == "__main__":
    main()
