"""Runs as events: `run_id`, `run_started`/`run_finished`, and what they buy.

Before this, a run existed only in `RunManager`'s memory. Two consequences,
both of which these tests pin shut:

* a server restart erased every run ever launched from the browser; and
* the log could say what was written but not *which run wrote it*, so a
  four-point scaling table would have meant four graphs and numbers copied by
  hand out of console output.

The run id was never the missing part — `RunManager` has always minted one. It
just never left the process.
"""
from __future__ import annotations

import json
import time

import pytest

from cohort.eventlog import (
    EventLog,
    read_events,
    read_refusals,
    read_runs,
    summarize_model_calls,
    summarize_refusals,
)
from cohort.graph import Graph
from cohort.schemas import ClaimPayload

AGENT = "agent:worker-1"
OTHER = "agent:worker-2"


# --- the stamp ---------------------------------------------------------------

def test_events_written_inside_a_run_carry_its_id_and_others_do_not(graph):
    """One choke point, not a parameter on every write: which run is writing
    is a property of the session, and a write signature that had to be told
    would be forgotten in exactly the call site that mattered."""
    before = graph.propose_claim(ClaimPayload(text="before"), authored_by=AGENT)
    with graph.during_run("run-abc"):
        inside = graph.propose_claim(ClaimPayload(text="inside"), authored_by=AGENT)
    after = graph.propose_claim(ClaimPayload(text="after"), authored_by=AGENT)

    stamped = {ev.node_id: ev.run_id for ev in read_events(graph.event_log.path)
               if ev.event == "propose"}
    assert stamped[before] is None
    assert stamped[inside] == "run-abc"
    assert stamped[after] is None


def test_a_run_that_raises_still_owns_what_it_wrote(graph):
    """A crashed run wrote events, and they still belong to it. Restoring the
    stamp in a `finally` is what makes that true."""
    def crash_after_writing():
        with graph.during_run("run-crash"):
            graph.propose_claim(ClaimPayload(text="written"), authored_by=AGENT)
            raise RuntimeError("the model went away")

    with pytest.raises(RuntimeError):
        crash_after_writing()

    assert graph.event_log.run_id is None
    stamped = [ev for ev in read_events(graph.event_log.path) if ev.run_id == "run-crash"]
    assert len(stamped) == 1


def test_a_nested_block_restores_its_caller_rather_than_clearing(graph):
    with graph.during_run("outer"):
        with graph.during_run("inner"):
            pass
        graph.propose_claim(ClaimPayload(text="still outer"), authored_by=AGENT)

    last = list(read_events(graph.event_log.path))[-1]
    assert last.run_id == "outer"


# --- the markers are audit records, not state --------------------------------

def test_run_markers_do_not_touch_the_projection(graph):
    """`run_started` is not a change to the graph, so it replays as a no-op —
    same footing as `model_call` and `refused`."""
    before = graph._snapshot()
    graph.log_run_started("r1", authored_by="run:r1", agents=[], budget_usd=0.05)
    graph.log_run_finished("r1", authored_by="run:r1", state="finished", spent_usd=0.001)
    assert graph._snapshot() == before


def test_rebuild_matches_live_with_run_events_present(tmp_path):
    log = EventLog(tmp_path / "events.jsonl")
    g = Graph(tmp_path / "graph.sqlite", event_log=log)
    g.log_run_started("r1", authored_by="run:r1", agents=[{"agent_id": AGENT}])
    with g.during_run("r1"):
        g.propose_claim(ClaimPayload(text="in the run"), authored_by=AGENT)
    g.log_run_finished("r1", authored_by="run:r1", state="finished")
    assert g.rebuild().ok is True
    g.close()


def test_a_log_written_before_run_ids_existed_replays_unchanged(tmp_path):
    """`run_id` is optional for the same reason the observability envelope is:
    every event logged before the field existed must replay identically, or
    the log stops being ground truth the moment the schema grows."""
    path = tmp_path / "old.jsonl"
    path.write_text(
        json.dumps({"seq": 0, "event": "propose", "authored_by": AGENT,
                    "at": "2026-01-01T00:00:00Z", "node_id": "claim:old",
                    "node_type": "claim",
                    "detail": {"payload": {"text": "written by an older version"}}})
        + "\n"
    )
    events = list(read_events(path))
    assert len(events) == 1 and events[0].run_id is None
    assert read_runs(path) == []


# --- reading runs back -------------------------------------------------------

