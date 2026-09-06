"""The leakage result and the vocabulary control, from one implementation.

    uv run python -m scripts.experiments.attribution_eval data/radich

Prints, for each vocabulary (Radich's Table 1; the commonest strings of the
grey texts; their union) and each of two classifiers, accuracy when one unit
is held out and when one whole work is held out; then the per-class table for
the work split. The 82%-to-52% gap is the first table; the Dharmarakṣa bias of
the curated list is the second.
"""

from __future__ import annotations

import argparse
import sys

from cohort.attribution import FEATURE_SETS, AttributionIndex
from scripts.experiments._common import CLASSIFIERS, evaluate, pct, pct0, works_per_class


def main() -> None:
    ap = argparse.ArgumentParser(description=__doc__)
    ap.add_argument("root", help="the Radich data folder")
    ap.add_argument("--features", nargs="*", default=list(FEATURE_SETS), choices=list(FEATURE_SETS))
    args = ap.parse_args()
    index = AttributionIndex.load(args.root)
    led = index.units()["ledger"]
    print(f"units {led['kept for profiling']}  classes {led['classes profiled']}  "
          f"(dropped: {sum(v for k, v in led.items() if k.startswith('dropped'))})", file=sys.stderr)

    print(f"\n{'features':<10}{'items':>8}{'classifier':>18}{'split by unit':>15}{'split by work':>15}")
    per_class: dict[str, tuple] = {}
    for feats in args.features:
        n_items = len(index._ix.features[feats])
        for name, clf in CLASSIFIERS.items():
            row = []
            for how in ("unit", "work"):
                ok, n = evaluate(index, feats, how, clf)
                row.append(pct(sum(ok.values()), sum(n.values())))
                if how == "work" and name == "naive Bayes":
                    per_class[feats] = (ok, n)
            print(f"{feats:<10}{n_items:>8,}{name:>18}{row[0]:>15}{row[1]:>15}")

    works = works_per_class(index)
    first = args.features[0]
    _, n = per_class[first]
    print("\n  naive Bayes, split by work, per class")
    head = f"{'class':<16}{'units':>6}{'works':>6}" + "".join(f"{f:>9}" for f in args.features)
    print(head)
    for label in sorted(n, key=lambda lab: -n[lab]):
        cells = "".join(f"{pct0(per_class[f][0][label], per_class[f][1][label]):>9}" for f in args.features)
        print(f"{label:<16}{n[label]:>6}{works[label]:>6}{cells}")


if __name__ == "__main__":
    main()
