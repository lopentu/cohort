# Buddhist studies background for the Cohort presenter

> Historical draft from 7 September 2026. For the current presentation and interface, use the [presenter walkthrough](presentation/walkthrough.md) and [cue card](presentation/presenter-cue-card.md). Earlier implementation descriptions and speaking sequences may be outdated.

Prepared 7 September 2026. This is a reading companion for a presenter who
knows NLP and is new to Buddhist textual scholarship. It explains why the
research question matters, what the demonstration's documents represent, and
which conclusions require historical judgment. Implementation boundaries
belong in [the speaker canvas](pnc-speaker-canvas.md); reported experimental
results belong in [the handoff](handoff.md), subject to that canvas's audit.
No restricted corpus material was opened or reproduced for this document.

## The historical question behind the classifier

Cohort's motivating question is whether tools can help researchers establish
more reliable translator ascriptions for Chinese Buddhist texts. An ascription
is a statement assigning responsibility for a text: for example, that a named
person translated it. The interesting research result would explain why that
statement deserves confidence, revision, or suspension. A model's preferred
label is one possible piece of evidence within that argument.

The distinction matters because the name supplied by a catalogue is itself
historical evidence. It may preserve excellent information, but it is not an
annotation made under modern benchmark conditions. If we evaluate a classifier
against received ascriptions, we measure its agreement with those ascriptions.
We have not independently established that every label is correct. This is a
methodological consequence of the task, and it should be stated before an
accuracy figure appears.

