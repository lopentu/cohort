# PNC demo: speaker cue sheet

> Historical draft from 7 September 2026. For the current presentation and interface, use the [presenter walkthrough](presentation/walkthrough.md) and [cue card](presentation/presenter-cue-card.md). Earlier implementation descriptions and speaking sequences may be outdated.

Working script for a twenty-minute presentation. Use the Claude explainer for
background, and [the working canvas](pnc-speaker-canvas.md) for the code audit.
Experimental figures belong on stage only after reconciling their recorded
outputs. This sheet introduces no new measurements.

## Opening · 0–2 minutes

“Can agents help a scholar investigate uncertain translator ascriptions?
We borrowed a philologist's question and materials to build an instrument for
that investigation. We have not attributed a text. We show where a resemblance
comes from, investigate what might explain it, and leave the judgment open.”

## The trap · 2–5 minutes

Show the work-held-out comparison once. Explain that training on other chapters
of the same collection can make a classifier appear to identify a translator
when it is recognising the collection. Agreement with catalogue labels under a
better split still does not establish the translator of an unknown text.

“Before asking an agent to interpret a number, we need to know what was counted
and what was kept out.”

## The instrument · 5–9 minutes

Open Evidence on T0453. Collapse introductory text before presenting. Pin the
pair of profiles so changing vocabulary does not change what the colours mean.
Explain only the pair, the coloured passage, and the strings pulling each way.
Open the ledger only if needed to answer a question.

“These colours show resemblance to two profiles. Shared wording, genre and
transmission can all produce that resemblance.”

## The known parallel · 9–12 minutes

Show the retrieved Ekottarika chapter and the located shared wording. Describe
alignment's percentage as a share of distinct ten-character strings. Withhold
the chapter, then the profiled collection, and inspect the changed ranking.

“This is a known parallel that the retrieval can recover. The surviving
resemblance still does not tell us whether we are seeing a translator's habits,
a genre, or a history of copying.”

## The encoder's limit · 12–14 minutes

Keep the retrieval evaluation separate from unit-level classification. The
encoder need not identify translators reliably to retrieve a useful parallel.
Do not infer that translator information is entirely absent from its vectors.

## The misleading resemblance · 14–18 minutes

Open T0603 with a pinned comparison. Show T1694 among its retrieved neighbours,
then the shared wording. Withhold T1694 and inspect the remaining margin.

“The ranking depended on a text reproducing the target's wording. Withholding
that text changes the evidence. It does not prove the opposite attribution.”

Show the actual agent trace: measurements, proposed explanations, and review.
Name a saved trace as a recording. Distinguish recomputing the profile from the
stored prospective-test mechanism, which currently checks search-hit counts.

## Ending · 18–20 minutes

If the selected run ends in indeterminate review:

“The reviewer has not attested this conjecture. The system therefore will not
let us accept it. We can inspect the evidence and the reasons it stopped.
The proposed relationship is recorded in prose; this run has not created a
dependency edge.”

“The contribution is an inspectable investigation: agents retrieve and compare,
propose competing readings, and expose what the checks do and do not establish.
The researcher's judgment remains necessary.”

## Before stepping on stage

- Rehearse the exact integrated branch on the presentation laptop.
- Correct the stale Graph introduction and the misleading Evidence verdict
  wording before relying on them as explanations.
- Reconcile the overlap figures and denominators; retain aggregate outputs.
- Prepare fresh-page links, explicitly select Evidence, pin each comparison,
  and close the intros. Hash changes alone do not refresh an open panel.
- Check the highlighted excerpt and essential caveat from the back of the room;
  use browser zoom and focus on one result instead of the whole dashboard.
- Keep a recorded run available. Do not depend on a new model run reaching a
  particular verdict or on the current server staying available.
