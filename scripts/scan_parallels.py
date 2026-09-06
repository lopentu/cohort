"""Corpus-wide validation of the `<cb:docNumber>` parser (read-only, no API).

`cohort/sources/cbeta_markup.py` was developed against roughly 120 real
cross-reference strings. This runs it over every entry in the archive and
writes three artifacts:

- `parallel_map.jsonl`  — one record per entry carrying cross-references
- `unparsed.txt`        — every distinct bracket the parser declined, deduped,
                          with a count and one example entry each
- `summary.txt`         — tallies, including the `<note type="cf*">` channel
                          docs/handoff.md flags as unexplored

The point is the second file. A parser that silently half-reads a reference
list would mint false `parallel_of` edges, and `parallel_of` suppresses
independent support — so the declined cases are the ones worth a human eye,
and they are written out in full rather than counted and discarded.

Safe to run detached (`setsid nohup ...`): it only reads the archive and
writes into its own output directory.

Usage:
    .venv/bin/python scripts/scan_parallels.py [--out DIR] [--limit N]
"""
from __future__ import annotations

import argparse
import json
import os
import re
import sys
import time
import zipfile
from collections import Counter
from pathlib import Path

from cohort.agents.openrouter import _load_dotenv
from cohort.sources.cbeta_markup import parse_parallel_refs
from cohort.sources.cbeta_reader import (
    CBETA_ENTRY_PREFIX,
    CbetaArchiveError,
    find_text_content_start,
    verify_archive_hash,
)

from cohort.sources.env import CBETA_V061_SHA256  # one definition; see docs/corpus.md
REPO_ROOT = Path(__file__).resolve().parent.parent

_T_REF_RE = re.compile(r"^T(\d+)n0*(\d+[A-Za-z]?)$")
_CBETA_REF_RE = re.compile(r"([A-Z]{1,2}\d+n[A-Za-z]?\d+[A-Za-z]?)")
_NOTE_CF_RE = re.compile(r'<note[^>]*\btype="(cf\d*|cf\.)"')


def _taisho_map(names: list[str]) -> dict[str, set[str]]:
    idx: dict[str, set[str]] = {}
    for name in names:
        match = _CBETA_REF_RE.search(Path(name).name)
        if not match:
            continue
        parts = _T_REF_RE.match(match.group(1))
        if parts:
            idx.setdefault(parts.group(2).lower(), set()).add(match.group(1))
    return idx


