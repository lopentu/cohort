"""How far apart the printed editions of one unit are, character by character.

    uv run python -m scripts.experiments.editions data/radich T0237

Radich's corpus keeps one file per historical edition of the canon in each
unit's folder. On Han characters, the count of characters not shared between
each pair of editions (difflib's matching blocks subtracted from the longer
text -- a similarity measure, not an edit distance). The eight editions of
T0237 fall into two families, which is the small worked example of "eight
files, two lines of transmission" behind Cohort's independence rule.
"""

from __future__ import annotations

import argparse
import difflib
from pathlib import Path

from cohort.attribution import CORPUS_DIR, is_han


def differing(a: str, b: str) -> int:
    sm = difflib.SequenceMatcher(None, a, b, autojunk=False)
    shared = sum(bl.size for bl in sm.get_matching_blocks())
    return max(len(a), len(b)) - shared


def main() -> None:
    ap = argparse.ArgumentParser(description=__doc__)
    ap.add_argument("root")
    ap.add_argument("unit")
    args = ap.parse_args()
    folder = Path(args.root) / CORPUS_DIR / args.unit
    editions = {p.stem: "".join(ch for ch in p.read_text(encoding="utf-8") if is_han(ch))
                for p in sorted(folder.glob("*.txt"))}
    if len(editions) < 2:
        msg = f"{folder}: fewer than two edition files"
        raise SystemExit(msg)
    names = list(editions)
    print(f"{args.unit}: {len(names)} editions, {min(len(t) for t in editions.values()):,}–"
          f"{max(len(t) for t in editions.values()):,} Han characters")
    print(f"{'':<8}" + "".join(f"{n:>7}" for n in names))
    for a in names:
        row = "".join(f"{differing(editions[a], editions[b]) if a != b else 0:>7}" for b in names)
        print(f"{a:<8}{row}")


if __name__ == "__main__":
    main()
