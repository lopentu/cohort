"""Is a group unusually close to this work, compared with the whole canon?

This answers a different question from `delta.NullBand`, and the difference is
the reason this module exists rather than another method on `DeltaSpace`.

A null band asks **"is this work inside the benchmark's own spread?"** Its
threshold is the distance of the benchmark's most eccentric member, so almost
nothing fails it: on the Paramārtha study every disputed work and every
interloper alike came back "not distinguishable", which is not an answer to
anything. The band is a good check on *over*-reading a small distance and a
useless one for finding an association.

This asks **"of the works nearest this one in the entire canon, are members of
the group more common than chance?"** Radich's brief is that question in his own
words — can we find features that associate a disputed work with P *against
texts by other translators in the canon*, or associate it with *some other
reference point in the canon* — and the canon is where the statistical power
is. Sixteen benchmark works among 1,464 profiled is 1.1%; a work whose
twenty-five nearest neighbours are 20% benchmark members is at odds of about
one in a quarter of a million against, and that is a number with an `n` behind
it, unlike a rank test over four disputed works and three controls.

**Nothing here is read against chance alone.** The hypergeometric p-value says
the enrichment is not an accident; it does not say the association is strong,
because "strong" only means anything relative to what a *known* member of the
group achieves. So every measure is calibrated leave-one-out over the group
itself, and the calibration reports the number that matters most: how many
known members the method **cannot see**. On the Paramārtha study that is six of
sixteen, so a work scoring zero here has not been shown to be an outsider — it
has landed in the same place as more than a third of the group's own
undisputed members. A method that reported those as negatives would be
manufacturing exclusions.

**Radich's question has two branches and both are answered here.** The first is
whether the group is over-represented among a work's neighbours. The second is
"features that might associate one text or more with *some other reference
point(s) in the canon*, suggesting an alternate ascription" — and a measure that
answered only the first would report three of four disputed works as "no
association" and stop, which reads as the method failing rather than as the
method saying something.

So a work is also characterised **independently of any group**: how near its
nearest neighbour is, how far the second is behind it, and how tightly its
neighbourhood holds together — each as a percentile of the canon's own
distribution of the same quantity, because none of the three raw numbers means
anything alone. A work whose nearest neighbour stands 0.105 clear of the next,
at the 88th percentile of the canon, has a *dominant attractor*: one reference
point worth checking, which is exactly what the second branch asks for. A work
at the 27th percentile has a diffuse neighbourhood and no such lead, and saying
so is also an answer.

**Neighbourhood structure is not a group signature and must never be shown as
one.** Measured over the sixteen undisputed P-23 works, nearest-neighbour
distance runs from the 4th percentile to the 96th and cohesion from the 37th to
the 98th. It says where a work sits in the canon, not who wrote it, and the two
readings are kept in separate sentences for that reason.

**The genre control is in the neighbour list, not beside it.** Character n-grams
track subject matter (see `attribution.CAVEAT`), so a work surrounded by
Abhidharma will be near any Abhidharma-heavy group whoever translated it. The
check that survives that is *within* the neighbourhood: the nearest group member
against the nearest work outside the group. If the same material by other hands
is further away than the group's own copy of it, the neighbourhood is not
explaining the result by itself.
"""
from __future__ import annotations

import statistics as st
from dataclasses import dataclass
from math import comb

#: Neighbourhood sizes reported together, because no single one is right and
#: choosing one after seeing the numbers is the error the whole project is
#: against. A result that holds at 25 and dies at 100 is a result about 25.
TOPK = (25, 50, 100)

#: Below this the calibration is an accident of which works happen to be in the
#: group, the same floor `null_band` applies for the same reason.
MIN_GROUP = 3

#: How many neighbours the cohesion statistic averages over. Small, because it
#: is asking whether a work sits *inside a cluster*, and a wide window would
#: measure the corpus rather than the neighbourhood.
COHESION_K = 10

#: Works sampled to estimate the canon's own distribution of these quantities.
#: The full matrix is 1,464 x 1,463 distances in pure Python; a sample of this
#: size puts every percentile below within a point or two, which is far finer
#: than the readings distinguish.
BASELINE_SAMPLE = 200

