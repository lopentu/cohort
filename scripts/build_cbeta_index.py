"""Build the full-corpus CBETA search index (manual, explicit, never automatic).

Reads the whole archive once and writes an FTS5 index of every citable span
(see `cohort/sources/cbeta_fts.py` for what "citable" means and why the index
holds nothing else). Minutes, not seconds, and a multi-gigabyte output file —
which is exactly why this is a script you run deliberately rather than
something a constructor does behind your back.

Usage:
    .venv/bin/python scripts/build_cbeta_index.py                 # whole archive
    .venv/bin/python scripts/build_cbeta_index.py --limit 500     # a quick trial
    .venv/bin/python scripts/build_cbeta_index.py --prefix Bookcase/CBETA/XML/T/
    .venv/bin/python scripts/build_cbeta_index.py --db /path/to/index.sqlite

Requires CBETA_ARCHIVE_PATH in `.env`. The output path defaults to
CBETA_FTS_PATH if set, else `cbeta_fts.sqlite` in the repo root (gitignored
by the existing `*.sqlite` rule — the index is corpus-derived and must never
be committed).
"""
from __future__ import annotations

import argparse
import os
import sys
import time
from pathlib import Path

from cohort.agents.openrouter import _load_dotenv
from cohort.sources.cbeta_fts import build_index
from cohort.sources.cbeta_reader import CBETA_ENTRY_PREFIX, CbetaArchiveError
from cohort.sources.env import CBETA_V061_SHA256  # one definition; see docs/corpus.md

REPO_ROOT = Path(__file__).resolve().parent.parent


def main() -> None:
    _load_dotenv(REPO_ROOT / ".env")

    parser = argparse.ArgumentParser(description=__doc__)
    parser.add_argument("--db", default=None, help="output index path")
    parser.add_argument("--prefix", default=CBETA_ENTRY_PREFIX, help="entry-path prefix to index")
    parser.add_argument("--limit", type=int, default=None, help="index only the first N entries")
    parser.add_argument(
        "--sha256", default=CBETA_V061_SHA256,
        help="expected archive SHA-256; recorded in the index and enforced on use",
    )
    args = parser.parse_args()

    archive_path = os.environ.get("CBETA_ARCHIVE_PATH")
    if not archive_path:
        print("config error: CBETA_ARCHIVE_PATH is not set (see docs/handoff.md)", file=sys.stderr)
        sys.exit(1)

    db_path = Path(
        args.db or os.environ.get("CBETA_FTS_PATH") or (REPO_ROOT / "cbeta_fts.sqlite")
    )

    print(f"archive : {archive_path}")
    print(f"index   : {db_path}")
    print(f"prefix  : {args.prefix}")
    print(f"limit   : {args.limit if args.limit is not None else 'none (whole archive)'}")
    print("\nverifying archive hash (reads the whole file once)...")

    started = time.monotonic()

    def progress(count: int, name: str) -> None:
        elapsed = time.monotonic() - started
        print(f"  {count:>6} entries  {elapsed:7.1f}s  {name.rsplit('/', maxsplit=1)[-1]}", flush=True)

    try:
        report = build_index(
            archive_path, args.sha256, db_path,
            prefix=args.prefix, limit=args.limit, progress=progress,
        )
    except CbetaArchiveError as e:
        print(f"\narchive error: {e}", file=sys.stderr)
        sys.exit(1)

    elapsed = time.monotonic() - started
    size_mb = db_path.stat().st_size / 1e6 if db_path.exists() else 0.0
    print(f"\ndone in {elapsed:.1f}s — {size_mb:.1f} MB at {db_path}")
    print(f"  entries indexed : {report.entries_indexed}")
    print(f"  entries skipped : {report.entries_skipped}")
    print(f"  citable runs    : {report.runs_indexed}")
    print(f"  dropped, not unique in document : {report.runs_not_unique}")
    print(f"  dropped, too short / no CJK     : {report.runs_too_short}")


if __name__ == "__main__":
    main()
