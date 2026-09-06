"""semantic_neighbors: which passages elsewhere in the corpus read like this one.

Backed by precomputed window embeddings from a frozen Buddhist-Chinese encoder
(`cohort/embeddings.py`). The encoder does not recognise translators (it is at
the largest-class baseline for that), so the tally it returns is never a vote
on attribution. What it is good at is finding the same content in other
words -- parallels, quotations, a commentary on the text under study -- which
is exactly the kind of dependency that makes string counts lie. Read-only.
"""

from __future__ import annotations

from typing import Any

from pydantic import BaseModel, ConfigDict, Field

from cohort.attribution import AttributionIndex
from cohort.embeddings import EmbeddingIndex
from cohort.errors import UnitNotInCorpus

NAME = "semantic_neighbors"
DESCRIPTION = (
    "For one unit of Radich's corpus, the passages in OTHER works whose meaning is "
    "closest to each of its 400-character windows (frozen Buddhist-Chinese encoder), "
    "with a short excerpt of both sides, plus a tally of which unit the nearest passage "
    "belongs to across all of the unit's windows. Use it to find texts that quote, "
    "parallel or comment on the target -- dependencies that make string evidence "
    "non-independent -- then check them with align_passages. The encoder does not "
    "recognise translators; do not read the tally as an attribution."
)
SNIPPET = 40


class SemanticNeighborsInput(BaseModel):
    model_config = ConfigDict(extra="forbid")
    uid: str = Field(min_length=1)
    top_k: int = Field(default=3, ge=1, le=10)
    max_windows: int = Field(default=6, ge=1, le=30, description="windows of the target to show")
    labelled_only: bool = Field(default=False, description="ignore grey neighbours")


def _snippet(index: AttributionIndex, uid: str, start: int) -> str:
    text = index.base_text(index.root, uid) or ""
    return text[start : start + SNIPPET].replace("\n", "")


def semantic_neighbors(
    embeddings: EmbeddingIndex, index: AttributionIndex, args: SemanticNeighborsInput,
) -> dict[str, Any]:
    try:
        out = embeddings.neighbors(
            args.uid, top_k=args.top_k, max_windows=args.max_windows,
            labelled_only=args.labelled_only,
        )
    except KeyError as e:
        raise UnitNotInCorpus(e.args[0] if e.args else str(e)) from e
    for w in out["shown"]:
        w["excerpt"] = _snippet(index, args.uid, w["start"])
        for n in w["neighbors"]:
            n["excerpt"] = _snippet(index, n["uid"], n["start"])
    out["encoder"] = embeddings.describe()
    out["reading"] = (
        "Cosine is similarity of meaning, not of wording; a neighbour that shares the "
        "target's wording is a candidate quotation -- confirm with align_passages. The "
        "tallies say what the unit is most like in content, not who translated it."
    )
    return out
