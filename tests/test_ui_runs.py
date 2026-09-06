"""Corpus endpoints and the agent-run launcher (the web/Python parity layer).

Two properties matter more than the routing:

* the run launcher cannot be talked into spending more than the server's
  ceiling, whatever the client sends; and
* single-writer discipline is not weakened by having a second way in — a run
  holds the lock, and the researcher's writes conflict rather than queueing.

No network: every run here goes through a fake transport, the same seam
`complete()` already exposes.
"""
from __future__ import annotations

import json
import re
import time

import itertools

import pytest

fastapi = pytest.importorskip("fastapi", reason="the `ui` extra is not installed")
from fastapi.testclient import TestClient  # noqa: E402

from cohort.agents.budget import BudgetedTransport, BudgetExceeded  # noqa: E402
from cohort.errors import CohortError  # noqa: E402
from cohort.graph import Graph  # noqa: E402
from cohort.schemas import ClaimPayload  # noqa: E402
from cohort.sources.local_reader import LocalReader  # noqa: E402
from cohort.ui.api import create_app  # noqa: E402
from cohort.ui.runs import (  # noqa: E402
    ROLE_REVIEWER,
    ROLE_WORKER,
    AgentSpec,
    RunManager,
    RunRejected,
)

from pathlib import Path  # noqa: E402

AGENT = "agent:worker-1"


FIXTURE = Path(__file__).parent.parent / "examples" / "local_corpus"


#: Distinct provider prefixes, because agents in one run may not share a model
#: family. The counter makes each `spec()` call independent by default, so a
#: test about attribution or budgets does not have to think about rosters — but
#: a test that *wants* a shared family passes `model=` explicitly.
_MODEL_SEQ = itertools.count()


def spec(agent_id="agent:ui-worker", instructions="go", scope="", method="", model=None,
         role=ROLE_WORKER):
    if model is None:
        model = f"vendor{next(_MODEL_SEQ)}/fake-model"
    return AgentSpec(agent_id, instructions, scope, method, model, role)


@pytest.fixture
def source():
    r = LocalReader(FIXTURE)
    yield r
    r.close()


@pytest.fixture
def graph_files(tmp_path):
    db_path = tmp_path / "graph.sqlite"
    log_path = tmp_path / "graph.jsonl"
    g = Graph.open(db_path, log_path)
    g.propose_claim(ClaimPayload(text="seed"), authored_by=AGENT)
    g.close()
    return db_path, log_path


# --- corpus endpoints --------------------------------------------------------

def test_corpus_search_matches_what_python_returns(graph_files, source):
    """Parity is the point: the endpoint must be `source.search()`, not a
    reimplementation that could drift from it."""
    db_path, _ = graph_files
    client = TestClient(create_app(db_path, source=source))

    body = client.get("/api/corpus/search", params={"q": "明月"}).json()
    direct = source.search("明月", max_results=20)

    assert body["count"] == len(direct)
    assert [h["ref"] for h in body["hits"]] == [h.ref for h in direct]


def test_corpus_search_says_it_is_unranked(graph_files, source):
    """A list that looks ranked but is not would misrepresent which witnesses
    are most relevant, so the absence of ranking is stated, not hidden."""
    db_path, _ = graph_files
    client = TestClient(create_app(db_path, source=source))
    body = client.get("/api/corpus/search", params={"q": "明月"}).json()
    assert "no relevance ranking" in body["ordering"]


def test_corpus_fetch_carries_license_terms_and_flags_truncation(graph_files, source):
    db_path, _ = graph_files
    client = TestClient(create_app(db_path, source=source))
    ref = source.search("明月", max_results=1)[0].ref

    full = client.get("/api/corpus/fetch", params={"ref": ref}).json()
    assert full["witness_ref"]
    assert full["truncated"] is False
    assert full["total_chars"] == len(full["text"])

    cut = client.get("/api/corpus/fetch", params={"ref": ref, "max_chars": 5}).json()
    assert cut["truncated"] is True
    assert len(cut["text"]) == 5
    assert cut["total_chars"] > 5  # the real length is still reported


