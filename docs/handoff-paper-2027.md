# Handoff: one month of work toward an ACL 2027 or IJCAI-27 submission

Written 2026-11-23. This is a plan, not a record of results. Every piece of
work below is **proposed**, and no number here was measured unless it is quoted
from an existing document that is named.

Read these first:

1. [handoff.md](handoff.md) for what the system does today. Its test count is
   stale: the suite is 651 passing as of this note.
2. [presentation/conjecture-review.md](presentation/conjecture-review.md), a
   review of the conjectures saved in the September session.
3. [presentation/researcher-review.md](presentation/researcher-review.md), a
   review of what each tool is useful for.

The last two are the most recent critical readings of what Cohort's output is
worth.

## What the paper is about

Cohort helps a researcher go from a **research question over a corpus** to
**hypotheses backed by actual claims**. It works with the record types and
statuses defined in [vocabulary.md](vocabulary.md):

- An agent proposes **claims**. A claim must cite passages in the corpus.
  Before a claim can reach `attested`, Cohort re-fetches every cited passage
  and checks that the quoted text is really there.
- An agent proposes **conjectures**. A conjecture may go beyond what the cited
  passages say; that is how something new gets proposed. In exchange,
  `propose_conjecture` refuses to record it unless the agent also supplies all
  of the following:
  - how the agent arrived at it;
  - which part of the corpus it covers;
  - how the selection of evidence could mislead;
  - other explanations;
  - a search for earlier work;
  - a search query whose result could refute it, with a prediction of how
    many hits that query will return, stated before the query is run.

  `run_prospective_test` later runs that query and compares the result with
  the prediction.
- A reviewing agent from a different model family checks the claim or
  conjecture. It can stop a record from advancing, but cannot advance one on
  its own judgement.
- Only the researcher can mark a record `accepted`.

[design.md](design.md) §7 calls the conjecture requirement the "falsifiability
gate". It also says this requirement is the project's contribution: it lets an
agent propose something new, but only together with a way to find out that it
is wrong. The paper should be built around that.

So the question the paper has to answer is:

> **Given a research question and a corpus, does an agent working under these
> requirements produce hypotheses that are better supported by their citations
> and easier to test than the same agent with the same tools and corpus but
> without the requirements? And what do the requirements cost in records they
> refuse?**

Nothing in that question names a language or a domain. Cohort is meant to work
with any research question over any corpus. **Every experiment in this plan
runs on your own data.** None of it needs CBETA, Radich's corpus or anything
under `data/`, and none of it should.

## Your data and your research questions

**What Cohort needs from your data.**
- **Plain-text files and a `manifest.csv`** listing them
  (`path, witness_ref, label, note`; see [corpus.md](corpus.md)). `LocalReader`
  indexes the text one character at a time, so search works in any script.
  It has only been used on Chinese, so check search on your data first.
- **Optional: known relations between your texts.** For example, "B copies A",
  or "these two are versions of one text". Item 3 below adds a file format for
  declaring them. Without it, Cohort has nothing to tell it that two agreeing
  sources are not independent.
- **Licence or permission** to use the texts, and to quote short passages in
  a paper. Record it beside the manifest, as `examples/local_corpus/README.md`
  does.

**What works on your data today:**
- the evidence graph and its event log;
- `propose_claim`, `propose_conjecture` and `run_prospective_test`;
- re-fetching cited passages;
- the reviewing agent;
- the refusal summary (`summarize_refusals()`);
- `question` records;
- the CLI and the web UI;
- `scripts/run_swarm_demo.py`, which uses `LocalReader`.

**Not yet**, until item 3 is done:
- `link_parallels` and `collate_editions`, which read CBETA markup;
- `align_passages`, which compares Chinese characters only.

Ignore `cohort/attribution.py`, `related.py`, `embeddings.py`, and the scripts
that read CBETA or Radich's corpus. They are not part of this plan.

**Research questions you can ask of your own data.** Choose the kinds your
corpus supports. For each, there are things your data must contain before the
question can be answered from it at all.