#: Fixed, so a baseline is reproducible. The sample is random and the
#: fingerprint of a recorded association covers the percentiles it produced —
#: an unseeded sample would make every re-measurement disagree with its own
#: baseline and report a corpus that had not changed as one that had.
BASELINE_SEED = 20260906

#: A nearest neighbour standing this far up the canon's gap distribution is
#: reported as *dominant*: one reference point clearly ahead of the rest, which
#: is what an alternate-ascription lead looks like. A threshold, not a finding —
#: it decides what gets a sentence, never what the sentence concludes.
DOMINANT_GAP_PERCENTILE = 80.0

#: Below this the neighbourhood is called diffuse — the work's nearest
#: neighbours are barely distinguishable from each other, so no one of them is
#: a lead.
DIFFUSE_GAP_PERCENTILE = 33.0


def ordinal(n: float) -> str:
    """`63rd`, not `63th`. A reading that a researcher will paste into a paper
    should not have to be corrected by hand first."""
    i = int(round(n))
    if 11 <= i % 100 <= 13:
        return f"{i}th"
    return f"{i}{ {1: 'st', 2: 'nd', 3: 'rd'}.get(i % 10, 'th') }"


def hypergeometric_at_least(hits: int, k: int, marked: int, total: int) -> float:
    """P(at least `hits` of `marked` land in a `k`-sized draw from `total`).

    Exact rather than a normal approximation: `k` is small, `marked` is smaller,
    and the interesting p-values are in the tail where the approximation is
    worst.
    """
    if k <= 0 or marked <= 0 or total <= 0 or k > total:
        return 1.0
    hi = min(k, marked)
    if hits > hi:
        return 0.0
    denominator = comb(total, k)
    return sum(
        comb(marked, i) * comb(total - marked, k - i) / denominator
        for i in range(max(hits, 0), hi + 1)
    )


@dataclass(frozen=True)
class RankedNeighbour:
    work: str
    label: str | None
    delta: float
    rank: int

    @property
    def in_group(self) -> bool:
        return self.label is not None

    def as_json(self) -> dict:
        return {"work": self.work, "label": self.label,
                "delta": round(self.delta, 4), "rank": self.rank}


@dataclass(frozen=True)
class Calibration:
    """What known members of the group score at one neighbourhood size, each
    measured with itself held out.

    `blind` is the field to read first. It counts members the method cannot
    recover *even though their membership is not in doubt*, which is the
    sensitivity of the measure stated as a number rather than assumed to be
    total. A zero score means nothing until you know how many undisputed
    members also score zero.
    """

    k: int
    n: int
    blind: int
    minimum: float
    median: float
    maximum: float

    def as_json(self) -> dict:
        return {"k": self.k, "n": self.n, "blind": self.blind,
                "min": round(self.minimum, 4), "median": round(self.median, 4),
                "max": round(self.maximum, 4)}


@dataclass(frozen=True)
class Enrichment:
    k: int
    hits: int
    share: float
    p_value: float
    calibration: Calibration

    @property
    def within_calibration(self) -> bool:
        """Whether this work scores at least the *median* known member.

        Compared against the calibration rather than against chance, because
        the two say different things: a p-value says the overlap is not an
        accident, and this says the association is as strong as membership
        normally looks.

        The median rather than the minimum, deliberately. The minimum on this
        study is zero — six of sixteen undisputed members are invisible to the
        measure — so a floor set there would be cleared by every work in the
        canon and would mean nothing. Half of a group's own members failing
        this is the expected shape, not a fault in the threshold.
        """
        return self.share >= self.calibration.median

    def as_json(self) -> dict:
        return {
            "k": self.k, "hits": self.hits, "share": round(self.share, 4),
            "p_value": self.p_value,
            "within_calibration": self.within_calibration,
            "calibration": self.calibration.as_json(),
        }


@dataclass(frozen=True)
class CanonBaseline:
    """The canon's own distribution of the three neighbourhood quantities.

    Sampled and cached, because a percentile is the only form in which any of
    them is readable: a nearest-neighbour distance of 0.45 is neither near nor
    far until you know what the rest of the corpus looks like.
    """

    n: int
    nearest: tuple[float, ...]
    gap: tuple[float, ...]
    cohesion: tuple[float, ...]

    @staticmethod
    def _pct(sorted_values: tuple[float, ...], x: float) -> float:
        if not sorted_values:
            return 0.0
        return round(
            100.0 * sum(1 for v in sorted_values if v < x) / len(sorted_values), 1
        )

    def as_json(self) -> dict:
        return {
            "n": self.n,
            "nearest_median": round(st.median(self.nearest), 4),
            "gap_median": round(st.median(self.gap), 4),
            "cohesion_median": round(st.median(self.cohesion), 4),
        }


