"""Deep links from a corpus reference to CBETA Online.

A `canonical_ref` here is the local archive's identifier — a path into the
XML tree, or the volume-scoped work token in it (`A097n1267`). CBETA Online
addresses the same text by a *canon-scoped* work id with the volume digits
removed (`A1267`), which is not derivable by eye and is why this lives in one
tested place rather than in a template string in a JSX file.

Verified against CBETA's own metadata API on 2026-09-02:

    A097n1267 -> A1267   大唐開元釋教廣品歷章
    B03na003  -> Ba003   大藏經補編
    T08n0235  -> T0235   金剛般若波羅蜜經

These links are **display-only provenance**. They point a reader at the
published edition so they can see the passage in its own context, and they are
deliberately not part of any check: `verify_exact_span` re-fetches from the
local archive whose bytes were hashed, because a verification that depended on
a remote page would fail on a network error and pass or fail differently
depending on when it ran. A link is a courtesy to the reader; a citation is
what the graph checks.
"""
from __future__ import annotations

import re

READER_BASE = "https://cbetaonline.dila.edu.tw"

#: `{canon}{volume}n{work}` as it appears in the archive's paths and refs.
#: The work number keeps its letters (`B03na003` -> work `a003`), so it is not
#: `\d+`; the volume is always digits, which is what lets the two be told apart.
#: Bounded by lookarounds rather than `\b`: the token is followed by `_004` in
#: an archive path, and `_` is a word character, so `\b` never matches there.
_WORK = re.compile(
    r"(?<![0-9a-zA-Z])([A-Z]{1,2})(\d+)n([0-9a-zA-Z]+)(?![0-9a-zA-Z])"
)
_JUAN = re.compile(r"_(\d+)\.xml\b")


def work_id(ref: str) -> str | None:
    """The CBETA Online work id for a reference, or None if there isn't one.

    None rather than a guess: a ref this does not recognise (a test fixture, a
    non-CBETA corpus) should produce no link at all. A link that silently
    resolves to the wrong text would be worse than none, because the reader
    has no way to tell.
    """
    m = _WORK.search(ref or "")
    return f"{m.group(1)}{m.group(3)}" if m else None


def juan(ref: str) -> int | None:
    """The fascicle number, from the archive filename that carries it."""
    m = _JUAN.search(ref or "")
    return int(m.group(1)) if m else None


def reader_url(ref: str, *, lang: str = "zh") -> str | None:
    """A link to this passage's text in CBETA Online.

    Falls back to the work without a fascicle when the ref does not name one —
    the right page is still one click away, and a fabricated `_001` would send
    the reader confidently to the wrong fascicle.
    """
    work = work_id(ref)
    if not work:
        return None
    n = juan(ref)
    return f"{READER_BASE}/{lang}/{work}_{n:03d}" if n else f"{READER_BASE}/{lang}/{work}"


def unit_reader_url(uid: str) -> str | None:
    """Open a single Taishō catalogue unit's work, never guess online offsets.

    Chapter/remainder suffixes identify local selections, not CBETA fascicles.
    Composite and unfamiliar identifiers are deliberately left without a link.
    """
    match = re.fullmatch(r"(T\d{4})(?:-[A-Za-z0-9][A-Za-z0-9.-]*)?", uid)
    return f"{READER_BASE}/zh/{match[1]}" if match else None
