"""COHORT demo — no corpus, no live API, no network (design doc §11; the
verification/agent-identity sections added under docs/roadmap.md "Scope
revision" need no corpus or API key either, since they operate on synthetic
refs and mocked-free graph calls).

Shows the single most important property of the system first: a claim's
attesting count stays the same while its independence flips to False the
instant a descent relation links its two supporting witnesses. That's the
three-line counter-argument to consensus-seeking (design doc §4).
"""
from __future__ import annotations

import tempfile
from pathlib import Path

from cohort.eventlog import read_events, summarize_model_calls
from cohort.graph import Graph
from cohort.schemas import (
    RESEARCHER,
    AgentKind,
    AgentProfile,
    AssuranceLevel,
    ClaimPayload,
    ConjecturePayload,
    Dating,
    DatingRoute,
    EdgeType,
    PassagePayload,
    QueryPayload,
    VerificationMethod,
    VerificationResult,
    WitnessPayload,
)

AGENT = "agent:demo-worker"
#: A second agent, because `attest()` refuses a self-attestation: the author
#: is the one party with an interest in the answer (cohort/graph.py
#: `_reviewer_conflict`). Neither demo agent declares a model, so the
#: model-family half of that rule has nothing to compare and stays quiet.
REVIEWER = "agent:demo-reviewer"


