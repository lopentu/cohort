"""Counting, with the three disciplines that keep a count honest.

COHORT could previously record that an agent *said* a phrase occurs eighteen
times and had no way to disagree. These tests pin the shape of the answer to
that, and most of them are about what the measurement refuses to do: it does
not pool, it does not count the same text seventeen times, and it does not
report a rate for a work too short to have one.
"""
from __future__ import annotations

import pytest

from cohort.measure import (
    DEFAULT_BASE_EDITION,
    FeatureMeasurement,
    count_occurrences,
    measure_feature,
)
from cohort.sources.radich_reader import RadichReader

LONG = "阿黎耶識" + "文" * 6_000          # attests, comfortably above the floor
LONGER = "文" * 20_000                    # does not attest, also above it
SHORT = "阿黎耶識" + "文" * 100            # attests, but far too short to rate


@pytest.fixture
def corpus(tmp_path):
    layout = {
        # same work, three editions: one observation, not three
        "T0001": {"大": LONG, "元": LONG, "宋": LONG},
        # base edition lacks it, another edition has it: a variant reading
        "T0002": {"大": LONGER, "元": "阿黎耶識" + LONGER},
        "T0003": {"大": LONGER},
        "T0004": {"大": SHORT},
        # no 大 at all
        "T0005": {"麗-CB": LONG},
    }
    for work, editions in layout.items():
        d = tmp_path / work
        d.mkdir()
        for edition, text in editions.items():
            (d / f"{edition}.txt").write_text(text, encoding="utf-8")
    r = RadichReader(tmp_path)
    yield r
    r.close()


LABELS = {"T0001": "bench", "T0002": "bench", "T0003": "bench",
          "T0004": "control", "T0005": "control"}


def measure(corpus, **kw):
    return measure_feature(corpus, "阿黎耶識", labels=LABELS, **kw)


# --- one work, one observation ----------------------------------------------

def test_the_rate_comes_from_one_edition_not_all_of_them(corpus):
    """Three identical editions must not treble the count. This is the single
    most consequential rule here: the real corpus has up to seventeen editions
    per work, differing by ~0.02%."""
    row = next(w for w in measure(corpus).works if w.work == "T0001")
    assert row.base_edition == DEFAULT_BASE_EDITION
    assert row.count == 1, "counted the base edition only"
    assert row.editions_total == 3


def test_the_other_editions_are_reported_as_transmission_not_support(corpus):
    """A different question, worth answering: is the feature stable across the
    tradition, or does one edition happen to carry it?"""
    rows = {w.work: w for w in measure(corpus).works}
    assert rows["T0001"].editions_attesting == 3, "stable across the tradition"
    assert rows["T0002"].count == 0, "absent from the base text"
    assert rows["T0002"].editions_attesting == 1, "but one edition has it"


def test_a_work_with_no_base_edition_falls_back_and_says_which(corpus):
    row = next(w for w in measure(corpus).works if w.work == "T0005")
    assert row.base_edition == "麗-CB"
    assert row.count == 1


# --- too short to measure ----------------------------------------------------

def test_a_short_work_gets_no_rate_rather_than_a_misleading_one(corpus):
    """`per_10k` is None, not 0.0, so it cannot be averaged into a group figure
    by accident. The real control set contains a 1,843-character text; a rate
    from it is noise, and saying so is a result."""
    row = next(w for w in measure(corpus).works if w.work == "T0004")
    assert row.sufficient is False
    assert row.per_10k is None
    assert row.count == 1, "the count is still reported; only the rate is withheld"
    assert "below the" in row.note


def test_short_works_are_excluded_from_the_group_tally_and_counted(corpus):
    """Excluded from `works_measured` so a share is not diluted by texts the
    method cannot speak to — and reported as `works_skipped_short`, so the
    exclusion is visible rather than silent."""
    s = measure(corpus).by_label()["control"]
    assert s.works_measured == 1 and s.works_skipped_short == 1


def test_the_floor_is_a_stated_parameter(corpus):
    assert measure(corpus, min_chars=10).by_label()["control"].works_measured == 2


# --- never pool --------------------------------------------------------------

def test_a_group_is_summarised_as_a_tally_of_works_not_a_pooled_rate(corpus):
    """P-23 is 59% two texts by character count. A pooled rate over it is
    mostly a measurement of those two, so the summary counts *works*, which is
    the unit an ascription claim is about."""
    s = measure(corpus).by_label()["bench"]
    assert (s.works_attesting, s.works_measured) == (1, 3)
    assert s.share_attesting == round(1 / 3, 4)
    assert not hasattr(s, "mean_rate") and not hasattr(s, "total_count")


def test_per_work_rates_are_exposed_but_not_averaged(corpus):
    s = measure(corpus).by_label()["bench"]
    assert len(s.rates) == 3, "every measurable work's rate is there to read"


def test_nothing_scores_or_ranks(corpus):
    """Reporting only. Whether these numbers discriminate anything is a claim
    somebody has to make and defend, not a field on the result."""
    payload = measure(corpus).as_json()
    forbidden = {"score", "confidence", "p_value", "rank", "verdict", "likely"}
    assert not (forbidden & set(str(payload).lower().split()))


# --- the numbers survive the trip -------------------------------------------

def test_the_result_serialises_flat_enough_to_store_and_recheck(corpus):
    """It goes into a verification's `detail`, so a later run can re-derive it
    and compare rather than take it on trust."""
    payload = measure(corpus).as_json()
    assert payload["feature"] == "阿黎耶識"
    assert payload["base_edition"] == DEFAULT_BASE_EDITION
    assert {r["work"] for r in payload["works"]} == set(LABELS)
    assert payload["by_label"]["bench"]["works_attesting"] == 1


def test_measuring_twice_gives_the_same_answer(corpus):
    """Determinism is what makes a measurement checkable at all."""
    assert measure(corpus).as_json() == measure(corpus).as_json()


# --- counting itself ---------------------------------------------------------

def test_occurrences_do_not_overlap():
    """A real choice, not an accident: counting overlaps would make a
    repeated-character feature's rate depend on run length in a way no
    philological claim intends."""
    assert count_occurrences("阿阿阿", "阿阿") == 1
    assert count_occurrences("", "阿") == 0
    assert count_occurrences("阿", "") == 0


def test_an_unlabelled_work_is_still_measured(corpus):
    """A comparison against the rest of the canon should not require inventing
    a label for it."""
    m = measure_feature(corpus, "阿黎耶識", labels={"T0001": "bench"})
    assert {w.label for w in m.works} == {"bench", None}
    assert list(m.by_label()) == ["bench"]
