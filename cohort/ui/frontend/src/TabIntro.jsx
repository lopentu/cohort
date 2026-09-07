import { useEffect, useRef, useState } from 'react'
import { usePresence } from './motion'

const INTROS = {
  graph: {
    title: 'What the Graph shows',
    body: [
      ['What it is', 'Every piece of evidence and every assertion, as a chain read left to right: witnesses (source texts) → passages (located spans of them) → hypotheses (claims and conjectures) → the research questions they address. The layout is fixed, not a physics simulation, so the same graph always draws the same way.'],
      ['Edges', 'Blue attests: a passage supports an assertion. Orange dashed parallel of / descends from / quotes: two sources are not independent (copies, the same passage in two texts, or one text quoting another) — this discounts support rather than adding it. Red contradicts. Violet dotted tests: the query that would refute a hypothesis, recorded before the evidence was in. Cyan addresses: which question an assertion answers. Grey: structure and audit.'],
      ['Nodes', 'The outline is the status: dashed = proposed by an agent, solid = attested (its citations were checked by a different agent), heavier = accepted by the researcher — the only citable state; a struck-through title = rejected. Click any node for its provenance: who wrote it, what attests it, and whether that support is independent.'],
      ['Refused writes', 'The counter in the top bar is an output, not an error log: every write the rules refused, and which rule. Zero is a fact worth showing.'],
    ],
  },
  findings: {
    title: 'What Findings shows',
    body: [
      ['What it is', 'Every hypothesis — every claim and conjecture — beside what the researcher has accepted (the only citable nodes) and what they rejected, with reasons. Rejections sit next to findings on purpose: conclusions without the discards would misrepresent the record.'],
      ['Not ranked', 'Sorting by how much attests a hypothesis would be a confidence score under another name, which is the habit this system exists to break. Where support does not survive the independence check the row says so; the count of citations is left unchanged.'],
      ['The dossier', 'Open a hypothesis for how it was derived, the corpus boundary it was framed against, its selection risks, the alternative explanations, the prior-art search actually run, the prediction recorded at proposal time and what the query found, the evidence with excerpts, and the verifications — the machine\'s finding and the reviewer\'s reading in separate fields.'],
      ['Integrity', 'Two checks, on demand: re-hash every stored payload against its recorded hash, and replay the event log to confirm the database matches it.'],
    ],
  },
  corpus: {
    title: 'What Corpus does',
    body: [
      ['Search', 'Exact substring match over every citable span — no wildcards, no stemming: what you type is what is found. Results come back in corpus order, not ranked: a relevance model would favour short commentaries over the scriptures they quote, a scholarly judgement smuggled into infrastructure. The count of what is not shown is stated.'],
      ['Reading', 'Open a hit to read the record, with its length stated. When the source carries TEI markup, a toggle strips it for reading — and warns that stripped text no longer shares character offsets with the witness, so it is for reading, never for locating a span.'],
      ['Sending to an agent', 'A phrase can be handed to the Inquiry tab as the seed of a task. Every record carries the licence terms of the corpus it came from.'],
    ],
  },
  evidence: {
    title: 'What Evidence shows',
    body: [
      ['What it is', 'For one text of Radich\'s pre-450 corpus: which translator\'s profile of short strings (2–4 characters) it fits best, by how much, and where in the text the evidence falls — painted onto the characters. A leaning with its reasons on show, not an attribution.'],
      ['Colours', 'Teal pulls toward translator A, rust toward translator B. A is the text\'s own catalogue label when it has one (otherwise the leader), B its strongest rival; the pair stays fixed when you switch vocabularies, so a change of colour is a change of evidence. Saturation is the weight of evidence on that character.'],
      ['What is withheld', 'Every unit of the text\'s own Taishō work is removed from the profiles before counting; otherwise the method recognises the book, not the translator (82% that was really 52%). You can withhold further units — a commentary you suspect of quoting the text — and recompute.'],
      ['Two vocabularies', 'Radich\'s curated strings (harvested for a Dharmarakṣa dictionary) and the commonest strings of the grey texts, chosen without reading a label. Their disagreement is the bias, made visible. "No evidence" means nothing in the vocabulary occurs; nothing is ranked.'],
    ],
  },
  run: {
    title: 'What Inquiry does',
    body: [
      ['What it is', 'The only tab that spends money. It opens on a research question — what is being asked and what would count as an answer, stated before looking — and runs agents against it with a hard budget per run that the browser cannot raise.'],
      ['The roster', 'Workers search the corpus and propose hypotheses through tools whose rules are enforced by the graph; a reviewer, which must be a different model family, checks that their citations resolve and attests or withholds. An agent cannot check its own work.'],
      ['What you see', 'Spend, tool calls, and refusals as the run proceeds. Everything an agent writes lands in the graph as proposed; nothing becomes citable here. The researcher accepts or rejects in Findings.'],
    ],
  },
}