def test_corpus_endpoints_absent_without_a_source(graph_files):
    db_path, _ = graph_files
    client = TestClient(create_app(db_path))
    assert client.get("/api/corpus/search", params={"q": "x"}).status_code == 404
    assert client.get("/api/health").json()["corpus_enabled"] is False


# --- the budget cap ----------------------------------------------------------

def _priced_response(cost):
    return json.dumps({
        "id": "gen", "model": "m",
        "choices": [{"message": {"role": "assistant", "content": "ok"}, "finish_reason": "stop"}],
        "usage": {"prompt_tokens": 1, "completion_tokens": 1, "cost": cost},
    }).encode()


def test_budget_stops_before_the_call_that_would_exceed_it(monkeypatch):
    """A budget checked only afterwards is a receipt, not a budget."""
    calls = []

    def fake_transport(url, headers, body, timeout):
        calls.append(1)
        return 200, _priced_response(0.04)

    monkeypatch.setattr("cohort.agents.budget.default_transport", fake_transport)
    t = BudgetedTransport(0.10)
    t(None, None, None, None)   # 0.04
    t(None, None, None, None)   # 0.08
    t(None, None, None, None)   # 0.12 -> over
    with pytest.raises(BudgetExceeded):
        t(None, None, None, None)
    assert len(calls) == 3, "the over-budget call must not be made"


def test_an_unpriced_response_is_charged_not_free(monkeypatch):
    """A provider omitting usage.cost must not grant an unlimited run."""
    monkeypatch.setattr(
        "cohort.agents.budget.default_transport",
        lambda *a: (200, _priced_response(None)),
    )
    t = BudgetedTransport(0.10, unknown_call_cost=0.05)
    t(None, None, None, None)
    t(None, None, None, None)
    snap = t.snapshot()
    assert snap["spent_usd"] == pytest.approx(0.10)
    assert snap["unpriced_calls"] == 2
    with pytest.raises(BudgetExceeded):
        t(None, None, None, None)


def test_budget_must_be_positive():
    with pytest.raises(ValueError):
        BudgetedTransport(0)


# --- the run launcher --------------------------------------------------------

class FakeRunTransport:
    """Answers with one tool call, then stops."""

    def __init__(self, tool="propose_claim", args=None):
        self.tool = tool
        self.args = args or {"text": "a claim from the UI", "grounding_query": "明月"}
        self.calls = 0

    def __call__(self, url, headers, body, timeout):
        self.calls += 1
        payload = json.loads(body)
        made_a_call = any(m["role"] == "tool" for m in payload["messages"])
        message = {"role": "assistant", "content": None if not made_a_call else "done"}
        if not made_a_call:
            message["tool_calls"] = [{
                "id": "c1", "type": "function",
                "function": {"name": self.tool, "arguments": json.dumps(self.args)},
            }]
        return 200, json.dumps({
            "id": "gen", "model": "fake-model",
            "choices": [{
                "message": message,
                "finish_reason": "tool_calls" if not made_a_call else "stop",
            }],
            "usage": {"prompt_tokens": 5, "completion_tokens": 5, "cost": 0.001},
        }).encode()


@pytest.fixture
def manager(graph_files, source, monkeypatch):
    monkeypatch.setenv("OPENROUTER_API_KEY", "test-key")
    monkeypatch.setenv("OPENROUTER_MODEL", "fake-model")
    db_path, log_path = graph_files
    transport = FakeRunTransport()
    return RunManager(
        db_path, log_path, source, max_budget_usd=0.50,
        transport_factory=lambda budget, on_call: transport,
    )


def _await_finish(manager, timeout=10.0):
    deadline = time.time() + timeout
    while time.time() < deadline:
        current = manager.current()
        if current is None:
            break
        time.sleep(0.02)
    runs = manager.history(limit=1)
    assert runs, "no run recorded"
    return runs[0]


