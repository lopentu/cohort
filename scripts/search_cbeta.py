"""Search the CBETA corpus from the command line.

A thin front end on the same `CbetaReader.search()` the tools use, so what a
researcher sees here is exactly what an agent would get — including the
guarantee that every hit is fetchable (`--fetch` proves it per hit, at the
cost of a full archive re-verification each time; see below).

Usage:
    .venv/bin/python scripts/search_cbeta.py 色即是空
    .venv/bin/python scripts/search_cbeta.py 色即是空 --limit 40
    .venv/bin/python scripts/search_cbeta.py 色即是空 --collection T
    .venv/bin/python scripts/search_cbeta.py 色即是空 --fetch

Requires CBETA_ARCHIVE_PATH in `.env` and an index built by
scripts/build_cbeta_index.py.

Note on `--fetch`: `CbetaReader.fetch()` re-hashes the whole archive twice per
call by design (`read_verified_entry`'s docstring explains why), which costs
seconds per hit. Searching does not touch the archive at all, so plain
searching stays fast.
"""
from __future__ import annotations

import argparse
import os
import sys
from pathlib import Path

from cohort.agents.openrouter import _load_dotenv
from cohort.sources.cbeta_fts import CbetaFtsIndex
from cohort.sources.cbeta_reader import CbetaArchiveError, CbetaReader
from cohort.sources.env import CBETA_V061_SHA256  # one definition; see docs/corpus.md

REPO_ROOT = Path(__file__).resolve().parent.parent


def main() -> None:
    _load_dotenv(REPO_ROOT / ".env")

    parser = argparse.ArgumentParser(description="Search the CBETA corpus.")
    parser.add_argument("query", help="exact character sequence to find")
    parser.add_argument("--limit", type=int, default=20, help="maximum hits (default 20)")
    parser.add_argument(
        "--collection", default=None,
        help="restrict to a CBETA collection prefix, e.g. T, X, J",
    )
    parser.add_argument(
        "--fetch", action="store_true",
        help="re-fetch each hit through the reader to prove the ref resolves (slow)",
    )
    parser.add_argument("--db", default=None, help="index path")
    args = parser.parse_args()

    archive_path = os.environ.get("CBETA_ARCHIVE_PATH")
    if not archive_path:
        print("config error: CBETA_ARCHIVE_PATH is not set (see docs/handoff.md)", file=sys.stderr)
        sys.exit(1)
    db_path = Path(
        args.db or os.environ.get("CBETA_FTS_PATH") or (REPO_ROOT / "cbeta_fts.sqlite")
    )

    try:
        index = CbetaFtsIndex(db_path, CBETA_V061_SHA256)
        reader = CbetaReader(archive_path, CBETA_V061_SHA256, fts=index)
    except CbetaArchiveError as e:
        print(f"error: {e}", file=sys.stderr)
        print("(build the index first: scripts/build_cbeta_index.py)", file=sys.stderr)
        sys.exit(1)

    # over-fetch when filtering by collection, so the filter does not starve
    # a limit the user asked for
    raw_limit = args.limit * 20 if args.collection else args.limit
    hits = reader.search(args.query, max_results=raw_limit)
    if args.collection:
        hits = [h for h in hits if h.title.startswith(args.collection)][: args.limit]

    if not hits:
        print(f"no hits for {args.query!r}")
        return

    print(f"{len(hits)} hit(s) for {args.query!r}\n")
    for hit in hits:
        print(f"  {hit.title:<14} {hit.snippet}")
        if args.fetch:
            try:
                record = reader.fetch(hit.ref)
                status = "ok" if (hit.snippet or "") in record.text else "MISSING FROM SOURCE"
                print(f"    fetch: {status} ({len(record.text)} chars, {record.locator})")
            except CbetaArchiveError as e:
                print(f"    fetch: FAILED — {e}")

    index.close()


if __name__ == "__main__":
    main()
