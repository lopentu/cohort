import { useEffect, useState } from 'react'

// A short, plain-language account at the top of every tab: what it shows, what
// you can do in it, and what its colours mean. Written for a researcher who
// has never seen an evidence graph, not for the people who built one.
//
// Collapsible, and the choice is remembered per tab in localStorage, so a
// first-time reader gets the explanation and a daily user is not nagged by it.
// localStorage can be absent or throwing (private windows, blocked storage);
// every access is guarded and the default is "open".

const INTROS = {
  graph: {
    title: 'What the Graph shows',
    body: [
      ['What it is', 'Every piece of evidence and every assertion, as a chain read left to right: witnesses (source texts) → passages (located spans of them) → claims and conjectures → the research questions they address. The layout is fixed, not a physics simulation, so the same graph always draws the same way.'],
      ['Edges', 'Blue attests: a passage supports an assertion. Orange dashed parallel of / descends from / quotes: two sources are not independent (copies, the same passage in two texts, or one text quoting another) — this discounts support rather than adding it. Red contradicts. Violet dotted tests: the query that would refute a conjecture, recorded before the evidence was in. Cyan addresses: which question an assertion answers. Grey: structure and audit.'],
      ['Nodes', 'The outline is the status: dashed = proposed by an agent, solid = attested (its citations were checked by a different agent), heavier = accepted by the researcher — the only citable state; a struck-through title = rejected. Click any node for its provenance: who wrote it, what attests it, and whether that support is independent.'],
      ['Refused writes', 'The counter in the top bar is an output, not an error log: every write the rules refused, and which rule. Zero is a fact worth showing.'],
    ],
  },
  findings: {
    title: 'What Findings shows',
    body: [
      ['What it is', 'Every claim and conjecture as a hypothesis, beside what the researcher has accepted (the only citable nodes) and what they rejected, with reasons. Rejections sit next to findings on purpose: conclusions without the discards would misrepresent the record.'],
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
      ['The roster', 'Workers search the corpus and propose claims and conjectures through tools whose rules are enforced by the graph; a reviewer, which must be a different model family, checks that their citations resolve and attests or withholds. An agent cannot check its own work.'],
      ['What you see', 'Spend, tool calls, and refusals as the run proceeds. Everything an agent writes lands in the graph as proposed; nothing becomes citable here. The researcher accepts or rejects in Findings.'],
    ],
  },
}

function remembered(tab) {
  try {
    const v = window.localStorage.getItem(`cohort.tabIntro.${tab}`)
    return v === null ? true : v === 'open'
  } catch {
    return true
  }
}

export default function TabIntro({ tab }) {
  const intro = INTROS[tab]
  const [open, setOpen] = useState(() => remembered(tab))
  useEffect(() => {
    try { window.localStorage.setItem(`cohort.tabIntro.${tab}`, open ? 'open' : 'closed') } catch { /* storage unavailable */ }
  }, [tab, open])
  if (!intro) return null
  return (
    <aside className={`tab-intro ${open ? 'open' : ''}`} aria-label={intro.title}>
      <button className="tab-intro-toggle" onClick={() => setOpen((v) => !v)} aria-expanded={open}>
        <span className="tab-intro-title">{intro.title}</span>
        <span className="tab-intro-hint">{open ? 'hide' : 'show'}</span>
      </button>
      {open && (
        <dl className="tab-intro-body">
          {intro.body.map(([term, text]) => (
            <div key={term}>
              <dt>{term}</dt>
              <dd>{text}</dd>
            </div>
          ))}
        </dl>
      )}
    </aside>
  )
}
