import { useEffect, useRef, useState } from 'react'
import { usePresence } from './motion'

const INTROS = {
  graph: {
    title: 'Graph',
    body: [
      ['Inspect', 'Select a record to see its sources, checks and researcher decisions.'],
      ['Status', 'Proposed: submitted. Attested: required checks passed. Accepted: researcher-approved.'],
      ['Links', 'The legend distinguishes support from relationships that reduce independence.'],
    ],
  },
  findings: {
    title: 'Findings',
    body: [
      ['Read', 'Open a claim or conjecture to inspect its evidence, alternatives and reviews.'],
      ['Decide', 'Follow a citation into Graph. Acceptance and rejection are researcher decisions.'],
      ['Checks', 'Integrity checks compare the database with its hashes and event log. They do not establish historical truth.'],
    ],
  },
  corpus: {
    title: 'Corpus',
    body: [
      ['Search', 'Exact-phrase search. Results appear in corpus order.'],
      ['Read', 'Open a result for context. Hiding markup changes displayed positions.'],
      ['Continue', 'Investigate this passage opens an Inquiry draft with the selected source. Review and record it before starting.'],
    ],
  },
  evidence: {
    title: 'Evidence',
    body: [
      ['Compare', 'Select a text to compare short-string counts across corpus groups.'],
      ['Repeat', 'Exclude a related text to test whether repeated material affects the result.'],
      ['Limits', 'Scores do not establish translator identity. Calculations leave the graph unchanged.'],
    ],
  },
  run: {
    title: 'Inquiry',
    body: [
      ['Start', 'Record a question and research instructions, then click Inquire.'],
      ['Roles', 'Workers retrieve and propose. A reviewer checks citations. Only you accept findings.'],
      ['Save', 'Results save automatically. Runs continue when you switch tabs.'],
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
        aria-label={`${intro.title} help`}
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
          <p><a href={`/assets/ui-guide.html#${tab === 'run' ? 'inquiry' : tab}`} target="_blank" rel="noopener noreferrer">Controls, outputs and getting started</a></p>
          {tab === 'graph' && <p><a href="/assets/graph-guide.html" target="_blank" rel="noopener noreferrer">How to read the graph — illustrated guide</a></p>}
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