| Kind of question | Example shape | Your data needs |
|---|---|---|
| Reuse | Does text B quote or adapt text A, and in which passages? | Two or more texts that might share wording |
| Dependence | Do these sources agree because they copy each other or a common source? | Several sources on one topic, plus whatever relations are already known |
| Contradiction | Where do two sources disagree about the same event, term or claim? | Overlapping coverage of the same subject |
| Spread of a term or motif | Where does a term first appear, and in which texts does it recur? | A term or motif to track, and texts with some known order or grouping |
| Authorship or style | Does a disputed text read more like group X or group Y? | Some texts with secure attribution, and some disputed ones |
| Dating | Is this text earlier or later than that one? | Some texts with known dates, and features expected to change over time |

**Rules for the question set.**
- **Write the questions down before any run**, and record them as `question`
  records. Nobody can then pick the questions after seeing which ones worked.
- **Include some questions whose answer you already know** from your own
  knowledge of the material, or from published work on it. That is how item 2
  checks whether a known answer is found. Include others whose answer is open.
- **Size.** 15–30 questions in total is realistic for a month. They may cover
  one corpus or two, and should cover at least three of the kinds above.
- **Use at least one question where agreement can mislead**, such as a
  dependence question with known copying. That is where the paper's argument
  about counting agreeing sources is tested.

## Deadlines

