# Cohort at PNC: speaker's working canvas

> Historical draft from 7 September 2026. For the current presentation and interface, use the [presenter walkthrough](presentation/walkthrough.md) and [cue card](presentation/presenter-cue-card.md). Earlier implementation descriptions and speaking sequences may be outdated.

For rehearsal, use the shorter [demo cue sheet](pnc-demo-cue-sheet.md). This
document is the supporting audit, not the script to read on stage.

Draft, 7 September 2026. A new working document, not a transcription of the
private Claude explainer. The locally downloaded explainer (HTML kept outside version control) is now
readable and its section 0 and sections 12–14 have been compared with the code;
adjacent sections were read for context. The original download named
`The Translator Question, From Zero.html` is only the surrounding page shell.
Code inspection below refers to `74e3525` on `docs/handoff-2026-09-07`, with
the experiment README and quotes-discount diff read from their separate local
branches. This is not yet verification of the merged stack or a rehearsal.

## 0. Presenter's brief

**Agent-Based Infrastructures for Diachronic Digital Humanities.**

The audience is PNC. The research question, corpus, catalogue labels and string
list come from Michael Radich's philological work. The demonstration asks what
agents can usefully do with this material while leaving interpretation and
acceptance to the researcher. It does not attribute a text to a translator.

The instrument retrieves passages, compares string profiles, exposes shared
wording, and lets a researcher inspect what happens when a suspected dependent
source is withheld. Agents can record a conjecture, rival explanations and a
search-hit prediction. Withholding and recomputing a profile is a separate
sensitivity check. Citation checking can establish that words are present at a recorded
location; it does not establish that they support the interpretation.

The handoff's two cases are T0453, a known answer approached without supplying
it to the run, and T0603, a misleading profile resemblance exposed by examining
its relationship to T1694. Present these as worked cases, not an evaluation of
the instrument's general ability to identify translators. “Blind” needs the
qualification that withholding an answer from a prompt does not demonstrate
that a pretrained model has never encountered it.

**Recommended ending for this demo:** record and inspect the conjecture. Say:

> The proposed relationship is on the record for the researcher to assess.
> This run has not turned it into an accepted dependency edge. Withholding the
> suspected dependent text is an explicit sensitivity check. The reviewer has
> withheld attestation, so the conjecture remains proposed.

That last sentence applies to the run as reported in the explainer. Inspect
the actual trace before presenting it as the outcome of a particular run.
The researcher cannot accept a proposed conjecture directly: acceptance needs
attestation first. Do not bypass that rule to make the ending work.

Do not say that accepting the conjecture makes the Evidence profiles remember
the dependency. The profile calculation does not read graph edges.

## Suggested twenty-minute running order

These follow the explainer's section 0 allocations, with the ending corrected.
They are proposed allocations, not measured rehearsal timings.

| Time | Purpose | Show or say |
|---|---|---|
| 0–2 min | Establish the question and limits | Borrowed philological question; agent assistance; researcher decides. |
| 2–5 min | The evaluation trap | Explain why chapters from the same work must be held out together. |
| 5–9 min | The instrument | Vocabulary control; open Evidence on T0453 and explain the painting once. |
| 9–12 min | T0453 | Inspect the retrieved parallel and located shared wording; explain what survives explicit withholding. |
| 12–14 min | The encoder's limit | Keep unit-level classification separate from window-level retrieval and its baseline. |
| 14–18 min | T0603 | Inspect the misleading ranking, examine T1694, withhold it, then inspect the agent's conjectures and reviewer outcome. |
| 18–20 min | End at the implemented boundary | No attribution; conjectures remain proposed when review is indeterminate; no dependency edge was written. |

Use a verified saved trace if the live run is unavailable. Describe it as a
recorded run. Rehearse on the exact integrated revision intended for the talk.

## Claims checked against the code

### Dependency edges: the gap includes acceptance semantics

[`Edge`](../cohort/schemas.py) has authorship and retraction fields but no
proposed/accepted status. [`Graph.add_edge`](../cohort/graph.py) writes an active
edge, and `independent_support` consults active relations without an acceptance
gate. It reports counts, a boolean and related pairs; it does not merge sources
into a single witness. PR #6 adds quotation to the discounting types, but that
change is not in the inspected handoff branch.

