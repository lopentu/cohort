"""The refusal census.

COHORT's distinctive output is not a set of findings but a set of *refusals*
(docs/design.md §15). A flat list of them answers no question a researcher
actually has, though: the question is which ones to read. That is what this
census is for, and these tests pin the two claims it makes —

* every refusal is classified, and adding a rule cannot silently skip that; and
* a *run* of refusals from one agent against one rule is surfaced, because that
  is the shape of a gap in the tool layer rather than a model error.

Neither concludes anything about a tool. The census counts; a human reads.
"""
from __future__ import annotations

from pathlib import Path

import pytest

from cohort.errors import (
    REFUSAL_CATEGORIES,
    CohortError,
    NodeNotFound,
    RefusalCategory,
    refusal_category,
)
from cohort.eventlog import summarize_refusals
from cohort.schemas import (
    RESEARCHER,
    ClaimPayload,
    Dating,
    DatingRoute,
    EdgeType,
    NodeStatus,
    PassagePayload,
    WitnessPayload,
)

AUTHOR = "agent:author"
OTHER = "agent:other"


def guessed(graph, author: str, node_id: str, tool: str = "find_attestations") -> None:
    """An agent naming a node that does not exist, recorded the way a real run
    records it.

    `NodeNotFound` is raised by *lookup*, not by a write, so it never reaches
    `_refuse` — it reaches the log through `log_refusal` at the tool boundary,
    which is precisely why that method exists (docs/changelog.md, the live
    conjecture run that lost five refusals this way). Tests that manufactured
    these some other route would exercise a path no agent takes."""
    graph.log_refusal(tool, author, NodeNotFound(node_id), node_id=node_id)


@pytest.fixture
def log_path(graph, tmp_path):
    return graph.event_log.path


# --- the taxonomy cannot rot -------------------------------------------------

def test_every_rule_has_a_category():
    """The guard that keeps this honest. A new `CohortError` with no category
    would land in `unclassified` and be quietly invisible in the one bucket
    breakdown the census exists to produce — so adding a rule has to include
    deciding what it indicts. Same discipline as `tests/test_parity.py`."""
    uncategorised = sorted(
        c.__name__ for c in CohortError.__subclasses__()
        if c.__name__ not in REFUSAL_CATEGORIES
    )
    assert not uncategorised, (
        f"rules with no refusal category: {uncategorised}. Add each to "
        f"REFUSAL_CATEGORIES in cohort/errors.py — what does this refusal tell "
        f"a researcher to go and look at?"
    )


def test_no_category_is_a_guess():
    """Every mapped name must be a real rule, or the taxonomy has drifted from
    the rules it claims to describe — a renamed error would otherwise leave a
    dead entry that silently classifies nothing."""
    known = {c.__name__ for c in CohortError.__subclasses__()} | {"ValidationError"}
    stale = sorted(name for name in REFUSAL_CATEGORIES if name not in known)
    assert not stale, f"REFUSAL_CATEGORIES names rules that no longer exist: {stale}"


def test_no_tool_refuses_with_a_rule_the_census_cannot_name():
    """The first live multi-model run censused (2026-09-02) returned exactly one
    refusal and it came back `unclassified`: `propose_claim` refused an
    ungrounded claim — the design's flagship evidence refusal — as a bare
    `ValueError`. Ten such raises were spread across the tool layer, so a
    reviewer, a mistyped id and a claim the corpus would not support all
    arrived under one meaningless rule name.

    The taxonomy guards above only see `CohortError` subclasses, which is
    precisely why they did not catch it. This one reads the tool layer itself.
    """
    import ast

    offenders: list[str] = []
    for path in sorted((Path(__file__).parent.parent / "cohort" / "tools").glob("*.py")):
        tree = ast.parse(path.read_text())
        for node in ast.walk(tree):
            if not isinstance(node, ast.Raise) or node.exc is None:
                continue
            exc = node.exc
            # `raise some_error` re-raises an object built elsewhere, whose
            # rule name is whatever that object already is.
            if not isinstance(exc, ast.Call):
                continue
            name = exc.func.attr if isinstance(exc.func, ast.Attribute) else getattr(exc.func, "id", "")
            if name and name not in REFUSAL_CATEGORIES:
                offenders.append(f"{path.name}:{node.lineno} raises {name}")

    assert not offenders, (
        "a tool refuses with a rule the census cannot categorise:\n  "
        + "\n  ".join(offenders)
        + "\nName it in cohort/errors.py and give it a category — the refusal "
          "log records the rule's *name*, so an unnamed rule tells a researcher "
          "nothing about what to go and look at."
    )


