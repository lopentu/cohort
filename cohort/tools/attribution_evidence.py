"""attribution_evidence: what the Evidence tab shows, as a tool an agent can call.

For one unit of Radich's corpus: which translator profile its 2-4 character
strings fit best, by how much, with the strings that pull each way and their
raw counts in each profile, after the unit's own Taishō work (and anything the
caller names) has been withheld from every profile. Read-only: it writes
nothing to the graph, so it needs no refusal path of its own; an agent turns
what it reads into a claim or conjecture through the writing tools, which are
where the rules bite.

The excerpt and the strip are left out on purpose: they are for a reader's
eyes, and a model given 2,400 painted characters spends its output narrating
them. The `withhold` argument is the sensitivity test -- name the unit you
suspect of quoting the target and see whether the leaning survives.
"""

from __future__ import annotations

from typing import Any

from pydantic import BaseModel, ConfigDict, Field

from cohort.attribution import FEATURE_SETS, AttributionIndex
from cohort.errors import UnitNotInCorpus

NAME = "attribution_evidence"
DESCRIPTION = (
    "For one unit of Radich's pre-450 corpus (an id such as T0603 or T0026-1-善法經): "
    "which translator's profile of 2-4 character strings it fits best, the margin, the "
    "strings pulling each way with their raw counts in each profile, and how much of "
    "each profile was left after the unit's own Taishō work was withheld. A leaning "
    "with its reasons, never an attribution; 'no evidence' when nothing in the "
    "vocabulary occurs. Pass `withhold` to remove further units (e.g. a commentary "
    "you suspect of quoting the target) and see whether the leaning survives. "
    "Use `features='generic'` for a vocabulary drawn from grey texts without labels."
)
TOP_ROWS = 8


class AttributionEvidenceInput(BaseModel):
    model_config = ConfigDict(extra="forbid")
    uid: str = Field(min_length=1, description="a unit id from Radich's catalogue")
    features: str = Field(default="radich", description=f"one of {list(FEATURE_SETS)}")
    withhold: list[str] = Field(default_factory=list, description="further profiled units to withhold")
    pair: list[str] | None = Field(
        default=None, min_length=2, max_length=2,
        description="two class labels to compare directly, e.g. ['ASg', 'pre-Dhr-other']",
    )


def attribution_evidence(index: AttributionIndex, args: AttributionEvidenceInput) -> dict[str, Any]:
    try:
        ev = index.evidence(
            args.uid, args.features, withhold=args.withhold, offset=0,
            pair=(args.pair[0], args.pair[1]) if args.pair else None,
        )
    except KeyError as e:
        # The index speaks in KeyError; the tool layer speaks in named rules
        # the refusal census can file.
        raise UnitNotInCorpus(e.args[0] if e.args else str(e)) from e
    keep = (
        "uid", "label", "work", "features", "n_features", "han_chars", "hits", "distinct",
        "withheld_units", "withheld_extra", "verdict", "first", "second", "margin", "gap",
        "pair", "no_profile", "provenance",
    )
    out: dict[str, Any] = {k: ev[k] for k in keep}
    out["ranking"] = ev["ranking"]
    out["profiles"] = ev["profiles"]
    out["for"] = ev["for"][:TOP_ROWS]
    out["against"] = ev["against"][:TOP_ROWS]
    out["reading"] = (
        "Weights are log-odds between the painted pair (A vs B); 'n' counts are raw "
        "occurrences in each profile and the honest size of the evidence. A margin near "
        "zero is nothing either way. Overlapping strings are not independent."
    )
    return out
