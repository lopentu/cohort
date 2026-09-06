"""Manual live demonstration of real concurrent multi-agent execution
(docs/roadmap.md "Scope revision", agent-society axis step 4).

Never imported by pytest, never run automatically — same discipline as
`scripts/smoke_openrouter.py`. `demo.py` itself stays corpus/API-key-free on
purpose; this is where a live-key-requiring example belongs instead.

Two agents, with distinct declared corpus/method scope (not a cosmetic
prompt difference — see `AttestationWorker`'s `profile` parameter), run
concurrently via `run_swarm()` against the same `Graph` and the same fixture
corpus, each searching for something different. Prints each worker's own
tool-call log, then each agent's contribution-history report.

Usage:
    .venv/bin/python scripts/run_swarm_demo.py

Requires OPENROUTER_API_KEY and OPENROUTER_MODEL (see .env.example).
"""
from __future__ import annotations

import asyncio
import sys
import tempfile
import time
from pathlib import Path

from cohort.agents.attestation_worker import AttestationWorker
from cohort.agents.openrouter import OpenRouterError
from cohort.agents.swarm import run_swarm
from cohort.graph import Graph
from cohort.schemas import AgentKind, AgentProfile, ClaimPayload
from cohort.sources.local_reader import LocalReader

FIXTURE = Path(__file__).resolve().parent.parent / "examples" / "local_corpus"

AGENT_1 = "agent:worker-moon"
AGENT_2 = "agent:worker-mountains"


def main() -> None:
    with tempfile.TemporaryDirectory(prefix="cohort_swarm_demo_") as tmp:
        tmp_path = Path(tmp)
        graph = Graph.open(tmp_path / "graph.sqlite", tmp_path / "events.jsonl")
        source = LocalReader(FIXTURE)

        graph.register_agent(
            AgentProfile(
                id=AGENT_1, kind=AgentKind.WORKER,
                corpus_scope="poems mentioning the moon", method_label="imagery/thematic",
            ),
            authored_by=AGENT_1,
        )
        graph.register_agent(
            AgentProfile(
                id=AGENT_2, kind=AgentKind.WORKER,
                corpus_scope="poems mentioning mountains or solitude", method_label="imagery/thematic",
            ),
            authored_by=AGENT_2,
        )

        try:
            worker_1 = AttestationWorker(graph, source=source, authored_by=AGENT_1, profile=graph.agent_profile(AGENT_1))
            worker_2 = AttestationWorker(graph, source=source, authored_by=AGENT_2, profile=graph.agent_profile(AGENT_2))
        except OpenRouterError as e:
            print(f"config error: {e}", file=sys.stderr)
            source.close()
            graph.close()
            sys.exit(1)

        claim_moon = graph.propose_claim(
            ClaimPayload(text="The moon appears in Tang poetry as a figure for homesickness"),
            authored_by=AGENT_1,
        )
        claim_mountains = graph.propose_claim(
            ClaimPayload(text="Solitary figures against mountain landscapes recur in Tang poetry"),
            authored_by=AGENT_2,
        )

        assignments = [
            (worker_1, f"Find attestations for claim {claim_moon!r} using the query 明月, then stop."),
            (worker_2, f"Find attestations for claim {claim_mountains!r} using the query 空山, then stop."),
        ]

        print(f"Running {len(assignments)} agents concurrently against OpenRouter...\n")
        started = time.monotonic()
        results = asyncio.run(run_swarm(assignments))
        elapsed = time.monotonic() - started
        print(f"Both agents finished in {elapsed:.2f}s (real overlap, not {len(assignments)}x sequential)\n")

        for (worker, _instructions), result in zip(assignments, results):
            print(f"--- {worker.authored_by} ---")
            if isinstance(result, BaseException):
                print(f"  failed: {type(result).__name__}: {result}")
            else:
                for entry in result:
                    status = "error" if entry["is_error"] else "ok"
                    print(f"  {entry['tool']} -> {status}: {entry['result']}")
            report = graph.agent_report(worker.authored_by)
            print(f"  agent_report: proposed={report.proposed} attested={report.attested} "
                  f"accepted={report.accepted} rejected={report.rejected}\n")

        source.close()
        graph.close()


if __name__ == "__main__":
    main()
