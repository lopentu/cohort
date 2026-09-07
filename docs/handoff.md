# Handoff: current state

What is true as of **2026-09-07**. For how the system got here, see
[changelog.md](changelog.md); for why it is shaped this way, see
[design.md](design.md). The previous handoff (2026-09-02) is in git history,
one commit before this file's rewrite; its "what does not exist" list is
summarised at the end.

## What we are trying to do

Give a twenty-minute demo at PNC 2026 under the abstract *Agent-Based
Infrastructures for Diachronic Digital Humanities*: agents that assist with
corpus retrieval, semantic analysis, variant alignment and interpretation,
provenance-aware, grounded in source texts, with the human researcher's
judgment kept in the loop.

To keep the demo grounded in something the field cares about, we took a
working philologist's research questions as the frame. Michael Radich sent
three; we use the first, *can we work out methods or tools that will help us
determine accurate ascriptions for texts whose translator is unknown ("grey")?*
The audience is PNC, not Radich. His questions and his corpus are the grounding;
the point of the talk is what LLM agents can do for this kind of research and
what the infrastructure refuses to let them do.

The honest Q1 result is an instrument, not attributions. No grey text has been
attributed and none will be claimed. What the instrument does is stated in
[the explainer](#artifacts) section 0 and summarised under *Numbers* below.

## Read first

1. **[design.md](design.md)** §0 carries the standing rule: when a rule cannot
   be honoured, say so and stop; do not build something that looks like it
   honours the rule.
2. **`AGENTS.md`** at the repository root: commands, the rules the tests
   enforce, style, and the list of things that bit us this week.
3. **This file.**
4. **The explainer artifact** (below), which is the speaker's brief and the
   most complete account of the results and their caveats.

## Verified state

    uv sync --extra dev --extra ui --extra evidence
    uv run pytest -q                  # 527 passed here; 528 with the two tests in #8
    uvx ruff check .                  # clean
    uvx ty check cohort scripts       # clean
    cd cohort/ui/frontend && npm install && npm run build

Live, this week, all manual: a worker on `meta/muse-spark-1.3` with a reviewer
on `x-ai/grok-4.6` chained `attribution_evidence` → `semantic_neighbors` →
`align_passages(T0603, T1694)` → `attribution_evidence(withhold T1694)` →
`propose_claim` → `find_attestations` → `propose_conjecture` (two rival
explanations with tests) in 73 s for $0.11; the reviewer returned
*indeterminate* twice and found one older claim unsound (5 of 53 spans failed
to re-fetch); five refusals were logged (four `UngroundedClaim`, one
`NodeNotFound`).

## The branch stack

Upstream is `lopentu/cohort`. `main` gained a force-directed Graph tab on
2026-09-06 (vis-network; claims coloured green, yellow or red from the edges).
Everything below is rebased onto that and open as pull requests, in this order:

| PR | branch | base | what |
|---|---|---|---|
| #2 | `chore/strict-ruff-ty` | `main` | strict ruff config, clean ty pass, `AGENTS.md` + `CLAUDE.md` shim |
| #3 | `feat/evidence-tab` | #2 | `cohort/attribution.py`, the Evidence tab, `cohort evidence`, `/api/evidence` |
| #4 | `feat/radich-corpus-source` | #3 | Radich's corpus as a `LocalReader` source (`LOCAL_CORPUS_ROOT`), output ceiling and reasoning effort configurable, CBETA pin configurable |
| #5 | `feat/evidence-tools` | #4 | `attribution_evidence`, `semantic_neighbors`, `align_passages` as worker tools; `cohort/embeddings.py`; `UnitNotInCorpus` |
| #6 | `feat/quotes-discounts-independence` | #2 | a `quotes` edge discounts independence like `parallel_of` |
| #7 | `feat/tab-intros` | #5 | a collapsible plain-language intro at the top of every tab |
| #8 | `feat/experiment-scripts` | #5 | `scripts/experiments/`: every number in the talk as a script over the library |
| #9 | `feat/evidence-pair-link` | #7 | `#uid=…&pair=A,B` pins the painted pair; a repaint box in the tab |
| #10 | `docs/handoff-2026-09-07` | #9 | this document and the doc updates around it |

Merge in numeric order; #6 can go any time after #2. `data/` is git-ignored and
must stay so (Radich's corpus is his unpublished modification of CBETA).

## What exists now that did not on 2026-09-02

- **The Evidence tab** ([ui.md](ui.md)). For any unit of Radich's corpus: a
  ranking of thirteen translator classes by string evidence, the text painted
  as a fixed pair A (teal) against B (rust) with saturation as summed log-odds,
  a strip over the whole text, the strings pulling each way with raw counts
  and rates, a withhold box for the sensitivity test, the ledger of what was
  discarded, and provenance hashes. The leakage rule (never profile the
  target's own work) is enforced on every query and asserted in code.
- **Two vocabularies.** Radich's Table 1 (7,270 strings of length 2–4) and a
  label-free vocabulary drawn from the grey texts, matched in size and length
  mix; 383 strings shared.
- **Three read-only evidence tools** a worker can chain ([tools.md](tools.md)).
  Embeddings come from the two Dharmamitra encoders over 400-character windows
  (54,616 windows, 2,160 units), stored as `.npz` outside the repository.
- **Radich's corpus as the Source** for Corpus and Inquiry, through
  `LOCAL_CORPUS_ROOT` and a generated manifest ([corpus.md](corpus.md)).
- **The experiments as scripts** (`scripts/experiments/README.md` maps every
  quoted number to a command).
- **Tab intros, pair links, the quotes discount, the upstream force graph.**

## Numbers, and where they come from

All from `uv run python -m scripts.experiments.<name> data/radich` unless
stated; the README there pastes the outputs.

| number | what | script |
|---|---|---|
| 82% → 52% | naive Bayes on Radich's strings, leave-one-unit-out vs leave-one-work-out | `attribution_eval` |
| 95% → 3% | Saṅghadeva across the same two splits (106 of 108 units are chapters of T26) | `attribution_eval` |
| 52.2% vs 47.8% | Radich's vocabulary vs label-free, works held out | `attribution_eval` |
| 33.7% / 34.0% | 2B / 9B encoder, nearest centroid on mean window vectors | `encoder_eval` |
| 23.7% vs 24.0% | nearest window in another work is by the same translator vs largest-class baseline | `neighbors_eval` |
| 56.8% | char 1–3-gram linear SVC, five grouped folds | `encoder_eval --trained` |
| 65% · 279 · 0.21% | T0603's 10-grams in T1694 · longest run · next unit | `overlap_scan` |
| +1.70 → +0.10 | T0603 margin before and after withholding T1694 | `cohort evidence T0603 [--withhold T1694]` |
| 10 of 10 · 0.94–0.99 | T0453 windows whose nearest neighbour is T0125-48-十不善品-3, both encoders | `semantic_neighbors` |
| 93% · 156 | T0453 characters covered by 10-grams shared with that chapter · longest run | `align_passages` |
| +1.18 → +1.11 → +0.53 | T0453 margin for ZFn: as is · chapter withheld · all 40 profiled T0125 units withheld | `cohort evidence T0453 --withhold …` |

Withdrawn and not to be quoted: the 38% temporal-adjacency figure; the first
per-class control table (a smoothing constant left at the wrong value); the
11.4% / 25–32-character overlap (punctuation left in).

## The two worked texts

- **T0453** (佛說彌勒下生經; Taishō byline Dharmarakṣa; Radich: grey). One text
  under two catalogue entries: it is discourse 48.3 of the Ekottarika-āgama
  (T125, Zhu Fonian in Radich's tables). The strings lean Zhu Fonian, every
  window retrieves the chapter, and the lean survives withholding the whole
  collection. The field has rejected the Dharmarakṣa ascription since 1935.
  Shown first: a known answer reached blind.
- **T0603** (陰持入經, An Shigao) and its commentary **T1694**. Radich's
  strings lean the wrong way because the commentary quotes the sūtra and sits
  in the rival profile; withholding it leaves no case either way. Shown second:
  the instrument catching itself.

## What needs a fresh set of eyes

Ordered by how much it could embarrass the talk.

1. **Step 6 of the demo may be narrative only.** The story ends with the
   researcher accepting a `quotes` (T0603/T1694) or `parallel_of`
   (T0453/T0125-48.3) edge. Check what can actually write those edges today:
   `link_parallels` writes only CBETA's asserted cross-references, and neither
   front end can draw an edge by hand. If nothing can propose the edge from the
   evidence tools' output, either add a tool that proposes it (with the same
   grounding rules) or say on stage that the last step is not built.
2. **Grounding relevance.** A claim grounded on the single character 佛 passed
   `propose_claim`. The span exists, so the rule is satisfied; nothing checks
   that the span bears on the claim. Decide whether a minimum span length or a
   reviewer instruction is the right fix.
3. **`T0125-minus-50.4`.** Radich's catalogue lists the whole Ekottarika-āgama
   less discourse 50.4 as one unit (359,955 characters) alongside its chapter
   units. Both are profiled, so the collection is in Zhu Fonian's profile
   twice. The leak check treats them as one work, so no leakage; the weights
   are still doubled. Decide whether to drop the composite unit from profiling.
4. **The verdict rule.** `leans` versus `low evidence` is decided by the count
   of distinct strings hit, so a margin of +0.10 still reads "leans". The
   explainer calls that "no case either way"; the tab should probably say so
   itself. Consider a margin floor and say what it is.
5. **Genre.** For T0453 the heaviest label-free strings are narrative formulae
   (爾時, 是時, 來至我所). The evidence tool measures resemblance to a profile,
   and profiles are mostly one genre per translator. The explainer says this;
   a reviewer should decide whether the tab needs to.
6. **The markup tools are not live** against the CBETA archive because `.env`
   points at Radich's corpus. Switching needs `CBETA_ARCHIVE_PATH`,
   `CBETA_ARCHIVE_SHA256` (a373aee3…da00e for the 2021Q3 bookcase),
   `CBETA_ARCHIVE_VERSION="xml-p5 2021Q3"` and `CBETA_FTS_PATH`; the Evidence
   tab does not depend on it.
7. **The frontend has no tests of its own.** The pair link and the intros were
   checked in a browser by hand. Note also that changing only the URL hash in
   an open tab does not reload the app.
8. **The host rebooted twice on 2026-09-06** as hard resets with no software
   cause found. Present from a laptop; keep a recorded trace of the agent run.
9. **An OpenRouter key was printed into a session transcript** and should be
   rotated.
10. **The explainer is long** (about 100 KB) and was written for the speaker,
    not the audience. A reader who checks it against the code for overclaims
    would be doing useful work; sections 12, 13 and 14 are where claims live.

## Environment

    OPENROUTER_API_KEY=                 # never in chat, logs or git
    OPENROUTER_MODEL=meta/muse-spark-1.3
    OPENROUTER_MODELS=meta/muse-spark-1.3,x-ai/grok-4.6
    OPENROUTER_MAX_OUTPUT_TOKENS=0      # 0 or none = no ceiling
    OPENROUTER_REASONING_EFFORT=low
    LOCAL_CORPUS_ROOT=data/radich/corpus/T-stripped
    EVIDENCE_EMBEDDINGS_PATH=~/corpora/embeddings/mitra-qwen35-embedder.npz

    uv run python scripts/serve_ui.py --db demo_graph.sqlite --radich data/radich \
        --corpus --allow-runs --allow-writes --max-budget 0.50 --port 8010

Data lives outside the repository: `data/radich/` (Zenodo 7750586 plus the
three files from the email; licence-restricted), `~/corpora/embeddings/*.npz`
(233 MB and 457 MB), `~/corpora/CBETA_xml-p5_2021Q3_bookcase.zip` and the FTS
index built from it. Re-embedding takes 36 minutes (2B) and two hours (9B) on
the lab GPU.

## Artifacts

Private pages on claude.ai/code, owned by the account that ran the sessions.

- **The Translator Question, From Zero** — the speaker's explainer: the
  presenter's brief (section 0), the corpus and the people, every experiment
  with its caveat, the two worked texts, every tab, the abstract mapping,
  numbers, floor questions, glossary.
  https://claude.ai/code/artifact/65c30918-dc56-423c-9b46-26d7ca9fa66a
- **Strings, Encoders, and One Bug** — the experiment write-up, including the
  smoothing bug and the corrected control table.
  https://claude.ai/code/artifact/36a4bd25-90c2-4d06-b492-c28b1a795df7
- **T0603 Evidence Map** — the first painted-text mock, superseded by the tab.
  https://claude.ai/code/artifact/26fc6f50-cdfc-4f82-bf56-5fbdc940473a
- **Cohort and the Radich Problems** — the early mapping of the three
  questions onto Cohort.
  https://claude.ai/code/artifact/3b547c34-25c2-44c5-8d58-4aecde3bc106
- **Attribution Without a Test Set** — superseded by the explainer; kept for
  the record.
  https://claude.ai/code/artifact/41fd9051-cd06-453d-9930-f871b0ee0dba

## What does not exist

Unchanged from 2026-09-02 unless noted: relevance ranking; `descends_from`
extraction; automatic contradiction detection; a measurement layer beyond
`run_prospective_test` and, now, the three evidence tools; claim versioning;
reputation scoring; access governance (ATELIER, not connected). New: accepting
an edge from the Evidence screen; a way to propose a `quotes` or `parallel_of`
edge from tool output (item 1 above).
