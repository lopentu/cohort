"""measure_claim: re-count what a claim rests on, and say whether it still holds.

An attribution claim is made of numbers — "this feature appears in three of
sixteen benchmark works and none of the control" — and until now the graph took
those on trust. This records them instead, as a `CORPUS_MEASUREMENT`
verification, and re-derives them on every later call.

**The first call establishes the record; every later one is the check.** That
asymmetry is the point. A single measurement proves nothing that the claim's
author could not have typed by hand; a second one, run against the same works
and the same base edition, either reproduces the first exactly or it does not —
and if it does not, something moved: the corpus, the catalogue, the floor, or
the counting itself. Any of those invalidates the claim, and none of them
announce themselves.

The comparison is a hash, not prose. `cohort.measure` is pure and
deterministic, so the canonical JSON of a measurement fingerprints it exactly;
`excerpt_hash` is where the earlier fingerprint lives, which is what those
fields are for. Two runs whose hashes match agree on every count, rate,
edition tally and skipped work, and no amount of readable summary could
promise that.

What this deliberately does **not** do is say whether a feature discriminates
anything. It re-derives the numbers; reading them is a judgement, and a
verification that returned a verdict on the strength of a contingency table
would be exactly the "confident sentence in the machine's field" the negative
control caught on 2026-09-02.
"""
from __future__ import annotations

import hashlib
import json

from pydantic import BaseModel, ConfigDict, Field

from ..catalogue import Catalogue
from ..errors import WrongNodeType
from ..graph import Graph
from ..measure import (
    DEFAULT_BASE_EDITION,
    DEFAULT_MIN_CHARS,
    FeatureMeasurement,
    measure_feature,
)
from ..schemas import (
    AssuranceLevel,
    NodeType,
    VerificationMethod,
    VerificationResult,
)

NAME = "measure_claim"
DESCRIPTION = (
    "Count a stated feature across catalogued works and record the numbers "
    "against a claim, so they can be re-derived later instead of trusted. The "
    "first call records a baseline; a later call re-counts and reports whether "
    "the numbers still reproduce. Reports counts only — it does not judge "
    "whether a feature discriminates anything."
)

MEASURABLE = (NodeType.CLAIM, NodeType.CONJECTURE)


class MeasureClaimInput(BaseModel):
    model_config = ConfigDict(extra="forbid")

    claim_or_conjecture_id: str = Field(min_length=1)
    feature: str = Field(min_length=1, description="exact character sequence to count")
    base_edition: str = DEFAULT_BASE_EDITION
    min_chars: int = Field(default=DEFAULT_MIN_CHARS, ge=0)


def fingerprint(m: FeatureMeasurement) -> str:
    """A stable hash of every number in a measurement.

    `sort_keys` and a fixed separator so the digest depends on the values and
    not on dict ordering — the whole point is that two runs which measured the
    same thing produce the same string.
    """
    canonical = json.dumps(m.as_json(), sort_keys=True, ensure_ascii=False,
                           separators=(",", ":"))
    return "sha256:" + hashlib.sha256(canonical.encode("utf-8")).hexdigest()


def _summary(m: FeatureMeasurement) -> str:
    parts = []
    for label, s in m.by_label().items():
        skipped = f", {s.works_skipped_short} too short" if s.works_skipped_short else ""
        parts.append(f"{label} {s.works_attesting}/{s.works_measured}{skipped}")
    return "; ".join(parts) or "no labelled works"


def measure_claim(
    graph: Graph, corpus, args: MeasureClaimInput, *, catalogue: Catalogue,
    authored_by: str, model_call_id: int | None = None,
) -> dict:
    node = graph.get_node(args.claim_or_conjecture_id)
    if node.type not in MEASURABLE:
        raise WrongNodeType(
            f"{args.claim_or_conjecture_id} is a {node.type}; only a claim or "
            "conjecture asserts something a count could bear on. Measuring a "
            "passage or a witness would record a number about the corpus with "
            "nothing staked on it"
        )

    labels = dict(catalogue.entries)
    catalogue.check_against(corpus.works())
    m = measure_feature(
        corpus, args.feature, labels=labels, works=catalogue.works(),
        base_edition=args.base_edition, min_chars=args.min_chars,
    )
    digest = fingerprint(m)
    summary = _summary(m)

    prior = _prior_measurement(graph, args.claim_or_conjecture_id, args.feature)

    if prior is None:
        result = VerificationResult.INDETERMINATE
        note = (
            "baseline recorded; there is nothing yet to compare it against. A "
            "first measurement says only what the numbers are, which is what "
            "the claim's author could already have said"
        )
    elif prior == digest:
        result = VerificationResult.PASS
        note = "the numbers reproduce exactly against the recorded baseline"
    else:
        result = VerificationResult.FAIL
        note = (
            f"these numbers no longer match the recorded baseline ({prior[:19]}…). "
            "The corpus, the catalogue, the character floor, or the counting "
            "changed; the claim rests on figures that no longer reproduce"
        )

    verification_id = graph.verify(
        args.claim_or_conjecture_id,
        method=VerificationMethod.CORPUS_MEASUREMENT,
        result=result,
        # Grants no rung, for the reason PROSPECTIVE_TEST grants none: the
        # ladder grades how well a node's *citations* stand up, and a feature
        # count says something else entirely. A claim whose numbers reproduce
        # is not thereby better cited.
        assurance_level=AssuranceLevel.A0_UNCHECKED,
        detail=(
            f"counted {args.feature!r} over {len(m.works)} catalogued work(s) "
            f"in edition {args.base_edition!r}, floor {args.min_chars} chars — "
            f"{summary}. {note}."
        ),
        limitations=(
            "Counts, not a verdict. Works attesting a feature is a tally over "
            "works of very unequal length, and says nothing on its own about "
            "whether the feature distinguishes one group from another — a "
            "question no recount can answer. Rates come from one base edition; "
            "agreement among a work's other editions is transmissional, not "
            "independent, support."
        ),
        excerpt_hash=digest,
        authored_by=authored_by,
        model_call_id=model_call_id,
    )
    return {
        "verification_id": verification_id,
        "result": result,
        "fingerprint": digest,
        "summary": summary,
        "measurement": m.as_json(),
    }


def _prior_measurement(graph: Graph, node_id: str, feature: str) -> str | None:
    """The fingerprint of the most recent measurement of *this feature* on this
    node.

    Filtered by feature, because a node may carry measurements of several, and
    comparing a count of one phrase against the baseline of another would fail
    every time while looking like a finding.
    """
    latest = None
    for v in graph.verifications(node_id):
        p = v.payload
        if p.get("method") != VerificationMethod.CORPUS_MEASUREMENT:
            continue
        if f"counted {feature!r} " not in (p.get("detail") or ""):
            continue
        if p.get("excerpt_hash"):
            latest = p["excerpt_hash"]
    return latest
