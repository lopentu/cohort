"""align_passages: how much of one unit's wording occurs verbatim in another.

Two measures on Han characters only (CBETA's punctuation and line breaks are
editorial and would break every shared run): the share of A's ten-character
strings that occur anywhere in B, and the longest runs the two texts share,
with offsets into the *original* text of each so a passage can be cited. The
first version of this check was run with punctuation left in and reported 11%
and 25-32-character runs for T0603/T1694; without it the figures are 65% and
279 characters. Read-only.
"""

from __future__ import annotations

import difflib
from typing import Any

from pydantic import BaseModel, ConfigDict, Field

from cohort.attribution import AttributionIndex, is_han

NAME = "align_passages"
DESCRIPTION = (
    "How much of unit A's wording occurs verbatim in unit B (share of A's ten-character "
    "strings found in B, and vice versa) and the longest passages they share, with "
    "character offsets into each original text so they can be cited. Han characters only; "
    "editorial punctuation is ignored. Use it after semantic_neighbors points at a text, to "
    "tell quotation from a mere likeness of subject."
)
GRAM = 10
MAX_CHARS = 80_000  # difflib is quadratic in the worst case; long works are truncated and say so


class AlignPassagesInput(BaseModel):
    model_config = ConfigDict(extra="forbid")
    uid_a: str = Field(min_length=1)
    uid_b: str = Field(min_length=1)
    min_run: int = Field(default=12, ge=4, le=200, description="shortest shared run worth listing")
    max_runs: int = Field(default=8, ge=1, le=40)


def _han_only(text: str) -> tuple[str, list[int]]:
    """The Han characters of `text`, and for each its offset in the original."""
    chars, offsets = [], []
    for i, ch in enumerate(text):
        if is_han(ch):
            chars.append(ch)
            offsets.append(i)
    return "".join(chars), offsets


def _coverage(a: str, b: str) -> float:
    grams_a = {a[i : i + GRAM] for i in range(len(a) - GRAM + 1)}
    if not grams_a:
        return 0.0
    grams_b = {b[i : i + GRAM] for i in range(len(b) - GRAM + 1)}
    return len(grams_a & grams_b) / len(grams_a)


def align_passages(index: AttributionIndex, args: AlignPassagesInput) -> dict[str, Any]:
    texts = {}
    for uid in (args.uid_a, args.uid_b):
        t = index.base_text(index.root, uid)
        if t is None:
            msg = f"{uid} has no base text in the corpus"
            raise KeyError(msg)
        texts[uid] = t
    ha, offs_a = _han_only(texts[args.uid_a])
    hb, offs_b = _han_only(texts[args.uid_b])
    truncated = len(ha) > MAX_CHARS or len(hb) > MAX_CHARS
    ha_cmp, hb_cmp = ha[:MAX_CHARS], hb[:MAX_CHARS]
    sm = difflib.SequenceMatcher(None, ha_cmp, hb_cmp, autojunk=False)
    blocks = [bl for bl in sm.get_matching_blocks() if bl.size >= args.min_run]
    blocks.sort(key=lambda bl: -bl.size)
    runs = [
        {
            "chars": bl.size,
            "text": ha_cmp[bl.a : bl.a + bl.size],
            "a_offset": offs_a[bl.a],
            "b_offset": offs_b[bl.b],
        }
        for bl in blocks[: args.max_runs]
    ]
    return {
        "uid_a": args.uid_a,
        "uid_b": args.uid_b,
        "han_chars_a": len(ha),
        "han_chars_b": len(hb),
        "share_of_a_in_b": round(_coverage(ha, hb), 4),
        "share_of_b_in_a": round(_coverage(hb, ha), 4),
        "gram": GRAM,
        "longest_shared_run": blocks[0].size if blocks else 0,
        "runs": runs,
        "compared_chars": min(len(ha), MAX_CHARS),
        "truncated": truncated,
        "reading": (
            "Shares near zero (under 1%) are what unrelated texts show; a share in the tens "
            "of percent with runs of dozens of characters is quotation or a shared source, "
            "not two translators writing alike. Offsets index the original text of each unit."
        ),
    }
