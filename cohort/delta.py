"""Burrows's Delta — exploratory distances, never shown without their null.

The field-standard measure for authorship attribution, implemented here for one
reason: the alternative was hand-picked features, and hand-picked features
cannot be defended by non-specialists. The top *n* most frequent character
bigrams are chosen by the corpus, so there is no selection to argue about.

**Delta is exploratory and this module says so in its types.** It produces a
distance, and a distance sorts, and a sorted list looks like a verdict. So a
`Profile` cannot be constructed without a `NullBand`: how far the benchmark's
own members sit from each other, computed leave-one-out. Every distance is
therefore rendered against the spread of distances among works nobody disputes.

That is not decoration. Twice on 2026-09-06 an apparent separation between the
disputed and control groups turned out to be an artifact — once from scoring a
group against a range it defined, once from comparing against 16 reference
works where the calibration used 15, which widened the band and made the test
easier. Both would have been caught immediately by a null shown alongside. So
the null is not an argument the caller can forget to make.

What this cannot do, stated once here because it belongs on every screen that
shows a result: character n-grams over this corpus track **subject matter**
heavily. A cosmological text lands near other cosmological texts whoever
translated it. Neighbourhoods are evidence about what a text resembles, not
about who wrote it, and the distinction is the reader's to keep.
"""
from __future__ import annotations

import collections
import statistics as st
from dataclasses import dataclass

#: Character bigrams rather than single characters or words: single characters
#: are too coarse to carry style and there is no reliable word segmentation for
#: this material without a dependency this project does not take.
DEFAULT_NGRAM = 2

#: Enough features for a stable distance, few enough that the rarest are still
#: common in every work. 300 is conventional for Delta and is not tuned here —
#: tuning it per study is a way of choosing an answer.
DEFAULT_FEATURES = 300

#: Below this a frequency profile is noise. Same floor as `measure.py`, and the
#: same reasoning: a rate from 1,800 characters is not a rate.
DEFAULT_MIN_CHARS = 5_000


@dataclass(frozen=True)
class NullBand:
    """How far the benchmark's own members are from each other.

    Leave-one-out: each benchmark work against the others, never against a set
    containing itself. A band computed with the work included is a band the
    work helped define, and everything falls inside it.
    """

    label: str
    n: int
    minimum: float
    median: float
    maximum: float

    def contains(self, d: float) -> bool:
        return d <= self.maximum

    def as_json(self) -> dict:
        return {"label": self.label, "n": self.n, "min": round(self.minimum, 4),
                "median": round(self.median, 4), "max": round(self.maximum, 4)}


@dataclass(frozen=True)
class Neighbour:
    work: str
    delta: float
    label: str | None

    def as_json(self) -> dict:
        return {"work": self.work, "delta": round(self.delta, 4), "label": self.label}


@dataclass(frozen=True)
class Profile:
    """One work's position, and the calibration needed to read it.

    `null` is required, not optional. A distance without the spread of
    undisputed distances beside it is a number that will be over-read, and this
    type exists to make that impossible rather than discouraged.
    """

    work: str
    label: str | None
    mean_delta_to_benchmark: float
    null: NullBand
    neighbours: tuple[Neighbour, ...]

    @property
    def inside_null(self) -> bool:
        """Whether this work is as close to the benchmark as the benchmark's
        own members are to each other. `True` means *not distinguishable* —
        which is a finding, and the commonest one."""
        return self.null.contains(self.mean_delta_to_benchmark)

    def as_json(self) -> dict:
        return {
            "work": self.work, "label": self.label,
            "mean_delta_to_benchmark": round(self.mean_delta_to_benchmark, 4),
            "inside_null": self.inside_null,
            "null": self.null.as_json(),
            "neighbours": [n.as_json() for n in self.neighbours],
            "reading": (
                "as close to the benchmark as its own members are to each "
                "other — not distinguishable from it by this measure"
                if self.inside_null else
                "further from the benchmark than any of its own members are "
                "from the rest, on this feature set"
            ),
        }


def _ngrams(text: str, n: int) -> collections.Counter:
    return collections.Counter(text[i:i + n] for i in range(len(text) - n + 1))


