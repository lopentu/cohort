"""Is the group unusually close to this work, against the whole corpus?

The measure that answers Radich's brief, as against the null band, which
answers a different question and reports "not distinguishable" for almost
everything on this corpus.

Most of what these pin is what the measure refuses to overclaim: that a zero is
not an exclusion when the method cannot see a third of the group's own
undisputed members, that a share is read against what a known member scores and
not against chance alone, and that the genre control travels in the same payload
as the thing it controls.
"""
from __future__ import annotations

import pytest

from cohort.association import (
    DOMINANT_GAP_PERCENTILE,
    MIN_GROUP,
    TOPK,
    associate,
    calibrate,
    canon_baseline,
    hypergeometric_at_least,
)
from cohort.delta import DEFAULT_MIN_CHARS, build_space

PAD = DEFAULT_MIN_CHARS


def corpus():
    """A group with an internal signature, a *genre cluster* that shares the
    group's subject matter without its signature, and a background canon.

    The genre cluster is the point. A fixture where the group is the only thing
    a test work resembles proves nothing about this measure, because character
    n-grams track subject matter (`attribution.CAVEAT`) and a work near the
    group's topic would land near the group whoever wrote it. So DECOY is
    built as a member of the genre cluster and MEMBERLIKE as a member of the
    group, and the measure has to tell them apart — which is exactly the
    T1584-versus-Abhidharma question on the real corpus.

    Every text is ~6,300 characters, above the 5,000 floor, and the three
    components of each are the same length so no work is separated by size.
    """
    SIG, THEME, U = "阿黎耶", "波羅蜜", 700
    fill = lambda c: (chr(c) * 3) * U
    texts = {}
    for i in range(6):
        texts[f"G{i}"] = SIG * U + THEME * U + fill(0x4E00 + i)
    texts["MEMBERLIKE"] = SIG * U + THEME * U + fill(0x4E20)
    texts["DECOY"] = THEME * U + fill(0x4E21) + fill(0x4E22)
    for i in range(30):
        texts[f"TH{i:02d}"] = THEME * U + fill(0x5100 + i) + fill(0x5200 + i)
    for i in range(150):
        texts[f"X{i:03d}"] = "多阿含" * U + fill(0x6000 + i) + fill(0x6100 + i)
    return texts


@pytest.fixture(scope="module")
def space():
    t = corpus()
    sp = build_space(t, labels={w: ("G" if w.startswith("G") else None) for w in t},
                     features=300)
    # This fixture got it wrong once: the background works were 4,900 characters
    # against a 5,000 floor, `build_space` skipped all 150 of them in silence,
    # and the measure was left being tested on a 38-work corpus where a top-25
    # neighbourhood is most of everything. A skipped work is a legitimate result
    # in production and a broken fixture here.
    assert not sp.skipped, f"fixture works below the floor: {sp.skipped}"
    return sp


@pytest.fixture(scope="module")
def group():
    return [f"G{i}" for i in range(6)]


@pytest.fixture(scope="module")
def cal(space, group):
    return calibrate(space, group, label="G")


@pytest.fixture(scope="module")
def base(space):
    return canon_baseline(space)


def assoc(space, work, group, cal, base):
    return associate(space, work, group=group, label="G",
                     calibration=cal, baseline=base)


# --- the arithmetic ---------------------------------------------------------

def test_the_tail_probability_is_exact_not_approximated(space):
    """`k` is small and the interesting values are deep in the tail, which is
    where a normal approximation is worst."""
    # 2 of 16 marked in a draw of 25 from 100: computable by hand as 1 minus
    # the zero- and one-hit terms.
    from math import comb
    n, k, marked = 100, 25, 16
    exact = 1 - sum(
        comb(marked, i) * comb(n - marked, k - i) / comb(n, k) for i in (0, 1)
    )
    assert hypergeometric_at_least(2, k, marked, n) == pytest.approx(exact)


def test_asking_for_more_hits_than_exist_is_impossible_not_unlikely(space):
    assert hypergeometric_at_least(30, 25, 16, 100) == 0.0


