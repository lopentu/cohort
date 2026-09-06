"""run_swarm() itself (docs/roadmap.md "Scope revision", agent-society step 4).

The deeper concurrency-safety proofs (real overlap, shared-graph writes,
error isolation) live in tests/test_attestation_worker.py, next to
AttestationWorker.run_async() — that's what the safety argument actually
rests on. This file just covers run_swarm()'s own contract: ordering and
the empty-input edge case.
"""
from __future__ import annotations

import asyncio

from test_attestation_worker import FakeTransport, _response

from cohort.agents.attestation_worker import AttestationWorker
from cohort.agents.swarm import run_swarm


def _worker(graph, *, authored_by, transport):
    return AttestationWorker(
        graph, source=None, authored_by=authored_by, model="test-model",
        api_key="test-key", transport=transport,
    )


def test_run_swarm_returns_results_in_assignment_order(graph):
    w1 = _worker(graph, authored_by="agent:worker-1",
                 transport=FakeTransport([_response(content="one", finish_reason="stop")]))
    w2 = _worker(graph, authored_by="agent:worker-2",
                 transport=FakeTransport([_response(content="two", finish_reason="stop")]))

    results = asyncio.run(run_swarm([(w1, "first"), (w2, "second")]))

    assert results == [[], []]  # both are no-tool-call turns, so both logs are empty


def test_run_swarm_with_no_assignments_returns_empty(graph):
    results = asyncio.run(run_swarm([]))
    assert results == []
