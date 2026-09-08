import { useEffect, useRef, useState } from 'react'
import { usePresence } from './motion'

const INTROS = {
  graph: {
    title: 'Inspect evidence and researcher decisions',
    body: [
      ['Next step', 'Select a record to open its sources, authorship and checks. Researcher decision controls are in that inspector. Drag and zoom to explore the graph.'],
      ['Status', 'Proposed means submitted for consideration; attested means the required checks passed; accepted means the researcher endorsed it. Colour alone does not mean accepted.'],
      ['Relationships', 'Use the legend to distinguish support from relationships that reduce independence. Two records can repeat the same evidence. Refused writes show operations the graph declined and why.'],
    ],
  },
  findings: {
    title: 'Read proposals before deciding',
    body: [
      ['Next step', 'Expand a hypothesis to read its argument, alternatives, cited passages and review outcomes. Follow a citation into Graph to inspect the record.'],
      ['Decisions', 'Citable contains researcher-accepted records. Rejected retains the reasons for rejection. Hypotheses are listed newest first, not ranked by confidence.'],
      ['Integrity', 'The checks compare stored hashes and replay the event log. They check record consistency, not historical truth. They run when this tab opens and can be repeated.'],
    ],
  },
  corpus: {
    title: 'Find exact wording in the source texts',
    body: [
      ['Next step', 'Search a phrase, then open a matching record to read its context. Results are in corpus order, not ranked by relevance.'],
      ['Continue in Inquiry', 'Send to agent prepares a task in Inquiry. It does not launch a run or attach a citation; inspect the task before starting.'],
      ['Reading', 'Removing TEI markup changes displayed character positions. Use that view for reading, not for locating a citation.'],
    ],
  },
  evidence: {
    title: 'Compare wording; investigate what explains it',
    body: [
      ['Next step', 'Choose a text, read the comparison, and try excluding material that might repeat it. A profile is a table of short-string counts for a translator or corpus group.'],
      ['Colours', 'Teal and rust compare two named groups. Choose a fixed pair before comparing vocabularies; automatic selection can change the pair.'],
      ['Limits', 'Resemblance can reflect genre or reused passages. This tab assigns no translator and does not change the graph. Exclusions affect this calculation only.'],
    ],
  },
  run: {
    title: 'Ask a question and start agent work',
    body: [
      ['Next step', 'Record a question and what would count as an answer. Inspect the agent tasks and models, then start the run when ready. Opening this tab does not spend money.'],
      ['Review', 'Workers retrieve and propose; a different agent from a different model family reviews citations. A citation check does not settle an interpretation.'],
      ['Continue in Findings', 'Read the resulting proposals in Findings, then follow records into Graph for researcher decisions. Opening a saved question does not restart its earlier runs.'],
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
