"""Does a frozen encoder recover Radich's labels under the honest split?

    uv run python -m scripts.experiments.encoder_eval data/radich ~/corpora/embeddings/mitra-qwen35-embedder.npz
    uv run --with scikit-learn python -m scripts.experiments.encoder_eval ... --trained

Same 368 units and 13 classes as attribution_eval.py. A unit's vector is the
mean of its windows; the classifier is nearest class centroid by cosine, the
same rule the string experiment uses, so the only thing that changed is the
representation. `--trained` adds two honest trained models (scikit-learn):
a linear probe on the encoder's window vectors, and a linear SVM on character
1-3-gram TF-IDF of the same windows, both with works held out in five grouped
folds and the IDF fitted inside each fold; a unit's answer is the majority
vote of its windows.
"""

from __future__ import annotations

import argparse
import collections
import sys

import numpy as np

from cohort.attribution import AttributionIndex, work_of
from scripts.experiments._common import pct, pct0


def main() -> None:
    ap = argparse.ArgumentParser(description=__doc__)
    ap.add_argument("root")
    ap.add_argument("npz")
    ap.add_argument("--trained", action="store_true", help="also fit the probe and the character SVM")
    args = ap.parse_args()

    index = AttributionIndex.load(args.root)
    kept = index._ix.unit_label
    z = np.load(args.npz)
    vec, uid, start = z["vec"], z["uid"].astype(str), z["start"]
    idx: dict[str, list[int]] = collections.defaultdict(list)
    for i, u in enumerate(uid):
        if u in kept:
            idx[u].append(i)
    missing = [u for u in kept if u not in idx]
    if missing:
        msg = f"{len(missing)} kept units have no windows: {missing[:5]}"
        raise SystemExit(msg)
    U = sorted(idx)
    X = np.stack([vec[idx[u]].astype(np.float32).mean(0) for u in U])
    X /= np.linalg.norm(X, axis=1, keepdims=True)
    y = np.array([kept[u] for u in U])
    W = np.array([work_of(u) for u in U])
    print(f"{len(U)} units, {len(set(y))} classes, dim {X.shape[1]}", file=sys.stderr)

    def centroid_eval(group_by: str) -> tuple[collections.Counter, collections.Counter]:
        ok, n = collections.Counter(), collections.Counter()
        for i, _u in enumerate(U):
            held = (W[i] == W) if group_by == "work" else (np.arange(len(U)) == i)
            train = ~held
            if not (train & (y == y[i])).any():
                continue
            cents = {c: X[train & (y == c)].mean(0) for c in set(y[train])}
            best = max(cents, key=lambda c: float(X[i] @ cents[c]) / (np.linalg.norm(cents[c]) or 1))
            n[y[i]] += 1
            ok[y[i]] += best == y[i]
        return ok, n

    name = args.npz.rsplit("/", 1)[-1].replace(".npz", "")
    res = {how: centroid_eval(how) for how in ("unit", "work")}
    print(f"\n{'':<40}{'split by unit':>15}{'split by work':>15}")
    print(f"{'nearest centroid, ' + name:<40}"
          + "".join(f"{pct(sum(res[h][0].values()), sum(res[h][1].values())):>15}" for h in ("unit", "work")))
    ok_u, n = res["unit"]
    ok_w, _ = res["work"]
    print(f"\n{'class':<16}{'units':>6}{'by unit':>9}{'by work':>9}")
    for label in sorted(n, key=lambda lab: -n[lab]):
        print(f"{label:<16}{n[label]:>6}{pct0(ok_u[label], n[label]):>9}{pct0(ok_w[label], n[label]):>9}")

    if not args.trained:
        return
    # Optional dependency, installed for this path only (uv run --with scikit-learn);
    # imported by name so the type checker does not need it present.
    import importlib

    try:
        fe = importlib.import_module("sklearn.feature_extraction.text")
        lm = importlib.import_module("sklearn.linear_model")
        ms = importlib.import_module("sklearn.model_selection")
        svm = importlib.import_module("sklearn.svm")
    except ModuleNotFoundError as e:
        msg = "--trained needs scikit-learn: uv run --with scikit-learn ..."
        raise SystemExit(msg) from e

    rows = np.array([i for i, u in enumerate(uid) if u in kept])
    yw = np.array([kept[u] for u in uid[rows]])
    gw = np.array([work_of(u) for u in uid[rows]])
    Uw = uid[rows]
    folds = list(ms.GroupKFold(n_splits=5).split(rows, yw, gw))

    def report(title: str, pred: np.ndarray) -> None:
        votes: dict[str, collections.Counter] = collections.defaultdict(collections.Counter)
        for u, p in zip(Uw, pred, strict=True):
            votes[u][p] += 1
        ok, n = collections.Counter(), collections.Counter()
        for u, label in kept.items():
            n[label] += 1
            ok[label] += votes[u].most_common(1)[0][0] == label
        macro = np.mean([ok[label] / n[label] for label in n])
        print(f"\n{title}\n  windows {pct(int((pred == yw).sum()), len(yw))}   units (majority vote) "
              f"{pct(sum(ok.values()), sum(n.values()))}   macro over classes {macro:.1%}")
        for label in sorted(n, key=lambda lab: -n[lab]):
            print(f"    {label:<16}{n[label]:>5}  {pct0(ok[label], n[label]):>5}")

    Xw = vec[rows].astype(np.float32)
    pred = np.empty(len(rows), dtype=object)
    for tr, te in folds:
        clf = lm.LogisticRegression(max_iter=2000, C=1.0, class_weight="balanced").fit(Xw[tr], yw[tr])
        pred[te] = clf.predict(Xw[te])
    report(f"A. linear probe on {name}", pred)

    texts: dict[str, str] = {}

    def window_text(u: str, s: int) -> str:
        if u not in texts:
            texts[u] = index.base_text(index.root, u) or ""
        return texts[u][s : s + 400]

    docs = [window_text(u, s) for u, s in zip(Uw, start[rows], strict=True)]
    hv = fe.HashingVectorizer(analyzer="char", ngram_range=(1, 3), n_features=2**20, alternate_sign=False, norm=None)
    counts = hv.transform(docs)
    pred = np.empty(len(rows), dtype=object)
    for tr, te in folds:
        tfidf = fe.TfidfTransformer(sublinear_tf=True).fit(counts[tr])   # fitted on the training fold only
        clf = svm.LinearSVC(C=0.5, class_weight="balanced").fit(tfidf.transform(counts[tr]), yw[tr])
        pred[te] = clf.predict(tfidf.transform(counts[te]))
    report("B. linear SVM on character 1-3-grams, learned weights, fold-internal IDF", pred)


if __name__ == "__main__":
    main()