def test_an_unknown_rule_is_reported_not_dropped():
    """A census reads logs written by other versions of this code. Crashing on
    an old log would defeat the historical reading it exists to support, and
    silently dropping what it cannot classify would understate the very thing
    it counts."""
    assert refusal_category("SomeRuleFromTheFuture") is RefusalCategory.UNCLASSIFIED


def test_the_gates_are_evidence_and_the_ladder_is_standing():
    """The two buckets that mean 'the system worked', kept apart because they
    say different things: one sends you to the texts, the other tells you the
    discipline held."""
    assert refusal_category("UnattestableConjecture") is RefusalCategory.EVIDENCE
    assert refusal_category("UnattestableClaim") is RefusalCategory.EVIDENCE
    assert refusal_category("SelfAttestation") is RefusalCategory.STANDING
    assert refusal_category("NotResearcher") is RefusalCategory.STANDING
    assert refusal_category("NodeNotFound") is RefusalCategory.EXPRESSION


# --- arithmetic --------------------------------------------------------------

def test_an_empty_log_is_a_result_not_an_absence(graph):
    census = summarize_refusals(graph.event_log.path)
    assert census.total == 0
    assert census.streaks == []
    # every category present, including the zeroes: a reader should see that
    # `evidence` was empty, not have to notice its absence
    assert set(census.by_category) == {c.value for c in RefusalCategory}
    assert census.first_at is None


def test_counts_by_rule_category_author_and_attempted(graph):
    claim = graph.propose_claim(ClaimPayload(text="uncited"), authored_by=AUTHOR)
    with pytest.raises(CohortError):
        graph.attest(claim, authored_by=OTHER)          # UnattestableClaim
    with pytest.raises(CohortError):
        graph.accept(claim, authored_by=AUTHOR)         # NotResearcher
    with pytest.raises(CohortError):
        graph.reject(claim, authored_by=RESEARCHER, reason="  ")  # MissingRejectionReason

    census = summarize_refusals(graph.event_log.path)
    assert census.total == 3
    assert census.by_rule == {
        "MissingRejectionReason": 1, "NotResearcher": 1, "UnattestableClaim": 1,
    }
    assert census.by_category["evidence"] == 1
    assert census.by_category["standing"] == 1
    assert census.by_category["expression"] == 1
    assert census.by_author == {AUTHOR: 1, OTHER: 1, RESEARCHER: 1}
    assert census.by_attempted == {"accept": 1, "attest": 1, "reject": 1}
    assert census.first_at is not None and census.last_at is not None


def test_rules_are_ranked_most_frequent_first_and_ties_are_stable(graph):
    """Stable ordering so two reads of one log can be diffed. Ties break by
    name rather than by insertion, which is otherwise dict order and would
    reshuffle when an unrelated rule fires."""
    for i in range(3):
        guessed(graph, AUTHOR, f"claim:nope{i}")
    with pytest.raises(CohortError):
        graph.accept("claim:nope", authored_by=AUTHOR)       # NotResearcher

    census = summarize_refusals(graph.event_log.path)
    assert list(census.by_rule) == ["NodeNotFound", "NotResearcher"]


# --- streaks -----------------------------------------------------------------

