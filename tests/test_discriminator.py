"""Register a prediction, survive a control, then speak — in that order.

The order is the method, so most of these test the refusals. Run the control
first and a feature can fail; run it afterwards and the result is
unfalsifiable by construction, which is the shape of a great deal of
stylometric attribution and the reason its findings are hard to trust.
"""
from __future__ import annotations

import pytest

from cohort.catalogue import load_catalogue
from cohort.errors import ControlNotPassed, WrongNodeType
from cohort.ledger import ledger_json
from cohort.schemas import ClaimPayload, VerificationResult
from cohort.sources.radich_reader import RadichReader
from cohort.tools.discriminator import (
    RegisterDiscriminatorInput,
    apply_to_disputed,
    control_status,
    register_discriminator,
    run_control_test,
)

AGENT = "agent:worker-1"
MARK = "阿黎耶識"
FILLER = "文" * 8_000


def body(has_mark: bool) -> str:
    return (MARK if has_mark else "") + FILLER


@pytest.fixture
def corpus(tmp_path):
    layout = {
        # benchmark: three of four carry the mark
        "B1": body(True), "B2": body(True), "B3": body(True), "B4": body(False),
        # control: none do
        "C1": body(False), "C2": body(False),
        # disputed: one does
        "D1": body(True), "D2": body(False),
    }
    for work, text in layout.items():
        d = tmp_path / "corpus" / work
        d.mkdir(parents=True)
        (d / "大.txt").write_text(text, encoding="utf-8")
        (d / "元.txt").write_text(text, encoding="utf-8")
    r = RadichReader(tmp_path / "corpus")
    yield r
    r.close()


@pytest.fixture
def catalogue(tmp_path):
    p = tmp_path / "cat.txt"
    p.write_text(
        "B1 bench\nB2 bench\nB3 bench\nB4 bench\n"
        "C1 control\nC2 control\nD1 disputed\nD2 disputed\n",
        encoding="utf-8",
    )
    return load_catalogue(p, benchmark_label="bench", control_label="control")


def register(graph, catalogue, **over):
    args = dict(
        feature=MARK, min_benchmark_share=0.6, max_control_share=0.1,
        derivation="a rendering peculiar to this translator",
        corpus_boundary="the fixture corpus, base edition 大",
        selection_risks="chosen by hand, not sampled",
        alternative_explanations="may track subject matter rather than translator",
    )
    args.update(over)
    return register_discriminator(
        graph, RegisterDiscriminatorInput(**args), catalogue=catalogue, authored_by=AGENT,
    )


# --- the prediction goes on the record first --------------------------------

def test_the_prediction_is_written_in_the_call_that_creates_the_conjecture(graph, catalogue):
    """A prediction recorded in a second call is one that could have been
    written after a first look at the numbers."""
    out = register(graph, catalogue)
    query = graph.get_node(out["query_id"])
    assert query.payload["discrimination"]["feature"] == MARK
    assert query.payload["discrimination"]["min_benchmark_share"] == 0.6


def test_a_prediction_that_permits_no_contrast_is_refused(graph, catalogue):
    """A floor at or below the ceiling lets the feature be as common outside
    the group as inside it, which is not a discrimination."""
    with pytest.raises(WrongNodeType, match="not a discrimination"):
        register(graph, catalogue, min_benchmark_share=0.2, max_control_share=0.5)


def test_a_catalogue_without_a_control_cannot_register_one(graph, tmp_path):
    """A study with no group believed not to belong cannot fail."""
    p = tmp_path / "c.txt"
    p.write_text("B1 bench\n", encoding="utf-8")
    with pytest.raises(WrongNodeType, match="cannot fail"):
        register(graph, load_catalogue(p))


# --- the gate ----------------------------------------------------------------

def test_an_untested_feature_may_not_touch_a_disputed_work(graph, corpus, catalogue):
    out = register(graph, catalogue)
    assert control_status(graph, out["conjecture_id"]) == "untested"
    with pytest.raises(ControlNotPassed, match="untested"):
        apply_to_disputed(graph, corpus, out["conjecture_id"],
                          catalogue=catalogue, disputed_label="disputed")


