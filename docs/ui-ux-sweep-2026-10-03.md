# UI/UX sweep — 2026-10-03

The inspected workflows work at desktop, tablet and phone widths under `/cohort/`. This was a bounded audit and repair pass on the existing interface, not a redesign. Browser checks used an isolated HTTPS container and synthetic graph, corpus, vocabulary and embedding inputs. No restricted material was captured, no paid models were called, and the running research workspace was unchanged.

## Repairs

| Issue | Impact | Change |
|---|---|---|
| Corpus metadata contrast below 4.5:1 | Small source positions and licence text were difficult to read | Use the existing stronger secondary-text token |
| Passage scroller could not receive focus | Keyboard users could not scroll the source excerpt | Give it a labelled tab stop and retain the shared focus ring |
| Outside graph labels used fixed dark ink | Hypothesis/question/query/audit labels disappeared on the dark canvas | Use theme ink and refresh canvas colours on explicit or system appearance changes |
| Inquiry exposed an untranslated configuration error | Chinese readers saw an English environment-variable diagnostic | Show a short translated explanation and ask the administrator to check model settings; precise diagnostics remain in the configuration API |

The existing canvas regression guard required fixed dark ink. It was updated to require theme ink, retaining its coverage of all outside-label shapes.

## Browser evidence

The final scan covered **50 rendered states**, with no axe WCAG A/AA findings or page-width overflow in those states. This is scoped evidence, not a WCAG conformance claim. The canvas graph is outside most axe checks.

- Login, incorrect-password feedback, sign-out, tour navigation and Escape dismissal.
- All five tabs in English and Traditional Chinese at 1440px and 390px widths.
- Populated vocabulary rankings, related results, shared-wording controls and editable pair-to-Inquiry handoffs at 1440px, 768px and 390px widths.
- Light/dark themes, an explicit theme switch with the graph mounted, system appearance changes and a reduced-motion preference.
- Live graph-label paint matched the theme token. The camera stayed unchanged; label coordinates varied by less than one pixel due to network rounding.
- Arrow-key scrolling worked inside the focused source excerpt. Findings expanded to show the supporting sources.
- No browser runtime errors or application requests escaping `/cohort/` in the main confirmation scan.

Representative screenshots were visually inspected. Touch-sized layouts were checked with Chromium emulation; no physical-device, synthesized graph-drag, screen-reader, Safari/Firefox or real browser-zoom certification is claimed. Reduced-motion preference handling was checked, but a live paid run/analysis stream was not exercised.

## Remaining work

**P1 — Canvas keyboard access.** Graph nodes are mouse/touch targets; the graph exposes a single image label rather than individually navigable records. Findings and Corpus provide readable alternatives, but full keyboard and screen-reader access to graph relationships still needs a separate implementation. Canvas fill/label contrast also needs dedicated coverage beyond axe. Suggested next pass: `impeccable harden`.

**P2 — Initial download.** The build retains an application chunk of roughly 951 kB before gzip. The build warns about it; no cold-network performance budget or slow-device benchmark was established. Split heavier graph/rendering dependencies in a focused performance change. Suggested next pass: `impeccable optimize`.

**P2 — Mobile graph density.** The legend and question controls fit without clipping, but leave less room for the drawing; the graph may require scrolling. Desktop remains the better setting for detailed relationship inspection. Suggested next pass: `impeccable adapt`, followed by `impeccable polish`.

## Design-system check

The mechanical detector returned 13 warnings in existing CSS: ten side-border matches and three width-transition matches. The borders convey status, refusals, citations or reading notices; they were not introduced by this repair. One width-transition match is actually `stroke-width`; the other two belong to the segmented indicator and spend bar. These are review signals, not runtime failures. This pass preserved the graph status channels required by `docs/design.md` rather than replacing them to silence a detector.

The implementation uses the existing tokens and shared Radix controls. No new component library, duplicated widget system or product claims were added.

## Rubric assessment

Scores are reviewer judgments on the inspected scope, not measured compliance percentages.

| Dimension | Score out of 4 | Practical limit |
|---|---:|---|
| Accessibility | 2 | Canvas navigation remains incomplete |
| Performance | 2 | Large chunk; no slow-network benchmark |
| Responsive layout | 3 | Layouts fit; graph remains dense on phones |
| Theming | 4 | Inspected views and live graph labels follow appearance |
| Implementation integrity | 3 | Shared controls/tokens retained; existing detector warnings reviewed |
| Total | 14/20 | Good within the inspected scope |
