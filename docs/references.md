# References

The external sources that Cohort's documentation relies on, gathered in one
place. Every entry here is already cited somewhere in `docs/`; the "Cited in"
line says where, so a reader can see the claim each source supports. This list
adds no new scholarly claims, and where an earlier note recorded that a source
was read only indirectly, that caveat is kept rather than dropped.

The local research inputs (Radich's modified corpus, the CBETA archive and the
correspondence under `data/`) are not listed as public references: they are
licence-restricted and stay out of the repository. See
[AGENTS.md](../AGENTS.md#data-and-licences).

## Corpora, editions and encoding

- **CBETA, catalogue introduction.** Describes the Taishō catalogue's contents
  and organisation.
  <https://archive2.cbeta.org/cbreader/help/cbeta_toc_en.htm>
  Cited in: [pnc-background-research.md](pnc-background-research.md),
  [presentation/walkthrough.md](presentation/walkthrough.md).
- **CBETA, description of its electronic collection** (copyright page).
  <https://cbetaonline.cn/doc/en/06-copyright.php>
  Cited in: [pnc-background-research.md](pnc-background-research.md).
- **CBETA, format comparison.** <https://cbeta.org/en/post/30729>
  Cited in: [pnc-background-research.md](pnc-background-research.md).
- **CBETA, line-reference format** (volume, page, column, line addressing).
  <https://archive2.cbeta.org/cbreader/help/rules_1.htm>
  Cited in: [pnc-background-research.md](pnc-background-research.md);
  the markup itself is described in [corpus.md](corpus.md).
- **Radich, Michael. TACL database deposit (2023).** Describes its corpus as a
  modified CBETA Taishō corpus; this establishes a public resource, not byte
  identity with the local input. <https://zenodo.org/records/7824781>
  Cited in: [pnc-background-research.md](pnc-background-research.md).
- **TEI Consortium. *TEI P5 Guidelines*, "Critical Apparatus".**
  <https://guidelines.tei-c.de/en/html/TC.html>
  Cited in: [pnc-background-research.md](pnc-background-research.md).

## Tools and models

- **TACL documentation** (Radich and Norrish's n-gram comparison tool).
  <https://tacl.readthedocs.io/>
  Cited in: [pnc-background-research.md](pnc-background-research.md).
- **Radich, Michael. *TACL* methods guide, updated August 2019.**
  <https://dazangthings.nz/documents/3/TACL_users_guide_NJRypi4.pdf>
  Cited in: [pnc-background-research.md](pnc-background-research.md).
- **CBC@ — Chinese Buddhist Canonical Attributions database.**
  <https://dazangthings.nz/cbc/> — entries used: T0453
  (<https://dazangthings.nz/cbc/text/616/>) and T1694
  (<https://dazangthings.nz/cbc/text/1598/>).
  Cited in: [pnc-background-research.md](pnc-background-research.md),
  [presentation/walkthrough.md](presentation/walkthrough.md).
- **`buddhist-nlp/mitra-qwen35-embedder`, model card.** The embedder named by
  the passage index's filename; the card does not name CBETA, so a blind test
  on unseen material cannot be claimed.
  <https://huggingface.co/buddhist-nlp/mitra-qwen35-embedder/blob/main/README.md>
  Cited in: [presentation/walkthrough.md](presentation/walkthrough.md).

## Scholarship on the worked examples

### T0453 and the Ekottarika-āgama (T0125)

- **Silk, Jonathan A. "Maitreya." 2019, p. 303.** Describes T0453's ascription
  to Dharmarakṣa as erroneous and its parallel with EĀ 48.3 as long known.
  <https://openphilology.eu/publications-jonathan-silk/articles_2019d_maitreya.pdf>
- **Legittimo, Elsa. "Reopening the Maitreya-files." *Journal of the
  International Association of Buddhist Studies* 31 (nominally 2008,
  published 2010).** Read indirectly, through CBC@; the publisher's PDF was
  blocked. The indexed first page gives pp. 251–293 while CBC@ gives 251–294:
  check the original before quoting a page range.
  <https://journals.ub.uni-heidelberg.de/index.php/jiabs/article/download/9004/2897/0>
- **Anālayo. "Mahāyāna in the Ekottarika-āgama." *Singaporean Journal of
  Buddhist Studies*, 2013,** opening and note 2.
  <https://bcs.edu.sg/images/uploads/Sporean%20Journal%20of%20Buddhist%20Studies%202013.pdf>
- **Radich, Michael. "On the Ekottarikāgama T 125 as a Work of Zhu Fonian."
  2017.**
  <https://chinesebuddhiststudies.org/article/on-the-ekottarikagama-t-125-as-a-work-of-zhu-fonian/>
- **Radich, Michael, and Jamie Norrish. "What happened to the Ekottarikāgama
  T125 after the death of Dao'an?" *International Journal of Asian Studies*
  (online January 2025; 2026 volume).**
  <https://doi.org/10.1017/S1479591424000366>

Cited in: [pnc-background-research.md](pnc-background-research.md),
[presentation/walkthrough.md](presentation/walkthrough.md).

### T0603 and its commentary T1694

- **Zacchetti, Stefano. "Some Remarks on the Authorship and Chronology of the
  *Yin chi ru jing zhu*…"** Repository record only; the full study has not been
  independently read for these documents, and the authorship account relies
  on CBC@'s summary. <https://iris.unive.it/handle/10278/28817>
- **Baley, "Chinese Transcription of Buddhist Terms in the Late Hàn
  Dynasty."** *Journal of Open Humanities Data*; section "Additions and
  removals" includes T0603 in An Shigao's accepted corpus.
  <https://openhumanitiesdata.metajnl.com/articles/10.5334/johd.110>
- Nattier's dating of T1694 is cited only as summarised in the CBC@ T1694
  entry above.

Cited in: [pnc-background-research.md](pnc-background-research.md),
[presentation/walkthrough.md](presentation/walkthrough.md).

### Computational philology in practice

- **Radich, Michael. Study of the *Mahāparinirvāṇa-sūtra*, *Hualin
  International Journal of Buddhist Studies* 2.1,** methodological discussion
  p. 234: TACL candidate strings examined in context with CBReader.
  <https://glorisunglobalnetwork.org/wp-content/uploads/2020/04/hualin2.1_radich.pdf>
  Cited in: [pnc-background-research.md](pnc-background-research.md).

## Graph methods (future work)

Cited for link prediction, which Cohort does **not** currently perform.

- **Hogan, Aidan, et al. "Knowledge Graphs."** <https://arxiv.org/abs/2003.02320>
- **Daza, Daniel, et al. "Inductive Entity Representations from Text via Link
  Prediction."** <https://arxiv.org/abs/2010.03496>

Cited in: [presentation/walkthrough.md](presentation/walkthrough.md).

## Adding a reference

Cite the source inline where the claim is made, then add it here with a
"Cited in" line. If you could not read the source itself, say what you read
instead, as the Legittimo and Zacchetti entries do. A reference whose only
citing document is deleted should be removed from this list too.