@dataclass(frozen=True)
class Neighbourhood:
    """Where a work sits in the canon, independent of any group.

    This answers the second branch of the question — what *is* this work near —
    and it is deliberately group-blind. Reported as percentiles of the canon
    because the raw numbers are unreadable, and kept in a separate sentence from
    the group reading because neighbourhood structure is not a group signature:
    across sixteen undisputed P-23 works these percentiles span almost the whole
    range.
    """

    nearest: RankedNeighbour | None
    nearest_delta: float
    gap_to_second: float
    cohesion: float
    nearest_percentile: float
    gap_percentile: float
    cohesion_percentile: float

    @property
    def dominant(self) -> bool:
        """One reference point clearly ahead of the rest — the shape of an
        alternate-ascription lead."""
        return self.gap_percentile >= DOMINANT_GAP_PERCENTILE

    @property
    def diffuse(self) -> bool:
        """Nearest neighbours barely distinguishable from one another, so no
        single one of them is a lead. A result, not a gap."""
        return self.gap_percentile <= DIFFUSE_GAP_PERCENTILE

    @property
    def reading(self) -> str:
        where = self.nearest.work if self.nearest else "nothing"
        if self.dominant:
            return (
                f"Its nearest work in the canon is {where} at Δ "
                f"{self.nearest_delta:.4f}, standing {self.gap_to_second:.4f} "
                f"clear of the next — a larger separation than "
                f"{self.gap_percentile:.0f}% of works in this corpus have. One "
                "reference point ahead of the rest is what an alternate "
                "ascription would look like, and is worth checking directly."
            )
        if self.diffuse:
            return (
                f"Its nearest work is {where} at Δ {self.nearest_delta:.4f}, but "
                f"the next is only {self.gap_to_second:.4f} behind — closer "
                f"together than {100 - self.gap_percentile:.0f}% of the corpus. "
                "No single work stands out as a reference point, so this "
                "neighbourhood offers no lead to follow."
            )
        return (
            f"Its nearest work is {where} at Δ {self.nearest_delta:.4f}, "
            f"{self.gap_to_second:.4f} ahead of the next — an ordinary "
            f"separation ({ordinal(self.gap_percentile)} percentile). Nothing about "
            "where this work sits is unusual by these measures."
        )

    def as_json(self) -> dict:
        return {
            "nearest": self.nearest.as_json() if self.nearest else None,
            "nearest_delta": round(self.nearest_delta, 4),
            "gap_to_second": round(self.gap_to_second, 4),
            "cohesion": round(self.cohesion, 4),
            "nearest_percentile": self.nearest_percentile,
            "gap_percentile": self.gap_percentile,
            "cohesion_percentile": self.cohesion_percentile,
            "dominant": self.dominant,
            "diffuse": self.diffuse,
            "reading": self.reading,
        }