An agent tool that merely calls `add_edge` cannot honour “proposed first,
effective only after researcher acceptance.” Stop short of implementing that
shortcut. A future proposal tool needs an explicit representation of the
proposal, grounded endpoints and evidence, and a researcher-controlled action
that makes the relation effective. That is more than wiring another tool.

[`AttributionIndex.evidence`](../cohort/attribution.py) withholds the target's
own work plus the units explicitly passed by the caller. It does not consult
the evidence graph. Even a future accepted edge would need additional,
deliberately designed integration to change profiles automatically.

### Grounding: existence is enforced; relevance is not

[`propose_claim`](../cohort/tools/propose_claim.py) accepts a nonempty grounding
query and requires search hits. It does not require that the claim follows
from the returned words, and it does not attach citations itself.

The [reviewer prompt](../cohort/agents/review_worker.py) already tells the model
to judge whether cited passages support the claim. Its objection can block
attestation. This is an instruction to a model, not a deterministic relevance
guarantee. A minimum span length alone would leave unrelated longer citations
able to pass. Describe the limit explicitly; do not promise relevance merely
by increasing the minimum length.

### Composite units: work withholding does not remove profile duplication

The profile builder keeps qualifying catalogue units and adds their string
counts. There is no composite-versus-chapter deduplication step. This confirms
the mechanism behind the handoff's concern about `T0125-minus-50.4`; this audit
has not reread restricted corpus contents or recomputed its contribution.

Recommended follow-up: deliberately define which representation contributes to
profiles, retain retrieval access to the other, and report exclusions in the
ledger. Recompute affected results before substituting numbers in the talk.
Do not silently drop the composite and retain the old margins or evaluation.

### “Leans” is not a calibrated decision

The backend chooses `low evidence` from a distinct-string count threshold;
otherwise it returns `leans`, without a margin floor. The
[Evidence panel](../cohort/ui/frontend/src/EvidencePanel.jsx) also renders the
word “leans” for nonempty results even when the backend says `low evidence`.

The [agent evidence tool](../cohort/tools/attribution_evidence.py) says a margin
near zero is nothing either way. The interface and this explanatory text do
not express the same decision rule. A neutral label such as “highest-scoring
profile” would report the calculation without inventing a calibrated cutoff.
Any abstention floor needs to be declared as a heuristic unless validated.

### Genre remains a competing explanation

String counts do not separate translator habits from genre, subject, shared
source or transmission. The tab's introductory material mentions genre, but
the result's numerical caveat mainly discusses overlapping strings. Put the
genre caveat beside the result as well, and retain it in the agent's reading.
Do not describe the strongest label-free strings as translator signatures.

### Alignment: name the measured quantity

[`align_passages._coverage`](../cohort/tools/align_passages.py) divides the
number of shared **distinct ten-character strings** by the number of distinct
ten-character strings in the first text, after retaining Han characters.
It does not calculate the proportion of text positions covered by matches.
The handoff's character-coverage wording for T0453 therefore needs another
calculation or corrected wording.

Runs come from `SequenceMatcher`, subject to its comparison-length limit;
coverage uses the full Han-only strings. The returned run text omits
punctuation, and offsets locate starts in the originals. Do not treat a run's
Han-character length as an original-text end offset.

Shared wording motivates quotation or common-source hypotheses. It does not
mechanically determine the direction of quotation or establish textual history.

## Direct comparison with the speaker's explainer

### Stage-critical corrections

**Section 0 contradicts section 12 about recording dependencies.** The opening
result says the instrument turns the hidden dependency into a recorded graph
relation, and its T0453 caution says a `parallel_of` edge gets recorded. Section
12's status paragraph and section 13b's caveat correctly say that tool is not
built. Use the latter status consistently, especially in the opening brief.

**Section 12's acceptance step needs a successful review first.** Section 13
reports indeterminate reviews of the new conjectures. In
[`review_claim`](../cohort/tools/review_claim.py), an indeterminate verdict does
not advance a node; `Graph.accept` refuses anything not already attested.
The explainer does not establish the later successful review its ending would
need. End on the recorded proposal and refusal to advance, or demonstrate a
separately verified attested finding. Do not describe a hypothetical acceptance
as part of the reported run.

