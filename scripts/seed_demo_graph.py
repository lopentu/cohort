"""Build a persistent demo graph from the real CBETA archive, for the UI to
show (build order stage 5).

Not a fixture: every witness and passage here is fetched and hash-verified
from the real archive, and the `parallel_of` edges are read out of CBETA's own
`<cb:docNumber>` cross-references by `link_parallels`. The graph therefore
contains a genuine instance of the thesis rather than a staged one — three
different Chinese translations of the Heart Sutra that all contain
色即是空，空即是色, whose agreement is shared descent rather than independent
confirmation.

No model call and no API key: everything here is mechanical. The one
hand-authored node is the conjecture, because `propose_conjecture`'s live
path against real text has not been exercised yet (see docs/handoff.md) and
inventing a model run would misrepresent what has been verified. Its dossier
fields are written as a researcher would write them, and it is left at
`proposed` — no `tests` edge, so the falsifiability gate would refuse to
attest it, which is exactly the state worth being able to see in the UI.

Usage:
    .venv/bin/python scripts/seed_demo_graph.py [--db demo_graph.sqlite] [--force]
"""
from __future__ import annotations

import argparse
import json
import os
import sys
from pathlib import Path

from cohort.agents.openrouter import _load_dotenv
from cohort.errors import SelfAttestation, UnattestableConjecture
from cohort.graph import Graph
from cohort.schemas import (
    RESEARCHER,
    AgentKind,
    AgentProfile,
    ClaimPayload,
    ConjecturePayload,
    Dating,
    DatingRoute,
    EdgeType,
    PassagePayload,
    QueryPayload,
    WitnessPayload,
)
from cohort.sources.cbeta_reader import CbetaArchiveError, CbetaReader
from cohort.sources.env import CBETA_V061_SHA256  # one definition; see docs/corpus.md
from cohort.tools.collate_editions import CollateEditionsInput, collate_editions
from cohort.tools.link_parallels import LinkParallelsInput, link_parallels
from cohort.tools.propose_claim import ProposeClaimInput, propose_claim
from cohort.tools.record_contradiction import (
    RecordContradictionInput,
    record_contradiction,
)
from cohort.tools.verify_exact_span import verify_exact_span

REPO_ROOT = Path(__file__).resolve().parent.parent

AGENT = "agent:worker-heart"
#: The demo graph now has two agents, because one cannot check its own work:
#: an agent may not attest a claim it authored, and a reviewer sharing its
#: model family is refused too. Both are registered with declared models so
#: the family check has something real to compare — a demo where the rule
#: could not fire would not be showing the rule.
REVIEWER = "agent:reviewer-heart"
WORKER_MODEL = "z-ai/glm-5.3"
REVIEWER_MODEL = "deepseek/deepseek-v4-flash"
EXCERPT = "色即是空，空即是色"
ENTRIES = [
    "Bookcase/CBETA/XML/T/T08/T08n0250_001.xml",
    "Bookcase/CBETA/XML/T/T08/T08n0251_001.xml",
    "Bookcase/CBETA/XML/T/T08/T08n0252_001.xml",
]


