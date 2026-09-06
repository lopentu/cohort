"""Shared pieces for the experiment scripts: the kept units, the two classifiers,
and the leave-one-group-out evaluation with the pooled-minus-held-out trick.

The evaluation is the place the 82%-versus-52% mistake lived, so it is written
once here. `group_by="unit"` holds out one unit (the leaky protocol);
`group_by="work"` holds out every unit of the same Taishō work (the honest one).
"""

from __future__ import annotations

import collections
import math
from collections.abc import Callable, Iterable

from cohort.attribution import AttributionIndex, work_of

Counts = collections.Counter
Classifier = Callable[[dict[str, Counts], Counts, int], str]


def naive_bayes(profiles: dict[str, Counts], counts: Counts, vocab: int) -> str:
    """The class whose string distribution makes these counts most likely;
    add-half smoothing over the feature vocabulary. `vocab` is a parameter, not
    a module global: a global left at the wrong value by a previous loop once
    rescored a whole per-class table with the wrong denominator."""
    best, top = "", -math.inf
    for label, prof in profiles.items():
        total = sum(prof.values()) + 0.5 * vocab
        score = sum(c * math.log((prof.get(g, 0) + 0.5) / total) for g, c in counts.items())
        if score > top:
            best, top = label, score
    return best


def nearest_centroid(profiles: dict[str, Counts], counts: Counts, vocab: int) -> str:
    """Cosine on square-rooted rates: a second, different model, so a result
    is about the data and not about naive Bayes."""

    def unit(d: Counts) -> dict[str, float]:
        total = sum(d.values()) or 1
        v = {k: math.sqrt(x / total) for k, x in d.items()}
        norm = math.sqrt(sum(x * x for x in v.values())) or 1
        return {k: x / norm for k, x in v.items()}

    q = unit(counts)
    best, top = "", -math.inf
    for label, prof in profiles.items():
        p = unit(prof)
        score = sum(w * p.get(g, 0) for g, w in q.items())
        if score > top:
            best, top = label, score
    return best


CLASSIFIERS: dict[str, Classifier] = {"nearest centroid": nearest_centroid, "naive Bayes": naive_bayes}


def evaluate(
    index: AttributionIndex, features: str, group_by: str, classify: Classifier,
) -> tuple[Counts, Counts]:
    """`(correct, total)` per class under leave-one-group-out.

    Class profiles are pooled once and the held-out group subtracted, which is
    the same answer as rebuilding every profile per unit without the quadratic
    cost. The check that matters -- that no contributor shares the target's
    work -- is asserted on the invariant, not on a recomputation of the sums.
    """
    ix = index._ix  # the experiments read the index's tables directly
    counts = ix.counts[features]
    vocab = len(ix.features[features])
    key = work_of if group_by == "work" else (lambda u: u)
    pooled: dict[str, Counts] = collections.defaultdict(Counts)
    groups: dict[tuple[str, str], list[str]] = collections.defaultdict(list)
    for uid, label in ix.unit_label.items():
        pooled[label].update(counts[uid])
        groups[(label, key(uid))].append(uid)
    correct, total = Counts(), Counts()
    for uid, label in ix.unit_label.items():
        held = groups[(label, key(uid))]
        rest = pooled[label].copy()
        for sib in held:
            rest.subtract(counts[sib])
        rest = +rest
        if not rest:
            continue  # nothing of this class left to recognise it by
        if group_by == "work":
            # Checked against a second source: the index's own membership table,
            # built when the index was. A check that reused this function's
            # grouping would agree with it by construction and could never fail.
            expected = set(ix.members.get(work_of(uid), [uid]))
            if set(held) != expected:
                msg = (f"leak: the held-out group for {uid} is {sorted(held)[:4]} but the index "
                       f"says its work holds {sorted(expected)[:4]}")
                raise RuntimeError(msg)
        profiles = dict(pooled)
        profiles[label] = rest
        total[label] += 1
        if classify(profiles, counts[uid], vocab) == label:
            correct[label] += 1
    return correct, total


def works_per_class(index: AttributionIndex) -> Counts:
    out: dict[str, set[str]] = collections.defaultdict(set)
    for uid, label in index._ix.unit_label.items():
        out[label].add(work_of(uid))
    return Counts({label: len(s) for label, s in out.items()})


def pct(c: int, n: int) -> str:
    return f"{c / n:.1%}" if n else "—"


def pct0(c: int, n: int) -> str:
    return f"{c / n:.0%}" if n else "—"


def sum_counts(c: Iterable[int]) -> int:
    return sum(c)
