"""Stage 4 tools: link_parallels and collate_editions, against a synthetic
CBETA archive (no corpus bytes in this repository — docs/handoff.md's rule).

The fixture holds three Taisho texts wired like the real Heart Sutra group:
T08n0251 lists 250 and 252 as parallels and 1712 as a mere `cf.`, so the
tests can check both what gets written and what deliberately does not.
"""
from __future__ import annotations

import hashlib
import zipfile
from io import BytesIO

import pytest

from cohort.errors import NodeNotFound, SourceRefMissing, WrongNodeType
from cohort.schemas import (
    AssuranceLevel,
    ClaimPayload,
    Dating,
    DatingRoute,
    EdgeType,
    PassagePayload,
    VerificationMethod,
    VerificationResult,
    WitnessPayload,
)
from cohort.sources.cbeta_reader import CbetaReader
from cohort.tools.collate_editions import CollateEditionsInput, collate_editions
from cohort.tools.link_parallels import LinkParallelsInput, link_parallels

AGENT = "agent:worker-1"

PREFIX = "Bookcase/CBETA/XML/T"
ENTRY_251 = f"{PREFIX}/T08/T08n0251_001.xml"
ENTRY_250 = f"{PREFIX}/T08/T08n0250_001.xml"
ENTRY_252 = f"{PREFIX}/T08/T08n0252_001.xml"


def _document(docnumber: str, body: str, apparatus: str = "") -> bytes:
    return (
        '<?xml version="1.0" encoding="UTF-8"?>\n'
        "<TEI><teiHeader><fileDesc>synthetic fixture</fileDesc></teiHeader>"
        f"<text><cb:docNumber>{docnumber}</cb:docNumber>{apparatus}"
        f"<p>{body}</p></text></TEI>\n"
    ).encode("utf-8")


APPARATUS = (
    '<app n="0001"><lem wit="【大】">A</lem>'
    '<rdg wit="【宋】 【元】 【明】" resp="Taisho">B</rdg></app>'
    '<app n="0002"><lem wit="【CB】" resp="CBETA.maha">C</lem>'
    '<rdg wit="【金藏】">D</rdg></app>'
)

ENTRIES = {
    # asserted parallels 250 and 252; 1712 only as `cf.`
    ENTRY_251: _document("No. 251 [Nos. 250, 252; cf. No. 1712]", "ALPHA", APPARATUS),
    ENTRY_250: _document("No. 250 [No. 251]", "BETA"),
    ENTRY_252: _document("No. 252 [No. 251]", "GAMMA"),
}


@pytest.fixture
def source(tmp_path):
    buf = BytesIO()
    with zipfile.ZipFile(buf, "w") as zf:
        for name, data in ENTRIES.items():
            zf.writestr(name, data)
    raw = buf.getvalue()
    path = tmp_path / "synthetic-cbeta.zip"
    path.write_bytes(raw)
    return CbetaReader(
        path, hashlib.sha256(raw).hexdigest(),
        index={ENTRY_251: ["ALPHA"], ENTRY_250: ["BETA"], ENTRY_252: ["GAMMA"]},
    )


def _add_witness(graph, source, entry_path, excerpt):
    """Mirror what find_attestations does: witness + passage carrying a
    source_ref, which is what both stage 4 tools re-fetch through."""
    record = source.fetch(f"{entry_path}::{excerpt}")
    witness_id = graph.propose_witness(
        WitnessPayload(
            canonical_ref=record.witness_ref, label=record.title,
            dating=Dating(confidence=DatingRoute.UNKNOWN, basis="not dated for this test"),
            source_terms=record.note,
        ),
        authored_by=AGENT,
    )
    passage_id = graph.propose_passage(
        PassagePayload(
            canonical_ref=f"{record.witness_ref}#{excerpt}",
            locator=record.locator or entry_path, excerpt=excerpt,
            source_ref=f"{entry_path}::{excerpt}",
        ),
        witness_id=witness_id, authored_by=AGENT,
    )
    return witness_id, passage_id


# --- link_parallels ----------------------------------------------------------

def test_links_only_witnesses_already_in_the_graph(graph, source):
    w251, _ = _add_witness(graph, source, ENTRY_251, "ALPHA")
    w250, _ = _add_witness(graph, source, ENTRY_250, "BETA")
    # 252 is asserted by the markup but never fetched, so it is not in the graph

    report = link_parallels(
        graph, source, LinkParallelsInput(witness_id=w251), authored_by=AGENT
    )
    assert report.linked == ["T08n0250"]
    assert report.absent_from_graph == ["T08n0252"]
    assert graph.edges(edge_type=EdgeType.PARALLEL_OF, src=w251, dst=w250)


def test_absent_parallel_is_not_invented_as_a_witness_node(graph, source):
    w251, _ = _add_witness(graph, source, ENTRY_251, "ALPHA")
    link_parallels(graph, source, LinkParallelsInput(witness_id=w251), authored_by=AGENT)
    # reporting a candidate must not have created an unevidenced node
    with pytest.raises(NodeNotFound):
        graph.get_node("witness:T08n0252")


