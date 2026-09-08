"""AttestationWorker's tool-dispatch loop, exercised against a fake
OpenRouter transport — no network, no API key. This does not prove the real
OpenRouter API round-trips correctly (see scripts/smoke_openrouter.py for
that, run once by hand); it proves the loop's own logic — message building,
tool dispatch, and error reporting — is correct.
"""
from __future__ import annotations

import asyncio
import json
import time
from pathlib import Path

import pytest

from cohort.agents.attestation_worker import AttestationWorker
from cohort.agents.openrouter import OpenRouterError
from cohort.agents.swarm import run_swarm
from cohort.eventlog import read_refusals, summarize_model_calls
from cohort.schemas import (
    RESEARCHER,
    AgentKind,
    AgentProfile,
    ClaimPayload,
    ConjecturePayload,
    EdgeType,
)
from cohort.sources.local_reader import LocalReader

AGENT = "agent:worker-1"
FIXTURE = Path(__file__).parent.parent / "examples" / "local_corpus"


@pytest.fixture
def source():
    r = LocalReader(FIXTURE)
    yield r
    r.close()


def _tool_call(name, args, id_="call_1"):
    return {"id": id_, "type": "function", "function": {"name": name, "arguments": json.dumps(args)}}


def _response(*, content=None, tool_calls=None, finish_reason, input_tokens=10,
              output_tokens=5, cost=None, model="test-model"):
    message: dict = {"role": "assistant", "content": content}
    if tool_calls:
        message["tool_calls"] = tool_calls
    return {
        "id": "gen-1", "model": model,
        "choices": [{"message": message, "finish_reason": finish_reason}],
        "usage": {"prompt_tokens": input_tokens, "completion_tokens": output_tokens, "cost": cost},
    }


class FakeTransport:
    """The test seam `complete()` exposes — no HTTP-mocking dependency
    needed, just a plain callable matching `(url, headers, body, timeout)
    -> (status, raw_bytes)`. `delay_s` does a real blocking `time.sleep()`
    before returning, so it genuinely occupies a thread-pool worker thread
    without blocking the event loop — that's what makes the concurrency
    tests below a real proof, not just "it didn't crash". `status` lets a
    test force a non-200 response, to prove `run_swarm`'s error isolation."""

    def __init__(self, responses: list[dict], *, delay_s: float = 0.0, status: int = 200):
        self._responses = list(responses)
        self.calls: list[dict] = []
        self.delay_s = delay_s
        self.status = status

    def __call__(self, url, headers, body, timeout):
        self.calls.append(json.loads(body))
        if self.delay_s:
            time.sleep(self.delay_s)
        if self.status != 200:
            return self.status, json.dumps({"error": {"message": "forced failure"}}).encode("utf-8")
        return 200, json.dumps(self._responses.pop(0)).encode("utf-8")


def _worker(graph, *, source=None, authored_by=AGENT, transport, profile=None):
    return AttestationWorker(
        graph, source=source, authored_by=authored_by, model="test-model",
        api_key="test-key", transport=transport, profile=profile,
    )


def test_worker_runs_a_tool_call_and_then_stops(graph, source):
    transport = FakeTransport([
        _response(tool_calls=[_tool_call("propose_conjecture", {
            "text": "a conjecture",
            "derivation": "vocabulary matches a known pattern",
            "corpus_boundary": "only the local_corpus fixture was searched",
            "selection_risks": "none identified",
            "alternative_explanations": "none identified",
            "prior_art_query": "a conjecture",
            "tests_query_text": "a testing query",
            "tests_expectation": "at_most", "tests_expected_hits": 0,
        })], finish_reason="tool_calls"),
        _response(content="done", finish_reason="stop"),
    ])
    worker = _worker(graph, source=source, transport=transport)

    log = worker.run("propose a conjecture")

    assert len(log) == 1
    assert log[0]["tool"] == "propose_conjecture"
    assert log[0]["is_error"] is False
    conjecture_id = log[0]["result"]
    assert graph.get_node(conjecture_id).type == "conjecture"
    assert graph.edges(edge_type=EdgeType.TESTS, dst=conjecture_id)
    assert len(transport.calls) == 2  # one tool_calls turn, one final turn


