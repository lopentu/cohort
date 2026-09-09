# Presenter cue card

20 slides, one sequence. Slides 1–18 introduce the purpose, material and tools. Switch to Cohort at slide 19 for ten minutes, then return to slide 20. Planned total: 30 minutes.

## 1. Agent-Based Infrastructures for Diachronic Digital Humanities

Cohort helps researchers find passages, compare them and keep a record of the investigation.

## 2. Acknowledgement

Thank you, Michael Radich, for sharing the texts, catalogue and string list. The groups come from catalogue labels; Cohort computes the comparisons.

## 3. Why we built Cohort

We built Cohort so researchers can direct agents and inspect the evidence behind their proposals. Today I will show the functions on Chinese Buddhist texts, including results that can mislead. The goal is to make the system and its limits clear enough for researchers to judge where it could help their own work.

## 4. Agent support for diachronic research

Diachronic means across time. We want agents to help find texts, compare their content and wording, and propose explanations. The sources and checks remain available for inspection, and the researcher decides what to accept.

## 5. Functions

Corpus is for finding and reading passages. Vocabulary comparison compares wording. Inquiry starts an agent investigation. Findings presents its proposals. Graph shows their sources and relationships.

## 6. Example research questions

We know that a later commentary repeats wording from T0603. Could shared wording mislead us about who translated this text? The Lotus example asks whether we can find related passages across two translations.

## 7. Corpus

Find passages and read them in context.

## 8. How related passages are found

An embedder has already converted passages to vectors. We compare those stored vectors, then read the candidates. The worker language model is separate.

## 9. Example: finding another Lotus translation

**Time cue:** Two translations from different periods.

We start with Dharmarakṣa’s Lotus translation. The retrieved passage comes from Kumārajīva’s translation of the same sūtra. It is a relevant candidate to read, even with little exact shared wording; the score does not prove an exact correspondence.

## 10. What vocabulary comparison calculates

We start with texts labelled by translator in Radich’s catalogue. We pool the string counts for each label into a comparison group. Two groups instead contain mixed historical material. The vocabulary list tells us which strings to count. We compare the target’s pattern of use with those groups.

## 11. Vocabulary comparison

Compare a text’s wording with texts labelled by translator.

## 12. T0603: remove the later commentary

**Time cue:** A later commentary preserves wording from an earlier text.

T1694 is in the mixed early-material group. Removing it changes that group’s profile and the leader. The target and vocabulary stay fixed. The margin is the score gap divided by distinct matched strings; it is not a probability.

## 13. Inquiry

Give agents a research question and inspect their actions.

## 14. From passages to research proposals

**Time cue:** Could reuse, revision or transmission explain the resemblance?

The worker can pull material together, suggest explanations we might want to examine, and propose a next search. These are possibilities for research. We inspect the cited passages and recorded checks before deciding what to pursue.

## 15. Graph

Follow links between sources, proposals and decisions.

## 16. Why a query points to a proposal

Supporting passages and investigation records are separate links. A grounding search saves a query and hit count but does not automatically make nodes for every result. A tests arrow records a planned test; check whether it ran.

## 17. Why use an evidence graph?

The graph helps us trace proposals back to sources, inspect recorded relationships between sources, and retain the history of checks and decisions. A possible next step is edge prediction: suggesting a relationship worth investigating. We have not implemented or evaluated that capability.

## 18. Findings

Read the agents’ proposals, citations and checks.

## 19. Cohort

Now I will use the same functions on the saved material.

## 20. Results and limits

We have useful candidate retrieval, inspectable comparisons and a record of agent work. We also have an incorrect vocabulary result and weak conjectures. These need evaluation with researchers, not a stronger claim on the slide.

## Application route

1. Corpus → Lotus related passages → shared wording.
2. Vocabulary comparison → T0603 → exclude T1694.
3. Inquiry → saved tool action → Graph → sources and checks → Findings → proposal.
4. Return to slide 20.