def test_a_run_started_from_the_api_writes_to_the_graph(manager, graph_files):
    manager.start(
        [spec(instructions="propose a claim about the moon")], budget_usd=0.10,
    )
    run = _await_finish(manager)

    assert run["state"] == "finished", run
    assert run["error"] is None
    assert [c["tool"] for c in run["tool_calls"]] == ["propose_claim"]
    assert run["tool_calls"][0]["is_error"] is False

    db_path, _ = graph_files
    g = Graph.open_read_only(db_path)
    try:
        claims = [n for n in g.nodes(node_type="claim") if "from the UI" in n.payload["text"]]
        assert len(claims) == 1
    finally:
        g.close()


def test_the_client_cannot_raise_the_servers_budget_ceiling(manager):
    """The browser proposes a budget; the server bounds it. A client-supplied
    number nothing checks is a suggestion, not a cap."""
    with pytest.raises(RunRejected, match="exceeds this server's ceiling"):
        manager.start([spec()], budget_usd=999.0)


def test_only_one_run_at_a_time(manager):
    manager.start([spec()], budget_usd=0.10)
    try:
        with pytest.raises(RunRejected, match="already in progress"):
            manager.start([spec(instructions="go again")], budget_usd=0.10)
    finally:
        _await_finish(manager)


def test_a_run_without_a_corpus_is_refused_with_a_reason(graph_files, monkeypatch):
    monkeypatch.setenv("OPENROUTER_API_KEY", "k")
    monkeypatch.setenv("OPENROUTER_MODEL", "m")
    db_path, log_path = graph_files
    m = RunManager(db_path, log_path, None)
    with pytest.raises(RunRejected, match="no corpus is configured"):
        m.start([spec(agent_id="agent:a")], budget_usd=0.1)


def test_empty_instructions_are_refused(manager):
    with pytest.raises(RunRejected, match="has no task"):
        manager.start([spec(instructions="   ")], budget_usd=0.1)


def test_a_runs_refusals_are_attributed_to_that_run(graph_files, source, monkeypatch):
    """A run reports the refusals *it* caused, not the log's whole history."""
    monkeypatch.setenv("OPENROUTER_API_KEY", "k")
    monkeypatch.setenv("OPENROUTER_MODEL", "fake-model")
    db_path, log_path = graph_files

    # a pre-existing refusal, from before this run
    g = Graph.open(db_path, log_path)
    stale = g.propose_claim(ClaimPayload(text="stale"), authored_by=AGENT)
    # a refusal by the write boundary, not merely any exception
    with pytest.raises(CohortError):
        g.attest(stale, authored_by=AGENT)
    g.close()

    transport = FakeRunTransport(
        tool="find_attestations",
        args={"claim_or_conjecture_id": "claim:invented", "query": "明月"},
    )
    m = RunManager(
        db_path, log_path, source, max_budget_usd=0.5,
        transport_factory=lambda budget, on_call: transport,
    )
    m.start([spec(instructions="attest something")], budget_usd=0.1)
    run = _await_finish(m)

    assert run["state"] == "finished"
    assert len(run["refusals"]) == 1, run["refusals"]
    assert run["refusals"][0]["rule"] == "NodeNotFound"


def test_a_real_run_records_itself_and_stamps_what_it_wrote(manager, graph_files):
    """End to end through `RunManager`: the id it has always minted now
    reaches the log, so the run and its writes can be found again after the
    process is gone."""
    from cohort.eventlog import read_events, read_runs

    _db, log_path = graph_files
    started = manager.start([spec(instructions="propose a claim")], budget_usd=0.10)
    run = _await_finish(manager)
    run_id = started["id"]

    recorded = read_runs(log_path)
    assert [r.run_id for r in recorded] == [run_id]
    assert recorded[0].state == run["state"] == "finished"
    assert recorded[0].finished_at is not None
    assert recorded[0].agents[0]["agent_id"] == "agent:ui-worker"
    assert recorded[0].spent_usd is not None

    # the seed claim was written before any run and must not be attributed
    proposes = [ev for ev in read_events(log_path) if ev.event == "propose"]
    assert proposes[0].run_id is None
    assert proposes[-1].run_id == run_id


