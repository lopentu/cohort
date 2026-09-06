"""Candidate discriminators: register a prediction, survive a control, then speak.

Three calls in a fixed order, and the order is the method.

`register_discriminator` proposes a conjecture — "feature F distinguishes the
benchmark from works that do not belong" — together with the two-sided
prediction that would settle it, recorded before anything is counted.

`run_control_test` counts, and compares against that prediction. Its subject is
the **negative control**: a group the researcher believes does *not* belong and
that earlier methods could not separate from the benchmark. Radich's
`interloper` set is exactly this. A feature that lights up on those has been
shown to track something other than authorship, and is finished.

`apply_to_disputed` refuses to run until the control test has passed. That
refusal is the entire contribution. Run the control first and a feature can
fail; run it afterwards and the result is unfalsifiable by construction, which
is the shape of most stylometric attribution and the reason its findings are
hard to trust.

Nothing here concludes. A surviving feature that places a disputed work with
the benchmark is one feature agreeing with a traditional ascription; how much
that is worth depends on how many features were tried, how many were discarded,
and whether they were independent of each other. The ledger reports all of
that, and none of it is a score.
"""
from __future__ import annotations

from pydantic import BaseModel, ConfigDict, Field

from ..catalogue import Catalogue
from ..errors import ControlNotPassed, WrongNodeType
from ..graph import Graph
from ..measure import DEFAULT_BASE_EDITION, DEFAULT_MIN_CHARS, measure_feature
from ..schemas import (
    AssuranceLevel,
    GroupOutcome,
    ConjecturePayload,
    DiscriminationPrediction,
    EdgeType,
    NodeType,
    QueryPayload,
    VerificationMethod,
    VerificationResult,
)

NAME = "register_discriminator"
DESCRIPTION = (
    "Propose that a feature distinguishes the benchmark group from works that "
    "do not belong, with the two-sided prediction that would settle it recorded "
    "before anything is counted. The feature cannot be applied to a disputed "
    "work until it has survived the negative control."
)


class RegisterDiscriminatorInput(BaseModel):
    model_config = ConfigDict(extra="forbid")

    feature: str = Field(min_length=1)
    #: why this feature might track a translator rather than a subject
    derivation: str = Field(min_length=1)
    corpus_boundary: str = Field(min_length=1)
    selection_risks: str = Field(min_length=1)
    alternative_explanations: str = Field(min_length=1)
    min_benchmark_share: float = Field(ge=0.0, le=1.0)
    max_control_share: float = Field(ge=0.0, le=1.0)
    base_edition: str = DEFAULT_BASE_EDITION
    min_chars: int = Field(default=DEFAULT_MIN_CHARS, ge=0)


def register_discriminator(
    graph: Graph, args: RegisterDiscriminatorInput, *, catalogue: Catalogue,
    authored_by: str, model_call_id: int | None = None,
) -> dict:
    """The conjecture and its registered prediction, written in one call.

    One call because a prediction recorded in a second call is a prediction
    that could have been written after a first look at the numbers. Same
    reasoning as `propose_conjecture`, which creates its `tests` query in the
    call that creates the conjecture.
    """
    if catalogue.benchmark_label is None or catalogue.control_label is None:
        raise WrongNodeType(
            "this catalogue names no benchmark and control group, so there is "
            "nothing for a discriminator to be tested against. Load it with "
            "`benchmark_label=` and `control_label=`; a study without a group "
            "believed not to belong cannot fail, which is why it is required "
            "here rather than optional"
        )
    if args.min_benchmark_share <= args.max_control_share:
        raise WrongNodeType(
            f"a prediction of at least {args.min_benchmark_share:.2f} in the "
            f"benchmark and at most {args.max_control_share:.2f} in the control "
            "is not a discrimination: it permits the feature to be at least as "
            "common outside the group as inside it. The benchmark floor must "
            "exceed the control ceiling"
        )

    prediction = DiscriminationPrediction(
        feature=args.feature,
        benchmark_label=catalogue.benchmark_label,
        control_label=catalogue.control_label,
        min_benchmark_share=args.min_benchmark_share,
        max_control_share=args.max_control_share,
    )

    conjecture_id = graph.propose_conjecture(
        ConjecturePayload(
            # The feature leads. Every one of these sentences is otherwise
            # identical, so a title truncated to fit a node box would show
            # twenty-two cards reading "The feature '…' dist…" — the one word
            # that tells them apart buried in the middle of the elision.
            text=(
                f"{args.feature} — distinguishes {catalogue.benchmark_label} "
                "works from works outside that group."
            ),
            derivation=args.derivation,
            corpus_boundary=args.corpus_boundary,
            selection_risks=args.selection_risks,
            alternative_explanations=args.alternative_explanations,
        ),
        authored_by=authored_by, model_call_id=model_call_id,
    )
    query_id = graph.propose_query(
        QueryPayload(
            text=(
                f"measure {args.feature!r} across {catalogue.benchmark_label} and "
                f"{catalogue.control_label} (edition {args.base_edition!r}, "
                f"floor {args.min_chars})"
            ),
            discrimination=prediction,
        ),
        authored_by=authored_by, model_call_id=model_call_id,
    )
    graph.add_edge(
        EdgeType.TESTS, query_id, conjecture_id,
        authored_by=authored_by, model_call_id=model_call_id,
    )
    return {"conjecture_id": conjecture_id, "query_id": query_id,
            "prediction": prediction.model_dump(mode="json")}


