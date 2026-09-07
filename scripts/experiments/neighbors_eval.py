"""What the encoder is actually good at, measured.

    uv run python -m scripts.experiments.neighbors_eval data/radich ~/corpora/embeddings/mitra-qwen35-embedder.npz [--unit T0603]

Two checks. Corpus-wide: for every labelled window, is its nearest neighbour in
a *different work* by the same translator? Reported against the largest-class
baseline (always guessing the most frequent class), which is the honest
"chance" for an imbalanced problem. Then, for one unit, the tally of which
unit and which label its windows' nearest neighbours belong to -- the check
that pointed from T0603 to its commentary T1694.
"""

from __future__ import annotations

import argparse
import collections
import sys

import numpy as np

from cohort.attribution import work_of
from cohort.embeddings import EmbeddingIndex
from scripts.experiments._common import pct


def main() -> None:
    ap = argparse.ArgumentParser(description=__doc__)
    ap.add_argument("root")
    ap.add_argument("npz")
    ap.add_argument("--unit", default="T0603")
    ap.add_argument("--chunk", type=int, default=1024)
    args = ap.parse_args()

    emb = EmbeddingIndex(args.npz)
    labelled = np.where(emb.label != "grey")[0]
    L = emb.vec[labelled].astype(np.float32)
    work = np.array([work_of(u) for u in emb.uid])
    same = 0
    per_n: collections.Counter = collections.Counter()
    per_ok: collections.Counter = collections.Counter()
    for i in range(0, len(labelled), args.chunk):
        q = L[i : i + args.chunk]
        sims = q @ L.T
        qi = labelled[i : i + args.chunk]
        sims[work[qi][:, None] == work[labelled][None, :]] = -2.0   # never its own work
        nn = labelled[sims.argmax(1)]
        for a, b in zip(qi, nn, strict=True):
            per_n[emb.label[a]] += 1
            if emb.label[a] == emb.label[b]:
                same += 1
                per_ok[emb.label[a]] += 1
        print(f"  {min(i + args.chunk, len(labelled)):>7,}/{len(labelled):,}", file=sys.stderr, end="\r")
    print(file=sys.stderr)
    biggest, n_big = collections.Counter(emb.label[labelled]).most_common(1)[0]
    print(f"window-level 1-NN, different work, same translator: {pct(same, len(labelled))} of {len(labelled):,} labelled windows")
    print(f"  largest-class baseline (always {biggest}): {pct(n_big, len(labelled))}")
    for label in sorted(per_n, key=lambda lab: -per_n[lab]):
        print(f"  {label:<16}{per_n[label]:>7}  {pct(per_ok[label], per_n[label]):>6}")

    out = emb.neighbors(args.unit, top_k=1, max_windows=0)
    print(f"\n{args.unit}: nearest window in another work, tallied over {out['windows']} windows")
    print("  by unit :", ", ".join(f"{u} {c}" for u, c in out["nearest_unit_tally"]))
    print("  by label:", ", ".join(f"{u} {c}" for u, c in out["nearest_label_tally"]))


if __name__ == "__main__":
    main()
