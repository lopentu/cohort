"""Recording a claim's numbers so they can be re-derived rather than trusted.

The asymmetry is the design: a first measurement proves nothing the claim's
author could not have typed by hand, so it is `INDETERMINATE`. A second one,
over the same works and the same base edition, either reproduces it exactly or
it does not — and if it does not, the corpus, the catalogue, the floor or the
counting moved, and none of those announce themselves.
"""
from __future__ import annotations

import pytest

from cohort.catalogue import load_catalogue
from cohort.errors import WrongNodeType
from cohort.schemas import (
    AssuranceLevel,
    ClaimPayload,
    Dating,
    DatingRoute,
    VerificationMethod,
    VerificationResult,
    WitnessPayload,
)
from cohort.sources.radich_reader import RadichReader
from cohort.tools.measure_claim import MeasureClaimInput, fingerprint, measure_claim
from cohort.measure import measure_feature

AGENT = "agent:worker-1"
LONG = "阿黎耶識" + "文" * 6_000
LONGER = "文" * 20_000


@pytest.fixture
def corpus(tmp_path):
    layout = {
        "T0001": {"大": LONG, "元": LONG},
        "T0002": {"大": LONGER},
        "T0003": {"大": LONG},
    }
    for work, editions in layout.items():
        d = tmp_path / "corpus" / work
        d.mkdir(parents=True)
        for edition, text in editions.items():
            (d / f"{edition}.txt").write_text(text, encoding="utf-8")
    r = RadichReader(tmp_path / "corpus")
    yield r
    r.close()


@pytest.fixture
def catalogue(tmp_path):
    p = tmp_path / "cat.txt"
    p.write_text("T0001 bench\nT0002 bench\nT0003 control\n", encoding="utf-8")
    return load_catalogue(p, benchmark_label="bench", control_label="control")


@pytest.fixture
def claim(graph):
    return graph.propose_claim(ClaimPayload(text="a feature claim"), authored_by=AGENT)


def run(graph, corpus, catalogue, claim, **over):
    args = MeasureClaimInput(
        claim_or_conjecture_id=claim, feature=over.pop("feature", "阿黎耶識"), **over
    )
    return measure_claim(graph, corpus, args, catalogue=catalogue, authored_by=AGENT)


# --- baseline, then check ----------------------------------------------------

def test_the_first_measurement_is_indeterminate_not_a_pass(graph, corpus, catalogue, claim):
    """It says only what the numbers are, which is what the author could
    already have asserted. Calling that a pass would let a claim verify itself
    by being measured once."""
    out = run(graph, corpus, catalogue, claim)
    assert out["result"] == VerificationResult.INDETERMINATE
    assert "nothing yet to compare" in graph.get_node(out["verification_id"]).payload["detail"]


def test_a_second_run_over_the_same_corpus_passes(graph, corpus, catalogue, claim):
    run(graph, corpus, catalogue, claim)
    out = run(graph, corpus, catalogue, claim)
    assert out["result"] == VerificationResult.PASS
    assert "reproduce exactly" in graph.get_node(out["verification_id"]).payload["detail"]


def test_a_changed_floor_is_caught_as_a_failure(graph, corpus, catalogue, claim):
    """The floor decides which works are measurable at all, so moving it
    changes every group tally. A claim whose numbers were computed under one
    floor does not hold under another, and saying so is the point."""
    run(graph, corpus, catalogue, claim)
    out = run(graph, corpus, catalogue, claim, min_chars=10)
    assert out["result"] == VerificationResult.FAIL
    assert "no longer reproduce" in graph.get_node(out["verification_id"]).payload["detail"]


def test_a_changed_corpus_is_caught_as_a_failure(graph, corpus, catalogue, claim, tmp_path):
    """The case this exists for: the bytes underneath moved and nothing said so."""
    run(graph, corpus, catalogue, claim)
    (tmp_path / "corpus" / "T0002" / "大.txt").write_text(LONG, encoding="utf-8")
    with RadichReader(tmp_path / "corpus") as fresh:
        out = run(graph, fresh, catalogue, claim)
    assert out["result"] == VerificationResult.FAIL