**Sections 12–13 conflate sensitivity analysis with executable prospective
testing.** [`propose_conjecture`](../cohort/tools/propose_conjecture.py) stores a
query string, hit-count expectation and expected number of hits.
[`run_prospective_test`](../cohort/tools/run_prospective_test.py) sends that string
to `Source.search`; it does not dispatch `attribution_evidence` or compare
profile margins. It is also not registered as a worker tool. An agent can call
the read-only evidence tool again with withholding and interpret the returned
change, but that is not execution of the stored prospective test. The reported
chain in the handoff places withholding before conjecture proposal, so it does
not demonstrate a prediction recorded before that measurement either.

**Section 0's automatic withdrawal is not implemented by the verdict rule.**
The instrument recomputes a ranking; it does not withdraw an attribution or
automatically classify a small margin as abstention. Section 8's claim that
the tab's rule says nothing either way is inconsistent with the backend.
Sections 10 and 13b also call a vocabulary flip a move from wrong to right.
Use “the ranking changes” and “the remaining margin does not establish an
attribution.” Distinguish the researcher's interpretation from a software
refusal that actually occurred.

### Measurement and mechanism corrections

| Location | What needs correction | Supported account |
|---|---|---|
| §§0, 12, 13b, 14 | T0453 overlap is described as character coverage or text in shared runs. | The implemented share is over distinct ten-character strings, not character positions. |
| §12, alignment step | The pair tool is said to find every shared run and the next-best unit in the corpus. | It returns a limited set of `SequenceMatcher` blocks, with a comparison-length limit. A separate corpus scan finds the next-best unit. |
| §12, neighbour step | Detailed neighbours are described as returned for every window by the default call. | The tally covers all windows; detailed results are restricted by `max_windows`, whose default is six. |
| §13, grounded interpretation | Claim grounding and a conjecture's test are described as universal write-boundary requirements. | The worker proposal tools require them. Direct graph claim proposal does not run grounding; direct conjecture proposal without a test is allowed but cannot be attested. |
| §13, human expertise | Nothing an agent writes is said to become more than proposed. | Reviewers can attest; source-derived passages can also be attested mechanically. Only acceptance is reserved for the researcher. |
| §§11, 13 | The budget is described as a hard spending ceiling. | `BudgetedTransport` stops new calls once recorded spend reaches the threshold. An in-flight call can exceed it; this is not a guaranteed final-cost ceiling. Do not add output-token limits to paper over this distinction. |
| §§11, 14–15 | Similar editions are treated as automatically reduced to independent transmission families. | The edition script prints a pairwise similarity matrix. It does not infer a stemma; the backend counts witness IDs and flags recorded relations without merging them. |
| §14, evaluation explanation | Work-held-out accuracy is said to recognise translators. | It measures agreement with catalogue labels under that split; genre and other work-level similarities remain possible explanations. |

The [budget implementation](../cohort/agents/budget.py) checks accumulated spend
before transport and charges the response afterward. Parallel calls can also
be in flight together. Missing provider cost is accounted for with a configured
substitute, so distinguish recorded spend from a provider billing guarantee.

The [neighbour implementation](../cohort/embeddings.py) explicitly separates
the all-window tally from the displayed windows. The separate edition and
overlap scripts were inspected on `feat/experiment-scripts`.

### Claims to qualify, not turn into new guarantees

- “Strings see habit; vectors see subject” is an explanatory shorthand, not a
  measured separation. Both can reflect shared wording, genre and transmission.
  The string-overlap scan itself can expose the commentary, so quotation is
  not something counting could never find.
- Poor nearest-neighbour translator performance does not prove an encoder
  contains no translator information. The explainer itself reports a linear
  probe; retain that qualification when discussing retrieval results.
- “Blind” means the answer was not supplied to that run, if the trace verifies
  this. It does not establish absence from model training. A high-overlap
  retrieval is not a historical judgment about who copied whom.
- The reported labelled-text evaluation is neither a demonstrated ceiling nor
  a measured grey-text accuracy. Replace claims that no result can ever
  transfer with “generalisation to grey texts has not been established here.”
- Section 14 lists a few leading strings, then generalises to every string
  responsible for the ranking. The leading rows alone cannot support that
  claim; it requires the full contribution calculation.