def test_cf_reference_never_becomes_an_edge(graph, source):
    w251, _ = _add_witness(graph, source, ENTRY_251, "ALPHA")
    report = link_parallels(
        graph, source, LinkParallelsInput(witness_id=w251), authored_by=AGENT
    )
    assert report.not_asserted["compare_only"] == ["1712"]
    assert "1712" not in report.linked


def test_rerunning_is_idempotent(graph, source):
    w251, _ = _add_witness(graph, source, ENTRY_251, "ALPHA")
    _add_witness(graph, source, ENTRY_250, "BETA")
    link_parallels(graph, source, LinkParallelsInput(witness_id=w251), authored_by=AGENT)
    second = link_parallels(
        graph, source, LinkParallelsInput(witness_id=w251), authored_by=AGENT
    )
    assert second.linked == []
    assert second.already_linked == ["T08n0250"]
    assert len(graph.edges(edge_type=EdgeType.PARALLEL_OF, src=w251)) == 1


def test_parallel_edge_flips_independent_support(graph, source):
    """The payoff: two witnesses the corpus itself calls parallel stop
    counting as independent confirmation of the same claim."""
    w251, p251 = _add_witness(graph, source, ENTRY_251, "ALPHA")
    _w250, p250 = _add_witness(graph, source, ENTRY_250, "BETA")
    claim_id = graph.propose_claim(ClaimPayload(text="a claim"), authored_by=AGENT)
    graph.add_edge(EdgeType.ATTESTS, p251, claim_id, authored_by=AGENT)
    graph.add_edge(EdgeType.ATTESTS, p250, claim_id, authored_by=AGENT)

    before = graph.independent_support(claim_id)
    assert before.independent is True
    assert before.attesting_count == 2

    link_parallels(graph, source, LinkParallelsInput(witness_id=w251), authored_by=AGENT)

    after = graph.independent_support(claim_id)
    assert after.independent is False
    assert after.attesting_count == 2  # count unchanged; only independence flips
    assert after.non_independent_pairs


def test_refuses_a_non_witness_target(graph, source):
    _, passage_id = _add_witness(graph, source, ENTRY_251, "ALPHA")
    with pytest.raises(WrongNodeType, match="not a witness"):
        link_parallels(
            graph, source, LinkParallelsInput(witness_id=passage_id), authored_by=AGENT
        )


def test_witness_without_a_source_ref_is_refused(graph, source):
    witness_id = graph.propose_witness(
        WitnessPayload(
            canonical_ref="T08n0999",
            dating=Dating(confidence=DatingRoute.UNKNOWN, basis="not dated for this test"),
        ),
        authored_by=AGENT,
    )
    with pytest.raises(SourceRefMissing, match="no passage carrying a source_ref"):
        link_parallels(
            graph, source, LinkParallelsInput(witness_id=witness_id), authored_by=AGENT
        )


# --- collate_editions --------------------------------------------------------

def test_collation_records_edition_families_without_splitting_them(graph, source):
    w251, _ = _add_witness(graph, source, ENTRY_251, "ALPHA")
    vid = collate_editions(
        graph, source, CollateEditionsInput(witness_id=w251), authored_by=AGENT
    )
    payload = graph.get_node(vid).payload
    assert payload["method"] == VerificationMethod.CROSS_EDITION_COLLATION
    assert payload["result"] == VerificationResult.PASS
    assert "【宋】 【元】 【明】" in payload["detail"]
    assert "Joint (shared-descent) groups" in payload["detail"]


def test_collation_flags_editorial_emendations(graph, source):
    w251, _ = _add_witness(graph, source, ENTRY_251, "ALPHA")
    vid = collate_editions(
        graph, source, CollateEditionsInput(witness_id=w251), authored_by=AGENT
    )
    assert "editorial emendation" in graph.get_node(vid).payload["detail"]


def test_collation_always_states_its_limitations(graph, source):
    """The rung says edition support, not independence — but the boundary is
    still worth stating on every record, because a reader who sees a witness
    at A3 beside a support count could still join the two into a claim about
    cross-witness independence that nothing here checked."""
    w251, _ = _add_witness(graph, source, ENTRY_251, "ALPHA")
    vid = collate_editions(
        graph, source, CollateEditionsInput(witness_id=w251), authored_by=AGENT
    )
    limitations = graph.get_node(vid).payload["limitations"]
    assert "says nothing about" in limitations
    assert "independent_support()" in limitations


def test_collation_is_indeterminate_without_apparatus(graph, source):
    w250, _ = _add_witness(graph, source, ENTRY_250, "BETA")  # fixture has no <app>
    vid = collate_editions(
        graph, source, CollateEditionsInput(witness_id=w250), authored_by=AGENT
    )
    payload = graph.get_node(vid).payload
    assert payload["result"] == VerificationResult.INDETERMINATE
    assert payload["assurance_level"] == AssuranceLevel.A0_UNCHECKED
    # an indeterminate result grants no assurance
    assert graph.assurance_for(w250) == AssuranceLevel.A0_UNCHECKED


def test_passing_collation_grants_edition_support_assurance(graph, source):
    w251, _ = _add_witness(graph, source, ENTRY_251, "ALPHA")
    collate_editions(
        graph, source, CollateEditionsInput(witness_id=w251), authored_by=AGENT
    )
    assert graph.assurance_for(w251) == AssuranceLevel.A3_EDITION_SUPPORT_CHECKED