//: The key the old inline block used, kept verbatim: a reader who had already
//: dismissed an intro should not have the dot come back because the control
//: moved. `'closed'` was written by the block on collapse and means "seen".
const key = (tab) => `cohort.tabIntro.${tab}`

function seen(tab) {
  try {
    return window.localStorage.getItem(key(tab)) === 'closed'
  } catch {
    return false
  }
}

export default function TabIntro({ tab, open, onToggle }) {
  const intro = INTROS[tab]
  const wrapRef = useRef(null)
  const pop = usePresence(open, 150)
  const [unseen, setUnseen] = useState(() => !seen(tab))

  // The dot is per tab, so switching tabs re-asks the question.
  useEffect(() => { setUnseen(!seen(tab)) }, [tab])

  // Opening it is what marks it seen — not closing it, which would leave a
  // reader who opened the panel and navigated away still flagged.
  useEffect(() => {
    if (!open) return
    setUnseen(false)
    try { window.localStorage.setItem(key(tab), 'closed') } catch { /* unavailable */ }
  }, [open, tab])

  // Dismiss on outside click and on Escape — the two gestures a popover owes
  // its reader, and the same two Settings binds. Bound only while open.
  useEffect(() => {
    if (!open) return undefined
    const onDown = (e) => {
      if (wrapRef.current && !wrapRef.current.contains(e.target)) onToggle(false)
    }
    const onKey = (e) => {
      if (e.key === 'Escape') { e.stopPropagation(); onToggle(false) }
    }
    document.addEventListener('mousedown', onDown)
    document.addEventListener('keydown', onKey, true)
    return () => {
      document.removeEventListener('mousedown', onDown)
      document.removeEventListener('keydown', onKey, true)
    }
  }, [open, onToggle])

  // A tab with nothing written about it hides the control rather than offering
  // an empty panel.
  if (!intro) return null

  return (
    <div className="settings-wrap" ref={wrapRef}>
      <button
        className={`icon-btn help ${open ? 'on' : ''} ${unseen ? 'unseen' : ''}`}
        onClick={() => onToggle(!open)}
        aria-label={intro.title}
        aria-expanded={open}
        title={intro.title}
      >
        <QuestionIcon />
      </button>

      {pop.mounted && (
        <div
          className={`settings-pop intro-pop ${pop.closing ? 'closing' : ''}`}
          role="dialog"
          aria-label={intro.title}
        >
          <h3>{intro.title}</h3>
          <dl className="tab-intro-body">
            {intro.body.map(([term, text]) => (
              <div key={term}>
                <dt>{term}</dt>
                <dd>{text}</dd>
              </div>
            ))}
          </dl>
        </div>
      )}
    </div>
  )
}

function QuestionIcon() {
  // Computed geometry, not a hand-traced path — the same discipline the gear
  // carries, and for the same reason: its first version was traced by eye and
  // the glyph sat low. It spanned y 4.43–12.83, so its centre was at 8.63
  // against the ring's 8.00, leaving 2.58 of margin above and 1.32 below.
  // Visibly off at 15px.
  //
  // Now: hook is a 270° arc of r=1.62 centred on (8, 6.05) — its free end at
  // 9 o'clock, sweeping clockwise over the top and down to 6 o'clock, which is
  // what makes it read as a question mark rather than a broken circle. The
  // stem drops 1.43 from there; the dot is r=0.75 at (8, 10.82). That puts the
  // glyph at y 4.43–11.57, centre exactly 8.000, with 2.58 of margin above and
  // below inside the r=6.15 ring.
  //
  // Everything is centred on x=8, so horizontal centring is exact by
  // construction.
  return (
    <svg width="15" height="15" viewBox="0 0 16 16" fill="none" aria-hidden="true">
      <g
        stroke="currentColor"
        strokeWidth="1.25"
        strokeLinecap="round"
        strokeLinejoin="round"
        vectorEffect="non-scaling-stroke"
      >
        <circle cx="8" cy="8" r="6.15" />
        <path d="M6.38 6.05 A1.62 1.62 0 1 1 8 7.67 V9.10" />
      </g>
      <circle cx="8" cy="10.82" r="0.75" fill="currentColor" />
    </svg>
  )
}
