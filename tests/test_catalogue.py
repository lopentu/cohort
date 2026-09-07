"""Subcorpus labels, and the control group that makes a study testable.

The catalogue is three lines of parsing and one idea: a study that names a
group believed *not* to belong has given itself a way to be wrong. Radich's
`interloper` set is exactly that — texts earlier methods could not separate
from `P-23` and that are believed not to be Paramārtha's — so `control_label`
is a first-class field rather than a convention, and the gate that uses it can
be enforced instead of remembered.
"""
from __future__ import annotations

import pytest

from cohort.catalogue import Catalogue, CatalogueError, load_catalogue

BODY = """\
# a header, and a blank line below it

T0237\tP-23
T1595\tP-23
T0097\tP-weird
T2783\tinterloper
"""


@pytest.fixture
def path(tmp_path):
    p = tmp_path / "cat.txt"
    p.write_text(BODY, encoding="utf-8")
    return p


def test_it_parses_labels_and_keeps_catalogue_order(path):
    cat = load_catalogue(path)
    assert cat.labels() == ["P-23", "P-weird", "interloper"]
    assert cat.counts() == {"P-23": 2, "P-weird": 1, "interloper": 1}
    assert cat.works("P-23") == ["T0237", "T1595"]
    assert cat.label_of("T0097") == "P-weird"
    assert cat.label_of("T9999") is None


def test_comments_and_blank_lines_are_skipped(path):
    """So a catalogue can carry its own provenance header — which matters for
    one transcribed out of an email rather than shipped as a file."""
    assert len(load_catalogue(path).entries) == 4


def test_a_work_in_two_groups_is_refused(tmp_path):
    """It would be counted as both benchmark and control, and a discriminator
    tested against itself passes."""
    p = tmp_path / "c.txt"
    p.write_text("T0237 P-23\nT0237 interloper\n", encoding="utf-8")
    with pytest.raises(CatalogueError, match="already labelled"):
        load_catalogue(p)


def test_a_malformed_line_names_its_line_number(tmp_path):
    p = tmp_path / "c.txt"
    p.write_text("T0237 P-23\nT1595 P 23\n", encoding="utf-8")
    with pytest.raises(CatalogueError, match="c.txt:2"):
        load_catalogue(p)


def test_an_empty_catalogue_is_an_error_not_an_empty_study(tmp_path):
    p = tmp_path / "c.txt"
    p.write_text("# nothing but a comment\n", encoding="utf-8")
    with pytest.raises(CatalogueError, match="no entries"):
        load_catalogue(p)


# --- the two roles -----------------------------------------------------------

def test_benchmark_and_control_must_name_real_labels(path):
    """A typo here would silently disable the negative-control gate, which is
    the one check the whole method rests on."""
    cat = load_catalogue(path, benchmark_label="P-23", control_label="interloper")
    assert cat.benchmark_label == "P-23" and cat.control_label == "interloper"
    with pytest.raises(CatalogueError, match="control label 'interlopers'"):
        load_catalogue(path, control_label="interlopers")


def test_asking_for_an_unknown_label_lists_the_real_ones(path):
    with pytest.raises(CatalogueError, match="P-23"):
        load_catalogue(path).works("P-24")


# --- agreement with the corpus ----------------------------------------------

def test_a_work_the_corpus_lacks_is_refused_before_anything_is_measured(path):
    """Dropping it silently would report a benchmark of a size nobody chose,
    and the missing works are as likely as any to be the interesting ones."""
    cat = load_catalogue(path)
    cat.check_against(["T0237", "T1595", "T0097", "T2783"])
    with pytest.raises(CatalogueError, match="T2783"):
        cat.check_against(["T0237", "T1595", "T0097"])


def test_it_knows_nothing_about_paramartha():
    """Generic on purpose: `{work: label}` plus which label is the benchmark
    and which the control. Encoding one scholar's problem into the vocabulary
    is the kind of thing §6 wants an argument for."""
    src = Catalogue.__doc__ + (load_catalogue.__doc__ or "")
    assert "Paramārtha" not in src and "Taishō" not in src
