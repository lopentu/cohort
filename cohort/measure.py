"""Counting things in a corpus, in a way the graph can check.

Until now COHORT could record that an agent *said* a phrase occurs eighteen
times and had no way to disagree. For an attribution study that is fatal:
every claim in one is a count or a rate, so a derivation citing numbers nobody
can recompute is a story with figures in it.

Everything here is deterministic and pure — same corpus, same feature, same
numbers — which is what lets a measurement be re-run later and compared, the
way `verify_exact_span` re-fetches a passage rather than trusting the excerpt.

Three rules are built in rather than left to the caller, because each is a way
this kind of study goes wrong quietly:

**Never pool.** Counts are reported per work and never summed into a group
total. Radich's P-23 is 768,035 characters of which T1559 and T1595 are
453,420 — 59% of the benchmark in two texts, both Abhidharma commentaries.
A pooled rate over that group is mostly a measurement of those two works, and
a "translator's style" extracted from it may be the style of a genre.

**Count one edition, report the others.** A work survives in up to seventeen
editions differing by ~0.02%; counting all of them multiplies one observation
seventeen-fold. So the rate comes from a single base edition, and the other
editions are reported separately as `editions_attesting` — which answers a
different and useful question: is this feature stable across transmission, or
is it a variant reading that one edition happens to carry?

**Refuse to measure what is too short to measure.** Rates from a
1,843-character text are noise. A work under `min_chars` is reported
`sufficient=False` with no rate, rather than a rate of zero that reads like
evidence of absence. "This method cannot speak to that text" is a result.

Nothing here scores, ranks, or concludes. It reports counts and how many works
in each group carry the feature; whether that discriminates anything is a claim
somebody has to make and defend.
"""
from __future__ import annotations

from dataclasses import dataclass, field
from typing import Protocol

#: The Taishō text, present for 4,632 of 4,662 work directories and the base
#: text the others are collated against. Named rather than assumed so a caller
#: measuring against a different base has to say so.
DEFAULT_BASE_EDITION = "大"

#: Below this, a rate is noise rather than a small number. Not a law — the
#: right floor depends on how common the feature is — but a stated default
#: beats an implicit one, and the caller who changes it has to write it down.
DEFAULT_MIN_CHARS = 5_000


class _Corpus(Protocol):
    def works(self) -> list[str]: ...
    def editions(self, work: str) -> list[str]: ...
    def fetch(self, ref: str): ...


@dataclass(frozen=True)
class WorkMeasurement:
    """One work, one feature. `count` and `per_10k` come from the base edition
    only; `editions_attesting` is out of `editions_total` and is transmissional
    corroboration, not independent support."""

    work: str
    label: str | None
    base_edition: str | None
    chars: int
    count: int
    editions_total: int
    editions_attesting: int
    sufficient: bool
    note: str | None = None

    @property
    def per_10k(self) -> float | None:
        """Occurrences per 10,000 characters, or None when the work is too
        short to carry a rate. None rather than 0.0 so it cannot be averaged
        into a group figure by accident."""
        if not self.sufficient or not self.chars:
            return None
        return round(self.count * 10_000 / self.chars, 4)


@dataclass(frozen=True)
class LabelSummary:
    """What a group of works shows — as a tally, never a mean.

    `works_attesting / works_measured` is the honest summary of a group whose
    members differ in length by 240×: it weights T1620 (1,110 chars) and T1559
    (264,402) equally as *works*, which is the unit an ascription claim is
    actually about. The per-work rates are there to be read; they are not
    averaged here, because the mean of rates over such a group is dominated by
    whichever short work happened to contain the feature twice.
    """

    label: str
    works_measured: int
    works_attesting: int
    works_skipped_short: int
    rates: tuple[float, ...]

    @property
    def share_attesting(self) -> float | None:
        if not self.works_measured:
            return None
        return round(self.works_attesting / self.works_measured, 4)