def test_run_endpoints_report_spend_and_conflict_with_researcher_writes(
    graph_files, source, monkeypatch
):
    """The lock is shared: while a run holds it, accept/reject must 409 — the
    same answer a script would force, surfaced instead of hidden."""
    monkeypatch.setenv("OPENROUTER_API_KEY", "k")
    monkeypatch.setenv("OPENROUTER_MODEL", "fake-model")
    db_path, log_path = graph_files

    holding = _HoldingTransport()
    m = RunManager(
        db_path, log_path, source, max_budget_usd=0.5,
        transport_factory=lambda budget, on_call: holding,
    )
    client = TestClient(
        create_app(db_path, log_path, allow_writes=True, source=source, run_manager=m)
    )

    assert client.get("/api/health").json()["runs_enabled"] is True
    assert client.get("/api/run/config").json()["max_budget_usd"] == 0.5

    started = client.post(
        "/api/run",
        json={"instructions": "go", "budget_usd": 0.1, "agent_id": "agent:ui-worker"},
    )
    assert started.status_code == 200, started.text

    try:
        holding.entered.wait(timeout=5)
        # a second run is refused while the first holds the lock
        again = client.post("/api/run", json={"instructions": "again", "budget_usd": 0.1})
        assert again.status_code == 409
        assert "already in progress" in again.json()["detail"]

        # and the researcher's own writes conflict rather than corrupting
        claim = next(
            n["id"] for n in client.get("/api/graph").json()["nodes"]
            if n["type"] == "claim"
        )
        r = client.post("/api/reject", params={"id": claim}, json={"reason": "x"})
        assert r.status_code == 409
        assert "Nothing was changed" in r.json()["detail"]

        stopped = client.post("/api/run/stop")
        assert stopped.status_code == 200
        assert stopped.json()["cancel_requested"] is True
    finally:
        holding.release.set()
        _await_finish(m)


class _HoldingTransport:
    """Blocks inside the model call so a test can observe a run mid-flight."""

    def __init__(self):
        import threading
        self.entered = threading.Event()
        self.release = threading.Event()

    def __call__(self, url, headers, body, timeout):
        self.entered.set()
        self.release.wait(timeout=15)
        return 200, json.dumps({
            "id": "gen", "model": "fake-model",
            "choices": [{"message": {"role": "assistant", "content": "done"},
                         "finish_reason": "stop"}],
            "usage": {"prompt_tokens": 1, "completion_tokens": 1, "cost": 0.0},
        }).encode()


# --- swarms ------------------------------------------------------------------

def test_several_agents_run_in_one_run_and_calls_are_attributed(
    graph_files, source, monkeypatch
):
    """Stage 5's "many agents" half. Three agents share one process, one graph,
    one lock and one budget — and every tool call must say which agent made it,
    because with distinct declared scopes that attribution is the whole reason
    to run several."""
    monkeypatch.setenv("OPENROUTER_API_KEY", "k")
    monkeypatch.setenv("OPENROUTER_MODEL", "fake-model")
    db_path, log_path = graph_files
    transport = FakeRunTransport()
    m = RunManager(
        db_path, log_path, source, max_budget_usd=0.50,
        transport_factory=lambda budget, on_call: transport,
    )

    m.start(
        [
            spec("agent:moon", "attest 明月", scope="Tang poetry", method="phrase"),
            spec("agent:hill", "attest 空山", scope="landscape verse", method="phrase"),
            spec("agent:third", "attest 明月 again", scope="all", method="phrase"),
        ],
        budget_usd=0.30,
    )
    run = _await_finish(m, timeout=20.0)

    assert run["state"] == "finished", run
    assert run["agent_id"] == "3 agents"
    by_id = {a["agent_id"]: a for a in run["agents"]}
    assert set(by_id) == {"agent:moon", "agent:hill", "agent:third"}
    for a in by_id.values():
        assert a["tool_calls"], f"{a['agent_id']} made no tool call"
        assert a["error"] is None
    # every call in the flat list is attributed
    assert all(c.get("agent_id") for c in run["tool_calls"])

    # declared scope reached the graph as a real profile, not a prompt flourish
    g = Graph.open_read_only(db_path)
    try:
        assert g.agent_profile("agent:moon").corpus_scope == "Tang poetry"
        assert g.agent_report("agent:hill").proposed > 0
    finally:
        g.close()