def test_every_draw_contains_at_least_zero(space):
    assert hypergeometric_at_least(0, 25, 16, 100) == pytest.approx(1.0)


# --- calibration ------------------------------------------------------------

def test_a_member_is_calibrated_against_the_group_without_itself(space, group, cal, base):
    """A member scored against a set containing itself is scored against a set
    it helped define, and recovers its own group trivially."""
    for k in TOPK:
        assert cal[k].n == len(group)


def test_the_calibration_reports_the_members_it_cannot_see(space, group, cal, base):
    """`blind` is the field that makes a zero readable. Without it a work the
    method simply misses is indistinguishable from one that does not belong,
    and reporting the first as the second manufactures exclusions."""
    for k in TOPK:
        assert 0 <= cal[k].blind <= cal[k].n


def test_a_group_too_small_to_calibrate_is_refused(space):
    with pytest.raises(ValueError, match=f"at least {MIN_GROUP}"):
        calibrate(space, ["G0", "G1"], label="G")


# --- the measure ------------------------------------------------------------

def test_a_work_carrying_the_groups_signature_associates(space, group, cal, base):
    a = assoc(space, "MEMBERLIKE", group, cal, base)
    assert a.headline.hits > 0
    assert a.headline.p_value < 0.01
    assert a.expected_share < a.headline.share


def test_a_work_sharing_only_the_subject_matter_does_not(space, group, cal, base):
    """The genre confound in miniature: DECOY is about what the group is about
    and carries none of its signature. If subject matter alone associated a
    work, this measure would be reporting `attribution.CAVEAT` as a finding."""
    a = assoc(space, "DECOY", group, cal, base)
    member = assoc(space, "MEMBERLIKE", group, cal, base)
    assert a.headline.share < member.headline.share


def test_the_nearest_work_outside_the_group_travels_with_the_nearest_inside(space, group, cal, base):
    """The two together are the genre control, and separated they are the half
    of the measure that flatters it — same reasoning as a `NullBand` travelling
    with a Delta."""
    a = assoc(space, "MEMBERLIKE", group, cal, base)
    assert a.nearest_in_group is not None
    assert a.nearest_outside_group is not None
    assert a.nearest_outside_group.work not in group


def test_a_member_scored_against_its_own_group_does_not_recover_itself(space, group, cal, base):
    a = assoc(space, "G0", group, cal, base)
    assert all(n.work != "G0" for n in a.neighbours)
    assert a.group_size == len(group) - 1


def test_ranks_start_at_one_so_no_member_is_not_a_member_at_the_top(space, group, cal, base):
    a = assoc(space, "MEMBERLIKE", group, cal, base)
    assert a.neighbours[0].rank == 1
    assert a.first_rank is None or a.first_rank >= 1


# --- what the reading may and may not say -----------------------------------

def test_a_null_result_is_reported_as_blindness_not_as_exclusion(space, group, base):
    """The sentence this measure exists to get right. A work the method cannot
    see must not read as a work shown not to belong."""
    blind_cal = {
        k: type(c)(k=k, n=6, blind=3, minimum=0.0, median=0.0, maximum=0.2)
        for k, c in calibrate(space, group, label="G").items()
    }
    a = assoc(space, "X000", group, blind_cal, base)
    if a.headline.hits == 0:
        assert "cannot see" in a.reading
        assert "does not separate" in a.reading


def test_the_headline_is_the_smallest_k_and_is_never_chosen(space, group, cal, base):
    """All three neighbourhood sizes are reported together. Picking the `k`
    that flatters a work after seeing all three is the error the fixed `TOPK`
    exists to prevent."""
    a = assoc(space, "MEMBERLIKE", group, cal, base)
    assert a.headline.k == min(TOPK)
    assert [e.k for e in a.enrichment] == list(TOPK)


def test_the_reading_never_states_an_ascription(space, group, cal, base):
    for work in ("MEMBERLIKE", "DECOY", "G0", "X000"):
        r = assoc(space, work, group, cal, base).reading
        for banned in ("wrote", "author", "by the same", "is by"):
            assert banned not in r.lower(), (work, r)


