"""verify_exact_span: re-fetch a passage's source and confirm its excerpt is
still exactly where it was last recorded.

This is a hash chain, not a bare substring check: `find_attestations.py`'s
own initial mechanical check ("the passage exists, the citation resolves")
is a one-time containment test at proposal time. This tool re-checks it
later, against a freshly-fetched source, and — once a passage has been
verified once — compares the excerpt's *location* against what was recorded
last time, not merely "found somewhere in the source." An excerpt that
recurs elsewhere in a witness could otherwise silently verify against the
wrong occurrence, which would make the check worse than useless: passing
review while proving nothing. The first verification for a passage
establishes the recorded baseline; every later one must match it or fail.
"""
from __future__ import annotations

import hashlib

from cohort.errors import WrongNodeType
from cohort.graph import Graph
from cohort.schemas import AssuranceLevel, VerificationMethod, VerificationResult
from cohort.sources.base import Source


def verify_exact_span(
    graph: Graph, source: Source, passage_id: str, *, authored_by: str,
    model_call_id: int | None = None,
) -> str:
    passage = graph.get_node(passage_id)
    if passage.type != "passage":
        raise WrongNodeType(f"{passage_id} is a {passage.type}, not a passage")

    source_ref = passage.payload.get("source_ref")
    excerpt = passage.payload.get("excerpt")
    if not source_ref or not excerpt:
        return graph.verify(
            passage_id, method=VerificationMethod.EXACT_SPAN,
            result=VerificationResult.INDETERMINATE,
            assurance_level=AssuranceLevel.A0_UNCHECKED,
            detail="passage has no source_ref or no excerpt recorded; nothing to re-check",
            authored_by=authored_by, model_call_id=model_call_id,
        )

    record = source.fetch(source_ref)
    source_hash = hashlib.sha256(record.text.encode("utf-8")).hexdigest()
    idx = record.text.find(excerpt)
    if idx == -1:
        return graph.verify(
            passage_id, method=VerificationMethod.EXACT_SPAN, result=VerificationResult.FAIL,
            assurance_level=AssuranceLevel.A0_UNCHECKED,
            detail="excerpt not found in the freshly-fetched source",
            source_hash=source_hash, authored_by=authored_by, model_call_id=model_call_id,
        )

    span_start, span_end = idx, idx + len(excerpt)
    excerpt_hash = hashlib.sha256(excerpt.encode("utf-8")).hexdigest()

    prior_spans = [
        n.payload for n in graph.verifications(passage_id)
        if n.payload["method"] == VerificationMethod.EXACT_SPAN
        and n.payload.get("span_start") is not None
    ]
    if prior_spans:
        last = prior_spans[-1]
        if (last["span_start"], last["span_end"], last["excerpt_hash"]) != (span_start, span_end, excerpt_hash):
            return graph.verify(
                passage_id, method=VerificationMethod.EXACT_SPAN, result=VerificationResult.FAIL,
                assurance_level=AssuranceLevel.A0_UNCHECKED,
                detail="excerpt moved or changed since the last recorded verification",
                source_hash=source_hash, excerpt_hash=excerpt_hash,
                span_start=span_start, span_end=span_end,
                authored_by=authored_by, model_call_id=model_call_id,
            )

    detail = (
        "excerpt located in the freshly-fetched source, matching its prior recorded location"
        if prior_spans else
        "excerpt located in the freshly-fetched source; recorded as the baseline for future re-verification"
    )
    return graph.verify(
        passage_id, method=VerificationMethod.EXACT_SPAN, result=VerificationResult.PASS,
        assurance_level=AssuranceLevel.A2_EXACT_SPAN_MATCHED, detail=detail,
        source_hash=source_hash, excerpt_hash=excerpt_hash,
        span_start=span_start, span_end=span_end,
        authored_by=authored_by, model_call_id=model_call_id,
    )
