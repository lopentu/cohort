"""Asking a question and letting the roster be planned.

Two things are being tested and they pull in opposite directions. The planner
is allowed to decide the *machinery* — how many agents, which models, which
roles — because none of that carries epistemic weight beyond one hard
constraint. It is not allowed to decide the *agenda*, because `ask_question` is
researcher-only precisely so that nothing else sets it (test_question.py).

So most of what follows pins what auto mode does *not* do: it does not invent a
question, does not paraphrase the researcher's, does not build a roster the
write boundary would refuse, and does not hand back a pile of claims with
nothing checking them.
"""
from __future__ import annotations

import pytest

from cohort.agents.roster import check_distinct_model_families
from cohort.eventlog import EventLog, read_events, read_runs
from cohort.graph import Graph
from cohort.schemas import (
    RESEARCHER,
    ClaimPayload,
    EdgeType,
    QuestionPayload,
)
from cohort.ui.runs import (
    INQUIRY_STANCES,
    ROLE_REVIEWER,
    ROLE_WORKER,
    RunRejected,
    plan_inquiry,
)

QUESTION = "Which witnesses share a transcription of the closing dhāraṇī?"
ANSWERABLE = "retrieval over the corpus as indexed; it cannot settle which is earlier"

THREE = ["alpha/m1", "beta/m2", "gamma/m3"]


def plan(**over):
    args = {"question": QUESTION, "answerable_by": ANSWERABLE, "models": THREE, "max_agents": 4}
    args.update(over)
    return plan_inquiry(**args)


# --- the agenda stays the researcher's ---------------------------------------

def test_the_question_reaches_the_agent_verbatim():
    """Not summarised, not rephrased. A planner that reworded the question
    would be choosing what gets investigated, which is the one decision this
    system reserves for the researcher."""
    for spec in plan():
        assert QUESTION in spec.instructions


def test_what_the_researcher_said_would_answer_it_travels_too():
    """`answerable_by` is the fence: the researcher saying what retrieval over
    this corpus can and cannot settle. An agent given the question without it
    will answer a dating question from a corpus that cannot date anything."""
    for spec in plan():
        assert ANSWERABLE in spec.instructions
        assert "outside what" in spec.instructions


def test_no_question_is_no_inquiry():
    with pytest.raises(RunRejected, match="needs a question"):
        plan(question="   ")


# --- the machinery it may decide ---------------------------------------------

def test_a_reviewer_is_reserved_before_a_second_worker():
    """An agent may not attest what it authored, so a roster of one family can
    propose but never promote: every claim stays at `proposed`. Spending the
    second seat on a reviewer rather than another worker is the whole reason to
    plan a roster at all."""
    two = plan(models=["alpha/m1", "beta/m2"])
    assert [s.role for s in two] == [ROLE_WORKER, ROLE_REVIEWER]


def test_one_family_gets_no_reviewer_and_does_not_pretend_otherwise():
    """Two agents on one family would be refused by the write boundary, so a
    single-family pool honestly yields one agent — not a reviewer that cannot
    review."""
    one = plan(models=["alpha/m1", "alpha/m2"])
    assert len(one) == 1 and one[0].role == ROLE_WORKER


def test_the_planned_roster_is_one_the_write_boundary_accepts():
    """The check that would otherwise reject the run, run against the plan.
    Planning a roster the graph refuses would turn auto mode into a button
    that reliably fails."""
    specs = plan()
    check_distinct_model_families({s.agent_id: s.model for s in specs})


def test_it_never_exceeds_the_server_ceiling():
    assert len(plan(max_agents=2, models=THREE)) == 2
    assert len(plan(max_agents=1, models=THREE)) == 1


def test_an_empty_pool_still_plans_one_agent():
    """No `OPENROUTER_MODELS` is a legitimate configuration — a single agent
    needs only the default model — so it plans one worker on the default
    rather than refusing."""
    specs = plan(models=[])
    assert len(specs) == 1 and specs[0].model == ""


# --- the second worker is not a copy of the first ----------------------------

def test_the_second_worker_looks_for_what_would_break_an_answer():
    """Two agents with the same question and the same instructions run the
    same searches and return the same passages, and two identical answers read
    as corroboration while being one result counted twice. So the stances
    differ, and the second one's job is disconfirmation."""
    specs = plan()
    workers = [s for s in specs if s.role == ROLE_WORKER]
    assert len(workers) == 2
    assert workers[0].instructions != workers[1].instructions
    assert workers[0].method_label == "direct attestation"
    assert workers[1].method_label == "disconfirmation"
    assert "contradiction" in workers[1].instructions


