# PNC presentation source

The deck follows the activities in the supplied abstract: corpus retrieval, semantic analysis, alignment, interpretation, provenance and researcher decisions. It has 15 main slides and six reference slides. The speaking plan allocates 24 minutes plus six minutes for questions.

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