def test_read_runs_reports_the_roster_the_spend_and_the_counts(graph):
    roster = [
        {"agent_id": AGENT, "role": "worker", "model": "a/one", "corpus_scope": "sutras"},
        {"agent_id": OTHER, "role": "reviewer", "model": "b/two", "corpus_scope": "what they cited"},
    ]
    graph.log_run_started("r1", authored_by="run:r1", agents=roster, budget_usd=0.05)
    with graph.during_run("r1"):
        graph.propose_claim(ClaimPayload(text="one"), authored_by=AGENT)
        graph.log_refusal("attest", OTHER, ValueError("nope"), node_id="claim:nope")
    graph.log_run_finished(
        "r1", authored_by="run:r1", state="finished", spent_usd=0.0031, calls=12,
    )

    runs = read_runs(graph.event_log.path)
    assert len(runs) == 1
    r = runs[0]
    assert r.run_id == "r1" and r.state == "finished"
    assert [a["role"] for a in r.agents] == ["worker", "reviewer"]
    assert r.budget_usd == 0.05 and r.spent_usd == 0.0031 and r.calls == 12
    assert r.refusals == 1
    # the propose and the refusal; the markers themselves are not stamped
    assert r.events == 2
    assert r.finished_at is not None


def test_a_run_with_no_closing_marker_is_reported_open_not_repaired(graph):
    """Killed mid-write, or still going. Both are facts about the session, and
    inventing an end for it would be the tidying this log refuses."""
    graph.log_run_started("r1", authored_by="run:r1", agents=[])
    with graph.during_run("r1"):
        graph.propose_claim(ClaimPayload(text="orphan"), authored_by=AGENT)

    r = read_runs(graph.event_log.path)[0]
    assert r.finished_at is None
    assert r.state is None
    assert r.events == 1


def test_runs_come_back_most_recent_first(graph):
    for i in range(3):
        graph.log_run_started(f"r{i}", authored_by=f"run:r{i}", agents=[])
        graph.log_run_finished(f"r{i}", authored_by=f"run:r{i}", state="finished")
        time.sleep(0.01)

    assert [r.run_id for r in read_runs(graph.event_log.path)] == ["r2", "r1", "r0"]
    assert [r.run_id for r in read_runs(graph.event_log.path, limit=2)] == ["r2", "r1"]


# --- slicing the log by run --------------------------------------------------

def test_refusals_and_the_census_narrow_to_one_run(graph):
    """The log is cumulative across a graph's whole life, so "what did the run
    I just watched refuse?" is a different question from "what has this graph
    ever refused" — and a scaling table needs the first one."""
    with graph.during_run("r1"):
        graph.log_refusal("attest", AGENT, ValueError("a"), node_id="claim:a")
    with graph.during_run("r2"):
        graph.log_refusal("attest", OTHER, ValueError("b"), node_id="claim:b")
        graph.log_refusal("attest", OTHER, ValueError("c"), node_id="claim:c")

    assert len(read_refusals(graph.event_log.path)) == 3
    assert len(read_refusals(graph.event_log.path, run_id="r2")) == 2

    whole = summarize_refusals(graph.event_log.path)
    just_r2 = summarize_refusals(graph.event_log.path, run_id="r2")
    assert whole.total == 3 and just_r2.total == 2
    assert just_r2.by_author == {OTHER: 2}


def test_model_calls_narrow_to_one_run(graph):
    with graph.during_run("r1"):
        graph.log_model_call(authored_by=AGENT, model="a/one", cost_usd=0.001)
    with graph.during_run("r2"):
        graph.log_model_call(authored_by=OTHER, model="b/two", cost_usd=0.002)
        graph.log_model_call(authored_by=OTHER, model="b/two", cost_usd=0.004)

    assert summarize_model_calls(graph.event_log.path).calls == 3
    r2 = summarize_model_calls(graph.event_log.path, run_id="r2")
    assert r2.calls == 2
    assert r2.total_cost_usd == pytest.approx(0.006)


# --- what it buys the run manager --------------------------------------------

def test_a_run_survives_the_process_that_started_it(tmp_path):
    """The restart case, which is the whole point. A fresh `RunManager` over
    the same log — a new server, a new day — still knows what has been run."""
    pytest.importorskip("fastapi", reason="the `ui` extra is not installed")
    from cohort.ui.runs import RunManager

    db, log = tmp_path / "g.sqlite", tmp_path / "g.jsonl"
    g = Graph.open(db, log)
    g.log_run_started("r1", authored_by="run:r1",
                      agents=[{"agent_id": AGENT, "role": "worker", "model": "a/one"}],
                      budget_usd=0.05)
    g.log_run_finished("r1", authored_by="run:r1", state="finished", spent_usd=0.002, calls=4)
    g.close()

    manager = RunManager(db, log, source=None)
    assert manager.history() == [], "nothing ran in this process"
    recorded = manager.recorded()
    assert [r["run_id"] for r in recorded] == ["r1"]
    assert recorded[0]["spent_usd"] == 0.002