def test_the_stances_are_fixed_not_generated():
    """Fixed on purpose: a per-run stance would be a model deciding how to
    inquire, and would make two runs on one question incomparable."""
    assert len(INQUIRY_STANCES) == 2
    assert plan()[0].instructions == plan()[0].instructions


def test_every_agent_declares_a_method():
    """Distinct declared scope or method per agent is this design's own
    condition for allowing more than one agent at all."""
    assert all(s.method_label for s in plan())


# --- the run records what it was asked ---------------------------------------

def test_the_run_log_says_which_question_it_served(tmp_path):
    """`run_id` groups a run's events; it does not say what the run was for.
    Without the question on the record, a second pass at one question is
    indistinguishable from an unrelated run."""
    log = EventLog(tmp_path / "events.jsonl")
    g = Graph(tmp_path / "g.sqlite", event_log=log)
    qid = g.ask_question(
        QuestionPayload(text=QUESTION, answerable_by=ANSWERABLE), authored_by=RESEARCHER,
    )
    g.log_run_started("run-1", authored_by="run:run-1", agents=[], question_id=qid)
    g.log_run_finished("run-1", authored_by="run:run-1", state="finished")

    record = read_runs(log.path)[0]
    assert record.question_id == qid
    g.close()


def test_a_run_with_no_question_records_none(tmp_path):
    """Free-text runs stay legal and answer to nothing in the graph. The field
    is absent rather than blank, so old logs replay identically."""
    log = EventLog(tmp_path / "events.jsonl")
    g = Graph(tmp_path / "g.sqlite", event_log=log)
    g.log_run_started("run-1", authored_by="run:run-1", agents=[])
    ev = next(e for e in read_events(log.path) if e.event == "run_started")
    assert "question_id" not in ev.detail
    assert read_runs(log.path)[0].question_id is None
    g.close()


def test_the_answer_is_linked_to_the_question_it_answered(tmp_path):
    """The worker adds the edge, not the researcher afterwards. A question
    whose answers are only sometimes attached to it reads as a tally."""
    from cohort.agents.attestation_worker import AttestationWorker

    log = EventLog(tmp_path / "events.jsonl")
    g = Graph(tmp_path / "g.sqlite", event_log=log)
    qid = g.ask_question(
        QuestionPayload(text=QUESTION, answerable_by=ANSWERABLE), authored_by=RESEARCHER,
    )
    worker = AttestationWorker.__new__(AttestationWorker)
    worker.graph, worker.authored_by, worker.question_id = g, "agent:w1", qid

    claim_id = g.propose_claim(ClaimPayload(text="an answer"), authored_by="agent:w1")
    assert worker._address(claim_id, None) == claim_id
    assert g.edges(edge_type=EdgeType.ADDRESSES, src=claim_id, dst=qid)
    g.close()


def test_a_bad_question_id_does_not_undo_a_written_claim(tmp_path):
    """The claim exists and its id is already on its way back to the model.
    Raising here would turn a successful proposal into a tool error and invite
    the model to propose it again — so the failure is logged, not raised."""
    from cohort.agents.attestation_worker import AttestationWorker

    log = EventLog(tmp_path / "events.jsonl")
    g = Graph(tmp_path / "g.sqlite", event_log=log)
    worker = AttestationWorker.__new__(AttestationWorker)
    worker.graph, worker.authored_by, worker.question_id = g, "agent:w1", "question:nope"

    claim_id = g.propose_claim(ClaimPayload(text="an answer"), authored_by="agent:w1")
    assert worker._address(claim_id, None) == claim_id
    assert g.get_node(claim_id).status == "proposed"
    refused = [e for e in read_events(log.path) if e.event == "refused"]
    # `add_edge`, not `address_question`: the write boundary refused it and
    # named itself, and `log_refusal` is idempotent with `_refuse`, so the
    # worker's own attempt to record it does not produce a second event with a
    # vaguer name. One refusal, named by the rule that made it.
    assert refused and refused[-1].detail["attempted"] == "add_edge"
    assert refused[-1].detail["rule"] == "EdgeEndpointMissing"
    g.close()


# --- the HTTP surface --------------------------------------------------------