- Sections 0 and 15 claim novelty and describe what Radich or the field lacks.
  Code inspection cannot establish these claims. Describe the demonstrated
  workflow without claiming priority or another researcher's limitations.

### Adjacent presentation details

Section 10 says the painted pair stays fixed across vocabulary switches. It
does when explicitly pinned; with an empty `pair`, the backend chooses the
leader or catalogue label and the strongest rival again on each request.
Pin both classes when a colour comparison is meant to hold them constant.
Use a fresh page load for prepared hash links: the panel reads the initial
hash once and does not subscribe to hash changes.

Section 11b still treats quotation as structural and undecided for independence,
while section 12 describes PR #6. The former matches the inspected branch;
the latter describes the separate pending change. Rehearse against the final
integrated graph styles and backend, not a mixture of those descriptions.

## Reproduced results and presentation package

This earlier audit is supplemented by the comprehensive local presenter guide
at `data/pnc-production/presenter-guide.html`, editable deck
`data/pnc-production/cohort-pnc-2026.pptx`, and measurement ledgers in that folder.
The private guide contains bounded source screenshots and should remain outside
Git. Use it as the current presentation reference.

Fresh calculations resolve the overlap discrepancy. T0453 shares 2,180 of
3,059 distinct Han 10-grams with the T0125 chapter (71.27%). Separately,
2,898 of 3,116 Han positions are covered by matching grams (93.00%). The
pairwise tool reports the first measure. T0603 shares 5,858 of 9,089 distinct
10-grams with T1694 (64.45%); the next match in the separate 2,305-unit scan
shares 14 (0.15%). These measures do not establish borrowing direction.

T0603's curated-vocabulary margin changes from pre-Dhr-other over ASg by
1.696 to ASg over pre-Dhr-other by 0.096 when T1694 is withheld. The actual
browser displays +0.10 and still says “leans.” Treat that as a sensitivity
result; do not describe it as calibrated automatic abstention.

## Verification record

The original checkout passed 527 tests; a temporary integration adding the
quotes-discount and experiment-script branches passed 530 tests. Both reported
two dependency deprecation warnings. Ruff and ty passed with cached tools.
No tracked application changes or PR merges were made. The frontend builds
passed with Vite's bundle-size warning.

The initial browser failure was overcome using cached Playwright Chromium.
The subsequent real-data walkthrough verified Evidence selection, vocabulary
switch, T0603 withholding, Findings expansion, located citation inspection,
Corpus search (two visible records) and task seeding into Inquiry. It reported
no page errors. No new paid agent run was performed. A changed URL hash alone
can leave the prior selection active; use a fresh document and check its ID.

The dense full graph and small supporting text remain presentation weaknesses.
The slides use selected panels and enlarged measurements; the guide teaches
all five tabs. The existing T0603 conjecture remains proposed. No general
grounded dependency-edge proposal/acceptance workflow was added, and Evidence
profiles do not consult accepted graph relations. The demonstration ends at
an inspectable proposal and the researcher's next question.

## Answers to likely floor questions

**Did you attribute a text?** No. We inspected evidence and its dependencies.
The researcher decides what, if anything, it warrants.

**Does citation verification make the interpretation correct?** No. It checks
recorded words against the source. Relevance and interpretation remain open.

**What is diachronic here?** Historical ordering supplied by ascriptions is
visible beside profiles. There is no implemented time model; say “dated by
ascription,” not “diachronic analysis.”

**Are the markup tools live in this demonstration?** The handoff says the
demo uses Radich's plain-text source. The CBETA apparatus tools require the XML
archive. Shared-run alignment should be named for what it actually shows.

**Does Cohort enforce access governance?** No. ATELIER is separate and is not
connected. Use locally held material within the stated restrictions; do not
claim governance from provenance hashes.

## Outstanding review

- Resolve the overlap denominator and conflicting recorded results.
- Inspect the actual run trace before claiming acceptance, prospective testing,
  a particular witness count, or an answer withheld from the prompt.
- Test the integrated PR stack and rehearse the exact demo actions.
- Confirm the presenter adopts the conjecture ending before treating it as
  the final talk script.

No corpus contents, embeddings, credentials or transcript excerpts are included
in this document. No runtime behaviour has been changed by this draft.
