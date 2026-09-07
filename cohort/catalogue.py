"""Subcorpus labels — which works a researcher has grouped, and why that matters.

An ascription study needs named groups of works: a benchmark believed genuine,
a set under question, and — if the researcher has been careful — a set believed
*not* genuine that earlier methods could not tell apart from the benchmark.

That third group is the valuable one, and this module exists partly to make it
hard to ignore. Radich's `interloper` set is a **labelled negative control**:
texts that previous tests could not distinguish from `P-23` and that are
believed most probably not Paramārtha's. A discriminator that cannot separate
those from the benchmark has not earned the right to pronounce on the disputed
set, however good its story about them sounds. `control_label` is how a
catalogue says which group plays that role, so the gate can be enforced rather
than remembered.

Deliberately generic. Nothing here knows about Paramārtha, Chinese, or the
Taishō: a catalogue is `{work id: label}` plus a statement of which label is
the benchmark and which is the control. The same shape serves any attribution
question, and encoding one scholar's problem into the vocabulary would be the
sort of thing §6 asks for an argument about.
"""
from __future__ import annotations

from dataclasses import dataclass
from pathlib import Path


class CatalogueError(Exception):
    """The catalogue is missing, malformed, or disagrees with the corpus."""


@dataclass(frozen=True)
class Catalogue:
    """Work ids grouped by label, with the two roles that make a study testable."""

    entries: tuple[tuple[str, str], ...]
    #: the group treated as a trustworthy sample of the target idiom
    benchmark_label: str | None = None
    #: the group believed *not* to belong, held back to test a discriminator
    control_label: str | None = None
    source: str | None = None

    def labels(self) -> list[str]:
        seen: dict[str, None] = {}
        for _work, label in self.entries:
            seen.setdefault(label, None)
        return list(seen)

    def works(self, label: str | None = None) -> list[str]:
        if label is None:
            return [w for w, _ in self.entries]
        if label not in self.labels():
            raise CatalogueError(
                f"no label {label!r} in this catalogue; it has "
                f"{', '.join(repr(l) for l in self.labels())}."
            )
        return [w for w, l in self.entries if l == label]

    def label_of(self, work: str) -> str | None:
        for w, label in self.entries:
            if w == work:
                return label
        return None

    def counts(self) -> dict[str, int]:
        return {label: len(self.works(label)) for label in self.labels()}

    def check_against(self, available: list[str]) -> None:
        """Refuse a catalogue naming works the corpus does not hold.

        Loudly, and before anything is measured. A study that silently drops
        the works it could not find reports a benchmark of a size nobody chose,
        and the missing ones are exactly as likely to be the interesting ones.
        """
        have = set(available)
        missing = [w for w, _ in self.entries if w not in have]
        if missing:
            raise CatalogueError(
                f"{len(missing)} catalogued work(s) are not in the corpus: "
                f"{', '.join(missing[:8])}"
                + (" …" if len(missing) > 8 else "")
                + ". Fix the catalogue or point at the right corpus; dropping "
                "them silently would change the size of every group without "
                "saying so."
            )


def load_catalogue(
    path: str | Path, *, benchmark_label: str | None = None,
    control_label: str | None = None,
) -> Catalogue:
    """Read a `<work-id><whitespace><label>` file. `#` comments and blank lines
    are skipped, so a catalogue can carry its own provenance header."""
    p = Path(path)
    if not p.is_file():
        raise CatalogueError(f"no catalogue at {p}")

    entries: list[tuple[str, str]] = []
    seen: dict[str, str] = {}
    for n, raw in enumerate(p.read_text(encoding="utf-8").splitlines(), start=1):
        line = raw.strip()
        if not line or line.startswith("#"):
            continue
        parts = line.split()
        if len(parts) != 2:
            raise CatalogueError(
                f"{p.name}:{n}: expected `<work-id> <label>`, got {raw.strip()!r}. "
                "Work ids and labels must not contain whitespace."
            )
        work, label = parts
        if work in seen:
            raise CatalogueError(
                f"{p.name}:{n}: {work} is already labelled {seen[work]!r}. A work "
                "in two groups would be counted as both benchmark and control."
            )
        seen[work] = label
        entries.append((work, label))

    if not entries:
        raise CatalogueError(f"{p.name} has no entries")

    cat = Catalogue(
        entries=tuple(entries), benchmark_label=benchmark_label,
        control_label=control_label, source=str(p),
    )
    for role, label in (("benchmark", benchmark_label), ("control", control_label)):
        if label is not None and label not in cat.labels():
            raise CatalogueError(
                f"{role} label {label!r} is not in {p.name}; it has "
                f"{', '.join(repr(l) for l in cat.labels())}."
            )
    return cat