def test_a_run_of_one_rule_from_one_agent_is_a_streak(graph):
    """The historical shape this exists to find: an agent guessing at ids,
    refused each time, because no tool would give it the real one."""
    for guess in ("witness:B01n0001", "B01n0001_002", "witness:B01n0001_002"):
        guessed(graph, AUTHOR, guess, tool="link_parallels")

    census = summarize_refusals(graph.event_log.path)
    assert len(census.streaks) == 1
    streak = census.streaks[0]
    assert streak.count == 3
    assert streak.rule == "NodeNotFound"
    assert streak.category == "expression"
    assert streak.authored_by == AUTHOR
    assert streak.attempted == ["link_parallels"]
    # several distinct ids under one rule is the strongest tell: it was guessing
    assert len(streak.node_ids) == 3
    assert census.streaked_count == 3


def test_one_refusal_is_not_a_streak(graph):
    guessed(graph, AUTHOR, "claim:nope")
    census = summarize_refusals(graph.event_log.path)
    assert census.streaks == []
    assert census.streaked_count == 0
    assert census.expression_count == 1


def test_a_different_rule_breaks_a_streak(graph):
    guessed(graph, AUTHOR, "claim:nope")
    with pytest.raises(CohortError):
        graph.accept("claim:nope", authored_by=AUTHOR)      # different rule
    guessed(graph, AUTHOR, "claim:nope-again")

    census = summarize_refusals(graph.event_log.path)
    assert census.streaks == [], "two NodeNotFounds either side of another rule are not a run"


def test_another_agents_refusal_does_not_break_a_streak(graph):
    """The property that makes this survive a swarm. Several agents interleave
    their refusals in one log; a run defined over the raw sequence would be
    broken by an unrelated agent's refusal landing in between, losing the
    signal exactly when the most agents are running."""
    guessed(graph, AUTHOR, "claim:a")
    guessed(graph, OTHER, "claim:x")      # interleaved
    guessed(graph, AUTHOR, "claim:b")

    census = summarize_refusals(graph.event_log.path)
    assert [(s.authored_by, s.count) for s in census.streaks] == [(AUTHOR, 2)]


def test_streaks_are_longest_first(graph):
    for i in range(2):
        guessed(graph, OTHER, f"claim:short{i}")
    for i in range(4):
        guessed(graph, AUTHOR, f"claim:long{i}")

    census = summarize_refusals(graph.event_log.path)
    assert [s.count for s in census.streaks] == [4, 2]


def test_the_new_reviewer_rule_shows_up_as_standing(graph, tmp_path):
    """An end-to-end census over the rule added most recently, so the taxonomy
    is exercised by a real refusal and not only by a name lookup."""
    w = graph.propose_witness(
        WitnessPayload(
            canonical_ref="T01n0001",
            dating=Dating(confidence=DatingRoute.UNKNOWN, basis="not dated for this test"),
        ),
        authored_by=AUTHOR,
    )
    graph.attest(w, authored_by=AUTHOR)
    p = graph.propose_passage(
        PassagePayload(canonical_ref="T01n0001#a", locator="juan 1", excerpt="明月"),
        witness_id=w, authored_by=AUTHOR,
    )
    graph.attest(p, authored_by=AUTHOR)
    claim = graph.propose_claim(ClaimPayload(text="the phrase recurs"), authored_by=AUTHOR)
    graph.add_edge(EdgeType.ATTESTS, p, claim, authored_by=AUTHOR)

    with pytest.raises(CohortError):
        graph.attest(claim, authored_by=AUTHOR)  # SelfAttestation

    census = summarize_refusals(graph.event_log.path)
    assert census.by_rule == {"SelfAttestation": 1}
    assert census.by_category["standing"] == 1
    assert census.by_category["expression"] == 0
    assert graph.get_node(claim).status == NodeStatus.PROPOSED


def test_the_census_covers_the_whole_log_not_a_truncated_view(graph):
    """`read_refusals(limit=n)` returns the tail. A census over the tail would
    report a smaller total than the log holds while looking authoritative, so
    this takes a path and reads all of it."""
    from cohort.eventlog import read_refusals

    for i in range(5):
        guessed(graph, AUTHOR, f"claim:{i}")

    assert len(read_refusals(graph.event_log.path, limit=2)) == 2
    assert summarize_refusals(graph.event_log.path).total == 5
