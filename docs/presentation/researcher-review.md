# Cohort from a researcher’s perspective

Review date: 9 September 2026. Current presentation branch: `feat/pnc-presentation-ready` at `9ad0876` before this documentation update. Remote branches fetched for inspection: `origin/feat/rq3` at `39bcc98`, and `origin/feat/rq3-force` at `2f8b97c`. Neither was merged into the running application.

## Assessment

Cohort is useful for locating passages, comparing their wording, and retaining the proposed explanations and actions for inspection. Its value is less clear when it presents a translator-group ranking before explaining which texts make up the groups or what the researcher should inspect next.

The strongest presentable operation is a concrete research task: find candidate parallels, read their context, compare wording, and document why a candidate was retained or set aside. The researcher still needs to assess genre, transmission, catalogue decisions and the relevance of quotations. Those judgments cannot be inferred from a successful span check.

The existing T0453 and T0603 cases are useful teaching examples, but they do not establish performance on unresolved ascriptions. Their historical relationships are already known. T0603 shows that including a commentary changes this numerical comparison; it does not show that the system can reliably discover all dependencies or correct its own interpretations. A harder example should be evaluated as an investigation with a reading payoff, not selected because it returns a more exciting label.

## What each tool contributes

| Tool or surface | Useful research action | Present limitation |
|---|---|---|
| Corpus | Locate an exact phrase and inspect its source context | Corpus-order results and a display limit; no ranking by scholarly relevance |
| Semantic neighbours | Suggest passages to compare when exact wording is not known | Similar subject matter can dominate; nearest does not imply historically related |
| Align passages | Locate shared runs in a selected pair | Exact normalised overlap misses paraphrase and does not establish borrowing direction |
| Evidence | Test whether a string-profile result depends on a vocabulary or an included source | Closed set of catalogue groups, uneven material, overlapping strings, no validated attribution threshold |
| Inquiry | Give agents a task and inspect their chosen tools and inputs | Agent choices and stopping behaviour vary; stated reasons can be weak |
| Findings and Graph | Reopen arguments, citations, checks and researcher decisions | A large or well-connected graph is not a measure of evidence quality |
| AI analysis | Ask for an explanation and further read-only investigation of the current view | Fallible interpretation; saved answers refer to a snapshot, not a continuously updated result |

## What Evidence is for

Its defensible question is: **how does this comparison behave when I change a declared assumption?**

A researcher can use it to identify strings that influence a ranking, inspect their contexts, exclude a suspected source of repeated wording, and see whether the result persists. Its output can help choose the next passage or control to inspect. It currently provides much weaker grounds for deciding between translator ascriptions.

The ranking is over profiles built from the supplied catalogue, not every CBETA text or every possible translator. The current API reports 368 retained units and 13 groups before withholding. Some units are chapters. The full ranking is now visible, but its score differences do not have a calibrated historical interpretation. A larger lead is a larger difference under these settings; it is not a confidence percentage.

For the presentation, call this a **wording comparison** and describe the exclusion operation. Avoid “translator detector,” “the system catches its own error,” and “the remaining margin means it abstains.” The application has an explicit no-matching-strings output; it does not have a validated small-margin abstention threshold.

## The teammates’ Q3 work

The branches address a Paramārtha ascription study. They distinguish a benchmark group treated as securely assigned, disputed works, and a negative-control group believed not to belong. The names `P-23`, `P-weird` and `interloper` are catalogue labels, not self-explanatory results. They should be expanded in a presentation.

Two additions are relevant:

1. **Feature testing.** Register a candidate string and expected benchmark/control occurrence shares, measure both groups, retain failures in a ledger, and allow application to disputed works only after a passing control record.
2. **Neighbourhood comparison.** Build a Burrows’s Delta space from character-bigram frequencies, inspect nearby works, compare the presence of benchmark members among neighbours, and report calibration from known group members.

These are more explicit research operations than a bare top-two ranking. They do not yet answer Q3 conclusively. The branch’s narrative reports candidate relationships worth examining, but I did not reproduce its real-corpus measurements in this review. Do not reuse its numerical results as newly verified findings.

## Findings that affect readiness