# --- what it will not do -----------------------------------------------------

def test_it_grants_no_rung_on_the_ladder(graph, corpus, catalogue, claim):
    """The ladder grades how well a node's *citations* stand up. A feature
    count says something else, and a claim whose numbers reproduce is not
    thereby better cited — the A3 mistake, of grading one thing with a name
    that reads as another."""
    run(graph, corpus, catalogue, claim)
    run(graph, corpus, catalogue, claim)
    assert graph.assurance_for(claim) == AssuranceLevel.A0_UNCHECKED


def test_it_reports_counts_and_refuses_to_call_them_discriminating(graph, corpus, catalogue, claim):
    """A verification that returned a verdict off a contingency table would be
    the confident sentence in the machine's field that the negative control
    caught on 2026-09-02."""
    out = run(graph, corpus, catalogue, claim)
    payload = graph.get_node(out["verification_id"]).payload
    assert "Counts, not a verdict" in payload["limitations"]
    assert "transmissional, not" in payload["limitations"]
    for word in ("discriminates", "confirms", "proves", "likely"):
        assert word not in payload["detail"].lower()


def test_only_an_assertion_can_be_measured(graph, corpus, catalogue):
    """Measuring a passage would record a number about the corpus with nothing
    staked on it."""
    w = graph.propose_witness(
        WitnessPayload(
            canonical_ref="T0001/大",
            dating=Dating(confidence=DatingRoute.UNKNOWN, basis="not dated for this test"),
        ),
        authored_by=AGENT,
    )
    with pytest.raises(WrongNodeType, match="only a claim or"):
        run(graph, corpus, catalogue, w)


# --- the fingerprint ---------------------------------------------------------

def test_the_fingerprint_depends_on_the_numbers_not_on_dict_order(corpus, catalogue):
    labels = dict(catalogue.entries)
    a = measure_feature(corpus, "阿黎耶識", labels=labels, works=catalogue.works())
    b = measure_feature(corpus, "阿黎耶識", labels=labels, works=catalogue.works())
    assert fingerprint(a) == fingerprint(b)
    c = measure_feature(corpus, "阿黎耶識", labels=labels, works=catalogue.works(), min_chars=10)
    assert fingerprint(c) != fingerprint(a)


def test_it_is_stored_where_a_later_run_can_find_it(graph, corpus, catalogue, claim):
    out = run(graph, corpus, catalogue, claim)
    payload = graph.get_node(out["verification_id"]).payload
    assert payload["method"] == VerificationMethod.CORPUS_MEASUREMENT
    assert payload["excerpt_hash"] == out["fingerprint"]


def test_two_features_keep_separate_baselines(graph, corpus, catalogue, claim):
    """A node may carry measurements of several features. Comparing a count of
    one phrase against the baseline of another would fail every time while
    looking like a finding."""
    run(graph, corpus, catalogue, claim, feature="阿黎耶識")
    other = run(graph, corpus, catalogue, claim, feature="文")
    assert other["result"] == VerificationResult.INDETERMINATE, "its own baseline"
    again = run(graph, corpus, catalogue, claim, feature="阿黎耶識")
    assert again["result"] == VerificationResult.PASS, "the first one still compares"


def test_a_catalogue_the_corpus_cannot_satisfy_is_refused(graph, corpus, catalogue, claim, tmp_path):
    from cohort.catalogue import CatalogueError, load_catalogue as load

    p = tmp_path / "bad.txt"
    p.write_text("T0001 bench\nT9999 bench\n", encoding="utf-8")
    with pytest.raises(CatalogueError, match="T9999"):
        measure_claim(
            graph, corpus,
            MeasureClaimInput(claim_or_conjecture_id=claim, feature="阿黎耶識"),
            catalogue=load(p), authored_by=AGENT,
        )
