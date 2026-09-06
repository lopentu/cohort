"""associate_work: is this group unusually close to this work, across the canon?

The tool for the question Radich actually asked — *can we discover features
that associate a work with P against texts by other translators in the canon,
or associate it with some other reference point, suggesting an alternate
ascription* — as against `place_work`, which measures a distance and reads it
against the benchmark's own internal spread.

The two are not interchangeable and the difference is worth stating once. A
null band's threshold is the distance of the group's most eccentric member, so
on this corpus every disputed work and every interloper alike came back "not
distinguishable from the benchmark" — true, and an answer to nothing. This
measure asks whether group members are over-represented among a work's nearest
neighbours in the whole corpus, where the comparison set is 1,464 works rather
than the handful in a catalogue, and where a result therefore has an `n` behind
it. `cohort.association` carries the full argument.

**Three things travel in the payload because each one is what stops the measure
being over-read.**

The **calibration** says what a *known* member scores, self held out. Without
it an enrichment is a p-value against chance, which says the overlap is not an
accident and does not say the association is as strong as membership normally
looks.

The **blind count** inside that calibration says how many undisputed members
the method fails to recover — six of sixteen here. A tool that reported an
unenriched work as an outsider would be manufacturing exclusions, so the
reading refuses to, in those words.

The **nearest work outside the group** is the genre control. Character n-grams
track subject matter, so a work surrounded by Abhidharma sits near any
Abhidharma-heavy group whoever translated it; the check that survives that is
whether the group's own member is nearer than the same material by other hands.

Nothing here concludes. It reports an enrichment, its calibration and its
control; whether that supports an ascription is a judgement, and the caveat
that these features track subject matter goes into `limitations` on every
write.
"""
from __future__ import annotations

import hashlib
import json

from pydantic import BaseModel, ConfigDict, Field

from ..errors import WrongNodeType
from ..graph import Graph
from ..schemas import (
    AssociationOutcome,
    AssuranceLevel,
    NodeType,
    VerificationMethod,
    VerificationResult,
)

NAME = "associate_work"
DESCRIPTION = (
    "Measure one work against the benchmark group across the whole corpus, and "
    "record it against a claim or conjecture. Answers two questions in one "
    "call. First: are benchmark works over-represented among this work's "
    "nearest neighbours, compared with what a known member of the group "
    "scores? Second, and independently of the group: what IS this work nearest "
    "to, and does one reference point stand clearly ahead of the rest — which "
    "is what an alternate ascription looks like. A work with no benchmark "
    "enrichment is NOT thereby excluded from the group; it is reported as "
    "unseen, with whatever its own neighbourhood does say."
)

MEASURABLE = (NodeType.CLAIM, NodeType.CONJECTURE)


class AssociateWorkInput(BaseModel):
    model_config = ConfigDict(extra="forbid")

    claim_or_conjecture_id: str = Field(min_length=1)
    work: str = Field(min_length=1, description="a work id as the catalogue names it")
    top: int = Field(
        default=15, ge=1, le=50,
        description="how many nearest neighbours to record by name",
    )


def fingerprint(payload: dict) -> str:
    """A stable hash of the whole association, calibration included.

    Calibration is inside the digest deliberately: it depends on which works
    are in the benchmark, and a run whose calibration moved has not reproduced
    the earlier result even if this work's own share is unchanged.
    """
    canonical = json.dumps(payload, sort_keys=True, ensure_ascii=False,
                           separators=(",", ":"))
    return "sha256:" + hashlib.sha256(canonical.encode("utf-8")).hexdigest()


def _prior(graph: Graph, node_id: str, work: str) -> str | None:
    latest = None
    for v in graph.verifications(node_id):
        p = v.payload
        if p.get("method") != VerificationMethod.CORPUS_MEASUREMENT:
            continue
        if f"associated {work!r} " not in (p.get("detail") or ""):
            continue
        if p.get("excerpt_hash"):
            latest = p["excerpt_hash"]
    return latest


def associate_work(
    graph: Graph, study, args: AssociateWorkInput, *, authored_by: str,
    model_call_id: int | None = None,
) -> dict:
    from ..attribution import CAVEAT

    node = graph.get_node(args.claim_or_conjecture_id)
    if node.type not in MEASURABLE:
        raise WrongNodeType(
            f"{args.claim_or_conjecture_id} is a {node.type}; only a claim or "
            "conjecture asserts something an association could bear on"
        )
    if args.work not in study.space.works():
        raise WrongNodeType(
            f"{args.work!r} has no profile in this space. Either the corpus "
            f"does not hold it, or it is under the {study.space.min_chars}-"
            "character floor and was deliberately not profiled — 'this method "
            "cannot speak to that work' is a result rather than a gap"
        )

    a = study.association(args.work, top=args.top)
    body = a.as_json()
    digest = fingerprint(body)
    prior = _prior(graph, args.claim_or_conjecture_id, args.work)

    if prior is None:
        result, note = VerificationResult.INDETERMINATE, (
            "baseline recorded; there is nothing yet to compare it against"
        )
    elif prior == digest:
        result, note = VerificationResult.PASS, (
            "the enrichment and its calibration reproduce exactly"
        )
    else:
        result, note = VerificationResult.FAIL, (
            f"this no longer matches the recorded baseline ({prior[:19]}…). The "
            "corpus, the feature set or the group's membership changed, and "
            "every rank in this space moves when any of them does"
        )

    payload = AssociationOutcome.model_validate({
        **body,
        # `neighbourhood` and `verdict` come through `body` unchanged; only the
        # enrichment rows are reshaped, because the compute layer nests the
        # calibration under each row and the payload keeps it flat so a table
        # can print one row per k without descending.

        "enrichment": [
            {
                "k": e["k"], "hits": e["hits"], "share": e["share"],
                "p_value": e["p_value"],
                "within_calibration": e["within_calibration"],
                "calibration_n": e["calibration"]["n"],
                "calibration_blind": e["calibration"]["blind"],
                "calibration_min": e["calibration"]["min"],
                "calibration_median": e["calibration"]["median"],
                "calibration_max": e["calibration"]["max"],
            }
            for e in body["enrichment"]
        ],
    })

    verification_id = graph.verify(
        args.claim_or_conjecture_id,
        method=VerificationMethod.CORPUS_MEASUREMENT,
        result=result,
        # Grants no rung, like every other measurement: the ladder grades how
        # well a node's citations stand up, and a neighbourhood says something
        # else entirely.
        assurance_level=AssuranceLevel.A0_UNCHECKED,
        detail=(
            f"associated {args.work!r} with {a.group_label} over "
            f"{a.corpus_size} profiled works [{a.verdict}] — {a.reading} {note}."
        ),
        limitations=(
            f"{CAVEAT} A neighbourhood is also not a roster: the corpus holds "
            "works by many hands and this measure names only whether one "
            "labelled group is over-represented, so a work with no enrichment "
            "has not been placed anywhere — it has only not been placed here. "
            "Where the second reading names a dominant nearest work, that is a "
            "reference point to check and not an ascription: nothing here "
            "establishes who produced that work either, and the two may be "
            "close for the same reasons of genre and subject that this measure "
            "cannot separate."
        ),
        excerpt_hash=digest,
        association=payload,
        authored_by=authored_by,
        model_call_id=model_call_id,
    )
    return {
        "verification_id": verification_id,
        "result": result,
        "fingerprint": digest,
        "association": body,
    }