@dataclass(frozen=True)
class FeatureMeasurement:
    feature: str
    base_edition: str
    min_chars: int
    works: tuple[WorkMeasurement, ...] = field(default_factory=tuple)

    def by_label(self) -> dict[str, LabelSummary]:
        out: dict[str, LabelSummary] = {}
        labels: list[str] = []
        for w in self.works:
            if w.label is not None and w.label not in labels:
                labels.append(w.label)
        for label in labels:
            sel = [w for w in self.works if w.label == label]
            usable = [w for w in sel if w.sufficient]
            out[label] = LabelSummary(
                label=label,
                works_measured=len(usable),
                works_attesting=sum(1 for w in usable if w.count > 0),
                works_skipped_short=len(sel) - len(usable),
                rates=tuple(w.per_10k for w in usable if w.per_10k is not None),
            )
        return out

    def as_json(self) -> dict:
        """The whole measurement, flat enough to store in a verification's
        `detail` and re-derive from later."""
        return {
            "feature": self.feature,
            "base_edition": self.base_edition,
            "min_chars": self.min_chars,
            "works": [
                {
                    "work": w.work, "label": w.label, "edition": w.base_edition,
                    "chars": w.chars, "count": w.count, "per_10k": w.per_10k,
                    "editions_attesting": w.editions_attesting,
                    "editions_total": w.editions_total,
                    "sufficient": w.sufficient, "note": w.note,
                }
                for w in self.works
            ],
            "by_label": {
                label: {
                    "works_measured": s.works_measured,
                    "works_attesting": s.works_attesting,
                    "works_skipped_short": s.works_skipped_short,
                    "share_attesting": s.share_attesting,
                }
                for label, s in self.by_label().items()
            },
        }


def count_occurrences(text: str, feature: str) -> int:
    """Non-overlapping occurrences of an exact character sequence.

    `str.count`, named and documented rather than inlined, because
    non-overlapping is a real choice: 阿阿阿 contains 阿阿 twice by overlap and
    once without. Counting overlaps would make a repeated-character feature's
    rate depend on run length in a way no philological claim intends.
    """
    return text.count(feature) if feature else 0


def measure_feature(
    corpus: _Corpus, feature: str, *, labels: dict[str, str] | None = None,
    works: list[str] | None = None, base_edition: str = DEFAULT_BASE_EDITION,
    min_chars: int = DEFAULT_MIN_CHARS,
) -> FeatureMeasurement:
    """Count `feature` in every named work, one row per work.

    `labels` maps work id to subcorpus label (from a `Catalogue`); works with
    no label are still measured and reported with `label=None`, so a comparison
    against the rest of the canon does not require inventing a label for it.
    """
    selected = works if works is not None else corpus.works()
    rows: list[WorkMeasurement] = []

    for work in selected:
        editions = corpus.editions(work)
        base = base_edition if base_edition in editions else (editions[0] if editions else None)
        if base is None:
            rows.append(WorkMeasurement(
                work=work, label=(labels or {}).get(work), base_edition=None,
                chars=0, count=0, editions_total=0, editions_attesting=0,
                sufficient=False, note="no edition files",
            ))
            continue

        text = corpus.fetch(f"{work}/{base}").text
        count = count_occurrences(text, feature)
        attesting = sum(
            1 for e in editions
            if count_occurrences(corpus.fetch(f"{work}/{e}").text, feature) > 0
        )
        chars = len(text)
        sufficient = chars >= min_chars
        rows.append(WorkMeasurement(
            work=work, label=(labels or {}).get(work), base_edition=base,
            chars=chars, count=count, editions_total=len(editions),
            editions_attesting=attesting, sufficient=sufficient,
            note=None if sufficient
            else f"{chars} chars is below the {min_chars}-char floor for a rate",
        ))

    return FeatureMeasurement(
        feature=feature, base_edition=base_edition, min_chars=min_chars,
        works=tuple(rows),
    )
