# Login, bilingual interface and first-use review

Reviewed on 2026-10-02 in `feat/auth-i18n-tour`, stacked on the presentation branch. The browser checks used generated test corpora, synthetic embeddings and a test graph on localhost. No licensed corpus screenshots, real credentials or paid model calls were used.

## Changes

React 18 remains the frontend. Radix UI now provides shared dialogs, popovers, tabs, labels and segmented controls; the existing panels use shared buttons and badges. Session requests and CSRF forwarding share one boundary. Credential handling is separate from the graph and its event log.

English and Taiwan Traditional Chinese use i18next/react-i18next resources. Switching language updates controls, helper text and graph labels. Source passages, saved research questions, model responses and opaque identifiers retain their original values. Unrecognized backend diagnostics remain verbatim.

The optional tour covers enabled tabs in this order: Corpus, Vocabulary comparison, Inquiry, Graph, Findings. It can be skipped or replayed. Its Open this tab action navigates to the feature; examples remain in the destination panels. The tour does not select data, start searches, launch models or write research records.

## Verified results

| Check | Observed result |
|---|---|
| Python suite | 606 passed |
| JavaScript tests | 32 passed, including translation coverage, CSRF forwarding and blocked browser storage |
| Ruff and ty | Both passed |
| Vite production build | Passed |
| Dependency audit | 0 vulnerabilities reported |
| Desktop 1440×1000 and phone 390×844 | All five tabs checked in both languages: 20 views, no document-level horizontal overflow |
| Browser runtime | No JavaScript exceptions in the 20-view sweep |
| Tour side effects | The only POST in the tour/tab sweep was sign-in; no research writes or model runs |
| Settings keyboard behavior | Focus enters the popup; Escape closes it and restores the trigger |
| Expired-session sign-out | A CSRF rejection followed by an unauthenticated session response returns to login |
| axe WCAG 2 A/AA and 2.1 AA checks | Login, tour and all tabs in both languages and both themes: 22 inspections, no reported violations after fixes |

Screenshots were inspected for login, the tour, mobile navigation, Inquiry, Findings, Corpus and vocabulary output. The synthetic vocabulary fixture uses the generic string set for a successful comparison; its curated fixture contains strings for only one group, so that setting correctly refuses to rank two groups.

The sweep fixed clipped phone navigation, insufficient contrast in status labels, missing search/reason labels, keyboard-inaccessible scrolling tables, untranslated interface messages, missing spaces around numeric text, blocked-storage initialization and expired-session logout. Graph status colors and evidence semantics remain intact.

A separate security review found no blocking issue in credential loading, password verification, session limits, request size limits, login throttling, CSRF/origin checks or protected routes. A separate frontend review checked the component boundaries, localization and tour behavior; its identified defects were resolved.

## Remaining limits

The application has one account and shared research records. Authentication does not provide per-user permissions or corpus licence governance. Normal serving remains localhost-only; public deployment is outside this change. Account setup is interactive and no default password is included.

Automated accessibility checks do not establish screen-reader usability of the graph canvas. The browser sweep did not run real paid inquiries or evaluate scholarly output against licensed material.

The graph application chunk is 950.68 kB minified, so Vite retains its size warning. The application loads separately from the login screen; further graph-library splitting remains possible.

The design detector reported 13 warnings in existing CSS: ten accent-border matches and three width-transition matches. All were present before this change. They were retained to avoid changing established evidence/status presentation and unrelated motion during this task; the detector result is not represented as clean.

## Starting this version

Follow [account setup and language controls](ui-access.md), or the [Taiwan Mandarin quickstart](quickstart-zh-TW.md). Rebuild the frontend after checking out the branch; compiled assets remain generated and ignored by Git.
