"""An ascription study: a catalogue, a corpus, and every distance calibrated.

Ties `catalogue.py` (which works are in which group) to `delta.py` (how far
apart they are) and hands back something a screen can render without needing
to know either. One object, built once, because the z-scores behind a Delta
depend on which works are in the space: two profiles computed in different
spaces are not comparable, and keeping them in one type is what prevents
somebody comparing them anyway.

**The reference space is the whole canon, not the catalogue.** A distance
computed only among thirty-three works would answer "which of these
thirty-three is this most like", which is not the question. Radich asked
whether a disputed work can be associated with *some other reference point in
the canon*, and that requires the canon to be in the space. It costs about
thirty-five seconds to build over 1,464 works and nothing per query afterwards,
so it is built once when a study is opened.

Everything here is exploratory and labelled as such. Nearest neighbours over
character n-grams track subject matter heavily on this corpus — a cosmological
text sits near cosmological texts whoever translated it — so a neighbourhood is
evidence about resemblance, not about authorship. The `caveat` field carries
that sentence into every payload rather than trusting a renderer to remember.
"""
from __future__ import annotations

from dataclasses import dataclass, field
from pathlib import Path

from .association import (
    Association,
    CanonBaseline,
    Calibration,
    associate,
    calibrate,
    canon_baseline,
)
from .catalogue import Catalogue
from .measure import _Corpus
from .sources.radich_reader import RadichReader
from .delta import (
    DEFAULT_FEATURES,
    DEFAULT_MIN_CHARS,
    DeltaSpace,
    NullBand,
    Profile,
    build_space,
)

#: The Taishō text. One edition per work, deliberately: the other editions of a
#: work are ~99.98% identical, so including them would put seventeen copies of
#: one text into a space whose z-scores are computed across its members.
BASE_EDITION = "大"

CAVEAT = (
    "Exploratory. Character n-grams over this corpus track subject matter "
    "heavily — a cosmological text sits near other cosmological texts whoever "
    "translated it — so a neighbourhood is evidence about what a work "
    "resembles, not about who wrote it."
)


@dataclass(frozen=True)
class Study:
    catalogue: Catalogue
    space: DeltaSpace
    null: NullBand
    corpus_size: int
    #: The catalogued works as a readable corpus — `works()`, `editions()`,
    #: `fetch()`, which is all `cohort.measure` asks for. Held here so that
    #: opening a study is the *one* act that makes an ascription question
    #: answerable: the Delta space and the counting corpus are two views of
    #: the same catalogue, and a caller who had to assemble them separately
    #: could pair a space built over one corpus with counts taken from
    #: another. Scoped to the catalogue rather than the canon, because
    #: indexing 2.4 GB to count a feature in thirty-three works is minutes of
    #: work for nothing — the space needs the canon, the counting does not.
    corpus: _Corpus | None = None
    #: Leave-one-out calibration of the association measure, computed on first
    #: use and kept. One full ranking of the corpus per benchmark member — half
    #: a second for sixteen, and the same numbers every time, since the space is
    #: frozen. Recomputing it per work would make a page of ten placements pay
    #: for it ten times over.
    _calibration: dict = field(default_factory=dict, repr=False, compare=False)
    #: The canon's own distribution of neighbourhood statistics, on the
    #: same terms and for the same reason: sampled once, reused, and
    #: deterministic so that a re-measurement compares against the
    #: baseline it was recorded under.
    _baseline: list = field(default_factory=list, repr=False, compare=False)

    def benchmark(self) -> list[str]:
        return [
            w for w in self.catalogue.works(self.catalogue.benchmark_label)
            if w in self.space._z
        ]

    def profile(self, work: str, *, top: int = 8) -> Profile:
        return self.space.profile(
            work, benchmark=self.benchmark(), null=self.null, top=top,
        )

    def unmeasurable(self, label: str) -> list[str]:
        """Catalogued works with no profile, because they are below the
        character floor. Named rather than omitted: a study that quietly drops
        the works it cannot handle reports a smaller question than it was
        asked."""
        return [w for w in self.catalogue.works(label) if w not in self.space._z]

    def calibration(self) -> dict[int, Calibration]:
        """What a *known* benchmark work scores on the association measure,
        each scored with itself held out.

        Without this an enrichment is uninterpretable. A p-value says the
        overlap is not chance; it does not say the association is as strong as
        membership normally looks, and on this study six of sixteen undisputed
        members score zero — so an unenriched work has not been shown to be an
        outsider, and a measure that reported it as one would be manufacturing
        exclusions.
        """
        if not self._calibration:
            self._calibration.update(
                calibrate(self.space, self.benchmark(),
                          label=self.catalogue.benchmark_label)
            )
        return self._calibration

    def baseline(self) -> CanonBaseline:
        """How near works in this corpus generally are to their own nearest
        neighbours, and how far the second one usually trails.

        Without it, "its nearest work is at Δ 0.45" is unreadable — neither
        near nor far — and the second branch of an ascription question, *what
        else is this work near*, cannot be answered at all.
        """
        if not self._baseline:
            self._baseline.append(canon_baseline(self.space))
        return self._baseline[0]

    def association(self, work: str, *, top: int = 15) -> Association:
        """Whether the benchmark is over-represented among `work`'s nearest
        neighbours in the whole corpus.

        This is the measure Radich's brief actually asks for — associate a work
        with the group *against texts by other translators in the canon* — and
        it is not the same question as `profile()`, whose band asks only whether
        a work sits inside the group's own spread. On this corpus the band
        answers "not distinguishable" for every disputed work and every
        interloper alike; the two are kept side by side because that contrast is
        itself worth seeing.
        """
        return associate(
            self.space, work, group=self.benchmark(),
            label=self.catalogue.benchmark_label,
            calibration=self.calibration(), baseline=self.baseline(), top=top,
        )

    def as_json(self, *, top: int = 8) -> dict:
        groups = {}
        for label in self.catalogue.labels():
            if label == self.catalogue.benchmark_label:
                continue
            groups[label] = {
                "profiles": [
                    {
                        **self.profile(w, top=top).as_json(),
                        # The band says "not distinguishable" for almost
                        # everything; the association is the measure with the
                        # canon behind it. Both, because a reader comparing them
                        # learns what the band is and is not good for.
                        "association": self.association(w).as_json(),
                    }
                    for w in self.catalogue.works(label) if w in self.space._z
                ],
                "unmeasurable": self.unmeasurable(label),
            }
        return {
            "benchmark_label": self.catalogue.benchmark_label,
            "control_label": self.catalogue.control_label,
            "null": self.null.as_json(),
            "features": len(self.space.features),
            "corpus_size": self.corpus_size,
            "min_chars": self.space.min_chars,
            "calibration": [c.as_json() for c in self.calibration().values()],
            "baseline": self.baseline().as_json(),
            "groups": groups,
            "caveat": CAVEAT,
        }