# --- the gate ---------------------------------------------------------------

def _prediction(graph: Graph, conjecture_id: str) -> tuple[str, DiscriminationPrediction]:
    node = graph.get_node(conjecture_id)
    if node.type != NodeType.CONJECTURE:
        raise WrongNodeType(
            f"{conjecture_id} is a {node.type}; only a conjecture carries a "
            "registered prediction"
        )
    for edge in graph.edges(edge_type=EdgeType.TESTS, dst=conjecture_id):
        payload = graph.get_node(edge.src).payload
        if payload.get("discrimination"):
            return edge.src, DiscriminationPrediction.model_validate(payload["discrimination"])
    raise WrongNodeType(
        f"{conjecture_id} has no registered discrimination prediction, so there "
        "is nothing to test it against. Use `register_discriminator`, which "
        "writes the prediction in the same call that creates the conjecture"
    )


def _shares(m, benchmark: str, control: str) -> tuple:
    by_label = m.by_label()
    b = by_label.get(benchmark)
    c = by_label.get(control)
    return b, c


def run_control_test(
    graph: Graph, corpus, conjecture_id: str, *, catalogue: Catalogue,
    base_edition: str = DEFAULT_BASE_EDITION, min_chars: int = DEFAULT_MIN_CHARS,
    authored_by: str, model_call_id: int | None = None,
) -> dict:
    """Count the feature over the benchmark and the control, and compare with
    the prediction registered when the conjecture was proposed."""
    query_id, pred = _prediction(graph, conjecture_id)
    labels = dict(catalogue.entries)
    works = catalogue.works(pred.benchmark_label) + catalogue.works(pred.control_label)
    m = measure_feature(
        corpus, pred.feature, labels=labels, works=works,
        base_edition=base_edition, min_chars=min_chars,
    )
    bench, control = _shares(m, pred.benchmark_label, pred.control_label)

    if not bench or not bench.works_measured or not control or not control.works_measured:
        result = VerificationResult.INDETERMINATE
        note = (
            "one of the two groups has no work long enough to measure at this "
            f"floor ({min_chars} chars), so the contrast the prediction is "
            "about cannot be observed. Reported rather than scored as a pass: "
            "a control that could not have failed has not been run"
        )
        held_b = held_c = None
    else:
        held_b = bench.share_attesting >= pred.min_benchmark_share
        held_c = control.share_attesting <= pred.max_control_share
        result = VerificationResult.PASS if (held_b and held_c) else VerificationResult.FAIL
        if result == VerificationResult.PASS:
            note = "the feature is present in the benchmark and absent from the control as predicted"
        else:
            broke = []
            if not held_b:
                broke.append(
                    f"benchmark share {bench.share_attesting:.2f} is below the "
                    f"predicted floor of {pred.min_benchmark_share:.2f}"
                )
            if not held_c:
                broke.append(
                    f"control share {control.share_attesting:.2f} exceeds the "
                    f"predicted ceiling of {pred.max_control_share:.2f}, so the "
                    "feature does not track membership of the group"
                )
            note = "; ".join(broke)

    detail = (
        f"control test of query {query_id}: {pred.feature!r} attests in "
        f"{bench.works_attesting if bench else 0}/{bench.works_measured if bench else 0} "
        f"{pred.benchmark_label} and "
        f"{control.works_attesting if control else 0}/{control.works_measured if control else 0} "
        f"{pred.control_label} work(s). {note}."
    )
    groups = tuple(
        GroupOutcome(
            label=g.label, works_measured=g.works_measured,
            works_attesting=g.works_attesting,
            works_skipped_short=g.works_skipped_short,
        )
        for g in (bench, control) if g is not None
    )
    verification_id = graph.verify(
        conjecture_id,
        # The same epistemic act `PROSPECTIVE_TEST` names: a prediction put on
        # the record before the evidence, then checked against it. What differs
        # is the shape of the prediction, not its status.
        method=VerificationMethod.PROSPECTIVE_TEST,
        result=result,
        assurance_level=AssuranceLevel.A0_UNCHECKED,
        detail=detail,
        limitations=(
            "A pass means the feature survived one negative control, not that "
            "it identifies an author. The control contains only the works "
            "someone thought to doubt; a feature can separate these and still "
            "track genre, date or subject. Shares are over works measurable at "
            "the stated floor — works below it were neither counted for nor "
            "against."
        ),
        groups=groups,
        authored_by=authored_by, model_call_id=model_call_id,
    )
    return {
        "verification_id": verification_id, "result": result,
        "benchmark": bench, "control": control, "prediction": pred,
        "measurement": m,
    }


