"""Write the LocalReader manifest for Radich's corpus.

Usage:
    uv run python scripts/radich_manifest.py data/radich [--all]

Then set LOCAL_CORPUS_ROOT=data/radich/corpus/T-stripped in .env and start the
UI with --corpus (and --allow-runs for agents).
"""

from __future__ import annotations

import argparse

from cohort.sources.radich_manifest import write_manifest


def main() -> None:
    parser = argparse.ArgumentParser(description=__doc__)
    parser.add_argument("root", help="the Radich data folder (holds the catalogue and corpus/)")
    parser.add_argument("--all", action="store_true", help="list units outside the catalogue too")
    args = parser.parse_args()
    ledger = write_manifest(args.root, include_uncatalogued=args.all)
    for k, v in ledger.items():
        print(f"{k:<32}{v:>7}")


if __name__ == "__main__":
    main()