def test_one_shared_budget_across_the_swarm_not_one_each(graph_files, source, monkeypatch):
    """Three agents with a cap each would be three caps, and the number the
    researcher typed would bound none of them."""
    monkeypatch.setenv("OPENROUTER_API_KEY", "k")
    monkeypatch.setenv("OPENROUTER_MODEL", "fake-model")
    db_path, log_path = graph_files
    seen = []

    def factory(budget, on_call):
        seen.append(budget)
        return FakeRunTransport()

    m = RunManager(db_path, log_path, source, max_budget_usd=0.5, transport_factory=factory)
    m.start([spec("agent:a", "go"), spec("agent:b", "go")], budget_usd=0.2)
    _await_finish(m, timeout=20.0)
    assert seen == [0.2], "the swarm must share exactly one budgeted transport"


def test_agents_must_have_distinct_ids(manager):
    with pytest.raises(RunRejected, match="share an id"):
        manager.start([spec("agent:same", "a"), spec("agent:same", "b")], budget_usd=0.1)


def test_the_client_cannot_exceed_the_agent_limit(manager):
    too_many = [spec(f"agent:{i}", "go") for i in range(9)]
    with pytest.raises(RunRejected, match="exceeds this server's limit"):
        manager.start(too_many, budget_usd=0.1)


def test_one_agents_transport_failure_does_not_fail_the_run(
    graph_files, source, monkeypatch
):
    """`run_swarm` returns exceptions in place, so a failure is reported against
    the agent that had it rather than taking the others down with it."""
    monkeypatch.setenv("OPENROUTER_API_KEY", "k")
    monkeypatch.setenv("OPENROUTER_MODEL", "fake-model")
    db_path, log_path = graph_files

    ok = FakeRunTransport()

    class Flaky:
        """Fails for one agent, answers normally for the other. Which agent a
        request belongs to is visible in the instructions it carries."""

        def __call__(self, url, headers, body, timeout):
            if "BREAK" in body.decode("utf-8", "replace"):
                return 500, json.dumps({"error": {"message": "forced"}}).encode()
            return ok(url, headers, body, timeout)

    m = RunManager(
        db_path, log_path, source, max_budget_usd=0.5,
        transport_factory=lambda budget, on_call: Flaky(),
    )
    m.start(
        [spec("agent:good", "attest 明月"), spec("agent:bad", "BREAK")],
        budget_usd=0.2,
    )
    run = _await_finish(m, timeout=20.0)

    by_id = {a["agent_id"]: a for a in run["agents"]}
    assert by_id["agent:bad"]["error"], "the failing agent should carry its error"
    assert by_id["agent:good"]["error"] is None
    assert by_id["agent:good"]["tool_calls"]
    assert run["state"] == "finished", "one agent failing must not fail the run"


def test_the_api_accepts_both_the_single_and_swarm_shapes(graph_files, source, monkeypatch):
    monkeypatch.setenv("OPENROUTER_API_KEY", "k")
    monkeypatch.setenv("OPENROUTER_MODEL", "fake-model")
    db_path, log_path = graph_files
    m = RunManager(
        db_path, log_path, source, max_budget_usd=0.5,
        transport_factory=lambda budget, on_call: FakeRunTransport(),
    )
    client = TestClient(create_app(db_path, log_path, source=source, run_manager=m))

    single = client.post(
        "/api/run", json={"instructions": "attest 明月", "budget_usd": 0.1},
    )
    assert single.status_code == 200, single.text
    assert len(single.json()["agents"]) == 1
    _await_finish(m, timeout=20.0)

    swarm = client.post("/api/run", json={
        "budget_usd": 0.1,
        "agents": [
            {"agent_id": "agent:x", "instructions": "attest 明月", "corpus_scope": "a",
             "model": "vendor-a/fake-model"},
            {"agent_id": "agent:y", "instructions": "attest 空山", "corpus_scope": "b",
             "model": "vendor-b/fake-model"},
        ],
    })
    assert swarm.status_code == 200, swarm.text
    assert len(swarm.json()["agents"]) == 2
    _await_finish(m, timeout=20.0)


# --- the reviewer role -------------------------------------------------------
#
# The criticism these answer (compare.md §10): verification was a tool any
# worker could call, and nothing stopped an agent attesting its own claim.