def main() -> None:
    parser = argparse.ArgumentParser(description=__doc__)
    parser.add_argument("--db", default=str(REPO_ROOT / "demo_graph.sqlite"))
    parser.add_argument("--force", action="store_true", help="replace an existing graph")
    args = parser.parse_args()

    _load_dotenv(REPO_ROOT / ".env")
    archive_path = os.environ.get("CBETA_ARCHIVE_PATH")
    if not archive_path:
        print("config error: CBETA_ARCHIVE_PATH is not set (see docs/handoff.md)", file=sys.stderr)
        sys.exit(1)

    index_path = REPO_ROOT / "cbeta_index.json"
    if not index_path.is_file():
        print(f"config error: no index at {index_path} (see docs/handoff.md)", file=sys.stderr)
        sys.exit(1)

    db_path = Path(args.db)
    log_path = db_path.with_suffix(".jsonl")
    if db_path.exists() or log_path.exists():
        if not args.force:
            print(f"{db_path} already exists; pass --force to replace it", file=sys.stderr)
            sys.exit(1)
        db_path.unlink(missing_ok=True)
        log_path.unlink(missing_ok=True)
        db_path.with_suffix(db_path.suffix + ".lock").unlink(missing_ok=True)

    try:
        source = CbetaReader(
            archive_path, CBETA_V061_SHA256,
            index=json.loads(index_path.read_text(encoding="utf-8")),
        )
    except CbetaArchiveError as e:
        print(f"archive error: {e}", file=sys.stderr)
        sys.exit(1)

    graph = Graph.open(db_path, log_path)
    graph.register_agent(
        AgentProfile(
            id=AGENT, kind=AgentKind.WORKER,
            corpus_scope="CBETA v061, Heart Sutra translations (T250, T251, T252)",
            method_label="direct textual attestation",
            model=WORKER_MODEL,
        ),
        authored_by=AGENT,
    )
    graph.register_agent(
        AgentProfile(
            id=REVIEWER, kind=AgentKind.REVIEWER,
            corpus_scope="CBETA v061, Heart Sutra translations (T250, T251, T252)",
            method_label="re-verification of cited spans",
            model=REVIEWER_MODEL,
        ),
        authored_by=REVIEWER,
    )

    claim_id = graph.propose_claim(
        ClaimPayload(text="Form is emptiness and emptiness is form"),
        authored_by=AGENT,
    )

    witnesses = []
    for entry in ENTRIES:
        record = source.fetch(f"{entry}::{EXCERPT}")
        witness_id = graph.propose_witness(
            WitnessPayload(
                canonical_ref=record.witness_ref, label=record.title,
                dating=Dating(
                    confidence=DatingRoute.UNKNOWN,
                    basis="not dated by this seed; no dating route was run",
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
        verify_exact_span(graph, source, passage_id, authored_by=AGENT)
        witnesses.append(witness_id)
        print(f"  attested {record.witness_ref}")

    for witness_id in witnesses:
        report = link_parallels(
            graph, source, LinkParallelsInput(witness_id=witness_id), authored_by=AGENT
        )
        collate_editions(
            graph, source, CollateEditionsInput(witness_id=witness_id), authored_by=AGENT
        )
        if report.linked:
            print(f"  {witness_id} parallel_of -> {', '.join(report.linked)}")

    # The worker gathered the evidence; a second agent on another provider is
    # what closes the rung. This is the author-is-not-reviewer rule, visible
    # in the demo graph's authorship trail rather than only in the tests.
    graph.attest(claim_id, authored_by=REVIEWER)
    graph.accept(claim_id, authored_by=RESEARCHER)

    # A conjecture the sources do not state outright, left unattested on
    # purpose: with no `tests` edge the falsifiability gate refuses it, and a
    # UI that cannot show that state is hiding the mechanism.
    conjecture_id = graph.propose_conjecture(
        ConjecturePayload(
            text=(
                "The three Chinese Heart Sutra translations descend from a shared "
                "Sanskrit recension rather than from one another"
            ),
            derivation=(
                "All three render the same passage with near-identical wording while "
                "differing in surrounding structure, and CBETA lists them as parallel texts"
            ),
            corpus_boundary="only T250, T251 and T252 were examined; no Sanskrit witness was consulted",
            selection_risks=(
                "the three texts were chosen because they share a phrase already known "
                "to the seeder, which is a biased sample of the Heart Sutra tradition"
            ),
            alternative_explanations=(
                "a later translator may have revised an earlier Chinese version directly, "
                "producing agreement without a shared Sanskrit parent"
            ),
        ),
        authored_by=AGENT,
    )
    query_id = graph.propose_query(
        QueryPayload(text="collate the three against an extant Sanskrit Prajnaparamita recension"),
        authored_by=AGENT,
    )
    graph.add_edge(EdgeType.SEARCHED_FOR, query_id, conjecture_id, authored_by=AGENT)

    # A recorded disagreement. `contradicts` has been in the vocabulary since
    # stage 1 and the UI draws it as heavily as `attests`, but until
    # `record_contradiction` existed nothing ever wrote one, so the "disagreement
    # made visible" half of docs/design.md §6 had no data behind it in any view.
    # This claim genuinely conflicts with the conjecture above: if the phrase was
    # already fixed in Chinese before the recensions split, they are not
    # independent descendants of a Sanskrit parent.
    rival_claim_id = propose_claim(
        graph, source,
        ProposeClaimInput(
            text=(
                "The shared wording of this passage was fixed in Chinese before the "
                "three recensions diverged, so their agreement is inherited"
            ),
            grounding_query=EXCERPT,
        ),
        authored_by=AGENT,
    )
    record_contradiction(
        graph,
        RecordContradictionInput(
            node_a_id=rival_claim_id, node_b_id=conjecture_id,
            reason=(
                "Both cannot hold: inherited Chinese wording explains the agreement "
                "without a shared Sanskrit parent, while descent from a common "
                "Sanskrit recension requires the agreement to predate the Chinese "
                "translations. They make incompatible predictions about whether an "
                "extant Sanskrit witness will match all three."
            ),
        ),
        authored_by=AGENT,
    )
    print(f"  contradicts: {rival_claim_id} <-> {conjecture_id}")

    # A refusal, on purpose: the conjecture above has no `tests` edge, so the
    # falsifiability gate must refuse to attest it. The refused write is logged
    # and shows up in the UI's "refused writes" panel — docs/design.md §15 counts
    # refusals as output, and a demo graph with none would understate what the
    # system does.
    # Two refusals, on purpose, because they are refused for different reasons
    # and the panel should show both: the author cannot close its own rung, and
    # even the reviewer cannot, because the falsifiability gate outranks review.
    try:
        graph.attest(conjecture_id, authored_by=AGENT)
    except SelfAttestation as e:
        print(f"  refused (as designed): {type(e).__name__}")
    try:
        graph.attest(conjecture_id, authored_by=REVIEWER)
    except UnattestableConjecture as e:
        print(f"  refused (as designed): {type(e).__name__}")

    support = graph.independent_support(claim_id)
    integrity = graph.verify_integrity()
    graph.close()

    print(
        f"\nseeded {db_path}\n"
        f"  attesting_count = {support.attesting_count}, "
        f"independent = {support.independent} "
        f"({len(support.non_independent_pairs)} non-independent pairs)\n"
        f"  integrity: {integrity.checked} rows, {len(integrity.mismatched)} mismatched\n\n"
        f"serve it:  .venv/bin/python scripts/serve_ui.py --db {db_path}"
    )


if __name__ == "__main__":
    main()