def load_study(
    corpus_root: str | Path, catalogue: Catalogue, *,
    base_edition: str = BASE_EDITION, features: int = DEFAULT_FEATURES,
    min_chars: int = DEFAULT_MIN_CHARS,
) -> Study:
    """Read one edition of every work in the corpus and build the space.

    The space reads the filesystem directly rather than going through
    `RadichReader`: the reader's job is refs, editions and provenance for the
    graph, and a Delta space needs one string per work and nothing else. Using
    it for all 4,652 would build an FTS index over 2.4 GB to compute
    frequencies that never touch it.

    A reader *is* built, over the catalogued works alone — thirty-three
    directories, seconds — because counting a feature needs every edition of a
    work and the space keeps only one. So the study holds both: the canon as a
    space, the catalogue as a corpus.
    """
    root = Path(corpus_root)
    if not root.is_dir():
        raise FileNotFoundError(f"no corpus at {root}")

    texts: dict[str, str] = {}
    for d in sorted(root.iterdir()):
        if not d.is_dir():
            continue
        f = d / f"{base_edition}.txt"
        if not f.is_file():
            candidates = sorted(d.glob("*.txt"))
            if not candidates:
                continue
            f = candidates[0]
        texts[d.name] = f.read_text(encoding="utf-8", errors="replace")

    if catalogue.benchmark_label is None:
        raise ValueError(
            "this catalogue names no benchmark group, so there is nothing to "
            "calibrate distances against. Load it with `benchmark_label=`"
        )
    catalogue.check_against(list(texts))

    labels = {w: catalogue.label_of(w) for w in texts}
    space = build_space(texts, labels=labels, features=features, min_chars=min_chars)
    bench = [w for w in catalogue.works(catalogue.benchmark_label) if w in space._z]
    null = space.null_band(bench, label=catalogue.benchmark_label)
    # Only the catalogued works that actually have a directory. A catalogue
    # naming a work this corpus does not hold is already reported by
    # `check_against` above; passing it to the reader as well would turn that
    # report into a crash from a different module.
    return Study(
        catalogue=catalogue, space=space, null=null, corpus_size=len(texts),
        corpus=RadichReader(root, works=[w for w in catalogue.works() if w in texts]),
    )


#: Where a study directory keeps its two halves. Stated once because three
#: callers used to spell it out independently — the CLI's `study` command, its
#: `run` command and `serve_ui.py` — and a layout convention repeated three
#: times is one that changes in two places.
CATALOGUE_FILE = "P-catalogue.txt"
CORPUS_SUBDIR = ("corpus", "T-stripped")


def open_study(
    root: str | Path, *, benchmark_label: str = "P-23",
    control_label: str = "interloper", features: int = DEFAULT_FEATURES,
    min_chars: int = DEFAULT_MIN_CHARS,
) -> Study:
    """A study from a directory laid out as `data/radich/` is.

    Thin, and deliberately so: `load_study` takes a catalogue because a study
    is not tied to one on-disk shape, and this is the shape this project's
    corpus happens to have.
    """
    from .catalogue import load_catalogue

    root = Path(root)
    catalogue = load_catalogue(
        root / CATALOGUE_FILE,
        benchmark_label=benchmark_label, control_label=control_label,
    )
    return load_study(
        root.joinpath(*CORPUS_SUBDIR), catalogue,
        features=features, min_chars=min_chars,
    )