There is a further complication familiar from collaborative writing. The
person associated with a translation need not have performed every operation
that produced its Chinese wording. For an example directly relevant to this
demo, Anālayo describes the Ekottarika-āgama translation as Zhu Fonian's Chinese
rendering of material recited by Dharmanandin. His discussion explicitly
distinguishes this account from the attribution to Saṅghadeva in later
catalogues. That is already more structured than a single author field.
[Anālayo, “Mahāyāna in the Ekottarika-āgama,” 2013, opening and note 2](https://bcs.edu.sg/images/uploads/Sporean%20Journal%20of%20Buddhist%20Studies%202013.pdf).

For the presenter, the productive question is therefore: **whose contribution,
to which surviving layer of which text, could this evidence identify?**
A wording preference might belong to a Chinese translator, a collaborating
editor, a later reviser, or a quoted source. A useful instrument should make
those possibilities easier to examine. It should not make them disappear
inside a label.

## What kind of library is being searched?

The Chinese Buddhist canon is a collection of collections, with different
kinds of writing. A sūtra presents authoritative Buddhist teaching; a vinaya
concerns monastic discipline; an abhidharma work systematically analyses
teachings and experience. Commentaries explain other texts. Catalogues,
biographies, histories, and encyclopedias are also part of the scholarly
landscape. CBETA's account of the Taishō catalogue describes these substantial
differences in contents and organisation. Consequently, treating every file
as the same kind of linguistic sample discards information that may explain
its vocabulary. [CBETA, catalogue introduction](https://archive2.cbeta.org/cbreader/help/cbeta_toc_en.htm).

A sūtra's traditional framing and a historian's reconstruction answer
different questions. The presenter can describe a work as a sūtra without
claiming that its surviving sentences are a direct transcript of an ancient
speaker. Likewise, recognising religious authority within a tradition does
not settle a document's translation or transmission history. Cohort's question
concerns the history of texts and evidence for responsibility for their wording.
It does not ask the software to adjudicate religious truth.

“Buddhist Chinese” is useful shorthand for the Chinese language of this
literature, rather than the name of a single uniform style. Genre, technical
terminology, repeated discourse formulas, and habits of particular translators
can all contribute to resemblance. In practical terms, two descriptions of
meditation may share specialised words because they discuss the same activity.
Two narrative passages may share scene-setting formulas. A commentary may
repeat another text because explaining that text is its purpose. Those are
plausible competing explanations to investigate, not noises that a larger
encoder automatically removes.

### Taishō, CBETA, and the local corpus are different objects

The **Taishō** is a modern edited canon. **CBETA**, the Chinese Buddhist
Electronic Text Association, produces and maintains electronic Buddhist texts.
Its remit includes the Taishō and other collections. Thus “Taishō text,”
“CBETA edition,” and “the files used in this experiment” should not be used
interchangeably. CBETA also distributes several formats whose contents and
apparatus support differ. A specific export is a research input with choices,
not a neutral synonym for the whole canon.
[CBETA's description of its electronic collection](https://cbetaonline.cn/doc/en/06-copyright.php);
[CBETA's format comparison](https://cbeta.org/en/post/30729).

A Taishō identifier locates an entry. The `T` in `T0453` means Taishō, and
`0453` is the text number. It is neither a year nor an author identifier.
A fuller reference adds volume, page, column, and line. CBETA documents this
addressing scheme explicitly. In the demo, the shorter identifier is a useful
handle for opening a text; the fuller location is what lets a specialist check
a particular passage. [CBETA, line-reference format](https://archive2.cbeta.org/cbreader/help/rules_1.htm).

The local handoff describes Radich's corpus as a modified plain-text source.
Do not assume that its segmentation, labels, or normalisation are identical
to a current public CBETA export. Nor should a publicly deposited TACL database
be identified with the local input just because both involve Radich and the
Taishō. Radich's 2023 deposit describes its associated corpus as a modified
CBETA Taishō corpus; that establishes a public resource, not byte identity with
this demonstration. [Radich, TACL database deposit](https://zenodo.org/records/7824781).

For reproducibility, record the exact input version, transformations, and
segmentation rule. A hash can establish which bytes were inspected. It cannot
establish that the editor chose the right reading, that the label is sound,
or that a quoted passage supports the interpretation attached to it.

## Four objects that must stay distinct

A **unit** is what the software treats as one sample: perhaps a complete short
text, a chapter, or an excerpt. A **work** is the larger entity used to group
related material for the current research design. Neither term guarantees an
independent historical origin. Cohort's work grouping serves a specific
computational purpose: preventing a held-out chapter from being tested against
other parts of its own work. Deciding how to group composite or overlapping
entries remains an explicit corpus-design decision.

A **witness** is a source that preserves evidence for wording. It may be a
manuscript, a printed edition, a translation, or a quotation in another work.
An **edition** is an editorial presentation of a text. An edition can itself
function as a witness in a later comparison, but it need not reproduce one
historical document without intervention. A **critical apparatus** records
variant readings and the witnesses associated with them.
[TEI Guidelines, “Critical Apparatus”](https://guidelines.tei-c.de/en/html/TC.html).

Imagine a short work printed by itself and quoted inside a commentary. The
corpus may contain two units under two catalogue numbers. For a particular
passage, there are two places where its wording survives. Whether these offer
independent evidence for a translator's habits is a separate question. If one
is quoting the other, counting both as independent support exaggerates the
amount of evidence for that claim. Nevertheless, the quotation can still be
valuable evidence for how the earlier work was read or transmitted.

This is why “remove duplication” is an incomplete research policy. Deduplicating
training evidence and preserving historical witnesses serve different needs.
A researcher may want to exclude a quotation from a translator profile while
retaining it for textual comparison. Cohort's current explicit withholding
makes a sensitivity comparison possible; it does not automatically reconstruct
transmission families or decide which sources should count independently.

## The first worked example: a Maitreya text in two places

T0453 is the *Fo shuo Mile xiasheng jing* 佛說彌勒下生經, a sūtra about
Maitreya's descent. Maitreya is the future Buddha: the descent literature
concerns his future arrival and teaching in this world. For the demo, that is
enough doctrinal context to understand the title. Jonathan Silk's scholarly
encyclopedia entry describes T0453's attribution to Dharmarakṣa as erroneous
and its parallel with Ekottarika-āgama 48.3 as long known.
[Silk, “Maitreya,” 2019, p. 303](https://openphilology.eu/publications-jonathan-silk/articles_2019d_maitreya.pdf).

The **Ekottarika-āgama**, T0125 or T125, is a collection of discourses. “48.3”
identifies an individual discourse within it. In the demo, an independently
catalogued short text is compared with that constituent discourse. “The same
text appears in two places” is understandable introductory language, provided
it is followed by the more precise statement that their wording is nearly
identical. It does not mean that two files must have identical bytes or that
their entire histories are known.

The historical correction is stronger than “scholars noticed this in 1935.”
CBC@, the Chinese Buddhist Canonical Attributions database, reports that
Legittimo traced recognition of the near identity to Matsumoto Bunzaburō in
1911. It also records earlier doubts about the Dharmarakṣa ascription by Sugi,
an editor of the Korean canon. Its two summaries of Sakaino's 1935 book point
in different directions: one passage retains Dharmarakṣa, while another treats
the text as an excerpt. These are reasons to avoid a single starting date for
unanimous rejection. **The safe statement is that the parallel and attribution
problem long predate Cohort.** This chronology is verified here through
CBC@'s scholarly summaries, not through new inspection of Matsumoto or
Sakaino. [CBC@, T0453](https://dazangthings.nz/cbc/text/616/).

Why does the demo show Zhu Fonian? That is the profile label used for T125
in the supplied research framing. It has substantial scholarly background:
Radich's 2017 study argues for Zhu Fonian rather than Saṅghadeva using diverse
stylistic evidence. This published argument is not an output of Cohort.
[Radich, “On the Ekottarikāgama T 125 as a Work of Zhu Fonian,” 2017](https://chinesebuddhiststudies.org/article/on-the-ekottarikagama-t-125-as-a-work-of-zhu-fonian/).

The demonstration can show an instrument bringing a researcher to a relevant,
previously studied relationship. It cannot turn retrieval into a fresh
translator attribution. An alignment establishes an observable relationship
between wordings. Historical conclusions about extraction, incorporation,
revision, or common ancestry need additional arguments.

Withholding the matching discourse asks how much the ranking depends on that
one item. Withholding its whole collection asks a broader question. Neither
operation automatically controls for genre, shared formulas, or dependence
elsewhere. If a profile remains highest-scoring, the correct immediate report
is that it remains highest-scoring under the specified exclusion. Whether
that residual evidence identifies a translator is still open.

## The second example: a translation inside its commentary

T0603 is the *Yin chi ru jing* 陰持入經, associated with An Shigao. The
speaker's existing brief glosses its subject as aggregates, elements, and
sense-fields: categories used to analyse experience. The doctrinal details
are not needed to understand this experiment. What matters is the relationship
between an earlier text and a later work devoted to explaining it.

T1694, the *Yin chi ru jing zhu* 陰持入經註, is an interlinear commentary on
that translation: explanation is interspersed with the material explained.
Zacchetti's university repository record identifies precisely this relation.
The repository's full PDF did not open through the research browser, so the
authorship qualifications below rely on CBC@'s attributed summary rather than
a claimed fresh reading of the complete chapter.
[Zacchetti, “Some Remarks on the Authorship and Chronology…,” repository record](https://iris.unive.it/handle/10278/28817).

Its authorship is not a settled one-name answer. CBC@ reports the received
credit to “Master Chen,” Nattier's assessment favouring a third-century date,
and Zacchetti's more detailed reconstruction. Zacchetti proposes production
in the first half of the third century by a circle associated with Kang
Senghui, with a possible identification of Master Chen as Chen Hui, while
retaining problems involving the preface's name Mi. For stage purposes,
“an early commentary whose precise authorship has been debated” is sufficient.
Do not simplify this to an uncontested statement that Chen Hui alone wrote it.
[CBC@, T1694, with references to Nattier and Zacchetti](https://dazangthings.nz/cbc/text/1598/).

Here is the statistical danger in ordinary language. Suppose a profile contains
a commentary that repeats the very text being classified. The target can
then resemble that profile because its own wording occurs there. A high score
need not mean the target was produced by the people represented by the
profile. The historical relationship makes the similarity expected.

That is an explanatory model for the reported T0603 demonstration, not a new
measurement in this research note. The handoff reports a change after T1694
is withheld; the speaker canvas identifies unresolved numerical and wording
issues. Keep the final numbers tied to the verified experiment record. Also
keep a mixed corpus bin distinct from a person: a label such as
`pre-Dhr-other` is a grouping used by the experiment, not the name of another
translator.

The useful stage moment is the change in the question. After inspecting the
commentary, the researcher asks whether the original ranking was supported by
independent evidence. Recomputing without that source helps assess the answer.
A small remaining margin does not assign the text to the next profile, and
the current interface does not automatically turn such a margin into a
historical abstention decision.

## What scholars already do with computational tools

TACL is especially relevant prior practice. Its own documentation describes
comparisons of character n-grams across arbitrary groups of CBETA texts,
including intersections and differences. Radich's methodological guide
explains how to use those operations for Buddhist research; Radich and Jamie
Norrish created the tool. This is an established computational philology
workflow, not a hypothetical manual task waiting for an LLM to make it
possible. [TACL documentation](https://tacl.readthedocs.io/);
[Radich, TACL methods guide, updated August 2019](https://dazangthings.nz/documents/3/TACL_users_guide_NJRypi4.pdf).

A published example describes using TACL to find strings confined to one
comparison group or shared between groups, then examining the resulting
expressions in context with CBReader. The reasoning proceeds from a
computationally produced candidate set to philological assessment.
[Radich, study of the Mahāparinirvāṇa-sūtra, methodological discussion p. 234](https://glorisunglobalnetwork.org/wp-content/uploads/2020/04/hualin2.1_radich.pdf).

There is also recent work on the exact collection in this demo. Radich and
Norrish's study of T125, first published online in January 2025 and appearing
in the 2026 volume of *International Journal of Asian Studies*, combines
text-historical anomalies with internal stylistic evidence to argue for
modification after Dao'an's death. It marks Zhu Fonian's responsibility for
some modifications as more speculative. Its notes describe TACL operations
and the ability to find phraseology in the Taishō apparatus as well as the
base text. This is particularly important context for claims about what
researchers could already inspect.
[Radich and Norrish, “What happened to the Ekottarikāgama T125 after the death of Dao'an?”](https://doi.org/10.1017/S1479591424000366).

Cohort's presentation should describe the particular orchestration and record
it demonstrates: a worker selects tools, retrieves evidence, proposes an
interpretation with alternatives, and receives a separate review within a
researcher-controlled process. Demonstrating that process can be worthwhile
without claiming a new discovery, the first use of string comparison, or a
capability that another researcher lacks. A familiar historical problem can
be a demanding and legible test of a new interface.

## People and names to recognise

The presenter does not need a dynasty-by-dynasty history or thirteen miniature
biographies. Keep these roles straight:

| Name | Why the name appears |
|---|---|
| An Shigao 安世高 | Translator associated with T0603; distinguish his translation from the commentary upon it. |
| Dharmarakṣa 竺法護 | Received translator credit for T0453 that scholarship has challenged. |
| Zhu Fonian 竺佛念 | Translator argued for in scholarship on T125; the relevant profile label in the supplied corpus. |
| Saṅghadeva / Saṃghadeva 僧伽提婆 | Alternative romanisations encountered in attribution discussions; the traditional T125 attribution differs from Radich's research framing. |
| Master Chen 陳氏, Chen Hui 陳慧, Kang Senghui 康僧會 | Names in the disputed reconstruction of T1694's production, not interchangeable credits. |
| Michael Radich and Jamie Norrish | Creators of TACL and CBC@; authors of computational and philological work relevant to the demo. |
| Elsa Legittimo and Stefano Zacchetti | Scholars whose studies directly address the two worked relationships. |

These roles follow the sources linked in the relevant sections. Do not expand
uncertain personal histories on stage. Also distinguish Dharmarakṣa from
Dharmakṣema: similar-looking romanised names are not interchangeable labels.
Use the profile name actually pinned in the interface when describing a
comparison.

## Questions that turn retrieval into research

These are questions for preparing and interpreting the demonstration, rather
than an extra feature list.

1. **What exactly is being attributed?** A complete translation, the Chinese
   wording of one passage, a revision, or the assembly of a composite work?
   The answer determines which comparison samples make sense.
2. **Why trust each comparison label?** Identify whether it is a received
   byline, an argument adopted from scholarship, or a provisional corpus bin.
   Otherwise, a model can appear to settle what its training data assumed.
3. **What survives excluding known dependencies?** State exactly which units
   and works were withheld. Preserve access to excluded evidence so the
   researcher can inspect the reason for exclusion.
4. **What would distinguish the competing histories?** Shared wording alone
   may fit quotation, common source, or later revision. Chronological evidence,
   the placement of explanation around quoted text, and diagnostic variants
   can suggest different follow-up investigations.
5. **Which observation could weaken the preferred interpretation?** For
   example, widespread use of a supposedly diagnostic expression in unrelated
   works would weaken its usefulness as a translator marker. Say whether that
   observation was sought before or after the conjecture was recorded.
6. **What did review actually establish?** Distinguish retrievable words,
   source identity, relevance, an attested proposal, and human acceptance.
   The speaker canvas explains why the recorded demonstration must not be
   narrated as an accepted dependency automatically changing future profiles.

## Short glossary and further reading

| Term | Working meaning for this presentation |
|---|---|
| Ascription | Assignment of responsibility, such as translator or author, made by a source or scholar. |
| Grey text | A text whose translator is not treated as securely assigned in this research framing; not a claim that nobody has studied it. |
| Philology | Historical study through close examination of language, documents, and their relationships. |
| Sūtra / jing 經 | A Buddhist scriptural discourse or text; the genre label alone does not establish production history. |
| Āgama | A collection of discourses; EĀ abbreviates the Ekottarika-āgama. |
| Juan 卷 / fascicle | A division of a Chinese work; a work may contain several. |
| Parallel | Related textual material; specify whether the claim is shared wording, shared content, or a historical relationship. |
| Attestation | An occurrence or documentary witness; in Cohort, “attested” also names a workflow status, which should be explained separately. |
| Stemma | A proposed genealogy of textual descent; a similarity matrix is not by itself a stemma. |
| Withholding | Recomputing after explicitly excluding material; a sensitivity analysis whose scope must be stated. |

For further preparation, begin with the TACL methods guide and the two worked
text entries in CBC@. Then read Radich's 2017 T125 study and the
Radich–Norrish article. Legittimo's *Reopening the Maitreya-files* is catalogued
as volume 31, nominally 2008 and published in 2010; the publisher's PDF was
blocked in this browser, so the historical account above identifies its
indirect support explicitly. The indexed first page gives pp. 251–293,
whereas CBC@ lists 251–294; check the original before finalising a bibliography.
[Legittimo, publisher PDF](https://journals.ub.uni-heidelberg.de/index.php/jiabs/article/download/9004/2897/0).

This note verifies public scholarly context and separates it from interpretation
of the supplied project record. It does not reproduce the experiments, resolve
translator ascriptions, inspect restricted texts, or certify historical priority.
