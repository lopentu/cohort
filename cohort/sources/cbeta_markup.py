"""Parsers for the two pieces of CBETA TEI markup stage 4 actually needs:
`<cb:docNumber>` parallel cross-references, and `<app>`/`<lem>`/`<rdg>`
edition apparatus.

Pure text-in, data-out — no `Graph`, no `Source`, no I/O. The tools in
`cohort/tools/` decide what to *write* from these results; this module only
reports what the markup says, which keeps the "what does the corpus claim"
question separable from the "what may we assert" question.

**Why conservative parsing is load-bearing here, not fussiness.** A
`parallel_of` edge is not decorative in COHORT: `Graph.independent_support()`
flips `independent` to False the moment one links two witnesses supporting the
same claim. So a wrongly-minted `parallel_of` *suppresses* independent
support — it manufactures the very consensus illusion the design exists to
expose (docs/design.md §4). Guessing is therefore worse than declining, and every
function below separates what it parsed cleanly from what it could not, rather
than dropping the remainder silently (docs/design.md §0's standing rule: say so and
stop).

Three distinctions the real corpus forces, all preserved rather than
flattened:

- a bare list (`No. 516 [Nos. 514, 515]`) *asserts* parallel texts;
- a `cf.` list (`No. 1754 [cf. No. 365]`) is a curatorial "compare", and the
  two can be mixed in one bracket (`No. 1597 [Nos. 1595, 1596; cf. Nos.
  1592-1594, 1598]`), so the split is by position within the bracket, not by
  whether `cf.` appears anywhere in it;
- `Part of` (`No. 294 [Part of No. 278(34), 279(39), 293]`) is a
  containment relation, not symmetric parallelism, so it is reported
  separately and never turned into a `parallel_of` by this module's callers.
"""
from __future__ import annotations

import re

from pydantic import BaseModel, ConfigDict

#: Taisho numbers are bare integers, optionally with a disambiguating letter
#: (`983A`, `1887B`, `1138a`), optionally followed by a parenthesised
#: sub-reference naming a juan/section/fascicle (`278(22)`, `125(35.10)`,
#: `1092(Fasc. 1)`). The sub-reference is provenance detail, not identity.
_RANGE_RE = re.compile(r"(\d+)\s*[-–]\s*(\d+)")
_SINGLE_RE = re.compile(r"(\d+)([A-Za-z]?)\s*(?:\(([^)]*)\))?")
_TAG_RE = re.compile(r"<[^>]+>")
_DOCNUMBER_RE = re.compile(r"<cb:docNumber>(.*?)</cb:docNumber>", re.S)
#: ASCII brackets only. Full-width `［...］` appears in at least one entry
#: (`No. 270［－］【CB】，[No. 271]【大】`) as an edition-specific editorial mark,
#: not a cross-reference list, so it is deliberately not treated as one.
_BRACKET_RE = re.compile(r"\[([^\]]*)\]")
_CF_RE = re.compile(r"\bcf\.", re.IGNORECASE)
_PART_OF_RE = re.compile(r"\bpart\s+of\b", re.IGNORECASE)
#: what may legitimately remain in a bracket once numbers and separators are
#: removed. Anything else (CJK, edition sigla, Pali/Sanskrit sutta titles,
#: `~` approximation marks) means the entry is not a plain Taisho list and the
#: whole bracket is reported unparsed rather than half-read.
_ALLOWED_RESIDUE_RE = re.compile(
    r"(?:Nos?\.|cf\.|Part\s+of|Fasc\.|and|etc\.|[\s,;:.&–-])+", re.IGNORECASE
)

_APP_RE = re.compile(r"<app\b([^>]*)>(.*?)</app>", re.S)
_READING_RE = re.compile(r"<(lem|rdg)\b([^>]*)>(.*?)</\1>", re.S)
_ATTR_RE = re.compile(r'(\w[\w:.-]*)\s*=\s*"([^"]*)"')
_SIGLUM_RE = re.compile(r"【[^】]*】")


class _Model(BaseModel):
    model_config = ConfigDict(extra="forbid")


class ParallelRef(_Model):
    """One cross-referenced Taisho text. `number` is the bare Taisho number
    as written (`"278"`, `"983A"`) — deliberately *not* a witness
    `canonical_ref` like `T08n0251`, because `<cb:docNumber>` records only
    the number, never the volume. Resolving number to volume needs the
    archive's own entry listing and is `CbetaReader`'s job, not the
    parser's."""

    number: str
    #: juan/section/fascicle named in parentheses, e.g. `"22"`, `"35.10"`,
    #: `"Fasc. 1"`. Provenance detail; never part of witness identity.
    sub_ref: str | None = None