class ReviewingTransport:
    """Emits `review_claim` against whatever id the reviewer's instructions
    name, and nothing on a second turn.

    It reads the claim id out of the prompt rather than being handed one,
    which makes this a real check that `pending_review_context` reaches the
    model — if the run layer stopped appending the pending list, this fake
    would have nothing to call and the test would fail rather than pass on a
    hardcoded id."""

    def __init__(self, verdict="sound"):
        self.verdict = verdict
        self.seen_tools: list[list[str]] = []

    def __call__(self, url, headers, body, timeout):
        payload = json.loads(body)
        self.seen_tools.append([t["function"]["name"] for t in payload["tools"]])
        made_a_call = any(m["role"] == "tool" for m in payload["messages"])
        prompt = " ".join(m.get("content") or "" for m in payload["messages"])
        ids = re.findall(r"claim:[0-9a-f]+", prompt)
        message = {"role": "assistant", "content": None if not made_a_call else "done"}
        if not made_a_call and ids:
            # One call per pending id, because a real graph has more than one
            # claim waiting and a fake that reviewed only the first would pass
            # or fail on listing order rather than on behaviour.
            message["tool_calls"] = [
                {
                    "id": f"r{i}", "type": "function",
                    "function": {
                        "name": "review_claim",
                        "arguments": json.dumps({
                            "claim_id": claim_id, "verdict": self.verdict,
                            "detail": "re-fetched the citations",
                        }),
                    },
                }
                for i, claim_id in enumerate(dict.fromkeys(ids))
            ]
        return 200, json.dumps({
            "id": "gen", "model": "fake-model",
            "choices": [{
                "message": message,
                "finish_reason": "tool_calls" if message.get("tool_calls") else "stop",
            }],
            "usage": {"prompt_tokens": 5, "completion_tokens": 5, "cost": 0.001},
        }).encode()


def _claim_awaiting_review(db_path, log_path, source, author="agent:someone-else") -> str:
    """A claim with real citations, stuck at `proposed` because its author may
    not close its own rung — the state a reviewer exists to resolve."""
    from cohort.tools.find_attestations import FindAttestationsInput, find_attestations

    g = Graph.open(db_path, log_path)
    try:
        claim_id = g.propose_claim(ClaimPayload(text="the moon recurs"), authored_by=author)
        find_attestations(
            g, source,
            FindAttestationsInput(claim_or_conjecture_id=claim_id, query="明月"),
            authored_by=author,
        )
        assert g.get_node(claim_id).status == "proposed"
    finally:
        g.close()
    return claim_id


def test_a_reviewer_attests_a_claim_its_author_could_not(graph_files, source, monkeypatch):
    monkeypatch.setenv("OPENROUTER_API_KEY", "test-key")
    monkeypatch.setenv("OPENROUTER_MODEL", "fake-model")
    db_path, log_path = graph_files
    claim_id = _claim_awaiting_review(db_path, log_path, source)

    transport = ReviewingTransport()
    m = RunManager(
        db_path, log_path, source, max_budget_usd=0.50,
        transport_factory=lambda budget, on_call: transport,
    )
    m.start([spec(agent_id="agent:reviewer", role=ROLE_REVIEWER,
                  instructions="review what is pending")], budget_usd=0.10)
    run = _await_finish(m)

    assert run["state"] == "finished", run
    assert {c["tool"] for c in run["tool_calls"]} == {"review_claim"}
    assert not any(c["is_error"] for c in run["tool_calls"])

    g = Graph.open_read_only(db_path)
    try:
        assert g.get_node(claim_id).status == "attested"
    finally:
        g.close()