def main() -> None:
    with tempfile.TemporaryDirectory(prefix="cohort_demo_") as tmp:
        tmp_path = Path(tmp)
        g = Graph.open(tmp_path / "graph.sqlite", tmp_path / "events.jsonl")

        print("=== COHORT demo ===\n")

        w1 = g.propose_witness(
            WitnessPayload(
                canonical_ref="T01n0001",
                label="Taisho ed., vol. 1, no. 1",
                dating=Dating(
                    confidence=DatingRoute.SOURCE_LABEL,
                    basis="colophon states a Northern Song printing",
                ),
            ),
            authored_by=AGENT,
        )
        w2 = g.propose_witness(
            WitnessPayload(
                canonical_ref="T02n0002",
                label="Taisho ed., vol. 2, no. 2",
                dating=Dating(
                    confidence=DatingRoute.UNKNOWN,
                    basis="no colophon survives, date not assigned",
                ),
            ),
            authored_by=AGENT,
        )

        p1 = g.propose_passage(
            PassagePayload(canonical_ref="T01n0001p0001a12", locator="juan 1, line 12"),
            witness_id=w1, authored_by=AGENT,
        )
        p2 = g.propose_passage(
            PassagePayload(canonical_ref="T02n0002p0003b04", locator="juan 3, line 4"),
            witness_id=w2, authored_by=AGENT,
        )
        g.attest(p1, authored_by=AGENT)
        g.attest(p2, authored_by=AGENT)

        claim_id = g.propose_claim(
            ClaimPayload(text="This sutra was translated under the Yao Qin"),
            authored_by=AGENT,
        )
        g.add_edge(EdgeType.ATTESTS, p1, claim_id, authored_by=AGENT)
        g.add_edge(EdgeType.ATTESTS, p2, claim_id, authored_by=AGENT)
        g.attest(claim_id, authored_by=REVIEWER)

        support = g.independent_support(claim_id)
        print("Before any descent relation is recorded:")
        print(f"  attesting_count     = {support.attesting_count}")
        print(f"  distinct_witnesses  = {support.distinct_witnesses}")
        print(f"  independent         = {support.independent}\n")

        g.add_edge(EdgeType.DESCENDS_FROM, w2, w1, authored_by=AGENT)
        support = g.independent_support(claim_id)
        print("After recording that witness 2 descends from witness 1:")
        print(f"  attesting_count     = {support.attesting_count}   (unchanged)")
        print(f"  distinct_witnesses  = {support.distinct_witnesses}")
        print(f"  independent         = {support.independent}   <- the counter-argument to consensus-seeking\n")

        print("--- verification and assurance ---")
        verification_id = g.verify(
            claim_id, method=VerificationMethod.CROSS_EDITION_COLLATION,
            result=(VerificationResult.PASS if support.independent else VerificationResult.FAIL),
            assurance_level=AssuranceLevel.A3_EDITION_SUPPORT_CHECKED,
            detail=f"independent_support: independent={support.independent}, "
                   f"non_independent_pairs={support.non_independent_pairs}",
            authored_by=AGENT,
        )
        print(f"verify(claim, CROSS_EDITION_COLLATION) -> {g.get_node(verification_id).payload['result']}")
        print(f"assurance_for(claim) = {g.assurance_for(claim_id)}   "
              f"<- stays A0_UNCHECKED: the one verification attempt failed, so it grants nothing\n")

        decision_id = g.accept(claim_id, authored_by=RESEARCHER)
        citable_ids = {n.id for n in g.citable()}
        print(f"Researcher accepted the claim -> decision node {decision_id}")
        print(f"citable() now includes it: {claim_id in citable_ids}\n")

        print("--- the falsifiability gate ---")
        conjecture_id = g.propose_conjecture(
            ConjecturePayload(
                text="An earlier Kuchean recension underlies this passage",
                derivation="vocabulary in T01n0001p0001a12 matches Kuchean loanword patterns",
                corpus_boundary="only the two witnesses in this demo were examined",
                selection_risks="none identified",
                alternative_explanations="a later redactor independently chose similar vocabulary",
            ),
            authored_by=AGENT,
        )
        try:
            g.attest(conjecture_id, authored_by=REVIEWER)
        except Exception as e:
            print(f"attest(conjecture) with no tests edge refused: {type(e).__name__}: {e}")
        query_id = g.propose_query(
            QueryPayload(text="search Kuchean fragment catalogues for a parallel to T01n0001p0001a12"),
            authored_by=AGENT,
        )
        g.add_edge(EdgeType.TESTS, query_id, conjecture_id, authored_by=AGENT)
        g.attest(conjecture_id, authored_by=REVIEWER)
        print("attest(conjecture) succeeds once a tests edge names what would refute it\n")

        print("--- persistent rejection ---")
        w3 = g.propose_witness(
            WitnessPayload(
                canonical_ref="T99n9999",
                dating=Dating(confidence=DatingRoute.UNKNOWN, basis="no catalogue entry located"),
            ),
            authored_by=AGENT,
        )
        g.reject(w3, authored_by=RESEARCHER, reason="catalogue reference does not resolve to a real text")
        try:
            g.propose_witness(
                WitnessPayload(
                    canonical_ref="T99n9999",
                    dating=Dating(confidence=DatingRoute.UNKNOWN, basis="no catalogue entry located"),
                ),
                authored_by=AGENT,
            )
        except Exception as e:
            print(f"re-proposing a rejected witness is refused: {type(e).__name__}: {e}\n")

        print("--- persistent rejection for content with no identity to block on ---")
        bad_conjecture_id = g.propose_conjecture(
            ConjecturePayload(
                text="An earlier Kuchean recension underlies this passage",
                derivation="vocabulary in T01n0001p0001a12 matches Kuchean loanword patterns",
                corpus_boundary="only the two witnesses in this demo were examined",
                selection_risks="none identified",
                alternative_explanations="a later redactor independently chose similar vocabulary",
            ),
            authored_by=AGENT,
        )
        g.reject(
            bad_conjecture_id, authored_by=RESEARCHER,
            reason="no Kuchean fragment catalogue exists for this text; unfalsifiable as stated",
        )
        print("a conjecture, reworded, has no canonical_ref to block re-proposal by id —")
        print("so a worker's own context has to carry the rejection instead:\n")
        for n in g.rejected(node_type="conjecture"):
            print(f"  [{n.type}] {n.payload['text']!r}")
            print(f"    reason: {n.rejected_reason}")
        print("(this is exactly what AttestationWorker.run() prepends to its instructions —")
        print(" see cohort/agents/attestation_worker.py::_rejected_context)\n")

        print("--- multi-agent identity and contribution history ---")
        g.register_agent(
            AgentProfile(
                id=AGENT, kind=AgentKind.WORKER,
                corpus_scope="T01n0001, T02n0002", method_label="philological/stemmatic",
            ),
            authored_by=AGENT,
        )
        second_agent = "agent:demo-worker-2"
        g.register_agent(
            AgentProfile(
                id=second_agent, kind=AgentKind.WORKER,
                corpus_scope="T99n9999 (uncatalogued)", method_label="doctrinal/thematic",
            ),
            authored_by=second_agent,
        )
        print(f"{AGENT} scope: {g.agent_profile(AGENT).corpus_scope} "
              f"({g.agent_profile(AGENT).method_label})")
        print(f"{second_agent} scope: {g.agent_profile(second_agent).corpus_scope} "
              f"({g.agent_profile(second_agent).method_label})")
        print("— declared viewpoint diversity, not agent count, is the point (docs/roadmap.md")
        print("  \"Scope revision\": this is what relaxing the agent-count anti-goal buys)\n")

        report = g.agent_report(AGENT)
        print(f"agent_report({AGENT!r}):")
        print(f"  proposed={report.proposed} attested={report.attested} "
              f"accepted={report.accepted} rejected={report.rejected}")
        print(f"  discount_edges_contributed={report.discount_edges_contributed}   "
              f"<- the descends_from edge recorded above; a count, never a score\n")

        print("--- rebuild from the event log ---")
        report = g.rebuild()
        print(
            f"rebuild: {report.events_replayed} events replayed, {report.nodes} nodes, "
            f"{report.edges} edges, matches live projection: {report.ok}\n"
        )

        refused = [e for e in read_events(tmp_path / "events.jsonl") if e.event == "refused"]
        print("--- honest log ---")
        print(f"{len(refused)} refused write(s) recorded in the log:")
        for e in refused:
            print(f"  {e.detail['attempted']} refused: {e.detail['rule']}")

        calls = summarize_model_calls(tmp_path / "events.jsonl")
        print(f"\n{calls.calls} model call(s) logged (this demo never calls a live model, so 0 is correct)")

        g.close()


if __name__ == "__main__":
    main()