def test_auto_without_a_question_is_refused_by_the_route(tmp_path, monkeypatch):
    """422, and the message says why rather than naming a missing field: the
    reason auto mode cannot proceed is that nothing may invent the agenda."""
    from fastapi.testclient import TestClient

    from cohort.ui.api import create_app
    from cohort.ui.runs import RunManager

    monkeypatch.setenv("OPENROUTER_API_KEY", "k")
    monkeypatch.setenv("OPENROUTER_MODEL", "alpha/m1")
    db, log = tmp_path / "g.sqlite", tmp_path / "g.jsonl"
    Graph(db, event_log=EventLog(log)).close()

    class _Source:
        def search(self, query, *, max_results=5):
            return []

        def fetch(self, ref):
            raise KeyError(ref)

    source = _Source()
    m = RunManager(db, log, source, max_budget_usd=0.5)
    client = TestClient(create_app(db, log, allow_writes=True, source=source, run_manager=m))

    r = client.post("/api/run", json={"auto": True, "budget_usd": 0.1})
    assert r.status_code == 422
    assert "question is the agenda" in r.json()["detail"]


def test_a_non_question_node_is_not_an_inquiry(tmp_path, monkeypatch):
    """`--question claim:abc` is a plausible typo, and the run costs money.
    Refused before the roster is built, not when the first proposal tries to
    link itself."""
    monkeypatch.setenv("OPENROUTER_API_KEY", "k")
    monkeypatch.setenv("OPENROUTER_MODEL", "alpha/m1")
    from cohort.ui.runs import RunManager

    db, log = tmp_path / "g.sqlite", tmp_path / "g.jsonl"
    g = Graph(db, event_log=EventLog(log))
    claim_id = g.propose_claim(ClaimPayload(text="not a question"), authored_by="agent:w1")
    g.close()

    class _Source:
        def search(self, query, *, max_results=5):
            return []

    m = RunManager(db, log, _Source(), max_budget_usd=0.5)
    with pytest.raises(RunRejected, match="not a question"):
        m.start(plan(), budget_usd=0.1, question_id=claim_id)


def test_the_config_reports_the_roster_auto_would_build(tmp_path, monkeypatch):
    """So the launcher can name what it is about to spend money on. Reported by
    the server because the shape depends on model *families*, which a browser
    would have to reimplement and would drift from."""
    monkeypatch.setenv("OPENROUTER_API_KEY", "k")
    monkeypatch.setenv("OPENROUTER_MODEL", "alpha/m1")
    monkeypatch.setenv("OPENROUTER_MODELS", "beta/m2,gamma/m3")
    from cohort.ui.runs import RunManager

    db, log = tmp_path / "g.sqlite", tmp_path / "g.jsonl"
    Graph(db, event_log=EventLog(log)).close()

    plan_rows = RunManager(db, log, None, max_budget_usd=0.5).config()["plan"]
    assert [r["role"] for r in plan_rows] == [ROLE_WORKER, ROLE_WORKER, ROLE_REVIEWER]
    # the preview carries no instructions: those depend on the question, and a
    # preview that showed a task for a question nobody picked would be fiction
    assert all("instructions" not in r for r in plan_rows)


def test_a_claim_id_is_refused_before_a_roster_is_planned(tmp_path, monkeypatch):
    """A claim payload also has a `text`, so planning first would build a whole
    roster around a claim's own words and only then be refused for the node's
    type. The message names what was passed, not a field."""
    from fastapi.testclient import TestClient

    from cohort.ui.api import create_app
    from cohort.ui.runs import RunManager

    monkeypatch.setenv("OPENROUTER_API_KEY", "k")
    monkeypatch.setenv("OPENROUTER_MODEL", "alpha/m1")
    db, log = tmp_path / "g.sqlite", tmp_path / "g.jsonl"
    g = Graph(db, event_log=EventLog(log))
    claim_id = g.propose_claim(ClaimPayload(text="not a question"), authored_by="agent:w1")
    g.close()

    class _Source:
        def search(self, query, *, max_results=5):
            return []

    source = _Source()
    m = RunManager(db, log, source, max_budget_usd=0.5)
    client = TestClient(create_app(db, log, allow_writes=True, source=source, run_manager=m))

    r = client.post("/api/run", json={"auto": True, "question_id": claim_id, "budget_usd": 0.1})
    assert r.status_code == 422
    assert "is a claim, not a question" in r.json()["detail"]

    missing = client.post(
        "/api/run", json={"auto": True, "question_id": "question:nope", "budget_usd": 0.1},
    )
    assert missing.status_code == 404
    assert "ask one first" in missing.json()["detail"]