def test_a_reviewer_is_given_only_the_reviewers_tools(graph_files, source, monkeypatch):
    """The restriction is the tool list, not the prompt: there is no
    `propose_claim` for a model to be talked into calling."""
    monkeypatch.setenv("OPENROUTER_API_KEY", "test-key")
    monkeypatch.setenv("OPENROUTER_MODEL", "fake-model")
    db_path, log_path = graph_files
    _claim_awaiting_review(db_path, log_path, source)

    transport = ReviewingTransport()
    m = RunManager(
        db_path, log_path, source, max_budget_usd=0.50,
        transport_factory=lambda budget, on_call: transport,
    )
    m.start([spec(agent_id="agent:reviewer", role=ROLE_REVIEWER, instructions="review")],
            budget_usd=0.10)
    _await_finish(m)

    assert transport.seen_tools, "the reviewer never ran"
    for tools in transport.seen_tools:
        assert "review_claim" in tools
        assert "propose_claim" not in tools
        assert "propose_conjecture" not in tools


def test_a_reviewer_is_registered_as_a_reviewer(graph_files, source, monkeypatch):
    monkeypatch.setenv("OPENROUTER_API_KEY", "test-key")
    monkeypatch.setenv("OPENROUTER_MODEL", "fake-model")
    db_path, log_path = graph_files
    _claim_awaiting_review(db_path, log_path, source)

    m = RunManager(
        db_path, log_path, source, max_budget_usd=0.50,
        transport_factory=lambda budget, on_call: ReviewingTransport(),
    )
    m.start([spec(agent_id="agent:reviewer", role=ROLE_REVIEWER, instructions="review")],
            budget_usd=0.10)
    _await_finish(m)

    g = Graph.open_read_only(db_path)
    try:
        assert g.agent_profile("agent:reviewer").kind == "reviewer"
    finally:
        g.close()


def test_a_reviewer_with_nothing_to_review_is_skipped_not_billed(graph_files, source, monkeypatch):
    """An empty turn still costs a model call. Nothing to review is a reason to
    skip the agent, and it is reported as a note rather than an error — the run
    did not fail, there was simply no work."""
    monkeypatch.setenv("OPENROUTER_API_KEY", "test-key")
    monkeypatch.setenv("OPENROUTER_MODEL", "fake-model")
    db_path, log_path = graph_files
    # "Nothing to review" means nothing *this reviewer may promote*, so the
    # reviewer has to be the author of everything pending — including the claim
    # `graph_files` seeds under AGENT.
    claim_id = _claim_awaiting_review(db_path, log_path, source, author=AGENT)

    transport = ReviewingTransport()
    m = RunManager(
        db_path, log_path, source, max_budget_usd=0.50,
        transport_factory=lambda budget, on_call: transport,
    )
    m.start([spec(agent_id=AGENT, role=ROLE_REVIEWER, instructions="review")],
            budget_usd=0.10)
    run = _await_finish(m)

    assert run["state"] == "finished", run
    assert transport.seen_tools == [], "a skipped reviewer must not cost a model call"
    note = run["agents"][0]["note"]
    assert note and "nothing to review" in note
    assert run["agents"][0]["error"] is None

    g = Graph.open_read_only(db_path)
    try:
        assert g.get_node(claim_id).status == "proposed"
    finally:
        g.close()


def test_a_reviewer_sharing_a_model_family_with_a_worker_is_refused(manager):
    """The roster check does not care about roles — a reviewer on the author's
    model is the overlap the rule exists to catch, in its sharpest form."""
    with pytest.raises(RunRejected, match="model family"):
        manager.start(
            [
                spec(agent_id="agent:w", model="z-ai/glm-5.3"),
                spec(agent_id="agent:r", model="z-ai/glm-5.3-flash", role=ROLE_REVIEWER),
            ],
            budget_usd=0.10,
        )


def test_an_unknown_role_is_refused_with_the_options(manager):
    with pytest.raises(RunRejected, match="expected one of"):
        manager.start([spec(role="auditor")], budget_usd=0.10)


def test_the_role_travels_in_the_run_snapshot(manager):
    """A researcher reading a finished run has to be able to tell which agent
    was checking which — the roles are the run's whole shape."""
    manager.start(
        [spec(agent_id="agent:w"), spec(agent_id="agent:r", role=ROLE_REVIEWER)],
        budget_usd=0.10,
    )
    run = _await_finish(manager)
    roles = {a["agent_id"]: a["role"] for a in run["agents"]}
    assert roles == {"agent:w": ROLE_WORKER, "agent:r": ROLE_REVIEWER}