@dataclass(frozen=True)
class Association:
    work: str
    group_label: str
    group_size: int
    corpus_size: int
    expected_share: float
    first_rank: int | None
    nearest_in_group: RankedNeighbour | None
    nearest_outside_group: RankedNeighbour | None
    enrichment: tuple[Enrichment, ...]
    neighbours: tuple[RankedNeighbour, ...]
    neighbourhood: Neighbourhood

    @property
    def headline(self) -> Enrichment:
        """The smallest neighbourhood, which is the tightest claim. Reported
        first and never chosen: `TOPK` is fixed in this module, so nobody picks
        the k that flatters a work after seeing all three."""
        return self.enrichment[0]

    @property
    def verdict(self) -> str:
        """One word for what this work's row should say it is.

        Every work gets one. Three of the four disputed works on the Paramārtha
        study show no group enrichment, and rendering all three as the same
        blank made the method look unable to answer rather than answering
        "not here, and here is where it does sit" — which is the second branch
        of the question and a determinate result.
        """
        if self.headline.hits and self.headline.within_calibration:
            return "associates"
        if self.headline.hits:
            return "weak"
        if self.neighbourhood.dominant:
            return "alternate"
        return "unplaced"

    @property
    def group_reading(self) -> str:
        e = self.headline
        cal = e.calibration
        if e.hits == 0:
            return (
                f"no {self.group_label} work is among the {e.k} nearest — but "
                f"{cal.blind} of {cal.n} undisputed {self.group_label} works "
                "score zero here too, so this does not separate a work outside "
                "the group from one the method cannot see."
            )
        if e.within_calibration:
            nearer = (
                self.nearest_outside_group is not None
                and self.nearest_in_group is not None
                and self.nearest_in_group.delta < self.nearest_outside_group.delta
            )
            return (
                f"{e.hits} of the {e.k} nearest works in the canon are "
                f"{self.group_label} ({e.share:.1%} against {self.expected_share:.1%} "
                f"by chance, p={e.p_value:.1e}) — at or above the "
                f"{cal.median:.1%} a known {self.group_label} work reaches, "
                "measured with itself held out."
                + (
                    f" Its single nearest work in the canon is a {self.group_label} "
                    "work, closer than anything outside the group, so the "
                    "neighbourhood's subject matter does not account for it "
                    "on its own."
                    if nearer else
                    " Works outside the group are nearer still, so the "
                    "neighbourhood's subject matter may account for part of this."
                )
            )
        return (
            f"{e.hits} of the {e.k} nearest works are {self.group_label} "
            f"({e.share:.1%} against {self.expected_share:.1%} by chance, "
            f"p={e.p_value:.1e}) — an enrichment, but below the {cal.median:.1%} "
            f"a known {self.group_label} work reaches."
        )

    @property
    def reading(self) -> str:
        """Both branches, in that order and always both.

        The group sentence answers "does this belong with P"; the neighbourhood
        sentence answers "then what is it near". A reader given only the first
        sees three quarters of this study report nothing.
        """
        return f"{self.group_reading} {self.neighbourhood.reading}"

    def as_json(self) -> dict:
        return {
            "work": self.work,
            "group_label": self.group_label,
            "verdict": self.verdict,
            "group_reading": self.group_reading,
            "neighbourhood": self.neighbourhood.as_json(),
            "group_size": self.group_size,
            "corpus_size": self.corpus_size,
            "expected_share": round(self.expected_share, 4),
            "first_rank": self.first_rank,
            "nearest_in_group": (
                self.nearest_in_group.as_json() if self.nearest_in_group else None
            ),
            "nearest_outside_group": (
                self.nearest_outside_group.as_json()
                if self.nearest_outside_group else None
            ),
            "enrichment": [e.as_json() for e in self.enrichment],
            "neighbours": [n.as_json() for n in self.neighbours],
            "reading": self.reading,
        }


def _ranked(space, work: str, marked: set[str]) -> list[RankedNeighbour]:
    """Every other profiled work, nearest first, with its rank and whether it
    is one of the marked (group) works."""
    ordered = sorted(
        ((space.distance(work, o), o) for o in space.works() if o != work),
    )
    return [
        RankedNeighbour(work=o, label=(space.labels.get(o) if o in marked else None),
                        delta=d, rank=i)
        for i, (d, o) in enumerate(ordered, 1)
    ]


def _shares(ranked: list[RankedNeighbour], marked: set[str]) -> dict[int, int]:
    return {
        k: sum(1 for n in ranked[:k] if n.work in marked) for k in TOPK
    }


def calibrate(space, group: list[str], *, label: str) -> dict[int, Calibration]:
    """What known members of `group` score, each measured with itself removed.

    Leave-one-out for the same reason `null_band` uses it: a member scored
    against a set containing itself is scored against a set it helped define,
    and would recover its own group trivially.

    This is the expensive call — one full ranking of the corpus per member — so
    a caller measuring several works should compute it once and pass it in.
    """
    members = [g for g in group if g in space.works()]
    if len(members) < MIN_GROUP:
        raise ValueError(
            f"{label} has {len(members)} profiled work(s); calibrating an "
            f"association needs at least {MIN_GROUP}, or what it reports as "
            "typical is an accident of which one or two are in it"
        )
    per_k: dict[int, list[float]] = {k: [] for k in TOPK}
    for member in members:
        marked = set(members) - {member}
        hits = _shares(_ranked(space, member, marked), marked)
        for k in TOPK:
            per_k[k].append(hits[k] / k)
    return {
        k: Calibration(
            k=k, n=len(members), blind=sum(1 for s in per_k[k] if s == 0.0),
            minimum=min(per_k[k]), median=st.median(per_k[k]), maximum=max(per_k[k]),
        )
        for k in TOPK
    }


