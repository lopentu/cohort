#!/usr/bin/env python3
"""Interactively create the one local researcher account (never pass a password argument)."""
from __future__ import annotations

import argparse
import getpass
import json
import os
import sys
import tempfile
from pathlib import Path

REPO_ROOT = Path(__file__).resolve().parents[1]
sys.path.insert(0, str(REPO_ROOT))


def main(argv: list[str] | None = None) -> None:
    parser = argparse.ArgumentParser(description=__doc__)
    parser.add_argument("--credentials", type=Path, default=REPO_ROOT / "data/ui-auth.json")
    parser.add_argument("--overwrite", action="store_true", help="explicitly replace an existing account")
    args = parser.parse_args(argv)
    if args.credentials.exists() and not args.overwrite:
        parser.error("credentials already exist; use --overwrite to replace the account")
    from cohort.ui.auth import credential_record

    username = input("Researcher username: ").strip()
    password = getpass.getpass("Password (at least 12 characters): ")
    confirmation = getpass.getpass("Confirm password: ")
    if password != confirmation:
        parser.error("passwords do not match")
    try:
        record = credential_record(username, password)
    except ValueError as exc:
        parser.error(str(exc))
    args.credentials.parent.mkdir(parents=True, exist_ok=True, mode=0o700)
    # Publish a fully written 0600 file atomically. Hard-link publication without
    # --overwrite refuses races; replacement never follows an existing symlink.
    temp_path = None
    try:
        with tempfile.NamedTemporaryFile(mode="w", encoding="utf-8", dir=args.credentials.parent,
                                         prefix=".ui-auth-", delete=False) as handle:
            temp_path = Path(handle.name)
            os.fchmod(handle.fileno(), 0o600)
            json.dump(record, handle)
            handle.write("\n")
            handle.flush()
            os.fsync(handle.fileno())
        if args.overwrite:
            os.replace(temp_path, args.credentials)
        else:
            os.link(temp_path, args.credentials)
    except OSError:
        parser.error("could not write credentials; check ownership and the destination")
    finally:
        if temp_path is not None:
            temp_path.unlink(missing_ok=True)
    print("Researcher account saved. Restart the UI server to apply account changes.")


if __name__ == "__main__":
    main()