| Venue | Deadline | How sure |
|---|---|---|
| ACL 2027 (through ACL Rolling Review) | **4 January 2027, AoE** | On the official [ACL 2027 site](https://2027.aclweb.org/) and in a [LINGUIST List call](https://linguistlist.org/issues/37/3233/). |
| IJCAI-27 | **Not announced** | Trackers guess 4 January ([myhuiban](https://www.myhuiban.com/conference/405?tracker-page=1)) or 15 January ([OpenCurious](https://www.opencurious.com/ai-conference-deadlines/ijcai-2027), which calls its date a projection). IJCAI usually wants an abstract some days before the paper. |

Recheck both.

Today to 4 January is 42 days. A month of building ends around 23 December,
leaving **12 days** of writing over the holidays. **Start writing in week 2.**

**Pick one venue.** ACL Rolling Review does not allow the same paper to be
under review elsewhere at the same time.

- ACL suits a paper about LLM agents doing evidence-based research on text.
- IJCAI suits a paper about AI-assisted discovery with a researcher in the
  loop.

The work is the same either way. If the evaluation does not produce a result,
ACL's System Demonstrations track (usually a later deadline) fits what already
exists.

## What already exists, and what is missing

**Problems already found.** The review of the three conjectures saved in
September ([conjecture-review.md](presentation/conjecture-review.md)) found:

- **Tests that could not fail.** Each conjecture's test searched for wording
  the agent had already seen, and predicted that the wording would be found
  again. That checks that the wording repeats, not that the conjecture is true.
- **Indistinguishable alternatives.** The other explanations were so broad
  that no recorded test could tell them apart.
- **Tests never run.** No test result was recorded for any of the three.
- **Numbers cited from the wrong place.** Numerical statements overreached:
  "a margin of 0.096 means no evidence". The figures were also cited through
  passages that do not contain them.
- **A reviewer that misdescribed its evidence.** The reviewing agent said the
  cited passages reported the computed margins. They do not.

**Missing for a paper.** There is no evaluation across many questions, no
comparison with an agent that lacks these requirements, and no measure of
hypothesis quality. Everything so far consists of single runs on one corpus.

## Work that fits in a month

The first two items are the paper. The third makes the second possible on your
data. The fourth and fifth measure the protections the paper depends on.
The rest is optional. Day estimates are judgement.

### 1. Refuse conjectures whose tests cannot fail *(core; ~6 days)*

Turn each problem from the September review into a refusal in the code that
records proposals (`cohort/graph.py` and the tools). A refusal in code is
enforced; an instruction in a prompt is only a request ([design.md](design.md)
§5).

1. **Refuse a test whose answer the agent has already seen.** Check the event
   log for the same search, earlier in the same run, by the same agent.
2. **Require each alternative explanation to predict something different.**
   Store alternatives as a list, not one paragraph. For each one, record what
   the test would return if it were true. Refuse the conjecture if every
   alternative predicts the same result as the conjecture itself.
3. **Make numbers cite the calculation that produced them.** A claim that
   states a computed figure must cite the recorded tool output, not a passage.
   [handoff.md](handoff.md) lists the absence of a measurement record as a gap.
   Recording tool outputs as citable records is enough for this.
4. **Run every conjecture's test at the end of the run**, and show the result
   with the conjecture.
5. **Give the reviewing agent the tool outputs** as well as the cited
   passages.

**Care needed.** Items 2 and 3 change `schemas.py` and the rules for what can
be recorded. Read [design.md](design.md) first. Keep `tests/test_parity.py`
green (every web route needs a matching CLI command). Records already in event
logs must still load.

### 2. Compare hypotheses with and without these requirements *(core; ~8 days; most of the model spending)*

Run the same model, tools, budget and questions twice:

- **With requirements.** Cohort, including the changes from item 1.
- **Without requirements.** The same agent and tools, writing hypotheses as
  free text.

If there is time, add a third run with Cohort as it was before item 1, to show
what item 1 adds. Use at least two model families.

**Measure:**
- **Do the citations check out?** The share of cited passages that re-fetch
  exactly, and the share of statements with at least one located citation.
  Extract citations from the free-text answers and check them the same way.
- **Could the tests fail?** The share of conjectures whose test result was not
  already known when they were proposed. The share whose alternatives predict
  different results.
- **What did the tests show?** Of the tests run, how many predictions held and
  how many failed. Tests that never fail are a warning sign.
- **Were known answers found?** For questions whose answer is already
  established, did a hypothesis reach it? The model may already know the
  answer from training. Report that as an unresolved issue, not as controlled.
- **What was refused?** Refusal counts by rule, from `summarize_refusals()`.
  Have a person judge whether a sample of refusals was right.
- **Do statements say more than their citations?** A blind rating of 50–100
  items by one or two people who know the corpus. This is the measure
  reviewers will trust most, and it cannot be automated. Arrange the raters in
  week 1.

**Cost.** Earlier single runs cost $0.002–0.004 each ([handoff.md](handoff.md)).
That does not predict the cost of this design. Run a pilot of 3 questions in
both settings, read the spend from the event log, then size the full run.

### 3. Make the remaining tools work on your data *(needed for item 2; ~4 days)*

1. **Let researchers declare relations between texts in a file.** One row per
   relation: `witness_ref, witness_ref, relation, source`, where `relation` is
   `parallel_of` or `descends_from`. Each row is recorded as an edge, with the
   file named as its source. Without this, `independent_support()` has nothing
   to work with in a new corpus.
2. **Make `align_passages` work beyond Chinese characters**, comparing words
   or normalised characters as each corpus needs.
3. **Let `collate_editions` read any TEI edition** that lists its witnesses in
   `<listWit>`. This is only needed if a chosen corpus has variant readings
   marked up.

Each change needs synthetic test data under `tmp_path`. The existing CBETA
tests use synthetic markup, so they run without CBETA. Keep them passing; they
are how you know the CBETA path still works.

### 4. Show that agreeing sources are not independent evidence *(supporting; ~4 days; no model spending)*

Measure how much counting agreeing witnesses overstates support, compared with
`independent_support()`.

- **Simulated copying.** Generate copies of a text from known family trees,
  varying copying errors, mixing between copies, and losses. Because the true
  relations are known, report results across these settings.
- **Your data.** Use the relations declared through item 3. Compare the
  support counts for your questions with and without those relations.

### 5. Show which errors citation checks catch *(supporting; ~4 days; small model spending)*

Plant five kinds of citation in your data:

- a changed character;
- a shifted passage;
- a citation swapped for a near-duplicate passage;
- a correct citation attached to a claim that says too much;
- an unchanged control.

Report which ones the passage re-fetch catches and which the reviewing agent
catches. `scripts/run_negative_control.py` did one such case. It reads CBETA,
so write a new version that uses `LocalReader` on your data.

### Optional

- **More agents.** Run 1, 2, 4 and 8 agents at once on the item 2 questions,
  and check whether they converge because they share evidence. This is item 4
  in [handoff.md](handoff.md). Do not headline claims per agent
  ([roadmap.md](roadmap.md) §9).
- **Refusals as results.** Tabulate refusals across all item 2 runs. This
  comes almost free from item 2.

### Not in a month

- Detecting shared passages automatically. Exclusion of stock phrases has to
  ship with it ([handoff.md](handoff.md)).
- Detecting contradictions automatically.
- A full user study.
- A dating scheme ([design.md](design.md) §14).

## Paper outline

Working title: *Conjectures That Can Fail: Testable Hypothesis Generation for
Corpus Research with LLM Agents.*

1. **Problem.** Research agents either repeat what their sources say or go
   beyond them without saying what would prove them wrong. Counting agreeing
   sources makes this worse when the sources copy one another.
2. **System.** Claims, conjectures and their requirements; independence-aware
   support; the reviewing agent; and acceptance by the researcher only.
3. **Evaluation.** Item 2.
4. **Supporting analyses.** Items 4 and 5.
5. **Worked example.** One question from your data, traced from question to accepted finding or refusal.
6. **Limitations.** Most of these are already listed under "What does not
   exist" in [handoff.md](handoff.md).

## Schedule

| Dates | Build | Needs someone else | Write |
|---|---|---|---|
| 23–30 Nov | Prepare your data and write the questions. Item 3. Item 1 parts 1, 4, 5. | Confirm venue, raters, spend limit. | Outline, problem, related work ([references.md](references.md)). |
| 1–7 Dec | Item 1 parts 2, 3. Item 2 pilot. Simulated copying. | — | System section. |
| 8–16 Dec | Item 2 full run. Items 4 and 5. | — | Evaluation set-up. |
| 17–23 Dec | Expert rating. Optional items. | — | Results. |
| 24 Dec – 4 Jan | Freeze code and regenerate every table. | — | Limitations, ARR checklist, anonymization, submit. |

Put each experiment in a script under a new, tracked `scripts/experiments/`
directory. A local copy of that directory holds only `__pycache__`. Each script
writes a JSON file with the corpus hash, code version, model names and a count
of everything it discarded. Every table in the paper must be regenerated from
those files.

## Before submitting

- **Anonymity.** `lopentu/cohort` is a **public** repository, and the docs name
  the lab, the hosted URL and collaborators. Link an anonymized copy and keep
  real links out of the PDF and supplement.
- **Data.** Nothing from `data/` goes in the paper, supplement or figures
  ([AGENTS.md](../AGENTS.md#data-and-licences)). Quote from your own data only
  as far as its licence or permission allows, and cite its source.
- **ARR requirements.** A Limitations section and the Responsible NLP
  checklist. Take model spending and model names from the event log.
- **Related work.** Cover LLM hypothesis-generation and "AI scientist" agents,
  and research or fact-checking agents that count agreeing sources. Also cover
  the existing tools researchers in your data's field already use. What is new is
  the requirement that conjectures carry refutable tests, and its evaluation,
  not retrieval.

## Decisions for the project lead

1. **Venue.** ACL or IJCAI, not both.
2. **The question set.** The person picking this up proposes questions about
   their own data. Agree on them before any run.
3. **Expert raters for item 2**, and whether they become authors.
4. **Item 1's new refusals.** They tighten the rules in
   [design.md](design.md) §7, so approve them before they are merged.
5. **Spending limit** for items 2 and 5 and the optional runs.
6. **The `feat/rq3` branches.** They are not ready to merge
   ([researcher-review.md](presentation/researcher-review.md): 77 lint findings
   and the chapter-leakage bug). Their idea of registering a prediction before
   measuring is close to item 1 and worth reusing.
7. **[design.md](design.md) §1** still describes the contribution as
   "methodological infrastructure for (Buddhist) DH". The paper claims more.
8. **Authorship and affiliations.**