def test_a_failed_feature_may_not_either(graph, corpus, catalogue):
    """The case that matters. A feature with a good story and a failed control
    is finished, and 'finished' has to be enforced rather than remembered."""
    out = register(graph, catalogue, min_benchmark_share=0.99)
    run_control_test(graph, corpus, out["conjecture_id"], catalogue=catalogue,
                     authored_by=AGENT)
    assert control_status(graph, out["conjecture_id"]) == "failed"
    with pytest.raises(ControlNotPassed, match="failed"):
        apply_to_disputed(graph, corpus, out["conjecture_id"],
                          catalogue=catalogue, disputed_label="disputed")


def test_a_survivor_may_be_applied(graph, corpus, catalogue):
    out = register(graph, catalogue)
    res = run_control_test(graph, corpus, out["conjecture_id"], catalogue=catalogue,
                           authored_by=AGENT)
    assert res["result"] == VerificationResult.PASS
    applied = apply_to_disputed(graph, corpus, out["conjecture_id"],
                                catalogue=catalogue, disputed_label="disputed")
    assert {r["work"]: r["attests"] for r in applied["works"]} == {"D1": True, "D2": False}


def test_the_latest_control_wins_not_the_best(graph, corpus, catalogue, tmp_path):
    """A feature that passed against an older corpus and fails against this one
    has failed — the bug that once let a superseded A2 outrank a later FAIL."""
    out = register(graph, catalogue)
    run_control_test(graph, corpus, out["conjecture_id"], catalogue=catalogue,
                     authored_by=AGENT)
    assert control_status(graph, out["conjecture_id"]) == "passed"

    (tmp_path / "corpus" / "C1" / "大.txt").write_text(body(True), encoding="utf-8")
    with RadichReader(tmp_path / "corpus") as moved:
        run_control_test(graph, moved, out["conjecture_id"], catalogue=catalogue,
                         authored_by=AGENT)
    assert control_status(graph, out["conjecture_id"]) == "failed"


# --- what a control test will not claim -------------------------------------

def test_a_group_too_short_to_measure_is_indeterminate_not_a_pass(graph, corpus, catalogue):
    """A control that could not have failed has not been run."""
    out = register(graph, catalogue)
    res = run_control_test(graph, corpus, out["conjecture_id"], catalogue=catalogue,
                           min_chars=10 ** 9, authored_by=AGENT)
    assert res["result"] == VerificationResult.INDETERMINATE
    assert control_status(graph, out["conjecture_id"]) == "failed", (
        "indeterminate is not a pass, so the gate stays shut"
    )


def test_a_pass_states_what_it_does_not_establish(graph, corpus, catalogue):
    out = register(graph, catalogue)
    res = run_control_test(graph, corpus, out["conjecture_id"], catalogue=catalogue,
                           authored_by=AGENT)
    limits = graph.get_node(res["verification_id"]).payload["limitations"]
    assert "not that" in limits and "genre" in limits


def test_applying_a_feature_reports_no_verdict_per_work(graph, corpus, catalogue):
    """`attests` is what was observed. Whether it places the work with the
    benchmark is a reading, and one feature is not an ascription."""
    out = register(graph, catalogue)
    run_control_test(graph, corpus, out["conjecture_id"], catalogue=catalogue,
                     authored_by=AGENT)
    applied = apply_to_disputed(graph, corpus, out["conjecture_id"],
                                catalogue=catalogue, disputed_label="disputed")
    for row in applied["works"]:
        assert set(row) & {"score", "likelihood", "verdict"} == set()


def test_a_plain_conjecture_has_no_prediction_to_test(graph, corpus, catalogue):
    from cohort.schemas import ConjecturePayload

    cid = graph.propose_conjecture(
        ConjecturePayload(text="t", derivation="d", corpus_boundary="c",
                          selection_risks="s", alternative_explanations="a"),
        authored_by=AGENT,
    )
    with pytest.raises(WrongNodeType, match="no registered discrimination"):
        run_control_test(graph, corpus, cid, catalogue=catalogue, authored_by=AGENT)


# --- the ledger --------------------------------------------------------------

