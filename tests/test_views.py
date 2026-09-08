"""Shared read-shapes (cohort/views.py) — the pure logic behind
`/api/passage/context` and its CLI twin `cohort context`, tested once here so
neither front end can drift from the other by drifting from this.
"""
from __future__ import annotations

import pytest

from cohort.views import locate_passage_span


def test_first_match_when_there_is_no_recorded_baseline():
    start, end, location = locate_passage_span("abcXYZdef", "XYZ", None)
    assert (start, end, location) == (3, 6, "first_match")


def test_a_matching_verified_span_is_trusted_over_a_search():
    # A second, earlier occurrence exists — the fresh-search answer would be
    # 0, not 3. The verified span must win regardless.
    text = "XYZ...XYZdef"
    start, end, location = locate_passage_span(text, "XYZ", (6, 9))
    assert (start, end, location) == (6, 9, "verified_span")


def test_a_stale_verified_span_falls_back_to_a_fresh_search():
    """The recorded offsets no longer point at the recorded text — the source
    moved, or the archive changed underneath it. Trusting stale offsets would
    show context around the wrong span, so this must fall through to a fresh
    search rather than return garbage silently."""
    start, end, location = locate_passage_span("abcXYZdef", "XYZ", (0, 3))
    assert (start, end, location) == (3, 6, "stale_verified_span")


def test_excerpt_not_found_raises_value_error():
    with pytest.raises(ValueError, match="not found"):
        locate_passage_span("abcdef", "ZZZ", None)
