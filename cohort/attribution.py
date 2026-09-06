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

from dataclasses import dataclass
from pathlib import Path

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

    def as_json(self, *, top: int = 8) -> dict:
        groups = {}
        for label in self.catalogue.labels():
            if label == self.catalogue.benchmark_label:
                continue
            groups[label] = {
                "profiles": [
                    self.profile(w, top=top).as_json()
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