class ParallelRefs(_Model):
    """What one document's `<cb:docNumber>` elements say. The four reference
    buckets are kept apart on purpose — see this module's docstring."""

    #: the document's own Taisho number, for cross-checking against the
    #: witness the caller thinks it is reading.
    self_number: str | None = None
    #: bare-list references: the corpus asserts these are parallel texts.
    asserted: list[ParallelRef] = []
    #: `cf.` references: curatorial "compare", too weak to mint an edge from.
    compare_only: list[ParallelRef] = []
    #: `Part of` references: containment, not symmetric parallelism.
    part_of: list[ParallelRef] = []
    #: bracket contents this parser declined to read, verbatim. Never empty
    #: silently: a caller that wants completeness must look here.
    unparsed: list[str] = []


class Reading(_Model):
    """One `<lem>` (adopted reading) or `<rdg>` (variant) inside an `<app>`.

    `sigla` is a *list* because a single `wit` attribute routinely names
    several editions jointly (`wit="【宋】 【元】 【明】 【宮】"`). Those
    editions agreeing is one shared-descent family reading one way — not
    four independent confirmations — and collapsing the list would erase
    exactly that distinction."""

    sigla: list[str] = []
    text: str = ""
    #: editorial responsibility, e.g. `"Taisho"`, `"CBETA.maha"`. A reading
    #: carrying `resp` is an editorial judgement, not an inherited witness
    #: reading, which is worth knowing before leaning on it as evidence.
    resp: str | None = None


class AppEntry(_Model):
    n: str | None = None
    lemma: Reading | None = None
    variants: list[Reading] = []


def _strip_tags(raw: str) -> str:
    """Tags occur *inside* bracket contents in the real corpus (one entry
    carries an `<lb/>` line-beginning marker mid-list), so stripping is
    required before parsing, not merely tidy."""
    return " ".join(_TAG_RE.sub("", raw).split())


def strip_markup_for_display(raw: str) -> str:
    """TEI tags removed and whitespace collapsed, for *reading only*.

    Public counterpart to `_strip_tags`, named for what callers must know
    about it: the result no longer aligns with the offsets `fetch()` returns,
    so it must never be used for locating or verifying a span. Every
    `EXACT_SPAN` verification hashes the text it was given and records the
    offset it found — feeding it a stripped copy would produce offsets that
    point nowhere in the real witness.

    It exists because a reader browsing the corpus in a UI should not have to
    read `<cb:mulu type="其他" level="1">` to see the text, and because doing
    the stripping in the frontend would put a second, drifting copy of this
    logic in JavaScript.
    """
    return _strip_tags(raw)


def _refs_from_segment(segment: str) -> tuple[list[ParallelRef], bool]:
    """Extract Taisho references from one bracket segment.

    Returns `(refs, clean)`. `clean` is False when the segment holds
    material this parser does not recognise, in which case the caller must
    discard `refs` and report the segment unparsed — a half-read reference
    list is exactly the kind of confident wrongness that would mint a false
    `parallel_of`."""
    # A `;`-delimited chunk carrying no digit at all is an annotation, not a
    # reference list — the corpus appends a Chinese title this way
    # (`Nos. 450, 451; 灌頂經卷第十二`). Dropping such a chunk can only remove
    # prose, never add a number, so it cannot manufacture a reference; without
    # it the stray CJK would fail the residue check and discard the perfectly
    # good numbers beside it.
    segment = "; ".join(
        chunk for chunk in segment.split(";") if any(c.isdigit() for c in chunk)
    )

    # (start_offset, refs) so the result follows the order the corpus wrote
    # them in, rather than ranges-then-singles by scan order.
    grouped: list[tuple[int, list[ParallelRef]]] = []
    consumed_spans: list[tuple[int, int]] = []

    for m in _RANGE_RE.finditer(segment):
        start, end = int(m.group(1)), int(m.group(2))
        # a descending or absurd range is a parse failure, not a silent skip
        if end < start or end - start > 200:
            return [], False
        grouped.append((m.start(), [ParallelRef(number=str(n)) for n in range(start, end + 1)]))
        consumed_spans.append(m.span())

    for m in _SINGLE_RE.finditer(segment):
        if any(s <= m.start() < e for s, e in consumed_spans):
            continue  # already covered by a range
        number = m.group(1) + (m.group(2) or "")
        sub = m.group(3).strip() if m.group(3) else None
        grouped.append((m.start(), [ParallelRef(number=number, sub_ref=sub or None)]))
        consumed_spans.append(m.span())

    residue = segment
    for start, end in sorted(consumed_spans, reverse=True):
        residue = residue[:start] + residue[end:]
    if _ALLOWED_RESIDUE_RE.fullmatch(residue) is None and residue.strip():
        return [], False

    grouped.sort(key=lambda t: t[0])
    return [r for _, refs in grouped for r in refs], True


