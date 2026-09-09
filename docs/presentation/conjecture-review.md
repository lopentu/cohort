# Review of the saved conjectures

Reviewed the running session on 9 September 2026, without changing any graph record. The Findings response contained eight proposals: three conjectures and five claims. This assessment covers all three conjectures, their dossiers, linked tests, citations and reviewer records. It is a methodological review, not a philological attribution judgment.

All three were proposed by `agent:inquiry-1`, using `meta/muse-spark-1.3`. Their recorded reviews used `agent:inquiry-reviewer`, with `x-ai/grok-4.6`. These identities were read from creation provenance, not inferred from current settings. All three currently have status `attested`; none is researcher-accepted.

## 1. Shared dependence or formulaic stock

Record: `conjecture:3df6f4eb11c24d3084847c509c9b39dc`.

**Reasonable as a cautious interpretation; weak as a testable conjecture.** It treats the T0603–T1694 resemblance as dependence, quotation, commentary, reuse or shared formulas, while withholding common authorship. The measured overlap supports investigating such explanations. But the alternatives are bundled so broadly that the recorded test cannot distinguish them. Shared formulas can also recur in separately composed texts; their presence alone does not exclude independent composition.

Its proposed test searches an already observed sequence and predicts at least two matches. That tests recurrence of the sequence, not which historical explanation is correct. No executed prospective-test result is recorded. The dossier also calls T1541 and T1553 “other quoters” without establishing that characterization in the cited records.

Better wording: “T0603 and T1694 share extensive wording. Quotation, commentary or another shared textual source could explain it; this comparison does not distinguish those possibilities or establish common authorship.” This is an exploratory interpretation, not a new attribution.

## 2. Exclusion leaves “no meaningful distinction”

Record: `conjecture:f70e3ff5912b46af9005d248f9ff41f3`.

**The change in ranking is real; the interpretation overreaches.** The comparison changes when T1694 is withheld. However, the code has no validated equivalence threshold that turns the remaining margin into “no meaningful distinction.” Calling the mixed pre-Dharmarakṣa material a translator's vocabulary also obscures that it is a collection of differently attributed material, not one translator.

The dossier says recurring formulas cannot explain runs longer than 100 characters. Length alone does not establish that exclusion. It also generalizes from comparisons with two additional candidates to a relationship “specific to T1694”; that is narrower evidence than the claim implies.

Its recorded test again searches known shared wording, rather than testing the exclusion effect or distinguishing reuse from common authorship. No prospective-test result is recorded.

Better wording: “With the curated strings and the current corpus, excluding T1694 changes the leading group from the mixed pre-Dharmarakṣa group to An Shigao. The resulting margin is 0.096. Its significance for attribution has not been calibrated.” The first two sentences report a measured result and fit a claim better than a new conjecture.

## 3. A margin of 0.096 means “no evidence either way”

Record: `conjecture:866ccf7d73cb4f2eb0d10d2b38f503f1`.

**Do not accept as written.** The statement converts a small lead into absence of evidence. The live calculation still has 35 distinct matched strings and 45 occurrences; it returns a ranking, not the code's no-evidence result. The justified conclusion is that this calculation does not establish an attribution, not that no evidence exists.

The linked test is another known-phrase search with an expected minimum of two matches. No prospective-test result is recorded. The broad claim about what the whole corpus can settle also exceeds the particular vocabulary calculation.

Use the replacement wording in item 2. These two conjectures largely duplicate the same observation across different inquiries.

## What the checks actually establish

Recomputed using the running vocabulary endpoint and the repository's alignment tool:

| Calculation | Result |
|---|---|
| Curated strings, no additional exclusion | Mixed pre-Dharmarakṣa group first; An Shigao second; margin 1.696 |
| Same calculation, T1694 excluded | An Shigao first; mixed group second; margin 0.096 |
| Matched vocabulary, both configurations | 35 distinct strings; 45 occurrences |
| T0603 distinct Han-character ten-grams also in T1694 | 0.6445 |
| Reverse ten-gram coverage | 0.3155 |
| Longest shared sequence | 279 Chinese characters; alignment not truncated |

All three conjectures cite the same two source-passage records, each containing a 22-character excerpt. Those excerpts locate shared wording; they do not contain the computed exclusion scores. The calculation is available in tool records, but it is not supplied by those source quotations.

The reviewer correctly noted this mismatch in earlier reviews of item 3, then later described the cited passages as reporting the computed margins. That later explanation is wrong. A stronger reviewer could still make the same error if its evidence-reading workflow is incomplete.

The support readout also reports `independent: true` for these pairs because no dependence edge is recorded. That is absence of a recorded dependency, not a demonstrated finding that T0603 and T1694 are independent sources.

## Model decision

A different worker model is worth evaluating, but changing models alone is not a demonstrated fix. First require numerical interpretations to name their calibration or stay descriptive; require proposed tests to distinguish the stated alternatives; and give the reviewer the actual tool results alongside the citations. Then compare worker models on the same question and instructions, assessing source use, numerical accuracy and whether their tests could fail. This review makes no claim that a particular alternative model is stronger.

No proposals were accepted, rejected, rewritten or deleted during this review.
