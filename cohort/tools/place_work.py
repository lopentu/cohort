"""place_work: where one work sits against the benchmark, recorded with its band.

The distance is not the finding. A Burrows's Delta of 0.83 is a number nobody
can read; the same 0.83 beside *the spread the benchmark's own members occupy*
is immediately legible as "no further out than the yardstick's own variation".
Twice on 2026-09-06 an apparent separation in this study turned out to be an
artifact — a work scored against a range it helped define, and a null band
calibrated on fifteen works while distances were taken against sixteen — and
both would have been obvious at a glance against the band.

So the band travels with every placement this writes, in the same payload, and
`Profile` refuses to exist without one. A renderer cannot drop the calibration
because it never receives the distance separately from it.

**What this does not do.** It records where a work sits; it does not say the
work is by anyone. Character n-grams over this corpus track subject matter
heavily — a cosmological text sits near cosmological texts whoever translated
it — so `CAVEAT` goes into the verification's `limitations` field, which is the
field a reader already sees under "Does not establish". Nothing here returns a
verdict, and the result is `INDETERMINATE` on the first call for the reason
`measure_claim`'s is: one measurement says only what the number is, which is
what the author of the hypothesis could already have typed.
"""
from __future__ import annotations

import hashlib
import json

from pydantic import BaseModel, ConfigDict, Field

from ..errors import WrongNodeType
from ..graph import Graph
from ..schemas import (
    AssuranceLevel,
    NodeType,
    VerificationMethod,
    VerificationResult,
)

NAME = "place_work"
DESCRIPTION = (
    "Measure how far one work sits from the benchmark group by Burrows's "
    "Delta over character bigrams, against the spread the benchmark's own "
    "members occupy, and record the numbers against a claim or conjecture. "
    "Reports a distance and its calibration — it does not say who wrote "
    "anything, and a work inside the band is simply not distinguishable from "
    "the benchmark by this measure."
)

MEASURABLE = (NodeType.CLAIM, NodeType.CONJECTURE)


class PlaceWorkInput(BaseModel):
    model_config = ConfigDict(extra="forbid")

    claim_or_conjecture_id: str = Field(min_length=1)
    work: str = Field(min_length=1, description="a work id as the catalogue names it")
    top: int = Field(
        default=8, ge=1, le=40,
        description="how many nearest neighbours in the whole corpus to return",
    )


def fingerprint(payload: dict) -> str:
    """A stable hash of the placement, so a later call can disagree with an
    earlier one instead of quietly replacing it. Same device as
    `measure_claim.fingerprint`: canonical JSON, sorted keys."""
    canonical = json.dumps(payload, sort_keys=True, ensure_ascii=False,
                           separators=(",", ":"))
    return "sha256:" + hashlib.sha256(canonical.encode("utf-8")).hexdigest()


def _prior_placement(graph: Graph, node_id: str, work: str) -> str | None:
    """The fingerprint of the last placement *of this work* on this node.

    Filtered by work, for the reason `measure_claim` filters by feature: a node
    may carry placements of several, and comparing one work's distance against
    another's baseline would fail every time while looking like a finding.
    """
    latest = None
    for v in graph.verifications(node_id):
        p = v.payload
        if p.get("method") != VerificationMethod.CORPUS_MEASUREMENT:
            continue
        if f"placed {work!r} " not in (p.get("detail") or ""):
            continue
        if p.get("excerpt_hash"):
            latest = p["excerpt_hash"]
    return latest


def place_work(
    graph: Graph, study, args: PlaceWorkInput, *, authored_by: str,
    model_call_id: int | None = None,
) -> dict:
    from ..delta_study import CAVEAT

    node = graph.get_node(args.claim_or_conjecture_id)
    if node.type not in MEASURABLE:
        raise WrongNodeType(
            f"{args.claim_or_conjecture_id} is a {node.type}; only a claim or "
            "conjecture asserts something a distance could bear on. Placing a "
            "work against a passage would record a number with nothing staked "
            "on it"
        )
    if args.work not in study.space.works():
        floor = study.space.min_chars
        raise WrongNodeType(
            f"{args.work!r} has no profile in this space. Either the corpus "
            f"does not hold it, or it is under the {floor}-character floor and "
            "was deliberately not profiled — a rate from a text that short is "
            "noise, and 'this method cannot speak to that work' is a result "
            "rather than a gap"
        )

    profile = study.profile(args.work, top=args.top)
    body = profile.as_json()
    digest = fingerprint(body)
    prior = _prior_placement(graph, args.claim_or_conjecture_id, args.work)

    if prior is None:
        result = VerificationResult.INDETERMINATE
        note = (
            "baseline recorded; there is nothing yet to compare it against"
        )
    elif prior == digest:
        result = VerificationResult.PASS
        note = "the distance and its band reproduce exactly against the recorded baseline"
    else:
        result = VerificationResult.FAIL
        note = (
            f"this placement no longer matches the recorded baseline ({prior[:19]}…). "
            "The corpus, the feature set, the character floor or the benchmark "
            "membership changed, and every distance in this space moves when "
            "any of them does"
        )

    band = profile.null
    verification_id = graph.verify(
        args.claim_or_conjecture_id,
        method=VerificationMethod.CORPUS_MEASUREMENT,
        result=result,
        # Grants no rung, for the reason a feature count grants none: the
        # ladder grades how well a node's citations stand up, and a distance
        # says something else entirely.
        assurance_level=AssuranceLevel.A0_UNCHECKED,
        detail=(
            f"placed {args.work!r} at Δ {body['mean_delta_to_benchmark']} from "
            f"{band.label} over {len(study.space.features)} character-bigram "
            f"features, against a benchmark band of {band.as_json()['min']}–"
            f"{band.as_json()['max']} across {band.n} works "
            f"(median {band.as_json()['median']}) — {body['reading']}. {note}."
        ),
        limitations=CAVEAT,
        excerpt_hash=digest,
        authored_by=authored_by,
        model_call_id=model_call_id,
    )
    return {
        "verification_id": verification_id,
        "result": result,
        "fingerprint": digest,
        "placement": body,
    }
