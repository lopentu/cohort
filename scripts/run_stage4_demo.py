"""Manual live demonstration of stage 4 against the real CBETA archive:
shared descent recognised, and consensus refused.

The case is the Heart Sutra. T08n0250, T08n0251 and T08n0252 are three
*different* Chinese translations, and all three contain the identical phrase
色即是空，空即是色. A verification model imported from fact-checking counts
that as three independent confirmations. It is not: CBETA's own
`<cb:docNumber>` lists them as parallel texts, and they descend from a shared
Sanskrit original, so their agreement is evidence of common descent rather
than independent support. That is docs/design.md §4's thesis, and this script shows
COHORT reaching that conclusion from the corpus's own markup — not from a
hand-added edge, as `demo.py` necessarily does with no corpus present.

No API key and no model call: every step here is mechanical. Requires only
CBETA_ARCHIVE_PATH in `.env` and a `cbeta_index.json` naming the three
entries (see docs/handoff.md).

Usage:
    .venv/bin/python scripts/run_stage4_demo.py
"""
from __future__ import annotations

import json
import os
import sys
import tempfile
from pathlib import Path

from cohort.agents.openrouter import _load_dotenv
from cohort.graph import Graph
from cohort.schemas import (
    ClaimPayload,
    Dating,
    DatingRoute,
    EdgeType,
    PassagePayload,
    WitnessPayload,
)
from cohort.sources.cbeta_reader import CbetaArchiveError, CbetaReader
from cohort.sources.env import CBETA_V061_SHA256  # one definition; see docs/corpus.md
from cohort.tools.collate_editions import CollateEditionsInput, collate_editions
from cohort.tools.link_parallels import LinkParallelsInput, link_parallels

REPO_ROOT = Path(__file__).resolve().parent.parent
INDEX_PATH = REPO_ROOT / "cbeta_index.json"

AGENT = "agent:worker-stage4"
EXCERPT = "色即是空，空即是色"
HEART_SUTRA_ENTRIES = [
    "Bookcase/CBETA/XML/T/T08/T08n0250_001.xml",
    "Bookcase/CBETA/XML/T/T08/T08n0251_001.xml",
    "Bookcase/CBETA/XML/T/T08/T08n0252_001.xml",
]


def main() -> None:
    _load_dotenv(REPO_ROOT / ".env")
    archive_path = os.environ.get("CBETA_ARCHIVE_PATH")
    if not archive_path:
        print("config error: CBETA_ARCHIVE_PATH is not set (see docs/handoff.md)", file=sys.stderr)
        sys.exit(1)
    if not INDEX_PATH.is_file():
        print(f"config error: no index at {INDEX_PATH} (see docs/handoff.md)", file=sys.stderr)
        sys.exit(1)

    index = json.loads(INDEX_PATH.read_text(encoding="utf-8"))
    missing = [e for e in HEART_SUTRA_ENTRIES if e not in index]
    if missing:
        print(f"config error: cbeta_index.json is missing {missing}", file=sys.stderr)
        sys.exit(1)

    try:
        source = CbetaReader(archive_path, CBETA_V061_SHA256, index=index)
    except CbetaArchiveError as e:
        print(f"archive error: {e}", file=sys.stderr)
        sys.exit(1)

    with tempfile.TemporaryDirectory(prefix="cohort_stage4_demo_") as tmp:
        tmp_path = Path(tmp)
        graph = Graph.open(tmp_path / "graph.sqlite", tmp_path / "events.jsonl")

        claim_id = graph.propose_claim(
            ClaimPayload(text="Form is emptiness and emptiness is form"),
            authored_by=AGENT,
        )

        print("--- recording the same phrase from three different translations ---")
        witnesses = []
        for entry in HEART_SUTRA_ENTRIES:
            record = source.fetch(f"{entry}::{EXCERPT}")
            witness_id = graph.propose_witness(
                WitnessPayload(
                    canonical_ref=record.witness_ref, label=record.title,
                    dating=Dating(
                        confidence=DatingRoute.UNKNOWN,
                        basis="not dated by this demo; no dating route run",
                    ),
                    source_terms=record.note,
                ),
                authored_by=AGENT,
            )
            passage_id = graph.propose_passage(
                PassagePayload(
                    canonical_ref=f"{record.witness_ref}#{EXCERPT}",
                    locator=record.locator or entry, excerpt=EXCERPT,
                    source_ref=f"{entry}::{EXCERPT}",
                ),
                witness_id=witness_id, authored_by=AGENT,
            )
            graph.attest(passage_id, authored_by=AGENT)
            graph.add_edge(EdgeType.ATTESTS, passage_id, claim_id, authored_by=AGENT)
            witnesses.append(witness_id)
            print(f"  {record.witness_ref}: attested {EXCERPT!r}")

        support = graph.independent_support(claim_id)
        print("\nBefore reading the corpus's own cross-references:")
        print(f"  attesting_count    = {support.attesting_count}")
        print(f"  distinct_witnesses = {support.distinct_witnesses}")
        print(f"  independent        = {support.independent}"
              "   <- three sources agree, so a consensus model stops here")

        print("\n--- link_parallels: what does CBETA itself say? ---")
        for witness_id in witnesses:
            report = link_parallels(
                graph, source, LinkParallelsInput(witness_id=witness_id), authored_by=AGENT
            )
            print(f"  {witness_id}")
            print(f"    linked            : {report.linked or '-'}")
            print(f"    already_linked    : {report.already_linked or '-'}")
            print(f"    absent_from_graph : {report.absent_from_graph or '-'}")
            if report.unresolved:
                print(f"    unresolved        : {report.unresolved}")
            weak = {k: v for k, v in report.not_asserted.items() if v}
            print(f"    not asserted      : {weak or '-'}")

        support = graph.independent_support(claim_id)
        print("\nAfter recording the parallels the corpus asserts:")
        print(f"  attesting_count    = {support.attesting_count}   (unchanged — nothing was retracted)")
        print(f"  distinct_witnesses = {support.distinct_witnesses}")
        print(f"  independent        = {support.independent}"
              "  <- agreement between parallel translations is shared descent")
        print(f"  non_independent_pairs = {len(support.non_independent_pairs)}")

        print("\n--- collate_editions: which editions stand behind each text? ---")
        for witness_id in witnesses:
            vid = collate_editions(
                graph, source, CollateEditionsInput(witness_id=witness_id), authored_by=AGENT
            )
            payload = graph.get_node(vid).payload
            print(f"  {witness_id} -> {payload['result']} / {payload['assurance_level']}")
            print(f"    {payload['detail'][:300]}")

        integrity = graph.verify_integrity()
        rebuild = graph.rebuild()
        print(f"\nintegrity: {integrity.checked} rows checked, "
              f"{len(integrity.mismatched)} mismatched")
        print(f"rebuild from event log: {'matches' if rebuild.ok else 'DIFFERS'} "
              f"({rebuild.events_replayed} events, {rebuild.nodes} nodes, {rebuild.edges} edges)")

        graph.close()


if __name__ == "__main__":
    main()
