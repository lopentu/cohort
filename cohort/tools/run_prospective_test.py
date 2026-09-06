"""run_prospective_test: ask the question the falsifiability gate demanded.

`propose_conjecture` has always required a query that would settle a conjecture
going forward, and `attest()` has always refused a conjecture that has no
`tests` edge. Between them they checked that a test *existed*. Nothing ever ran
it. A gate that demands a prediction and never collects on it is a gate on
paperwork.

This runs it: re-fetch the stored query, run it against the corpus, and compare
the hit count to the prediction its author recorded at proposal time. The
prediction is on the query node's own payload, written in the same call that
created the conjecture and immutable afterwards, which is what makes this a
prospective test rather than a number with a story attached.

**Not registered as an agent tool**, for the same reason as
`verify_exact_span`: it is a check, not a contribution, and its whole value is
in being run *later* — against a rebuilt index, a newer corpus version, or a
corpus that has grown since. An agent running it in the same turn that proposed
the conjecture would be testing a prediction against the state that produced
it, which is not a test of anything.

What it deliberately does **not** do is decide what the result means. A
prediction that failed may indict the conjecture, the query, or the corpus
boundary, and which of those it is takes a reading. The record says what was
predicted, what was found, and whether they agree.
"""
from __future__ import annotations

from pydantic import BaseModel, ConfigDict

from cohort.errors import WrongNodeType
from cohort.graph import Graph
from cohort.schemas import (
    AssuranceLevel,
    EdgeType,
    HitExpectation,
    NodeType,
    VerificationMethod,
    VerificationResult,
)
from cohort.sources.base import Source

NAME = "run_prospective_test"

#: The search cap. It matters more here than anywhere else in the tool layer,
#: because here the *count* is the finding rather than the hits. A query that
#: returns the cap has not been counted — it has been floored — and the
#: comparison below is careful about which predictions a floor can settle.
MAX_RESULTS = 200


class ProspectiveTestReport(BaseModel):
    model_config = ConfigDict(extra="forbid")

    conjecture_id: str
    query_id: str
    query_text: str
    #: None when the conjecture predates the prediction fields — reported as
    #: indeterminate rather than assumed to have meant "no hits".
    expectation: HitExpectation | None
    expected_hits: int | None
    observed_hits: int
    #: True when the search returned the cap, in which case `observed_hits` is
    #: a floor rather than a count and some predictions cannot be settled.
    count_saturated: bool
    result: VerificationResult
    verification_id: str
    note: str


def _tests_query(graph: Graph, conjecture_id: str):
    """The most recent `tests` query for a conjecture.

    Most recent, not "the one", because `tests` is a plain edge type and
    nothing forbids a second one. Taking the newest is the only reading that
    stays honest if a conjecture is ever re-tested with a sharper query, and
    the verification records which query id it ran.
    """
    edges = list(graph.edges(edge_type=EdgeType.TESTS, dst=conjecture_id))
    if not edges:
        return None
    queries = [graph.get_node(e.src) for e in edges]
    return max(queries, key=lambda n: n.created_seq)


def run_prospective_test(
    graph: Graph, source: Source, conjecture_id: str, *, authored_by: str,
    model_call_id: int | None = None,
) -> ProspectiveTestReport:
    node = graph.get_node(conjecture_id)
    if node.type != NodeType.CONJECTURE:
        raise WrongNodeType(
            f"{conjecture_id} is a {node.type}; only a conjecture carries a "
            "prospective query. A claim asserts what the sources already say, "
            "so there is nothing about it to predict"
        )

    query = _tests_query(graph, conjecture_id)
    if query is None:
        # Unreachable for anything `propose_conjecture` wrote, and reachable
        # for a conjecture written straight through `graph.propose_conjecture`
        # — which the falsifiability gate already refuses to attest.
        raise WrongNodeType(
            f"{conjecture_id} has no tests query, so there is nothing to run. "
            "It is also unattestable for the same reason (docs/design.md §7)"
        )

    query_text = query.payload["text"]
    expectation = query.payload.get("expectation")
    expected = query.payload.get("expected_hits")

    observed = len(source.search(query_text, max_results=MAX_RESULTS))
    saturated = observed >= MAX_RESULTS

    if expectation is None or expected is None:
        result = VerificationResult.INDETERMINATE
        note = (
            f"{query_text!r} returned {observed} hit(s), but no prediction was "
            "recorded when this conjecture was proposed, so there is nothing "
            "to compare against. Reported rather than assumed: reading it as "
            "'no hits were expected' would invent the prediction after seeing "
            "the answer"
        )
    else:
        word = "at most" if expectation == HitExpectation.AT_MOST else "at least"
        # A saturated search gives a *floor*, not a count, and a floor settles
        # only some predictions. `at most E` is decided when the floor already
        # exceeds E; `at least E` is decided when the floor already reaches it.
        # Otherwise the true count is somewhere above the cap and the honest
        # answer is that this test did not settle the question — counting a
        # capped result as if it were exact is how a measurement layer starts
        # reporting numbers it did not measure.
        if expectation == HitExpectation.AT_MOST:
            decided, held = (not saturated or observed > expected), observed <= expected
        else:
            decided, held = (not saturated or observed >= expected), observed >= expected

        if not decided:
            result = VerificationResult.INDETERMINATE
            note = (
                f"predicted {word} {expected}; the search returned the cap of "
                f"{MAX_RESULTS}, so the true count is at least that and this "
                "test cannot settle the prediction. Narrow the query or raise "
                "the cap"
            )
        else:
            result = VerificationResult.PASS if held else VerificationResult.FAIL
            seen = f"at least {observed}" if saturated else str(observed)
            note = (
                f"predicted {word} {expected}, observed {seen} — "
                f"{'the prediction held' if held else 'the prediction broke'}"
            )

    verification_id = graph.verify(
        conjecture_id,
        method=VerificationMethod.PROSPECTIVE_TEST,
        result=result,
        # Grants no rung, deliberately, and a passing test grants none either.
        # The ladder records how well a node's *citations* stand up; a
        # prospective test says something else entirely — that a prediction
        # about the corpus survived. Giving it a rung would repeat the A3
        # mistake of grading one thing with a name that reads as another.
        assurance_level=AssuranceLevel.A0_UNCHECKED,
        detail=(
            f"prospective test of query {query.id}: {query_text!r} returned "
            f"{'at least ' if saturated else ''}{observed} hit(s). {note}."
        ),
        limitations=(
            "A prediction that broke may indict the conjecture, the query, or "
            "the corpus boundary it was framed against; which of those it is "
            "takes a reading. A prediction that held is one test survived, not "
            "a conjecture confirmed — and both are answers about the corpus as "
            "indexed today."
        ),
        authored_by=authored_by,
        model_call_id=model_call_id,
    )

    return ProspectiveTestReport(
        conjecture_id=conjecture_id,
        query_id=query.id,
        query_text=query_text,
        expectation=expectation,
        expected_hits=expected,
        observed_hits=observed,
        count_saturated=saturated,
        result=result,
        verification_id=verification_id,
        note=note,
    )
