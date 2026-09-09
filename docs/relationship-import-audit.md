# Relationship import check — 2026-09-09

The presentation server uses `LocalReader` over Radich’s `corpus/T-stripped`,
not the CBETA archive reader. The current `link_parallels` tool requires CBETA
cross-reference markup and a reader that resolves Taishō numbers. A research
instruction alone cannot make that tool produce links from this source.

Read-only inspection of the supplied files found:

| Check | Computed result |
|---|---:|
| Main catalogue nonempty rows | 2,335 |
| Main catalogue rows with exactly two whitespace-separated fields | 2,335 |
| Secondary catalogue nonempty rows, all with two fields | 33 |
| Corpus text files scanned | 38,369 |
| Text files containing `docNumber`, TEI `relation`, `link`, or `quote` elements, or `parallel_of` / `descends_from` tokens | 0 |
| Notes in the vocabulary XML | 4,475 |
| Notes matching `quot`, `parallel`, `deriv`, `borrow`, or `descen` (case-insensitive) | 143 |
| Notes containing more than one distinct `T` + four-digit identifier | 20 |
| XML attributes, including explicit source/target attributes | 0 |

The note counts are search candidates, not counts of asserted relationships.
This audit did not interpret every note or inspect private correspondence.
No source text, notes, correspondence, or relationship payloads were exported.
No graph records were changed.

There is no ready-made typed relationship table in the inspected inputs.
Scholarly prose in the notes may still discuss relationships; it needs reading
in context before deciding whether it asserts one and which sources it concerns.
An automatic import based on keywords or co-occurring identifiers would invent
semantics not established by this audit.

Next options:

- Use the original CBETA source in a separate graph to exercise the existing
  markup-grounded parallel importer. Do not silently substitute CBETA source
  bytes for Radich’s modified texts in existing citations.
- Inspect candidate vocabulary notes and prepare individually sourced proposals
  for researcher review. Quotation and descent still lack Inquiry tools that
  create such reviewable relationship proposals.

`docs/design.md` §0 requires stopping when a design rule cannot be honoured;
§12 records that descent import is blocked without a source channel asserting
it. This audit supplies no basis for creating quotation or descent edges now.