def test_worker_logs_a_model_call_event_with_token_and_latency_metadata(graph):
    transport = FakeTransport([
        _response(content="done", finish_reason="stop", input_tokens=42, output_tokens=7, cost=0.0034),
    ])
    worker = _worker(graph, transport=transport)

    worker.run("do nothing")

    summary = summarize_model_calls(graph.event_log.path)
    assert summary.calls == 1
    assert summary.total_input_tokens == 42
    assert summary.total_output_tokens == 7
    assert summary.total_cost_usd == pytest.approx(0.0034)


def test_worker_reports_a_refused_write_as_a_tool_error_without_crashing(graph):
    transport = FakeTransport([
        _response(tool_calls=[_tool_call(
            "find_attestations", {"claim_or_conjecture_id": "claim:missing", "query": "x"},
        )], finish_reason="tool_calls"),
        _response(content="adjusting", finish_reason="stop"),
    ])
    worker = _worker(graph, transport=transport)

    log = worker.run("find attestations for a claim that doesn't exist")

    assert log[0]["is_error"] is True
    assert "NodeNotFound" in log[0]["result"]


def test_worker_prepends_rejected_conjectures_to_its_instructions(graph):
    conjecture_id = graph.propose_conjecture(
        ConjecturePayload(
            text="an earlier Kuchean recension underlies this",
            derivation="vocabulary matches Kuchean loanword patterns",
            corpus_boundary="only the local_corpus fixture was searched",
            selection_risks="none identified",
            alternative_explanations="none identified",
        ),
        authored_by=AGENT,
    )
    graph.reject(
        conjecture_id, authored_by=RESEARCHER,
        reason="no Kuchean fragment catalogue exists for this text",
    )

    transport = FakeTransport([_response(content="noted", finish_reason="stop")])
    worker = _worker(graph, transport=transport)

    worker.run("propose any conjectures worth testing")

    sent_content = transport.calls[0]["messages"][1]["content"]  # [0] is the system message
    assert "Kuchean recension" in sent_content
    assert "no Kuchean fragment catalogue exists" in sent_content
    assert "propose any conjectures worth testing" in sent_content


def test_worker_prepends_its_declared_profile(graph):
    profile = AgentProfile(
        id=AGENT, kind=AgentKind.WORKER, corpus_scope="T01-T02", method_label="philological",
    )
    transport = FakeTransport([_response(content="noted", finish_reason="stop")])
    worker = _worker(graph, transport=transport, profile=profile)

    worker.run("do something")

    sent_content = transport.calls[0]["messages"][1]["content"]
    assert "T01-T02" in sent_content
    assert "philological" in sent_content
    assert "do something" in sent_content


def test_worker_without_a_profile_sends_plain_instructions(graph):
    transport = FakeTransport([_response(content="noted", finish_reason="stop")])
    worker = _worker(graph, transport=transport)

    worker.run("do something")

    sent_content = transport.calls[0]["messages"][1]["content"]
    assert sent_content == "do something"


def test_worker_omits_rejection_context_when_nothing_is_rejected(graph):
    transport = FakeTransport([_response(content="noted", finish_reason="stop")])
    worker = _worker(graph, transport=transport)

    worker.run("propose any conjectures worth testing")

    sent_content = transport.calls[0]["messages"][1]["content"]
    assert sent_content == "propose any conjectures worth testing"


def test_worker_stops_immediately_on_end_turn_with_no_tool_use(graph):
    transport = FakeTransport([_response(content="nothing to do", finish_reason="stop")])
    worker = _worker(graph, transport=transport)

    log = worker.run("do nothing")

    assert log == []
    assert len(transport.calls) == 1


def test_run_raises_a_clear_error_from_inside_a_running_event_loop(graph):
    transport = FakeTransport([_response(content="noted", finish_reason="stop")])
    worker = _worker(graph, transport=transport)

    async def call_run_from_a_coroutine():
        worker.run("do something")  # should raise before ever awaiting anything

    with pytest.raises(RuntimeError, match="use run_async"):
        asyncio.run(call_run_from_a_coroutine())


# --- real concurrency (docs/roadmap.md "Scope revision", agent-society step 4) --

