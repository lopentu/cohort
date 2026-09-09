# PNC presentation source

Downloads: [PowerPoint](cohort-pnc-2026.pptx) · [PDF](cohort-pnc-2026.pdf) · [Presenter cue card](presenter-cue-card.md)

The deck follows the activities in the supplied abstract: corpus retrieval, semantic analysis, alignment, interpretation, provenance and researcher decisions. It has 7 main slides and 28 reference slides. The plan is eight minutes of introduction, sixteen minutes in the application and six minutes of results and limits, with no scheduled audience Q&A.

- [Walkthrough](walkthrough.md): current controls, speaking guidance and background explanations.
- [Researcher review](researcher-review.md): usefulness, limitations and inspection of the Q3 branches.
- `slides.json`: editable text, geometry and speaker notes for all slides.
- `measurements.json`: aggregate results used in the T0603 comparison.
- `diagrams/`: interface diagrams generated from the slide layouts; no corpus screenshots.

Build editable PowerPoint and browser previews with:

```sh
uv run --script docs/presentation/build.py --output /path/to/presentation-output
```

The prepared local files are in `/home/richard/github/cohort/data/pnc-abstract/`. The same current deck and walkthrough are copied to `data/pnc-revised/` for existing links. Its previous presentation files are retained in `data/pnc-revised/previous-20260909/`.

The PDF is rendered from the shared HTML layout. PowerPoint text and shapes are native objects, but font substitution still needs a check in the application used to present. The source files contain no private correspondence, source passages or dataset paths.

Related-passage examples are reproduced by `scripts/check_method_examples.py`; `method-examples.json` contains aggregate measurements only.

Slides 8–12 are screenshots of the five tabs, for backup use. Source-passage text is hidden where applicable; Inquiry shows an unsent draft. Screenshot images can be replaced in PowerPoint. The title, acknowledgement, functions and example questions precede the application walkthrough.
