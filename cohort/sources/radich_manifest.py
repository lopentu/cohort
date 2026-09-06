"""A LocalReader manifest for Radich's plain-text Taishō corpus.

`LocalReader` infers nothing from a filename: a record exists only if a
manifest row names it. Radich's corpus is one directory per unit, one file per
edition; this writes the row for each unit's Taishō base text, so that the
Corpus tab, the agents' span verification and the Evidence tab all read the
same bytes.

By default only the units in Radich's catalogue are listed (about 2,300 of
the corpus's 4,600), because those are the texts the demo is about and the
FTS index is built at every start; `include_uncatalogued=True` lists them all.
"""

from __future__ import annotations

import csv
from pathlib import Path

from cohort.attribution import CATALOGUE, CORPUS_DIR, EDITIONS, read_catalogue

NOTE = (
    "Radich's modified CBETA/Taishō text (paratext removed, composite works split); "
    "CBETA is CC BY-NC-SA-equivalent and this derivative is unpublished. Local use only."
)


def write_manifest(
    root: str | Path, out: str | Path | None = None, *, include_uncatalogued: bool = False,
) -> dict[str, int]:
    """Write `manifest.csv` for the corpus under `root` and return a small ledger."""
    root = Path(root)
    corpus = root / CORPUS_DIR
    if not corpus.is_dir():
        msg = f"{corpus}: no corpus directory"
        raise FileNotFoundError(msg)
    labels, _, _ = read_catalogue(root / CATALOGUE)
    out_path = Path(out) if out else corpus / "manifest.csv"
    ledger = {"listed": 0, "skipped: not in catalogue": 0, "skipped: no base text": 0}
    with out_path.open("w", encoding="utf-8", newline="") as fh:
        w = csv.writer(fh)
        w.writerow(["path", "witness_ref", "label", "note"])
        for d in sorted(p for p in corpus.iterdir() if p.is_dir()):
            uid = d.name
            if uid not in labels and not include_uncatalogued:
                ledger["skipped: not in catalogue"] += 1
                continue
            base = next((d / ed for ed in EDITIONS if (d / ed).is_file()), None)
            if base is None:
                ledger["skipped: no base text"] += 1
                continue
            label = labels.get(uid, "not in catalogue")
            w.writerow([f"{uid}/{base.name}", uid, f"{uid} · {label}", NOTE])
            ledger["listed"] += 1
    return ledger
