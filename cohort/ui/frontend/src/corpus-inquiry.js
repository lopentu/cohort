// Keep the selected source reference verbatim; a phrase alone loses which
// search result the researcher chose to investigate.
export function corpusInquiryDraft(source) {
  if (!source) return null
  if (source.kind === 'passage-pair') return passagePairDraft(source)
  return {
    question: `Where else does the wording “${source.phrase}” occur, and how do those passages relate to this passage?`,
    instructions: `Start with source reference ${source.ref}${source.title ? ` (${source.title})` : ''}. Fetch it and inspect the context of “${source.phrase}”. Find related passages, compare their contexts and cite the sources. Consider quotation and recurring expressions. State what the evidence cannot establish.`,
    sourceRef: source.ref,
  }
}

// Include the bounded windows: the worker's search tools cannot fetch a
// local unit at an arbitrary character offset. Supplied text is context,
// not a substitute for resolving citations through the corpus tools.
function passagePairDraft({ selected, match }) {
  const location = p => `${p.uid}, characters ${p.start}–${p.end}`
  const passage = (label, p) => `${label}: ${location(p)}\nSource SHA-256: ${p.source_sha256}\n${p.text}`
  return {
    question: `Do these passages from ${selected.uid} and ${match.uid} describe the same episode or teaching? What agrees and what differs?`,
    instructions: `Explain each passage in plain English, then compare the people, ideas and sequence of events. Quote the Chinese wording supporting each point. Distinguish a corresponding passage from a general similarity of subject. Search distinctive phrases from both passages to resolve citations and inspect available context before recording evidence. Treat interpretations as proposals; say when the comparison is inconclusive. Do not infer borrowing, translation authorship or direction of influence from similarity alone.\n\nRetrieval measurements: cosine ${match.cosine}; longest shared sequence ${match.longest_shared_run} Chinese characters. These do not establish correspondence. Positions below are zero-based local source characters, end excluded; they are not CBETA line numbers. The supplied excerpts are starting context, not independently verified citations.\n\n${passage('Selected passage', selected)}\n\n${passage('Related passage', match)}`,
    sourceRef: `${location(selected)}; ${location(match)}`,
  }
}