def test_run_swarm_runs_workers_concurrently_not_sequentially(graph, source):
    delay_s = 0.2
    workers = [
        _worker(graph, source=source, authored_by=f"agent:worker-{i}",
                transport=FakeTransport([_response(content="done", finish_reason="stop")], delay_s=delay_s))
        for i in range(3)
    ]
    assignments = [(w, "do nothing") for w in workers]

    started = time.monotonic()
    results = asyncio.run(run_swarm(assignments))
    elapsed = time.monotonic() - started

    assert all(isinstance(r, list) for r in results)
    # sequentially this would take ~3 * delay_s; concurrently, close to delay_s alone
    assert elapsed < delay_s * 2, f"expected concurrent overlap, took {elapsed:.2f}s for 3x{delay_s}s workers"


def test_run_swarm_both_workers_write_to_the_shared_graph(graph, source):
    w1 = _worker(graph, source=source, authored_by="agent:worker-1", transport=FakeTransport([
        _response(tool_calls=[_tool_call("propose_conjecture", {
            "text": "conjecture from worker 1",
            "derivation": "n/a", "corpus_boundary": "n/a",
            "selection_risks": "none identified", "alternative_explanations": "none identified",
            "prior_art_query": "worker 1 query", "tests_query_text": "a testing query",
            "tests_expectation": "at_most", "tests_expected_hits": 0,
        })], finish_reason="tool_calls"),
        _response(content="done", finish_reason="stop"),
    ]))
    w2 = _worker(graph, source=source, authored_by="agent:worker-2", transport=FakeTransport([
        _response(tool_calls=[_tool_call("propose_conjecture", {
            "text": "conjecture from worker 2",
            "derivation": "n/a", "corpus_boundary": "n/a",
            "selection_risks": "none identified", "alternative_explanations": "none identified",
            "prior_art_query": "worker 2 query", "tests_query_text": "a testing query",
            "tests_expectation": "at_most", "tests_expected_hits": 0,
        })], finish_reason="tool_calls"),
        _response(content="done", finish_reason="stop"),
    ]))

    results = asyncio.run(run_swarm([(w1, "propose a conjecture"), (w2, "propose a conjecture")]))

    conjecture_id_1 = results[0][0]["result"]
    conjecture_id_2 = results[1][0]["result"]
    assert conjecture_id_1 != conjecture_id_2
    assert graph.get_node(conjecture_id_1).payload["text"] == "conjecture from worker 1"
    assert graph.get_node(conjecture_id_2).payload["text"] == "conjecture from worker 2"


def test_run_swarm_isolates_one_workers_transport_failure(graph):
    good = _worker(graph, authored_by="agent:worker-good",
                    transport=FakeTransport([_response(content="done", finish_reason="stop")]))
    bad = _worker(graph, authored_by="agent:worker-bad",
                   transport=FakeTransport([], status=500))

    results = asyncio.run(run_swarm([(good, "do nothing"), (bad, "do nothing")]))

    assert results[0] == []  # the good worker's normal (empty) log
    assert isinstance(results[1], OpenRouterError)


class ClaimThenAttestTransport:
    """Reads the claim id back out of the tool-result message, the way the
    model itself has to, instead of having it patched in. That makes this a
    real proof that propose_claim's return value is usable as the next
    call's input — which is the whole point of adding the tool."""

    def __init__(self):
        self.calls: list[dict] = []

    def __call__(self, url, headers, body, timeout):
        payload = json.loads(body)
        self.calls.append(payload)
        tool_results = [m for m in payload["messages"] if m["role"] == "tool"]
        if not tool_results:
            resp = _response(tool_calls=[_tool_call("propose_claim", {
                "text": "The moon figures as homesickness in this corpus",
                "grounding_query": "明月",
            })], finish_reason="tool_calls")
        elif len(tool_results) == 1:
            claim_id = json.loads(tool_results[0]["content"])["result"]
            resp = _response(tool_calls=[_tool_call(
                "find_attestations", {"claim_or_conjecture_id": claim_id, "query": "明月"},
                id_="call_2",
            )], finish_reason="tool_calls")
        else:
            resp = _response(content="done", finish_reason="stop")
        return 200, json.dumps(resp).encode("utf-8")


