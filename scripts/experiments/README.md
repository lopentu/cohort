# The experiments behind the numbers

Every number quoted in the PNC talk about Radich's question 1 comes from one of
these scripts, and each script reuses `cohort.attribution` (parsing, profiles,
the withholding rule) and `cohort.embeddings`, so there is one implementation
behind a number, not a script and a copy. Run them from the repository root;
`ROOT` is Radich's data folder (never committed), `EMB` a window-embedding file.

    uv run python -m scripts.experiments.attribution_eval ROOT
    uv run python -m scripts.experiments.encoder_eval ROOT EMB [--trained]
    uv run python -m scripts.experiments.neighbors_eval ROOT EMB --unit T0603
    uv run python -m scripts.experiments.overlap_scan ROOT T0603
    uv run python -m scripts.experiments.editions ROOT T0237
    uv run --with torch --with transformers python -m scripts.experiments.embed_windows MODEL ROOT --out EMB

| number in the talk | script | what it is |
|---|---|---|
| 82% → 52% (naive Bayes 81.8% → 52.2%; nearest centroid 82.6% → 50.0%) | `attribution_eval` | leave-one-unit-out vs leave-one-work-out on Radich's 7,270 strings, 368 units, 13 classes |
| Saṅghadeva 95% → 3% | `attribution_eval` | 106 of his 108 units are chapters of T0026 |
| his vocabulary 52.2% vs label-free 47.8%; Dhr 86 vs 74, Kj 83 vs 37, ASg 55 vs 100, ZQ 12 vs 75 | `attribution_eval` | the vocabulary control; label-free = commonest strings of the grey texts, no label read |
| 383 strings shared by the two vocabularies | `cohort evidence --list` (ledger) | |
| 2B 33.7%, 9B 34.0% (nearest centroid, works held out) | `encoder_eval` | frozen Dharmamitra encoders, unit = mean of its windows |
| 23.7% vs 24.0% largest-class baseline | `neighbors_eval` | nearest window in another work is by the same translator, 36,517 labelled windows |
| T0603 → T1694 in 25 of 30 windows | `neighbors_eval --unit T0603` | |
| 64.45% of T0603's ten-character strings in T1694; next unit 0.15% | `overlap_scan ROOT T0603` | Han characters only |
| 279-character shared run | `cohort/tools/align_passages.py` (also via the agent) | |
| T0237: two edition families, ≤3 / ≤24 within, ≥56 between | `editions ROOT T0237` | |
| linear probe on 9B vectors 39.4%; character-n-gram SVM 56.8% | `encoder_eval --trained` | five grouped folds by work, IDF fitted per fold; needs scikit-learn |
| 54,616 windows, 2,160 units, 36 min (2B) / 120 min (9B) on an A5000 | `embed_windows` | needs a GPU, torch and transformers |

Outputs recorded 6 September 2026 on Radich's corpus (Zenodo 7750586 as
modified by him) with the Dharmamitra encoders `buddhist-nlp/mitra-qwen35-2b-embedder`
and `buddhist-nlp/mitra-qwen35-embedder` (2026-07-29 releases):

    features     items        classifier  split by unit  split by work
    radich       7,270  nearest centroid          82.6%          50.0%
    radich       7,270       naive Bayes          81.8%          52.2%
    generic      7,270  nearest centroid          75.3%          38.0%
    generic      7,270       naive Bayes          81.2%          47.8%
    both        14,157  nearest centroid          76.6%          38.3%
    both        14,157       naive Bayes          81.5%          48.9%

    window-level 1-NN, different work, same translator: 23.7% of 36,517 labelled windows
      largest-class baseline (always ZFn): 24.0%
    T0603: nearest window in another work, tallied over 30 windows
      by unit : T1694 25, T1541 1, T0006-fascicle-1 1, T1553 1, T0057 1, T0125-49-放牛品-5 1

    T0603: 9,089 distinct 10-character strings; share found verbatim in each other unit
       64.45%  T1694   pre-Dhr-other
        0.15%  T1509   Kj

Two numbers were quoted and then withdrawn, and are deliberately not
reproduced here: "errors land on a historically adjacent translator 38% of the
time vs 10% by chance" (56 of the 67 cases were the single Saṅghadeva→ZFn
confusion the leakage rule creates), and an earlier per-class control table
whose smoothing denominator had been left at the wrong vocabulary size.
