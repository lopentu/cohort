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
with any research question over any corpus. The evaluation should therefore
vary the **kind of research question**. Examples include:

- who wrote or translated a text;
- when a text was written;
- whether one text reuses another;
- how a term spread;
- where two sources contradict each other.

## Working without CBETA

The person picking this up **does not have access to CBETA**. That also rules
out Radich's corpus and everything else under `data/`. It does not narrow
what the paper can claim. It does decide which corpora the evaluation runs on.

**What works on any corpus today.** None of the following assumes a particular
corpus or language:

- the evidence graph and its event log;
- `propose_claim`, `propose_conjecture` and `run_prospective_test`;
- re-fetching cited passages;
- the reviewing agent;
- the refusal summary (`summarize_refusals()`);
- `question` records;
- the CLI and the web UI.

`LocalReader` reads any folder of plain-text files listed in a `manifest.csv`
(`path, witness_ref, label, note`; see [corpus.md](corpus.md)). It indexes the
text one character at a time, so search works in any script. It has only been
used on Chinese, so check it on the chosen corpora first.

**What is tied to CBETA or to Chinese.**
- `link_parallels` reads parallel-text links only from CBETA's `<cb:docNumber>`
  markup.
- `collate_editions` understands only CBETA's edition labels.
- `align_passages` compares Chinese characters only.
- `cohort/attribution.py` is built on Radich's catalogue.
- Every script that reads a real corpus needs CBETA, except
  `run_swarm_demo.py`. That includes `run_negative_control.py`,
  `run_conjecture_demo.py`, `run_stage4_demo.py` and `seed_demo_graph.py`.

**Choosing corpora.** Pick open corpora that support real research questions,
including some whose answers are already settled in the scholarship, so the
evaluation can check whether those answers are found. Two corpora with 8–15
questions each is realistic for a month.

A corpus with well-documented reuse between texts is especially useful. Texts
that copy from one another are exactly where counting agreeing sources goes
wrong. The Synoptic Gospels in a public-domain translation are one example.

Confirm the licence of each corpus before committing anything from it, as
`examples/local_corpus/README.md` does for its poems. Write the questions down
**before** any run and record them as `question` records, so nobody can pick
questions after seeing which ones worked.

**CBETA as an optional extra example.** Someone with CBETA access can run the
same scripts on it by changing a path. They commit **only summary numbers**:
counts, rates, file hashes and the code version, with no passages and no file
paths ([AGENTS.md](../AGENTS.md#data-and-licences)). The paper does not depend
on those runs. The T0453 and T0603 examples can appear only as already written
up in [pnc-background-research.md](pnc-background-research.md).

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

The first two items are the paper. The third makes the second possible on open
corpora. The fourth and fifth measure the protections the paper depends on.
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

### 3. Remove the CBETA-only parts *(needed for item 2; ~4 days)*

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

Each change needs synthetic test data under `tmp_path`. Also add a test that
CBETA behaviour is unchanged, because the person making these changes cannot
check CBETA directly.

### 4. Show that agreeing sources are not independent evidence *(supporting; ~4 days; no model spending)*

Measure how much counting agreeing witnesses overstates support, compared with
`independent_support()`.

- **Simulated copying.** Generate copies of a text from known family trees,
  varying copying errors, mixing between copies, and losses. Because the true
  relations are known, report results across these settings.
- **The chosen corpora.** Use the relations declared in item 3. Someone with
  CBETA access may add one CBETA run. That would be a lower bound, because
  CBETA's "cf." cross-references are not read
  ([changelog.md](changelog.md)).

### 5. Show which errors citation checks catch *(supporting; ~4 days; small model spending)*

Plant five kinds of citation in the open corpora:

- a changed character;
- a shifted passage;
- a citation swapped for a near-duplicate passage;
- a correct citation attached to a claim that says too much;
- an unchanged control.

Report which ones the passage re-fetch catches and which the reviewing agent
catches. `scripts/run_negative_control.py` did one such case, but it reads
CBETA, so rewrite it to use `LocalReader`.

### Optional

- **Leakage in attribution scores, run on CBETA by someone with access.**
  Holding out single chapters instead of whole works raised agreement with
  catalogue labels from 52% to 82%. Today that is recorded only in a docstring
  of `cohort/attribution.py`. Turn it into a script, test it on synthetic data,
  and have someone with access run it.
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
5. **CBETA example.** T0453 and T0603, plus the leakage study if it was run.
6. **Limitations.** Most of these are already listed under "What does not
   exist" in [handoff.md](handoff.md).

## Schedule

| Dates | Build | Needs someone else | Write |
|---|---|---|---|
| 23–30 Nov | Choose corpora and write questions. Item 3. Item 1 parts 1, 4, 5. | Confirm venue, licences, raters, spend limit. | Outline, problem, related work ([references.md](references.md)). |
| 1–7 Dec | Item 1 parts 2, 3. Item 2 pilot. Simulated copying. | — | System section. |
| 8–16 Dec | Item 2 full run. Items 4 and 5. | Optional CBETA run. | Evaluation set-up. |
| 17–23 Dec | Expert rating. Optional items. | Optional leakage run. | Results. |
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
  ([AGENTS.md](../AGENTS.md#data-and-licences)). CBETA's licence is
  non-commercial and share-alike; cite it.
- **ARR requirements.** A Limitations section and the Responsible NLP
  checklist. Take model spending and model names from the event log.
- **Related work.** Cover LLM hypothesis-generation and "AI scientist" agents,
  and research or fact-checking agents that count agreeing sources. For
  Buddhist texts, TACL and CBC@ already support string comparison
  ([pnc-background-research.md](pnc-background-research.md)). What is new is
  the requirement that conjectures carry refutable tests, and its evaluation,
  not retrieval.

## Decisions for the project lead

1. **Venue.** ACL or IJCAI, not both.
2. **Corpora and questions.** Who proposes them, who confirms licences, and who
   frames the questions, as Radich's Q1 did for CBETA.
3. **Expert raters for item 2**, and whether they become authors.
4. **Item 1's new refusals.** They tighten the rules in
   [design.md](design.md) §7, so approve them before they are merged.
5. **Spending limit** for items 2 and 5 and the optional runs.
6. **Michael Radich's role**, if any CBETA work uses his corpus.
7. **The `feat/rq3` branches.** They are not ready to merge
   ([researcher-review.md](presentation/researcher-review.md): 77 lint findings
   and the chapter-leakage bug). Their idea of registering a prediction before
   measuring is close to item 1 and worth reusing.
8. **[design.md](design.md) §1** still describes the contribution as
   "methodological infrastructure for (Buddhist) DH". The paper claims more.
9. **Authorship and affiliations.**