def control_status(graph: Graph, conjecture_id: str) -> str:
    """`passed`, `failed`, or `untested` — latest control test wins.

    Latest rather than best, for the reason `assurance_for` takes the latest
    per method: a feature that passed against an older corpus and fails against
    this one has failed, and letting the stale pass stand would be exactly the
    bug that let a superseded A2 outrank a later failure.
    """
    latest = None
    for v in graph.verifications(conjecture_id):
        p = v.payload
        if p.get("method") != VerificationMethod.PROSPECTIVE_TEST:
            continue
        if "control test of query" not in (p.get("detail") or ""):
            continue
        latest = p["result"]
    if latest is None:
        return "untested"
    return "passed" if latest == VerificationResult.PASS else "failed"


def apply_to_disputed(
    graph: Graph, corpus, conjecture_id: str, *, catalogue: Catalogue,
    disputed_label: str, base_edition: str = DEFAULT_BASE_EDITION,
    min_chars: int = DEFAULT_MIN_CHARS,
) -> dict:
    """Where each disputed work sits on a feature that has survived its control.

    Refused outright until it has. This is the gate, and it is a refusal rather
    than a warning because a warning is something a hurried reader scrolls past
    on the way to the number they wanted.
    """
    status = control_status(graph, conjecture_id)
    if status != "passed":
        _, pred = _prediction(graph, conjecture_id)
        raise ControlNotPassed(
            f"{conjecture_id} is {status} against its {pred.control_label} "
            f"control, so it may not be applied to {disputed_label}. A feature "
            "that has not been shown to separate works believed not to belong "
            "has not earned an opinion about works in doubt — run "
            "`run_control_test` first, and accept that it may fail"
        )

    _, pred = _prediction(graph, conjecture_id)
    labels = dict(catalogue.entries)
    m = measure_feature(
        corpus, pred.feature, labels=labels,
        works=catalogue.works(pred.benchmark_label) + catalogue.works(disputed_label),
        base_edition=base_edition, min_chars=min_chars,
    )
    by_label = m.by_label()
    rows = [
        {
            "work": w.work, "chars": w.chars, "count": w.count,
            "per_10k": w.per_10k, "sufficient": w.sufficient,
            "editions_attesting": w.editions_attesting,
            "editions_total": w.editions_total,
            "attests": w.count > 0 if w.sufficient else None,
            "note": w.note,
        }
        for w in m.works if w.label == disputed_label
    ]
    return {
        "feature": pred.feature,
        "benchmark": by_label.get(pred.benchmark_label),
        "disputed_label": disputed_label,
        "works": rows,
        # No verdict per work, deliberately. "Attests / does not attest" is what
        # was observed; whether that places the work with the benchmark is a
        # reading, and one feature is not an ascription.
        "measurement": m,
    }