def _dedupe(refs: list[ParallelRef]) -> list[ParallelRef]:
    """Order-preserving de-duplication. Needed across bracket groups, not
    just within one: at least one entry repeats a reference in two separate
    brackets (`No. 270［－］【CB】，[No. 271]【大】 [No. 271]`)."""
    seen: set[tuple[str, str | None]] = set()
    unique: list[ParallelRef] = []
    for r in refs:
        key = (r.number, r.sub_ref)
        if key not in seen:
            seen.add(key)
            unique.append(r)
    return unique


def parse_parallel_refs(document: str) -> ParallelRefs:
    """Read every `<cb:docNumber>` in `document` and classify its bracketed
    cross-references. Documents without a bracket yield empty buckets; that
    is the common case (roughly four in five, by sampling) and is not an
    error."""
    out = ParallelRefs()
    for m in _DOCNUMBER_RE.finditer(document):
        clean = _strip_tags(m.group(1))
        if out.self_number is None:
            self_m = re.match(r"No\.\s*(\d+[A-Za-z]?)", clean)
            if self_m:
                out.self_number = self_m.group(1)

        for bracket in _BRACKET_RE.findall(clean):
            body = bracket.strip()
            if not body:
                continue

            containment = _PART_OF_RE.search(body)
            cf = _CF_RE.search(body)
            # split by position: everything from the first `cf.` onward is
            # compare-only, whatever precedes it stands on its own footing.
            head = body[: cf.start()] if cf else body
            tail = body[cf.end():] if cf else ""

            head_refs, head_clean = _refs_from_segment(
                _PART_OF_RE.sub("", head) if containment else head
            )
            tail_refs, tail_clean = _refs_from_segment(tail) if tail.strip() else ([], True)

            if not (head_clean and tail_clean):
                out.unparsed.append(body)
                continue

            if containment:
                out.part_of.extend(head_refs)
            else:
                out.asserted.extend(head_refs)
            out.compare_only.extend(tail_refs)

    out.asserted = _dedupe(out.asserted)
    out.compare_only = _dedupe(out.compare_only)
    out.part_of = _dedupe(out.part_of)
    return out


def _attrs(raw: str) -> dict[str, str]:
    return dict(_ATTR_RE.findall(raw))


def _sigla(wit: str | None) -> list[str]:
    if not wit:
        return []
    found = _SIGLUM_RE.findall(wit)
    return found if found else wit.split()


def parse_apparatus(document: str) -> list[AppEntry]:
    """Read every `<app>` in `document` into its adopted reading and its
    variants, preserving joint edition sigla as single groups (see
    `Reading`)."""
    entries: list[AppEntry] = []
    for m in _APP_RE.finditer(document):
        app_attrs = _attrs(m.group(1))
        entry = AppEntry(n=app_attrs.get("n"))
        for kind, raw_attrs, text in _READING_RE.findall(m.group(2)):
            attrs = _attrs(raw_attrs)
            reading = Reading(
                sigla=_sigla(attrs.get("wit")),
                text=_strip_tags(text),
                resp=attrs.get("resp"),
            )
            if kind == "lem" and entry.lemma is None:
                entry.lemma = reading
            else:
                entry.variants.append(reading)
        entries.append(entry)
    return entries


def edition_families(entries: list[AppEntry]) -> dict[str, int]:
    """Tally how often each edition *group* is cited across `entries`, keyed
    by the group as written (`"【宋】 【元】 【明】"`), deliberately not split
    into individual editions.

    Splitting would double-count a shared-descent family as several
    independent witnesses, which is the consensus illusion docs/design.md §4
    exists to refuse. Callers wanting per-edition counts must decide that
    question explicitly rather than inherit it from a convenience helper."""
    tally: dict[str, int] = {}
    for e in entries:
        for reading in ([e.lemma] if e.lemma else []) + e.variants:
            if not reading.sigla:
                continue
            key = " ".join(reading.sigla)
            tally[key] = tally.get(key, 0) + 1
    return tally
