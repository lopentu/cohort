"""Local refs to CBETA Online links.

The mapping is not guessable — CBETA Online drops the volume digits the local
archive's refs carry — so these cases were checked against CBETA's metadata API
rather than reasoned out, and the titles are recorded here so a future change
can be checked against something.
"""
from __future__ import annotations

import pytest

from cohort.sources.cbeta_refs import juan, reader_url, work_id

#: ref -> (work id, the title CBETA's API returns for it)
VERIFIED = {
    "A097n1267": ("A1267", "大唐開元釋教廣品歷章"),
    "B03na003": ("Ba003", "大藏經補編"),
    "T08n0235": ("T0235", "金剛般若波羅蜜經"),
    "B07n0022": ("B0022", "新譯薄伽梵母智慧到彼岸心經詮釋"),
}


@pytest.mark.parametrize(("ref", "expected"), [(k, v[0]) for k, v in VERIFIED.items()])
def test_work_ids_match_what_cbeta_returns(ref, expected):
    assert work_id(ref) == expected


def test_a_work_number_may_carry_letters():
    """`B03na003` is volume 03, work `a003` — so the work number cannot be
    parsed as digits, and the volume is what distinguishes them."""
    assert work_id("B03na003") == "Ba003"


def test_it_reads_the_work_out_of_a_full_archive_path():
    ref = "Bookcase/CBETA/XML/A/A097/A097n1267_004.xml::般若波羅蜜多心經"
    assert work_id(ref) == "A1267"
    assert juan(ref) == 4
    assert reader_url(ref) == "https://cbetaonline.dila.edu.tw/zh/A1267_004"


def test_an_unrecognised_ref_gets_no_link():
    """None, not a guess. A link that silently resolves to the wrong text is
    worse than no link, because the reader cannot tell."""
    assert work_id("poem-001") is None
    assert reader_url("poem-001") is None
    assert reader_url("") is None


def test_a_ref_with_no_fascicle_links_to_the_work():
    """Rather than inventing `_001`, which would send a reader confidently to
    the wrong fascicle of a seventeen-fascicle work."""
    assert reader_url("A097n1267") == "https://cbetaonline.dila.edu.tw/zh/A1267"
    assert juan("A097n1267") is None


def test_language_is_selectable_and_defaults_to_chinese():
    ref = "Bookcase/CBETA/XML/T/T08/T08n0235_001.xml"
    assert reader_url(ref) == "https://cbetaonline.dila.edu.tw/zh/T0235_001"
    assert reader_url(ref, lang="en") == "https://cbetaonline.dila.edu.tw/en/T0235_001"


@pytest.mark.parametrize('uid', ['T0603', 'T0263-rest', 'T0262-exDevadatta', 'T0125-48.3'])
def test_catalogue_units_link_to_work_without_inventing_a_fascicle(uid):
    from cohort.sources.cbeta_refs import unit_reader_url

    assert unit_reader_url(uid) == f'https://cbetaonline.dila.edu.tw/zh/{uid[:5]}'


@pytest.mark.parametrize('uid', ['poem-001', 'T12345', 'T0263+T0262', 'T0263/other', ''])
def test_unrecognised_or_composite_unit_has_no_link(uid):
    from cohort.sources.cbeta_refs import unit_reader_url

    assert unit_reader_url(uid) is None
