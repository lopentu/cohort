# Corpora

COHORT's whole corpus seam is two functions — `search(query)` and `fetch(ref)`
— and nothing more ([design.md](design.md) §2). That shape is deliberate: it
matches ATELIER's adapter interface, so integrating the two later means writing
one adapter class rather than reshaping the swarm.

Two readers implement it, and `LocalReader` has a second job: it is how a
researcher's own plain-text corpus becomes the Source for Corpus, Inquiry and
the agent tools without a new reader.

## The fixture: `LocalReader`

Manifest-driven plain text. Every test and the offline demo use it, so the suite
needs no corpus, no key and no network.

    examples/local_corpus/
      manifest.csv        path, witness_ref, label, note
      texts/*.txt

Four Tang poems, public domain in every jurisdiction. **Illustrative, never a
finding** — this is not a research corpus and nothing derived from it is a
scholarly result.

## A researcher's corpus as the Source: `LOCAL_CORPUS_ROOT`

Set `LOCAL_CORPUS_ROOT` to a folder holding a `manifest.csv` (`path,
witness_ref, label, note`) and `LocalReader` is chosen before the CBETA
archive. `scripts/radich_manifest.py` writes that manifest for Radich's corpus
(Zenodo 7750586: CBETA's Taishō text with paratext stripped and composite works
split; one folder per unit, one file per printed edition), listing the Taishō
file of every unit as a witness (2,306 of them). The folder is licence-
restricted and git-ignored; nothing from it may be committed, printed or
screenshotted in bulk.

The Evidence tab and the three evidence tools read the same folder through
`--radich PATH`, but through `cohort/attribution.py`, not through the reader:
they need the catalogue and the marker list beside the texts.

## The development corpus: CBETA v061

- **File**: `CBETA_電子佛典_xml_v061_20210710.zip`
- **SHA-256**:
  `90a663f212bc854e6a758ed06c74776cef5cbf8e7040d0192ff3301e6f7158f2`
- **Size**: 20,190 entries across 24 collections (T, X, J, A, B, ZW, …),
  4,852 distinct texts.

### Licence — this is not public domain

CBETA is **CC BY-NC-SA-equivalent**: non-commercial, attribution, share-alike,
version and intact-header requirements. [design.md](design.md) §2 rule 1 says
"public-domain **or** locally-held"; this qualifies on the second limb, with its
terms *preserved rather than waived*.

That preservation is in code, not just prose: `SourceRecord.note` carries the
terms into `WitnessPayload.source_terms` on every witness node, and into every
corpus API response. **Corpus bytes are never committed to this repository** —
only a local path is configured. If you ever add corpus files, add the
`.gitignore` rule in the same change.

This is provenance hygiene, not governance, and it is not a substitute for it.
See [design.md](design.md) §2 rule 2: claiming governance COHORT does not have
is forbidden.

### Setup

    # 1. Verify the file is what you think it is, before pointing anything at it
    shasum -a 256 /path/to/CBETA_電子佛典_xml_v061_20210710.zip

    # 2. Configure
    echo 'CBETA_ARCHIVE_PATH=/path/to/....zip' >> .env

    # 3. Confirm the reader agrees
    .venv/bin/python -c "
    from cohort.sources.cbeta_reader import CbetaReader
    CbetaReader('/path/to/....zip', '90a663f2...58f2')
    print('archive verified')"

**If the hash doesn't match: stop.** Don't substitute a different tree. A
mismatched archive is a different, unidentified version, and provenance claims
built on it would be false from the start — [design.md](design.md) §0's standing
rule applies exactly here.

Beware convenient-looking derivative trees. An already-extracted
`.../Bookcase/CBETA/XML` directory or a transformed plain-text variant is a
**separate, unverified extraction**, not the canonical archive, and a document
in one can differ from the archive copy.

## The search index

FTS5 over every citable span, built once, deliberately by hand:

    .venv/bin/python scripts/build_cbeta_index.py

Measured on the real archive: **432s, 1.14 GB, 20,190 entries, 0 skipped,
15.28M citable runs** (1.43M dropped as non-unique, 1.13M as too short).
Queries answer in ~65ms. Path defaults to `cbeta_fts.sqlite`, overridable with
`CBETA_FTS_PATH`.

**"Citable" is the point.** The index holds only spans that are unique within
their entry and at least `MIN_RUN_CHARS` (2) characters with CJK content — so
*every hit is fetchable by construction*. Searchable and citable are the same
set, rather than search promising something `fetch` can't honour.

**The CJK tokenizer trick**: FTS5's default tokenizer treats an unbroken CJK run
as one token, so `MATCH "寂寞"` against a real sentence matches nothing. Indexing
space-separated characters and phrase-querying fixes this with no segmenter
dependency.

**No relevance ranking**, deliberately. Results come back in corpus order and
every response says so. A list that looked ranked but wasn't would misrepresent
which witnesses matter most.

An older hand-maintained `cbeta_index.json` (`entry_path -> known excerpts`,
gitignored) predates the FTS index and is still accepted; some live scripts pass
it. Without either, `search()` raises `NotImplementedError` rather than silently
returning nothing.

## What the markup gives us

The corpus's own TEI markup is where stage 4's edges come from — read out of the
source rather than hand-added.

### `<cb:docNumber>` — cross-references

The real parallel-text channel. 14 of 65 docNumber elements in a 300-file sample
carry a bracketed list. **Two incompatible semantics live in that bracket:**

- a bare list — `No. 991 [Nos. 989, 992, 993]` — **asserts parallel texts**;
- a `cf.` list — `[cf. No. 2810]`, `[cf. No. 220(4 or 5) etc.]` — is a
  curatorial "compare", sometimes deliberately vague.

Only bare lists become `parallel_of` edges. A `parallel_of` edge *suppresses*
independent support, so minting one from a vague `cf. … etc.` would silently
discount real evidence — the failure mode the design exists to prevent.

Parsing notes: sub-references appear inside brackets (`No. 26(131)`,
`No. 99(449-450)`), and at least one bracket contains an embedded `<lb/>`, so
tags must be stripped before parsing. `scripts/scan_parallels.py` validates the
parser corpus-wide in ~8s, read-only.

Generic TEI pointers are **not** the channel: `<ref>` appears in 16/300 files,
`<cit>`/`<cb:tt>` in 5.

### `<app>` / `<lem>` / `<rdg>` — the apparatus

Pervasive and directly usable: **271 of 300 files** contain an `<app>` citing
two or more distinct editions, with real sigla (`【CB】`, `【金藏】`, `【宋】`).

The sigla are frequently **joint**: `【宋】【元】【明】【宮】` appears as a single
`wit` value 2,155 times. **A joint siglum is one shared-descent family, never
four independent confirmations** — splitting it would manufacture exactly the
false corroboration this system exists to refuse.

### `<note type="cf1|cf2|cf3">` — unread

436 occurrences in the 300-file sample, roughly 31,800 corpus-wide. **Nothing
reads this channel yet.** Noted rather than quietly omitted.

### Descent

Nothing in the markup asserts descent directly. There is no corpus channel for
`descends_from`, so COHORT does not extract it and does not pretend to.
`parallel_of` is what the corpus actually states.