def main() -> None:
    _load_dotenv(REPO_ROOT / ".env")
    parser = argparse.ArgumentParser(description=__doc__)
    parser.add_argument("--out", default=str(Path.home() / "cbeta_scan"))
    parser.add_argument("--limit", type=int, default=None)
    args = parser.parse_args()

    archive_path = os.environ.get("CBETA_ARCHIVE_PATH")
    if not archive_path:
        print("config error: CBETA_ARCHIVE_PATH is not set", file=sys.stderr)
        sys.exit(1)

    out_dir = Path(args.out)
    out_dir.mkdir(parents=True, exist_ok=True)

    started = time.monotonic()
    print("verifying archive hash...", flush=True)
    try:
        verify_archive_hash(Path(archive_path), CBETA_V061_SHA256)
    except CbetaArchiveError as e:
        print(f"archive error: {e}", file=sys.stderr)
        sys.exit(1)

    zf = zipfile.ZipFile(archive_path)
    all_names = sorted(
        n for n in zf.namelist()
        if n.startswith(CBETA_ENTRY_PREFIX) and n.endswith(".xml")
    )
    # the resolution map is always built from the whole archive: `--limit`
    # restricts what is scanned, not what a reference may resolve to, or a
    # trial run would report spurious "unknown" numbers.
    taisho = _taisho_map(all_names)
    names = all_names if args.limit is None else all_names[: args.limit]
    print(
        f"{len(names)} of {len(all_names)} entries to scan; "
        f"{len(taisho)} distinct Taisho numbers in the resolution map",
        flush=True,
    )

    unparsed: Counter[str] = Counter()
    unparsed_example: dict[str, str] = {}
    note_cf_types: Counter[str] = Counter()
    stats = Counter()
    resolved_pairs = 0
    ambiguous: Counter[str] = Counter()
    unknown: Counter[str] = Counter()

    map_path = out_dir / "parallel_map.jsonl"
    with map_path.open("w", encoding="utf-8") as fh:
        for i, name in enumerate(names, 1):
            data = zf.read(name)
            try:
                body = data[find_text_content_start(data):].decode("utf-8")
            except (CbetaArchiveError, UnicodeDecodeError):
                stats["entries_unreadable"] += 1
                continue
            stats["entries_read"] += 1

            for t in _NOTE_CF_RE.findall(body):
                note_cf_types[t] += 1

            refs = parse_parallel_refs(body)
            if not (refs.asserted or refs.compare_only or refs.part_of or refs.unparsed):
                continue
            stats["entries_with_refs"] += 1
            stats["asserted"] += len(refs.asserted)
            stats["compare_only"] += len(refs.compare_only)
            stats["part_of"] += len(refs.part_of)

            for bracket in refs.unparsed:
                unparsed[bracket] += 1
                unparsed_example.setdefault(bracket, name)

            resolved: list[str] = []
            for ref in refs.asserted:
                candidates = sorted(taisho.get(ref.number.lower(), set()))
                if not candidates:
                    stripped = ref.number.lower().rstrip("abcdefghijklmnopqrstuvwxyz")
                    candidates = sorted({
                        r for k, v in taisho.items()
                        if k.rstrip("abcdefghijklmnopqrstuvwxyz") == stripped for r in v
                    })
                if len(candidates) == 1:
                    resolved.append(candidates[0])
                    resolved_pairs += 1
                elif candidates:
                    ambiguous[ref.number] += 1
                else:
                    unknown[ref.number] += 1

            fh.write(json.dumps({
                "entry": name,
                "self_number": refs.self_number,
                "asserted": [r.model_dump() for r in refs.asserted],
                "resolved_witness_refs": resolved,
                "compare_only": [r.model_dump() for r in refs.compare_only],
                "part_of": [r.model_dump() for r in refs.part_of],
                "unparsed": refs.unparsed,
            }, ensure_ascii=False) + "\n")

            if i % 2500 == 0:
                print(f"  {i}/{len(names)}  {time.monotonic()-started:.0f}s", flush=True)

    with (out_dir / "unparsed.txt").open("w", encoding="utf-8") as fh:
        fh.write(f"# {len(unparsed)} distinct bracket(s) the parser declined\n")
        fh.write("# Each is reported rather than half-read: see cbeta_markup.py.\n\n")
        for bracket, count in unparsed.most_common():
            fh.write(f"[x{count}] {unparsed_example[bracket]}\n    {bracket}\n\n")

    lines = [
        f"elapsed: {time.monotonic()-started:.1f}s",
        f"entries read           : {stats['entries_read']}",
        f"entries unreadable     : {stats['entries_unreadable']}",
        f"entries with refs      : {stats['entries_with_refs']}",
        f"asserted references    : {stats['asserted']}",
        f"  resolved 1:1         : {resolved_pairs}",
        f"  ambiguous (declined) : {sum(ambiguous.values())} over {len(ambiguous)} numbers",
        f"  unknown  (declined)  : {sum(unknown.values())} over {len(unknown)} numbers",
        f"compare_only (cf.)     : {stats['compare_only']}",
        f"part_of                : {stats['part_of']}",
        f"distinct unparsed      : {len(unparsed)} (total {sum(unparsed.values())})",
        "",
        "<note type=cf*> channel:",
        *(f"  {t:<6} {c}" for t, c in note_cf_types.most_common()),
        "",
        f"most ambiguous numbers : {ambiguous.most_common(10)}",
        f"most unknown numbers   : {unknown.most_common(10)}",
    ]
    summary = "\n".join(lines)
    (out_dir / "summary.txt").write_text(summary + "\n", encoding="utf-8")
    print("\n" + summary, flush=True)
    print(f"\nwrote {map_path}, unparsed.txt, summary.txt in {out_dir}", flush=True)


if __name__ == "__main__":
    main()