@dataclass(frozen=True)
class DeltaSpace:
    """A z-scored frequency space over a fixed feature set.

    Built once for a corpus and reused: z-scores depend on which works are in
    the space, so two profiles computed in different spaces are not comparable
    and this type is what keeps them together.
    """

    features: tuple[str, ...]
    labels: dict[str, str | None]
    _z: dict[str, tuple[float, ...]]
    min_chars: int
    skipped: tuple[str, ...]

    def works(self) -> list[str]:
        return sorted(self._z)

    def distance(self, a: str, b: str) -> float:
        za, zb = self._z[a], self._z[b]
        return sum(abs(x - y) for x, y in zip(za, zb)) / len(za)

    def mean_distance(self, work: str, group: list[str]) -> float:
        others = [g for g in group if g != work and g in self._z]
        if not others:
            raise ValueError(
                f"no reference works to measure {work} against — a distance to "
                "an empty group is not a small distance, it is no measurement"
            )
        return sum(self.distance(work, g) for g in others) / len(others)

    def null_band(self, group: list[str], *, label: str) -> NullBand:
        members = [g for g in group if g in self._z]
        if len(members) < 3:
            raise ValueError(
                f"{label} has {len(members)} measurable work(s); a null band "
                "needs at least 3, or the spread it reports is an accident of "
                "which two works happen to be in it"
            )
        spread = sorted(self.mean_distance(w, members) for w in members)
        return NullBand(label=label, n=len(members), minimum=spread[0],
                        median=st.median(spread), maximum=spread[-1])

    def profile(
        self, work: str, *, benchmark: list[str], null: NullBand, top: int = 8,
    ) -> Profile:
        near = sorted(
            (Neighbour(work=o, delta=self.distance(work, o), label=self.labels.get(o))
             for o in self._z if o != work),
            key=lambda n: n.delta,
        )[:top]
        return Profile(
            work=work, label=self.labels.get(work),
            mean_delta_to_benchmark=self.mean_distance(work, benchmark),
            null=null, neighbours=tuple(near),
        )


def build_space(
    texts: dict[str, str], *, labels: dict[str, str | None] | None = None,
    features: int = DEFAULT_FEATURES, ngram: int = DEFAULT_NGRAM,
    min_chars: int = DEFAULT_MIN_CHARS,
) -> DeltaSpace:
    """Z-scored frequencies of the most frequent n-grams *in this corpus*.

    Features come from the corpus, not from the caller. That is the whole
    argument for using Delta here: a hand-picked feature list has to be
    defended by whoever picked it, and we are not the people who could defend
    one for sixth-century translation Chinese.
    """
    kept = {w: "".join(c for c in t if not c.isspace()) for w, t in texts.items()}
    skipped = tuple(sorted(w for w, t in kept.items() if len(t) < min_chars))
    kept = {w: t for w, t in kept.items() if len(t) >= min_chars}
    if len(kept) < 3:
        raise ValueError(
            f"only {len(kept)} work(s) are at least {min_chars} characters; "
            "a z-score over fewer is not a normalisation"
        )

    total: collections.Counter = collections.Counter()
    for t in kept.values():
        total.update(_ngrams(t, ngram))
    feats = tuple(g for g, _ in total.most_common(features))

    freq = {}
    for w, t in kept.items():
        c = _ngrams(t, ngram)
        n = max(1, len(t) - ngram + 1)
        freq[w] = [c[g] / n for g in feats]

    z: dict[str, tuple[float, ...]] = {}
    mu = [st.mean(freq[w][i] for w in kept) for i in range(len(feats))]
    #: population sd, and a floor: a feature with no variance would divide by
    #: zero, and it carries no information either way.
    sd = [st.pstdev(freq[w][i] for w in kept) or 1e-12 for i in range(len(feats))]
    for w in kept:
        z[w] = tuple((freq[w][i] - mu[i]) / sd[i] for i in range(len(feats)))

    return DeltaSpace(
        features=feats, labels=dict(labels or {}), _z=z,
        min_chars=min_chars, skipped=skipped,
    )