# --- the second branch: what is it near? ------------------------------------

def test_every_work_gets_a_determinate_verdict(space, group, cal, base):
    """Three of the four disputed works on the Paramārtha study show no group
    enrichment. Rendering all three as the same blank made the method look
    unable to answer, when "not here, and here is where it does sit" is an
    answer — so `verdict` is total over the works, never empty."""
    for w in ("MEMBERLIKE", "DECOY", "G0", "X000", "TH00"):
        v = assoc(space, w, group, cal, base).verdict
        assert v in {"associates", "weak", "alternate", "unplaced"}, (w, v)


def test_the_reading_always_says_where_the_work_sits_not_only_whether_it_belongs(
    space, group, cal, base,
):
    """Both branches, always. A reader given only the group half sees three
    quarters of this study report nothing."""
    for w in ("MEMBERLIKE", "DECOY", "X000"):
        a = assoc(space, w, group, cal, base)
        assert a.group_reading in a.reading
        assert a.neighbourhood.reading in a.reading
        assert a.neighbourhood.reading != a.group_reading


def test_a_dominant_nearest_work_is_named_as_a_lead_not_as_an_ascription(
    space, group, cal, base,
):
    for w in ("MEMBERLIKE", "DECOY", "G0", "X000"):
        n = assoc(space, w, group, cal, base).neighbourhood
        if n.dominant:
            assert "would look like" in n.reading or "worth checking" in n.reading
        for banned in ("is by", "was translated by", "the author of"):
            assert banned not in n.reading.lower()


def test_dominant_and_diffuse_are_never_both_true(space, group, cal, base):
    for w in space.works()[:25]:
        n = assoc(space, w, group, cal, base).neighbourhood
        assert not (n.dominant and n.diffuse)
        assert n.dominant == (n.gap_percentile >= DOMINANT_GAP_PERCENTILE)


def test_the_baseline_is_reproducible_so_a_fingerprint_can_mean_something(space):
    """The sample is random and a recorded association is fingerprinted. An
    unseeded sample would make every re-measurement disagree with its own
    baseline and report an unchanged corpus as a changed one."""
    a, b = canon_baseline(space), canon_baseline(space)
    assert a.nearest == b.nearest and a.gap == b.gap and a.cohesion == b.cohesion


def test_the_two_readings_are_decided_separately(space, group, cal, base):
    """Neighbourhood structure is not a group signature and must never act as
    one. Across sixteen undisputed P-23 works on the real corpus, gap
    percentile runs from the 4th to the 96th and cohesion from the 37th to the
    98th — so a verdict that let a tight neighbourhood push a work towards
    "associates" would be reading position in the canon as authorship.

    Asserted as a logical invariant over `verdict` rather than by looking for
    variance in the fixture, because a fixture built to have that variance
    would be testing the fixture.
    """
    for w in space.works():
        a = assoc(space, w, group, cal, base)
        enriched = a.headline.hits > 0
        if enriched and a.headline.within_calibration:
            # decided by the group alone, whatever the neighbourhood says
            assert a.verdict == "associates", w
        elif enriched:
            assert a.verdict == "weak", w
        else:
            # only here may the neighbourhood decide anything
            assert a.verdict == ("alternate" if a.neighbourhood.dominant
                                 else "unplaced"), w


def test_percentiles_read_as_english(space, group, cal, base):
    """`63rd`, not `63th`. A reading a researcher pastes into a paper should
    not need correcting by hand first."""
    from cohort.association import ordinal

    assert [ordinal(n) for n in (1, 2, 3, 4, 11, 12, 13, 21, 51, 63, 92, 100)] == [
        "1st", "2nd", "3rd", "4th", "11th", "12th", "13th",
        "21st", "51st", "63rd", "92nd", "100th",
    ]
    for w in ("MEMBERLIKE", "DECOY", "X000"):
        r = assoc(space, w, group, cal, base).neighbourhood.reading
        for bad in ("1th", "2th", "3th", "21th", "22th", "23th"):
            assert bad not in r, (w, r)