def test_worker_proposes_a_claim_and_cites_it_but_cannot_close_the_rung(graph, source):
    """The round trip the live conjecture run could not make: before
    propose_claim existed, a worker that wanted attestations for a
    proposition not yet in the graph had to invent a node id, and was
    refused five times over. Here it gets the id from its own previous tool
    call and both calls succeed.

    Where it now stops is the author-is-not-reviewer rule: the worker records
    the passages and the `attests` edges — all the evidence — and leaves the
    claim at `proposed` for someone else to check. Neither call is an error,
    which matters: this is the designed path, not a refusal the model has to
    work around."""
    worker = _worker(graph, source=source, transport=ClaimThenAttestTransport())

    log = worker.run("propose and attest a claim")

    assert [e["tool"] for e in log] == ["propose_claim", "find_attestations"]
    assert not any(e["is_error"] for e in log)
    claim_id = log[0]["result"]
    assert graph.get_node(claim_id).type == "claim"
    assert graph.edges(edge_type=EdgeType.ATTESTS, dst=claim_id), "evidence recorded"

    assert graph.get_node(claim_id).status == "proposed"


def test_worker_reports_an_ungrounded_claim_back_to_the_model(graph, source):
    """The grounding guard has to surface as a tool error the model can act
    on, not as a crash — same contract as every other refusal."""
    transport = FakeTransport([
        _response(tool_calls=[_tool_call("propose_claim", {
            "text": "a claim about nothing in this corpus",
            "grounding_query": "龍樹菩薩勸誡王頌",
        })], finish_reason="tool_calls"),
        _response(content="adjusting", finish_reason="stop"),
    ])
    worker = _worker(graph, source=source, transport=transport)

    log = worker.run("propose a claim")

    assert log[0]["is_error"] is True
    assert "no hits" in log[0]["result"]
    assert not graph.nodes(node_type="claim")


def test_a_refused_tool_call_is_recorded_in_the_event_log(graph, source):
    """The live conjecture run lost five refusals this way: `NodeNotFound`
    comes from a *lookup*, not from `graph._refuse()`, so it was reported to
    the model and then vanished — the log recorded a clean run. docs/design.md §15
    claims refusals are part of the scholarly output, which has to include
    the most common one an agent actually hits."""
    transport = FakeTransport([
        _response(tool_calls=[_tool_call(
            "find_attestations",
            {"claim_or_conjecture_id": "claim:invented_by_the_model", "query": "明月"},
        )], finish_reason="tool_calls"),
        _response(content="adjusting", finish_reason="stop"),
    ])
    worker = _worker(graph, source=source, transport=transport)

    log = worker.run("attest something")
    assert log[0]["is_error"] is True

    refusals = read_refusals(graph.event_log.path)
    assert len(refusals) == 1
    assert refusals[0].rule == "NodeNotFound"
    assert refusals[0].attempted == "find_attestations"
    assert refusals[0].node_id == "claim:invented_by_the_model"
    assert refusals[0].authored_by == AGENT
    # linked back to the model call that caused it, so cost and refusal join up
    assert refusals[0].model_call_id is not None


def test_a_write_boundary_refusal_is_logged_once_not_twice(graph, source):
    """`graph._refuse()` already logs; `_dispatch` must not log it again."""
    claim_id = graph.propose_claim(ClaimPayload(text="c"), authored_by=AGENT)
    graph.reject(claim_id, authored_by=RESEARCHER, reason="thrown out")
    before = len(read_refusals(graph.event_log.path))

    # re-proposing a rejected claim is refused at the write boundary
    transport = FakeTransport([
        _response(tool_calls=[_tool_call("record_contradiction", {
            "node_a_id": claim_id, "node_b_id": claim_id, "reason": "self",
        })], finish_reason="tool_calls"),
        _response(content="ok", finish_reason="stop"),
    ])
    worker = _worker(graph, source=source, transport=transport)
    log = worker.run("try it")

    assert log[0]["is_error"] is True
    after = read_refusals(graph.event_log.path)
    assert len(after) == before + 1, "a single refusal must produce a single event"
    assert after[-1].rule == "EdgeSelfLoop"


@pytest.mark.parametrize(('finish_reason', 'expected'), [('tool_calls', True), ('stop', False)])
def test_turn_limit_is_distinct_from_model_finishing(graph, finish_reason, expected):
    transport = FakeTransport([_response(finish_reason=finish_reason)])
    worker = _worker(graph, transport=transport)
    worker.run('investigate', max_turns=1)
    assert worker.turn_limit_reached is expected