**1. Chapter dependence is still possible in the Q3 neighbourhood calculation.** `delta_study.py` loads individual directories as entries, and `association.py:_ranked` excludes only the exact target ID. `delta.py:profile` does the same. A synthetic example with `T0001-1` and `T0001-2` containing identical text returned the second chapter as the first chapter’s nearest neighbour, at Delta 0.0. The code does not exclude the rest of the target’s work. This is useful for finding repetition but undermines interpretation of neighbour counts as independent evidence about a translator. Whole-work identity and dependence need explicit treatment before an attribution evaluation.

**2. “Survives a genre control” overstates the implemented comparison.** `Association.group_reading` names the nearest group member and nearest outsider. There is no genre-matched sampling or genre annotation in that operation. A nearer benchmark work is a reason to read that pair, not proof that genre has been controlled. The hypergeometric calculation also uses an idealised random-neighbour reference; corpus dependence and genre can invalidate an attribution reading of its p-value.

**3. A passed feature control is not bound to all later measurement settings.** Registration stores the feature and group-share prediction, while `run_control_test` and `apply_to_disputed` separately accept edition and length-floor arguments. `control_status` checks for the latest passing control verification on the conjecture; it does not compare the later corpus, catalogue membership, edition or floor with those of the passing run. Bind the pass to a fingerprint of the measurement configuration before claiming an enforced same-experiment gate. This finding is from code inspection, not an exercised exploit.

**4. The branch uses exploratory thresholds as categorical wording.** `Association.verdict` uses the benchmark median and neighbour-gap percentile rules to produce `associates`, `weak`, `alternate` and `unplaced`. These rules can organise reading priorities, but they have not been shown here to recover translator identity on independent data. The wording needs to name the observed relationship rather than imply an ascription.

**5. A seeded workflow is not an autonomous run.** `scripts/seed_paramartha_demo.py` registers chosen features and invokes tools directly. This is useful for testing the workflow and constructing inspectable records. If shown, identify it as a scripted study. It is not evidence that an agent independently selected those features or discovered those results.

**6. Integration is not ready for the active application.** On an isolated snapshot of `2f8b97c`, the focused calculation/tool suite passed 104 tests. Ruff reported 77 findings, including 43 relative-import violations. Ty reported nine diagnostics when pointed at the existing project environment. These are measured check results, not a full acceptance test of the branch. Its source, graph, UI and schema changes overlap the current presentation work. A night-before merge would require resolving those differences and retesting the application.

## Changes worth making before presenting

**Do now in the materials:** structure the talk around the abstract’s operations; show one input, output and next action for each. Introduce the local corpus and closed comparison set before showing ranks. Use the T0603 exclusion to teach the comparison, with an explicit statement that it is a known relationship. Keep Q3 in a reference slide as current development, not a completed answer.

**Low-risk UI follow-up:** put the dataset scope and group count beside the Evidence result; explain the two score scales there; make the route from a high-weight string to its Corpus contexts more direct. The first two are copy and placement changes. The last needs a small interaction change and a browser check. This review does not itself change the running UI.

**After the presentation:** repair the reviewer’s evidence-access sequence; bind feature-control passes to their measurement inputs; apply whole-work exclusions in the Q3 study; compare results under feature, length, genre and source-dependence controls; then rehearse a disputed case with a domain researcher. Report useful retrieved passages, misleading candidates and reading effort as well as label agreement.

## Examples to consider next

Keep **T0603 with T1694 excluded** for explaining a sensitivity check. Use **T0453 and its known parallel** as an optional retrieval/alignment control.

The Q3 branch names **T1529 compared with T1820** as a possible alternative reference point, and **T1584 compared with T1559** as a benchmark-related candidate. These deserve bounded source reading and an alignment check before presentation. They are candidates from the branch, not recommendations endorsed by newly reproduced results. Do not swap them into the live session solely because their status labels look stronger.

We do not need to answer all of Radich’s questions to present Cohort. We do need to show an operation that helps a scholar examine evidence and explain what remains unresolved. Q3 may offer the better future evaluation because it includes specified benchmark and control material, but its current implementation still needs the checks above.