def test_the_ledger_keeps_discarded_features(graph, corpus, catalogue):
    """The reason it exists. Features that did not work are invisible in
    ordinary stylometry, so a reader cannot tell a discovery from a fishing
    expedition."""
    good = register(graph, catalogue)
    bad = register(graph, catalogue, feature="文", min_benchmark_share=0.9,
                   max_control_share=0.1)
    for out in (good, bad):
        run_control_test(graph, corpus, out["conjecture_id"], catalogue=catalogue,
                         authored_by=AGENT)
    register(graph, catalogue, feature="未試")

    led = ledger_json(graph)
    assert led["tried"] == 3
    assert led["by_fate"] == {"usable": 1, "discarded": 1, "untested": 1}
    assert {r["feature"] for r in led["features"]} == {MARK, "文", "未試"}


def test_the_ledger_leads_with_how_many_were_tried(graph, corpus, catalogue):
    """Three survivors out of four is a different claim from three out of
    ninety, and the ledger must not let the second read like the first."""
    out = register(graph, catalogue)
    run_control_test(graph, corpus, out["conjecture_id"], catalogue=catalogue,
                     authored_by=AGENT)
    led = ledger_json(graph)
    assert "1 of 1" in led["reading"]
    assert "by chance" in led["reading"], "the multiple-comparisons caveat is stated"


def test_the_ledger_offers_no_ranking(graph, corpus, catalogue):
    out = register(graph, catalogue)
    run_control_test(graph, corpus, out["conjecture_id"], catalogue=catalogue,
                     authored_by=AGENT)
    row = ledger_json(graph)["features"][0]
    assert set(row) & {"score", "rank", "confidence", "strength"} == set()
    assert row["fate"] == "usable"
    assert "survived" in row["licenses"]


def test_an_empty_ledger_says_so(graph):
    led = ledger_json(graph)
    assert led["tried"] == 0
    assert "no candidate discriminators" in led["reading"]


# --- the application is a record, not a printout ----------------------------

def test_applying_a_survivor_writes_nothing_without_an_author(graph, corpus, catalogue):
    """The default stays read-only. `apply_to_disputed` is also a library call
    made by scripts that print rather than write, and giving it an author it
    did not ask for would put a verification into every one of those graphs."""
    out = register(graph, catalogue)
    run_control_test(graph, corpus, out["conjecture_id"], catalogue=catalogue,
                     authored_by=AGENT)
    before = len(graph.verifications(out["conjecture_id"]))
    applied = apply_to_disputed(graph, corpus, out["conjecture_id"],
                                catalogue=catalogue, disputed_label="disputed")
    assert applied["verification_id"] is None
    assert len(graph.verifications(out["conjecture_id"])) == before


def test_an_authored_application_records_the_rows_it_measured(graph, corpus, catalogue):
    """This is the one concrete output of the whole method — which works in
    doubt a surviving feature places where — and until 2026-09-06 it went to
    stdout and never reached the record it was derived from."""
    out = register(graph, catalogue)
    run_control_test(graph, corpus, out["conjecture_id"], catalogue=catalogue,
                     authored_by=AGENT)
    applied = apply_to_disputed(graph, corpus, out["conjecture_id"],
                                catalogue=catalogue, disputed_label="disputed",
                                authored_by=AGENT)

    v = graph.get_node(applied["verification_id"])
    rows = {w["work"]: w for w in v.payload["works"]}
    assert set(rows) == {"D1", "D2"}
    assert rows["D1"]["count"] > 0 and rows["D2"]["count"] == 0
    # Per work and never pooled: the payload has no field for a group total,
    # and the rows carry the edition tally separately from the count.
    assert rows["D1"]["editions_total"] == 2


def test_an_application_never_returns_pass_or_fail(graph, corpus, catalogue):
    """Pass/fail is for a prediction meeting evidence. The registered
    prediction was about the benchmark and the control and has already been
    settled; a PASS here would read as 'the disputed work belongs', which is
    the one sentence nothing in this system may write."""
    out = register(graph, catalogue)
    run_control_test(graph, corpus, out["conjecture_id"], catalogue=catalogue,
                     authored_by=AGENT)
    applied = apply_to_disputed(graph, corpus, out["conjecture_id"],
                                catalogue=catalogue, disputed_label="disputed",
                                authored_by=AGENT)
    v = graph.get_node(applied["verification_id"])
    assert v.payload["result"] == VerificationResult.INDETERMINATE
    assert "not an ascription" in v.payload["limitations"]
