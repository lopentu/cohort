"""How much of one unit's wording occurs verbatim in every other unit.

    uv run python -m scripts.experiments.overlap_scan data/radich T0603

The whole-corpus control behind "T1694 shares 65% of T0603's ten-character
strings; the next-highest unit in the corpus shares 0.2%". Han characters
only: CBETA's punctuation and line breaks are editorial and break every shared
run (with them in, the same pair read as 11%).
"""

from __future__ import annotations

import argparse

from cohort.attribution import CATALOGUE, AttributionIndex, is_han, read_catalogue
from cohort.tools.align_passages import GRAM


def han(text: str) -> str:
    return "".join(ch for ch in text if is_han(ch))


def grams(text: str) -> set[str]:
    return {text[i : i + GRAM] for i in range(len(text) - GRAM + 1)}


def main() -> None:
    ap = argparse.ArgumentParser(description=__doc__)
    ap.add_argument("root")
    ap.add_argument("unit")
    ap.add_argument("--top", type=int, default=8)
    args = ap.parse_args()
    from pathlib import Path

    root = Path(args.root)
    labels, _, _ = read_catalogue(root / CATALOGUE)
    target = AttributionIndex.base_text(root, args.unit)
    if target is None:
        msg = f"{args.unit}: no base text"
        raise SystemExit(msg)
    g = grams(han(target))
    rows = []
    for uid, label in labels.items():
        if uid == args.unit:
            continue
        text = AttributionIndex.base_text(root, uid)
        if text is None:
            continue
        share = len(g & grams(han(text))) / len(g)
        rows.append((share, uid, label))
    rows.sort(reverse=True)
    print(f"{args.unit}: {len(g):,} distinct {GRAM}-character strings; share found verbatim in each other unit")
    for share, uid, label in rows[: args.top]:
        print(f"  {share:7.2%}  {uid:<40}{label}")
    above_1pct = sum(1 for s, _, _ in rows if s > 0.01)
    print(f"  units above 1%: {above_1pct} of {len(rows)}")


if __name__ == "__main__":
    main()
