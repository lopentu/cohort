"""Agents in one run must not share a model family.

COHORT allows several agents only when they demonstrate declared viewpoint
diversity, and the run launcher tells the researcher their disagreement "means
something". That was not true while every agent ran the same model: two agents
on one model share training priors, so their agreement is one observation
reported twice — the exact error `independent_support()` exists to catch
between witnesses, committed one layer up between readers.

Found by comparing this project against `epistemic-swarm`, which refuses an
overlapping roster at its configuration boundary (compare.md §8).
"""
from __future__ import annotations

import pytest

from cohort.agents.roster import (
    RosterNotIndependent,
    check_distinct_model_families,
    model_family,
)
from cohort.ui.runs import AgentSpec, RunManager, RunRejected


# --- the family heuristic, and its stated limits -----------------------------

def test_family_is_the_provider_prefix():
    assert model_family("z-ai/glm-5.3-flash") == "z-ai"
    assert model_family("deepseek/deepseek-v4-flash") == "deepseek"


def test_two_models_from_one_provider_are_one_family():
    """The case the rule is actually for: a roster filled from one provider."""
    assert model_family("z-ai/glm-5.3") == model_family("z-ai/glm-5.3-flash")


def test_a_bare_id_is_its_own_family():
    """Nothing can be inferred from an id with no provider, and guessing would
    make the check look stronger than it is."""
    assert model_family("local-model") == "local-model"


def test_family_is_case_insensitive():
    assert model_family("Z-AI/GLM") == model_family("z-ai/glm")


# --- the check ---------------------------------------------------------------

def test_a_single_agent_is_always_fine():
    """With nothing to agree with, shared priors cannot manufacture
    corroboration."""
    check_distinct_model_families({"a": "z-ai/glm-5.3-flash"})


def test_distinct_families_pass():
    check_distinct_model_families({
        "a": "z-ai/glm-5.3-flash",
        "b": "deepseek/deepseek-v4-flash",
    })


def test_a_shared_family_is_refused():
    with pytest.raises(RosterNotIndependent) as e:
        check_distinct_model_families({
            "a": "z-ai/glm-5.3-flash",
            "b": "z-ai/glm-5.3",
        })
    message = str(e.value)
    assert "z-ai" in message
    # The refusal has to say which agents clashed, or it cannot be acted on.
    assert "a" in message and "b" in message


def test_the_refusal_names_every_clashing_agent():
    with pytest.raises(RosterNotIndependent) as e:
        check_distinct_model_families({
            "a": "z-ai/one", "b": "z-ai/two", "c": "deepseek/x", "d": "deepseek/y",
        })
    message = str(e.value)
    assert "z-ai" in message and "deepseek" in message


# --- enforced where a run starts, not merely documented ----------------------

def test_run_manager_refuses_a_roster_sharing_one_model(tmp_path, monkeypatch):
    # `start()` reads the OpenRouter config before the roster check, so an
    # unstated model is checked as what it will actually be. Both specs below
    # state one, but the config read still happens — without these the test
    # fails on a missing key and never reaches the rule it is about.
    monkeypatch.setenv("OPENROUTER_API_KEY", "k")
    monkeypatch.setenv("OPENROUTER_MODEL", "m")
    from cohort.eventlog import EventLog
    from cohort.graph import Graph

    db, log = tmp_path / "g.sqlite", tmp_path / "g.jsonl"
    Graph(db, event_log=EventLog(log)).close()

    class _Source:
        def search(self, query, *, max_results=5):
            return []

    manager = RunManager(db, log, _Source())
    with pytest.raises(RunRejected, match="model family"):
        manager.start(
            [
                AgentSpec("agent:a", "go", model="z-ai/glm-5.3-flash"),
                AgentSpec("agent:b", "go", model="z-ai/glm-5.3"),
            ],
            budget_usd=0.01,
        )


def test_the_check_happens_before_any_money_is_spent(tmp_path, monkeypatch):
    """A refusal after the first call would be a report, not a rule."""
    # Same reason as above, and here it decides what the test proves: without
    # the config set, `start()` refuses for a missing key, `RunRejected` is
    # raised, no request is made — and the assertion below passes while the
    # roster check is never reached.
    monkeypatch.setenv("OPENROUTER_API_KEY", "k")
    monkeypatch.setenv("OPENROUTER_MODEL", "m")
    from cohort.eventlog import EventLog
    from cohort.graph import Graph

    db, log = tmp_path / "g.sqlite", tmp_path / "g.jsonl"
    Graph(db, event_log=EventLog(log)).close()
    calls: list[str] = []

    def transport_factory(budget, on_call):
        def _transport(*a, **kw):
            calls.append("spent")
            raise AssertionError("no request should be made")
        return _transport

    class _Source:
        def search(self, query, *, max_results=5):
            return []

    manager = RunManager(db, log, _Source(), transport_factory=transport_factory)
    with pytest.raises(RunRejected, match="model family"):
        manager.start(
            [
                AgentSpec("agent:a", "go", model="z-ai/one"),
                AgentSpec("agent:b", "go", model="z-ai/two"),
            ],
            budget_usd=0.01,
        )
    assert calls == []