def _neighbourhood(
    space, ranked: list[RankedNeighbour], baseline: CanonBaseline,
) -> Neighbourhood:
    nearest_d = ranked[0].delta if ranked else 0.0
    second_d = ranked[1].delta if len(ranked) > 1 else nearest_d
    near = [n.work for n in ranked[:COHESION_K]]
    pairs = [
        space.distance(a, b)
        for i, a in enumerate(near) for b in near[i + 1:]
    ]
    cohesion = st.mean(pairs) if pairs else 0.0
    return Neighbourhood(
        nearest=ranked[0] if ranked else None,
        nearest_delta=nearest_d,
        gap_to_second=second_d - nearest_d,
        cohesion=cohesion,
        nearest_percentile=baseline._pct(baseline.nearest, nearest_d),
        gap_percentile=baseline._pct(baseline.gap, second_d - nearest_d),
        cohesion_percentile=baseline._pct(baseline.cohesion, cohesion),
    )


def canon_baseline(space, *, sample: int = BASELINE_SAMPLE) -> CanonBaseline:
    """The corpus's own distribution of nearest-neighbour distance, gap and
    cohesion — the scale every neighbourhood reading is expressed on.

    Sampled with a fixed seed. The sample must be reproducible because a
    recorded association is fingerprinted, and percentiles drawn from a fresh
    random sample each time would make every re-measurement disagree with its
    own baseline and report an unchanged corpus as a changed one.
    """
    import random

    works = space.works()
    rng = random.Random(BASELINE_SEED)
    chosen = works if len(works) <= sample else rng.sample(works, sample)

    nearest: list[float] = []
    gap: list[float] = []
    cohesion: list[float] = []
    for w in chosen:
        ordered = sorted((space.distance(w, o), o) for o in works if o != w)
        if not ordered:
            continue
        first = ordered[0][0]
        second = ordered[1][0] if len(ordered) > 1 else first
        near = [o for _, o in ordered[:COHESION_K]]
        pairs = [
            space.distance(a, b)
            for i, a in enumerate(near) for b in near[i + 1:]
        ]
        nearest.append(first)
        gap.append(second - first)
        cohesion.append(st.mean(pairs) if pairs else 0.0)
    return CanonBaseline(
        n=len(nearest), nearest=tuple(sorted(nearest)),
        gap=tuple(sorted(gap)), cohesion=tuple(sorted(cohesion)),
    )


def associate(
    space, work: str, *, group: list[str], label: str,
    calibration: dict[int, Calibration], baseline: CanonBaseline,
    top: int = 15,
) -> Association:
    """Where `work` sits relative to `group` in the whole corpus.

    `work` is excluded from the marked set if it is in `group`, so a member can
    be scored against its own group without recovering itself.
    """
    members = [g for g in group if g in space.works()]
    marked = set(members) - {work}
    ranked = _ranked(space, work, marked)
    hits = _shares(ranked, marked)
    total = len(ranked)

    enrichment = tuple(
        Enrichment(
            k=k, hits=hits[k], share=hits[k] / k,
            p_value=hypergeometric_at_least(hits[k], k, len(marked), total),
            calibration=calibration[k],
        )
        for k in TOPK
    )
    in_group = next((n for n in ranked if n.work in marked), None)
    outside = next((n for n in ranked if n.work not in marked), None)
    return Association(
        work=work, group_label=label, group_size=len(marked), corpus_size=total,
        expected_share=len(marked) / total if total else 0.0,
        first_rank=in_group.rank if in_group else None,
        nearest_in_group=in_group, nearest_outside_group=outside,
        enrichment=enrichment, neighbours=tuple(ranked[:top]),
        neighbourhood=_neighbourhood(space, ranked, baseline),
    )
